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

"""Recognition: a thank-you to a person or a team on the floor.

People give kudos, helping-hand, improvement, safety and quality recognitions to each other.
FoaMES gives two kinds itself: milestones for a person's own contributions (daily) and team
highlights per line when a week went well (weekly). Both are idempotent through the recognition
key. A recognition says something good; FoaMES never ranks people or turns a bad result into a
record about a person. The rules are pure logic in foames.foames_mes.recognition.

Privacy: a Private recognition is seen only by the person recognized, the giver and supervisors,
and never reaches the floor. People listed in Recognition Settings' opt-out table are never shown
on the floor, and can be left out of automatic milestones; anyone can add or remove themselves
with set_my_recognition_preferences.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder.functions import Count
from frappe.utils import add_days, cint, flt, get_datetime, getdate, now_datetime

from foames.foames_mes import recognition as logic

# Roles that see every recognition, private ones included, and can withdraw any of them.
STEWARD_ROLES = ("System Manager", "FoaMES Engineer", "FoaMES Supervisor")
SYSTEM_USERS = ("Administrator", "Guest")
# Fields that can change after a recognition is given; everything else is fixed once said.
MUTABLE_FIELDS = ("status", "private")

SETTINGS_DEFAULTS = {
	"floor_days": 7,
	"show_names_on_floor": 1,
	"notify_recipient": 1,
	"milestones_enabled": 1,
	"milestone_thresholds": ",".join(str(t) for t in logic.DEFAULT_THRESHOLDS),
	"team_highlights_enabled": 1,
	"oee_gain_points": 5,
	"min_planned_hours": 8,
}


def recognition_settings() -> frappe._dict:
	"""The settings with the defaults for any value never saved, plus the opt-out sets: `hidden`
	(never shown on the floor) and `no_automatic` (no milestones)."""
	stored = frappe.db.get_singles_dict("Recognition Settings", cast=False) or {}
	out = frappe._dict()
	for key, default in SETTINGS_DEFAULTS.items():
		value = stored.get(key)
		out[key] = default if value in (None, "") else value
	for key in ("floor_days", "show_names_on_floor", "notify_recipient", "milestones_enabled"):
		out[key] = cint(out[key])
	out.team_highlights_enabled = cint(out.team_highlights_enabled)
	out.floor_days = max(out.floor_days, 0)
	out.oee_gain_points = flt(out.oee_gain_points)
	out.min_planned_hours = flt(out.min_planned_hours)
	out.thresholds = logic.parse_thresholds(out.milestone_thresholds)
	opt_out = frappe.qb.DocType("Recognition Opt Out")
	rows = (
		frappe.qb.from_(opt_out)
		.select(opt_out.user, opt_out.hide_from_floor, opt_out.no_automatic)
		.where((opt_out.parent == "Recognition Settings") & (opt_out.parenttype == "Recognition Settings"))
		.run(as_dict=True)
	)
	out.hidden = {r.user for r in rows if r.hide_from_floor}
	out.no_automatic = {r.user for r in rows if r.no_automatic}
	return out


def is_steward(user: str | None = None) -> bool:
	return bool(set(frappe.get_roles(user)) & set(STEWARD_ROLES))


class Recognition(Document):
	def validate(self):
		system = bool(self.flags.given_by_foames)
		if self.is_new():
			self.recognized_at = self.recognized_at or now_datetime()
			self.given_by = None if system else frappe.session.user
			self.status = "Active"
		else:
			self.check_change()
		if self.recipient_type == "Team":
			self.recipient = None
		problems = logic.check_recognition(
			self.kind,
			self.recipient_type,
			self.recipient,
			self.team,
			self.message,
			self.given_by,
			system=system,
		)
		if problems:
			frappe.throw("<br>".join(_(p) for p in problems))

	def check_change(self):
		before = self.get_doc_before_save()
		if not before:
			return
		changed = [
			f.fieldname
			for f in self.meta.fields
			if f.fieldname not in MUTABLE_FIELDS
			and f.fieldtype not in ("Section Break", "Column Break")
			and comparable(self.get(f.fieldname)) != comparable(before.get(f.fieldname))
		]
		if changed:
			frappe.throw(
				_("A recognition cannot be edited once given; withdraw it and give a new one instead")
			)
		user = frappe.session.user
		if self.status != before.status and not (user == self.given_by or is_steward(user)):
			frappe.throw(_("Only the giver or a supervisor can withdraw a recognition"))
		if cint(self.private) != cint(before.private) and not (
			user in (self.given_by, self.recipient) or is_steward(user)
		):
			frappe.throw(_("Only the giver, the person recognized or a supervisor can change who sees it"))

	def after_insert(self):
		if self.recipient_type == "Person" and self.recipient and recognition_settings().notify_recipient:
			notify(self)


def comparable(value):
	return str(value) if value not in (None, "", 0) else None


def notify(doc):
	"""An alert in the recipient's notifications. A failure here never loses the recognition."""
	try:
		giver = frappe.utils.get_fullname(doc.given_by) if doc.given_by else "FoaMES"
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": doc.recipient,
				"from_user": doc.given_by,
				"type": "Alert",
				"document_type": "Recognition",
				"document_name": doc.name,
				"subject": _("{0} recognized you: {1}").format(giver, doc.message),
			}
		).insert(ignore_permissions=True)
	except Exception:
		frappe.log_error(title="Recognition notification failed", reference_doctype="Recognition")


