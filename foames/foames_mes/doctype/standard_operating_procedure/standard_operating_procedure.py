# Copyright 2026 CLR Technologies Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""One revision of a controlled standard operating procedure.

Each revision is its own record, named <code>-R<revision>. Only a Draft can be edited; the content of
a revision that has gone to review is fixed, and a change is a new revision made with
`new_revision`. Status moves only through the whitelisted methods below (submit for review, sign,
reject, retire, record review) and the daily `check_sops`, which makes approved revisions effective
on their date, supersedes the revision they replace, keeps the review dates current and raises
Agent Suggestions for overdue reviews and missing training. The rules themselves are pure, in
foames.foames_mes.sop.

Signatures record who signed, for which role, with which meaning and when. They are an audit trail,
not a validated 21 CFR Part 11 electronic signature: a site that needs one adds re-authentication and
its own validation on top.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, getdate, now_datetime, nowdate

from foames.foames_mes.sop import (
	DEFAULT_ACKNOWLEDGE_DAYS,
	DEFAULT_REVIEW_MONTHS,
	OPEN_STATUSES,
	allowed_transition,
	applies,
	approvals_complete,
	findings,
	missing_approvals,
	next_review,
	normalise_code,
	review_status,
	revision_name,
	signable_rows,
	training_due,
	training_matrix,
)

DOCTYPE = "Standard Operating Procedure"
ACK_DOCTYPE = "SOP Acknowledgement"
CONTROLLED_FIELDS = (
	"title",
	"category",
	"purpose",
	"scope",
	"responsibilities",
	"procedure",
	"references",
	"attachment",
	"change_summary",
	"effective_on",
	"review_interval_months",
	"requires_acknowledgement",
	"acknowledge_within_days",
)
# Set only by the actions below, never by editing the record.
SYSTEM_FIELDS = (
	"prepared_by",
	"supersedes",
	"superseded_by",
	"last_reviewed_on",
	"retired_on",
	"retire_reason",
)
CONTROLLED_TABLES = {
	"applies_to": ("machine", "line", "external_reference", "note"),
	"approvals": ("role", "meaning"),
	"training_roles": ("role",),
}