def has_permission(doc, ptype=None, user=None, debug=False):
	"""Private recognitions are for the recipient, the giver and supervisors. Only they (and the
	giver for withdrawal) may change one."""
	user = user or frappe.session.user
	if is_steward(user):
		return True
	involved = user in (doc.recipient, doc.given_by, doc.owner)
	if ptype in (None, "read", "print", "email", "export", "report") and not cint(doc.private):
		return True
	if ptype == "create":
		return True
	return involved


def get_permission_query_conditions(user=None, doctype=None):
	user = user or frappe.session.user
	if is_steward(user):
		return ""
	quoted = frappe.db.escape(user)
	return (
		"(`tabRecognition`.`private` = 0"
		f" or `tabRecognition`.`recipient` = {quoted}"
		f" or `tabRecognition`.`given_by` = {quoted}"
		f" or `tabRecognition`.`owner` = {quoted})"
	)


# People ---------------------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def give_recognition(
	message: str,
	kind: str = "Kudos",
	recipient: str | None = None,
	team: str | None = None,
	machine: str | None = None,
	private: int = 0,
	reference_doctype: str | None = None,
	reference_name: str | None = None,
) -> dict:
	"""Recognize a person (recipient) or, without one, a team. Returns the new recognition's name."""
	frappe.has_permission("Recognition", "create", throw=True)
	doc = frappe.get_doc(
		{
			"doctype": "Recognition",
			"kind": kind,
			"recipient_type": "Person" if recipient else "Team",
			"recipient": recipient,
			"team": team,
			"machine": machine,
			"message": message,
			"private": cint(private),
			"reference_doctype": reference_doctype,
			"reference_name": reference_name,
		}
	).insert()
	return {"name": doc.name, "kind": doc.kind}


@frappe.whitelist(methods=["POST"])
def withdraw_recognition(name: str) -> dict:
	doc = frappe.get_doc("Recognition", name)
	doc.check_permission("write")
	if doc.status != "Withdrawn":
		doc.status = "Withdrawn"
		doc.save()
	return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def get_my_recognition_preferences() -> dict:
	settings = recognition_settings()
	user = frappe.session.user
	return {"show_on_floor": user not in settings.hidden, "milestones": user not in settings.no_automatic}


@frappe.whitelist(methods=["POST"])
def set_my_recognition_preferences(show_on_floor: int = 1, milestones: int = 1) -> dict:
	"""Anyone can keep their own name off the floor, and turn their own milestones off, without
	needing access to Recognition Settings."""
	user = frappe.session.user
	if user == "Guest":
		raise frappe.PermissionError
	settings = frappe.get_single("Recognition Settings")
	settings.set("opt_out", [r for r in settings.opt_out if r.user != user])
	if not cint(show_on_floor) or not cint(milestones):
		settings.append(
			"opt_out",
			{
				"user": user,
				"hide_from_floor": 0 if cint(show_on_floor) else 1,
				"no_automatic": 0 if cint(milestones) else 1,
			},
		)
	settings.flags.ignore_permissions = True
	settings.save()
	return get_my_recognition_preferences()


def floor_recognitions(now=None) -> list[dict]:
	"""Recent recognitions the floor may show, newest first (see recognition.floor_items)."""
	settings = recognition_settings()
	if not settings.floor_days:
		return []
	now = now or now_datetime()
	rows = frappe.get_all(
		"Recognition",
		filters={
			"status": "Active",
			"private": 0,
			"recognized_at": (">=", add_days(now, -settings.floor_days)),
		},
		fields=[
			"name",
			"kind",
			"recipient_type",
			"recipient",
			"team",
			"machine",
			"message",
			"recognized_at",
			"given_by",
			"private",
			"status",
		],
		order_by="recognized_at desc",
		limit=50,
	)
	people = {r.recipient for r in rows if r.recipient} | {r.given_by for r in rows if r.given_by}
	names = (
		{
			u.name: u.full_name
			for u in frappe.get_all("User", {"name": ("in", list(people))}, ["name", "full_name"])
		}
		if people
		else {}
	)
	return logic.floor_items(rows, settings.hidden, bool(settings.show_names_on_floor), names)


@frappe.whitelist()
def list_recognitions(days: int = 7) -> list[dict]:
	"""Recognitions of the last `days` days the user may read, newest first."""
	frappe.has_permission("Recognition", "read", throw=True)
	return frappe.get_list(
		"Recognition",
		filters={"status": "Active", "recognized_at": (">=", add_days(now_datetime(), -cint(days)))},
		fields=[
			"name",
			"kind",
			"recipient_type",
			"recipient",
			"team",
			"machine",
			"message",
			"recognized_at",
			"given_by",
		],
		order_by="recognized_at desc",
		limit=200,
	)


# Given by FoaMES ------------------------------------------------------------------------------


def give_from_foames(key: str, kind: str, message: str, **values) -> str | None:
	"""Insert a milestone or team highlight once per key. Returns its name, or None when the key
	was already given."""
	if frappe.db.exists("Recognition", {"recognition_key": key}):
		return None
	evidence = values.pop("evidence", None)
	doc = frappe.get_doc(
		{
			"doctype": "Recognition",
			"kind": kind,
			"message": message,
			"recognition_key": key,
			"evidence": frappe.as_json(evidence) if evidence is not None else None,
			**values,
		}
	)
	doc.flags.given_by_foames = True
	doc.insert(ignore_permissions=True)
	return doc.name


def milestone_counts() -> dict[str, dict[str, int]]:
	"""user -> metric -> running total, over real (enabled, non-system) users."""
	counts: dict[str, dict[str, int]] = {}

	def add(rows, metric):
		for user, total in rows:
			if user and user not in SYSTEM_USERS:
				counts.setdefault(user, {})[metric] = counts.get(user, {}).get(metric, 0) + total

	call = frappe.qb.DocType("Andon Call")
	add(
		frappe.qb.from_(call)
		.select(call.acknowledged_by, Count(call.name))
		.where(call.acknowledged_by.isnotnull() & (call.status != "Cancelled"))
		.groupby(call.acknowledged_by)
		.run(),
		"andon_answered",
	)
	# A call resolved by someone other than whoever acknowledged it counts for both of them, once each.
	add(
		frappe.qb.from_(call)
		.select(call.resolved_by, Count(call.name))
		.where(
			(call.status == "Resolved")
			& call.resolved_by.isnotnull()
			& (call.acknowledged_by.isnull() | (call.acknowledged_by != call.resolved_by))
		)
		.groupby(call.resolved_by)
		.run(),
		"andon_answered",
	)
	suggestion = frappe.qb.DocType("Agent Suggestion")
	# Andon escalations are closed by answering the call, which andon_answered already counts.
	add(
		frappe.qb.from_(suggestion)
		.select(suggestion.resolved_by, Count(suggestion.name))
		.where(
			(suggestion.status == "Done")
			& suggestion.resolved_by.isnotnull()
			& (suggestion.category != "Andon")
		)
		.groupby(suggestion.resolved_by)
		.run(),
		"suggestions_done",
	)
	add(
		frappe.qb.from_(suggestion)
		.select(suggestion.credited_to, Count(suggestion.name))
		.where((suggestion.status == "Done") & suggestion.credited_to.isnotnull())
		.groupby(suggestion.credited_to)
		.run(),
		"ideas_credited",
	)
	if counts:
		enabled = set(frappe.get_all("User", {"name": ("in", list(counts)), "enabled": 1}, pluck="name"))
		counts = {u: c for u, c in counts.items() if u in enabled}
	return counts


def recognize_milestones() -> list[str]:
	"""Scheduled daily: recognize the milestones people have reached since the last run."""
	settings = recognition_settings()
	if not settings.milestones_enabled:
		return []
	given = set(
		frappe.get_all("Recognition", {"recognition_key": ("like", "milestone:%")}, pluck="recognition_key")
	)
	created = []
	for m in logic.due_milestones(milestone_counts(), given, settings.thresholds, settings.no_automatic):
		name = give_from_foames(
			m["key"],
			"Milestone",
			m["message"],
			recipient_type="Person",
			recipient=m["recipient"],
			evidence={"metric": m["metric"], "threshold": m["threshold"], "total": m["total"]},
		)
		if name:
			created.append(name)
	return created