class StandardOperatingProcedure(Document):
	def autoname(self):
		self.sop_code = normalise_or_throw(self.sop_code)
		if not self.revision:
			self.revision = next_revision_number(self.sop_code)
		self.name = revision_name(self.sop_code, self.revision)

	def validate(self):
		self.sop_code = normalise_or_throw(self.sop_code)
		before = self.get_doc_before_save()
		previous = before.status if before else None
		if self.is_new():
			self.status = "Draft"
			self.prepared_by = self.prepared_by or frappe.session.user
			self.validate_new_revision()
		elif not self.flags.status_change and self.status != previous:
			frappe.throw(_("Use the form's actions to change an SOP's status"))
		if not allowed_transition(previous, self.status):
			frappe.throw(_("An SOP cannot go from {0} to {1}").format(_(previous), _(self.status)))
		if before and not self.flags.status_change:
			self.check_system_fields(before)
			if previous != "Draft":
				self.check_unchanged(before)
		if self.review_interval_months is None or self.review_interval_months == "":
			self.review_interval_months = DEFAULT_REVIEW_MONTHS
		if int(self.review_interval_months) < 0:
			frappe.throw(_("Review Every (Months) cannot be negative"))
		if self.acknowledge_within_days is None or self.acknowledge_within_days == "":
			self.acknowledge_within_days = DEFAULT_ACKNOWLEDGE_DAYS
		if int(self.acknowledge_within_days) < 0:
			frappe.throw(_("Acknowledge Within (Days) cannot be negative"))
		for row in self.applies_to:
			if not (row.machine or row.line or row.external_reference):
				frappe.throw(
					_("Row {0} of Applies To names no machine, line or process reference").format(row.idx)
				)
		roles = [row.role for row in self.approvals]
		if len(roles) != len(set(roles)):
			frappe.throw(_("Each role can appear only once in the sign-off"))
		self.refresh_review(getdate(nowdate()))

	def validate_new_revision(self):
		open_revision = frappe.db.get_value(
			DOCTYPE,
			{"sop_code": self.sop_code, "status": ("in", OPEN_STATUSES), "name": ("!=", self.name)},
			"name",
		)
		if open_revision:
			frappe.throw(
				_("{0} already has a revision in progress: {1}. Finish or retire it first").format(
					self.sop_code, open_revision
				)
			)
		if int(self.revision) > 1:
			self.supersedes = self.supersedes or current_revision(self.sop_code)
		else:
			self.supersedes = None
		self.superseded_by = self.last_reviewed_on = self.retired_on = self.retire_reason = None
		for row in self.approvals:
			row.signed_by = row.signed_on = row.comment = None

	def check_system_fields(self, before):
		"""Fields the actions set, and the signatures, cannot be changed by editing the record."""
		changed = [
			self.meta.get_label(f) for f in SYSTEM_FIELDS if _norm(self.get(f)) != _norm(before.get(f))
		]
		signed_before = {row.name: _signature(row) for row in before.approvals}
		if any(_signature(row) != signed_before.get(row.name, (None, None, None)) for row in self.approvals):
			changed.append(_("Signatures"))
		if changed:
			frappe.throw(_("{0} are set by the SOP's actions, not by editing it").format(", ".join(changed)))

	def check_unchanged(self, before):
		changed = [f for f in CONTROLLED_FIELDS if _norm(self.get(f)) != _norm(before.get(f))]
		for table, columns in CONTROLLED_TABLES.items():
			if _rows(self.get(table), columns) != _rows(before.get(table), columns):
				changed.append(table)
		if changed:
			frappe.throw(
				_("{0} is {1} and its content is controlled. Start a new revision to change {2}").format(
					self.name, _(before.status), ", ".join(self.meta.get_label(f) for f in changed)
				)
			)

	def refresh_review(self, today):
		if self.status == "Effective":
			due = next_review(self.effective_on, self.review_interval_months, self.last_reviewed_on)
			self.next_review_on = due
			self.review_status = review_status(due, today)
		else:
			self.next_review_on = None
			self.review_status = None

	def set_status(self, status: str):
		self.status = status
		self.flags.status_change = True
		try:
			self.save(ignore_permissions=True)
		finally:
			self.flags.status_change = False

	def required_users(self) -> set[str]:
		if not self.requires_acknowledgement:
			return set()
		return users_with_roles([row.role for row in self.training_roles])


def _norm(value):
	if value is None or value == "":
		return None
	return str(value)


def _signature(row):
	signed_on = get_datetime(row.get("signed_on")) if row.get("signed_on") else None
	return (_norm(row.get("signed_by")), _norm(signed_on), _norm(row.get("comment")))


def _rows(rows, columns):
	return [tuple(_norm(row.get(c)) for c in columns) for row in rows or ()]


def normalise_or_throw(code):
	try:
		return normalise_code(code)
	except ValueError as e:
		frappe.throw(_(str(e)))


def next_revision_number(code: str) -> int:
	revisions = frappe.get_all(DOCTYPE, filters={"sop_code": code}, pluck="revision")
	return max((int(r) for r in revisions if r), default=0) + 1


def current_revision(code: str) -> str | None:
	"""The Effective revision of an SOP code, if any."""
	return frappe.db.get_value(DOCTYPE, {"sop_code": code, "status": "Effective"}, "name")


def users_with_roles(roles) -> set[str]:
	"""Enabled system users holding any of the roles (Administrator and Guest left out)."""
	roles = [r for r in roles if r]
	if not roles:
		return set()
	has_role, user = frappe.qb.DocType("Has Role"), frappe.qb.DocType("User")
	rows = (
		frappe.qb.from_(has_role)
		.join(user)
		.on(user.name == has_role.parent)
		.select(user.name)
		.distinct()
		.where(
			(has_role.parenttype == "User")
			& (has_role.role.isin(roles))
			& (user.enabled == 1)
			& (user.user_type == "System User")
			& (user.name.notin(["Administrator", "Guest"]))
		)
		.run(pluck=True)
	)
	return set(rows)


def acknowledged_revisions(code: str, users=None) -> dict[str, int]:
	"""user -> the highest revision of the SOP code each user acknowledged."""
	filters = {"sop_code": code}
	if users is not None:
		if not users:
			return {}
		filters["user"] = ("in", list(users))
	out = {}
	for row in frappe.get_all(ACK_DOCTYPE, filters=filters, fields=["user", "revision"]):
		out[row.user] = max(out.get(row.user, 0), int(row.revision or 0))
	return out


def _load_for_action(name: str, perm: str = "write"):
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission(perm)
	return doc


def make_effective(doc, today=None):
	"""Make an approved revision Effective and supersede the revision it replaces."""
	today = getdate(today or nowdate())
	previous = current_revision(doc.sop_code)
	if not doc.effective_on:
		doc.effective_on = today
	doc.set_status("Effective")
	if previous and previous != doc.name:
		old = frappe.get_doc(DOCTYPE, previous)
		old.superseded_by = doc.name
		old.set_status("Superseded")
		close_suggestions(previous, _("Superseded by {0}").format(doc.name))
	return doc


def close_suggestions(name: str, resolution: str, prefix: str | None = None):
	"""Mark the open SOP suggestions of a revision Done."""
	for row in frappe.get_all(
		"Agent Suggestion",
		filters={"reference_doctype": DOCTYPE, "reference_name": name, "status": "Open"},
		fields=["name", "rule_key"],
	):
		if prefix and not (row.rule_key or "").startswith(prefix):
			continue
		doc = frappe.get_doc("Agent Suggestion", row.name)
		doc.status = "Done"
		doc.resolution = resolution
		doc.save(ignore_permissions=True)


# The form's actions


@frappe.whitelist(methods=["POST"])
def submit_for_review(name: str) -> dict:
	"""Draft -> In Review. The content is fixed from here; the sign-off rows must be filled in."""
	doc = _load_for_action(name)
	if doc.status != "Draft":
		frappe.throw(_("Only a Draft can be sent for review"))
	if not doc.approvals:
		frappe.throw(_("Add at least one sign-off row before sending the SOP for review"))
	if int(doc.revision) > 1 and not (doc.change_summary or "").strip():
		frappe.throw(_("Say what changed from the previous revision in Change Summary"))
	for row in doc.approvals:
		row.signed_by = row.signed_on = row.comment = None
	doc.set_status("In Review")
	return {"name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def sign(name: str, comment: str | None = None) -> dict:
	"""Sign the next sign-off row the current user may sign. When every row is signed the revision is
	Approved, and Effective at once if its effective date has come (or is empty)."""
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("read")
	if doc.status != "In Review":
		frappe.throw(_("Only an SOP in review can be signed"))
	user = frappe.session.user
	rows = [row.as_dict() for row in doc.approvals]
	indexes = signable_rows(rows, user, frappe.get_roles(user), doc.prepared_by)
	if not indexes:
		frappe.throw(
			_("You cannot sign {0}: it needs {1}, you are its author, or you have signed it already").format(
				doc.name, ", ".join(missing_approvals(rows)) or _("no more signatures")
			),
			frappe.PermissionError,
		)
	row = doc.approvals[indexes[0]]
	row.signed_by, row.signed_on, row.comment = user, now_datetime(), comment
	if approvals_complete([r.as_dict() for r in doc.approvals]):
		doc.set_status("Approved")
		if not doc.effective_on or getdate(doc.effective_on) <= getdate(nowdate()):
			make_effective(doc)
	else:
		doc.flags.status_change = True
		try:
			doc.save(ignore_permissions=True)
		finally:
			doc.flags.status_change = False
	return {
		"name": doc.name,
		"status": doc.status,
		"role": row.role,
		"missing": missing_approvals([r.as_dict() for r in doc.approvals]),
	}


@frappe.whitelist(methods=["POST"])
def reject(name: str, comment: str) -> dict:
	"""Send a revision in review back to Draft with its signatures cleared. A reviewer who holds one of
	the sign-off roles (or anyone who may edit the SOP) can reject it; the reason goes on the record."""
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("read")
	if doc.status != "In Review":
		frappe.throw(_("Only an SOP in review can be rejected"))
	if not (comment or "").strip():
		frappe.throw(_("Say why the SOP is rejected"))
	roles = set(frappe.get_roles())
	if not (roles & {row.role for row in doc.approvals} or frappe.has_permission(DOCTYPE, "write", doc=doc)):
		frappe.throw(_("Only a reviewer can reject {0}").format(doc.name), frappe.PermissionError)
	for row in doc.approvals:
		row.signed_by = row.signed_on = row.comment = None
	doc.set_status("Draft")
	doc.add_comment("Comment", _("Rejected in review: {0}").format(comment))
	return {"name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def new_revision(name: str) -> str:
	"""A Draft copy of an Effective or Approved revision, numbered next, to change it. Returns its name."""
	source = _load_for_action(name)
	frappe.has_permission(DOCTYPE, "create", throw=True)
	if source.status not in ("Effective", "Approved"):
		frappe.throw(_("Start a new revision from the Effective or Approved revision"))
	copy = frappe.copy_doc(source)
	copy.update(
		{
			"revision": None,
			"status": "Draft",
			"prepared_by": frappe.session.user,
			"supersedes": source.name if source.status == "Effective" else source.supersedes,
			"superseded_by": None,
			"effective_on": None,
			"last_reviewed_on": None,
			"next_review_on": None,
			"review_status": None,
			"retired_on": None,
			"retire_reason": None,
			"change_summary": None,
		}
	)
	copy.insert()
	return copy.name


@frappe.whitelist(methods=["POST"])
def retire(name: str, reason: str) -> dict:
	"""Withdraw a revision with no replacement: it becomes Obsolete."""
	doc = _load_for_action(name)
	if not (reason or "").strip():
		frappe.throw(_("Say why the SOP is retired"))
	if not allowed_transition(doc.status, "Obsolete") or doc.status == "Obsolete":
		frappe.throw(_("An SOP that is {0} cannot be retired").format(_(doc.status)))
	doc.retired_on, doc.retire_reason = nowdate(), reason
	doc.set_status("Obsolete")
	close_suggestions(doc.name, _("Retired: {0}").format(reason))
	return {"name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def record_review(name: str, comment: str | None = None) -> dict:
	"""The periodic review found the Effective revision still right: restart its review interval."""
	doc = _load_for_action(name)
	if doc.status != "Effective":
		frappe.throw(_("Only the Effective revision is reviewed"))
	doc.last_reviewed_on = nowdate()
	doc.flags.status_change = True
	try:
		doc.save(ignore_permissions=True)
	finally:
		doc.flags.status_change = False
	doc.add_comment("Comment", _("Periodic review: still current. {0}").format(comment or ""))
	close_suggestions(doc.name, _("Reviewed on {0}").format(doc.last_reviewed_on), prefix="sop-review:")
	return {"name": doc.name, "next_review_on": str(doc.next_review_on) if doc.next_review_on else None}


# Acknowledgement and training


@frappe.whitelist(methods=["POST"])
def acknowledge(name: str) -> dict:
	"""The current user has read and understood the Effective revision."""
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("read")
	return record_acknowledgement(doc, frappe.session.user, "Read and Understood")


@frappe.whitelist(methods=["POST"])
def record_training(name: str, user: str, method: str = "Trained", note: str | None = None) -> dict:
	"""A trainer records that someone was trained on the Effective revision."""
	frappe.only_for(("System Manager", "FoaMES Quality", "FoaMES Supervisor", "FoaMES Engineer"))
	if method not in ("Trained", "Trained and Assessed"):
		frappe.throw(_("Method must be Trained or Trained and Assessed"))
	doc = frappe.get_doc(DOCTYPE, name)
	doc.check_permission("read")
	return record_acknowledgement(doc, user, method, recorded_by=frappe.session.user, note=note)


def record_acknowledgement(doc, user: str, method: str, recorded_by=None, note=None) -> dict:
	if doc.status != "Effective":
		frappe.throw(
			_("Only the Effective revision of an SOP can be acknowledged; {0} is {1}").format(
				doc.name, _(doc.status)
			)
		)
	existing = frappe.db.get_value(ACK_DOCTYPE, {"sop": doc.name, "user": user}, "name")
	if existing:
		ack = frappe.get_doc(ACK_DOCTYPE, existing)
		if method != "Read and Understood" and ack.method != method:
			ack.update({"method": method, "recorded_by": recorded_by, "note": note})
			ack.save(ignore_permissions=True)
	else:
		ack = frappe.get_doc(
			{
				"doctype": ACK_DOCTYPE,
				"sop": doc.name,
				"user": user,
				"method": method,
				"recorded_by": recorded_by,
				"note": note,
			}
		).insert(ignore_permissions=True)
	return {
		"name": ack.name,
		"sop": doc.name,
		"user": user,
		"method": ack.method,
		"acknowledged_on": str(ack.acknowledged_on),
	}


@frappe.whitelist()
def get_effective_sops(machine: str | None = None) -> list[dict]:
	"""The Effective SOPs that apply at a machine (site-wide ones included), or all of them."""
	frappe.has_permission(DOCTYPE, "read", throw=True)
	line = frappe.db.get_value("Machine", machine, "line") if machine else None
	out = []
	for name in frappe.get_all(DOCTYPE, filters={"status": "Effective"}, pluck="name", order_by="sop_code"):
		doc = frappe.get_doc(DOCTYPE, name)
		if machine and not applies([r.as_dict() for r in doc.applies_to], machine, line):
			continue
		out.append(
			{
				"name": doc.name,
				"sop_code": doc.sop_code,
				"revision": doc.revision,
				"title": doc.title,
				"category": doc.category,
				"effective_on": str(doc.effective_on) if doc.effective_on else None,
				"requires_acknowledgement": bool(doc.requires_acknowledgement),
			}
		)
	return out


@frappe.whitelist()
def operator_sop_gaps(user: str | None = None, machine: str | None = None) -> list[dict]:
	"""The Effective SOPs at a machine that `user` (default: the current user) must acknowledge and has
	not, each with Missing or Outdated. An empty list means the user is current on every SOP there.

	This is for the floor and for agents to show or suggest; FoaMES does not stop anyone working."""
	user = user or frappe.session.user
	if user != frappe.session.user:
		frappe.only_for(("System Manager", "FoaMES Quality", "FoaMES Supervisor", "FoaMES Engineer"))
	roles = set(frappe.get_roles(user))
	gaps = []
	for sop in get_effective_sops(machine):
		if not sop["requires_acknowledgement"]:
			continue
		doc = frappe.get_doc(DOCTYPE, sop["name"])
		if not roles & {row.role for row in doc.training_roles}:
			continue
		status = training_matrix([user], acknowledged_revisions(doc.sop_code, [user]), doc.revision)[user]
		if status != "Current":
			gaps.append({**sop, "status": status})
	return gaps


def check_sops(today=None) -> list[str]:
	"""Scheduled daily: make approved revisions effective on their date, refresh review dates, and raise
	Agent Suggestions for reviews coming due and for people not trained in time. Returns the
	suggestions created or reopened."""
	from foames.foames_mes.doctype.agent_suggestion.agent_suggestion import raise_suggestions

	today = getdate(today or nowdate())
	for name in frappe.get_all(
		DOCTYPE,
		filters={"status": "Approved", "effective_on": ("<=", today)},
		pluck="name",
		order_by="revision",
	):
		make_effective(frappe.get_doc(DOCTYPE, name), today)

	rows = []
	for name in frappe.get_all(DOCTYPE, filters={"status": "Effective"}, pluck="name", order_by="name"):
		doc = frappe.get_doc(DOCTYPE, name)
		doc.refresh_review(today)
		frappe.db.set_value(
			DOCTYPE,
			name,
			{"next_review_on": doc.next_review_on, "review_status": doc.review_status},
			update_modified=False,
		)
		overdue = []
		if doc.requires_acknowledgement and training_due(
			doc.effective_on, doc.acknowledge_within_days, today
		):
			required = doc.required_users()
			matrix = training_matrix(required, acknowledged_revisions(doc.sop_code, required), doc.revision)
			overdue = [user for user, status in matrix.items() if status != "Current"]
			if not overdue:
				close_suggestions(name, _("Everyone required has acknowledged it"), prefix="sop-training:")
		rows.append(
			{
				"name": name,
				"code": doc.sop_code,
				"title": doc.title,
				"revision": doc.revision,
				"review_status": doc.review_status,
				"next_review_on": doc.next_review_on,
				"overdue_users": overdue,
				"acknowledge_days": doc.acknowledge_within_days,
			}
		)
	return raise_suggestions(findings(rows), agent="foames-sop")