def credit_idea(suggestion) -> str | None:
	"""When a suggestion with an Idea From is marked Done, recognize that person for it, once."""
	person = suggestion.credited_to
	if not person or person in SYSTEM_USERS or person in recognition_settings().no_automatic:
		return None
	key = f"idea:{suggestion.name}"
	if frappe.db.exists("Recognition", {"recognition_key": key}):
		return None
	doc = frappe.get_doc(
		{
			"doctype": "Recognition",
			"kind": "Improvement",
			"recipient_type": "Person",
			"recipient": person,
			"message": _("Your idea was put into practice: {0}").format(suggestion.title),
			"reference_doctype": "Agent Suggestion",
			"reference_name": suggestion.name,
			"recognition_key": key,
		}
	)
	# Given by FoaMES on behalf of whoever closed the suggestion; nobody thanks themselves.
	doc.flags.given_by_foames = True
	doc.insert(ignore_permissions=True)
	return doc.name


def team_of(machine: dict) -> str:
	return machine.get("line") or machine.get("title") or machine["name"]


def recognize_team_highlights(today=None, history_weeks: int = 8) -> list[str]:
	"""Scheduled weekly: highlights per line for the last complete week (Monday to Monday)."""
	settings = recognition_settings()
	if not settings.team_highlights_enabled:
		return []
	start, end = logic.last_complete_week(getdate(today) if today else getdate())
	earliest = add_days(start, -7 * history_weeks)
	machines = frappe.get_all("Machine", {"disabled": 0}, ["name", "title", "line"])
	teams: dict[str, list[str]] = {}
	for m in machines:
		teams.setdefault(team_of(m), []).append(m.name)
	created = []
	for team, members in sorted(teams.items()):
		periods = frappe.get_all(
			"OEE Period",
			filters={
				"machine": ("in", members),
				"from_time": (">=", get_datetime(earliest)),
			},
			fields=["from_time", "planned_minutes", "oee", "good_count", "scrap_count"],
		)
		by_week: dict = {}
		for p in periods:
			if get_datetime(p.from_time) < get_datetime(end):
				by_week.setdefault(logic.week_start(get_datetime(p.from_time)), []).append(p)
		this_week = logic.summarize_periods(by_week.get(start, []))
		history = [
			logic.summarize_periods(by_week.get(add_days(start, -7 * i), []))
			for i in range(1, history_weeks + 1)
		]
		history = [h for h in history if h["planned_minutes"]]
		for h in logic.team_highlights(
			team,
			start,
			this_week,
			history,
			andon_on_target(members, start, end),
			oee_gain_points=settings.oee_gain_points,
			min_planned_minutes=settings.min_planned_hours * 60,
		):
			name = give_from_foames(
				h["key"],
				"Team Highlight",
				_("{0}, week of {1}: {2}").format(h["title"], h["week"], h["message"]),
				recipient_type="Team",
				team=team,
				evidence=h["evidence"],
			)
			if name:
				created.append(name)
	return created


def andon_on_target(machines: list[str], start, end) -> dict:
	"""{"calls", "on_target"} for the answered calls raised on these machines in [start, end) whose
	call type has an acknowledge target. Cancelled calls are left out."""
	call, kind = frappe.qb.DocType("Andon Call"), frappe.qb.DocType("Andon Call Type")
	rows = (
		frappe.qb.from_(call)
		.join(kind)
		.on(kind.name == call.call_type)
		.select(call.status, call.acknowledged_at, call.response_minutes, kind.acknowledge_within_minutes)
		.where(
			call.machine.isin(machines)
			& (call.raised_at >= get_datetime(start))
			& (call.raised_at < get_datetime(end))
			& (call.status != "Cancelled")
			& (kind.acknowledge_within_minutes > 0)
		)
		.run(as_dict=True)
	)
	# An empty Float is stored as 0, so a call counts as answered only once it was acknowledged or
	# resolved; one still unanswered at the end of the week is not on target.
	on_target = sum(
		1
		for r in rows
		if (r.acknowledged_at or r.status == "Resolved")
		and flt(r.response_minutes) <= flt(r.acknowledge_within_minutes)
	)
	return {"calls": len(rows), "on_target": on_target}
