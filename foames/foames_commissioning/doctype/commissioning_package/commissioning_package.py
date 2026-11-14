# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""One commissioning job: the equipment in scope, the tests it must pass, and its handover.

The package's progress and status are worked out from its tests, loop checks and punch items each
time one of them changes. Handover needs every blocker cleared (see
`foames.foames_commissioning.commissioning.readiness`) and both acceptors' sign-off.

Two hooks let other apps take part:

- `foames_commissioning_readiness_checks`: dotted paths called with the package; each returns a
  list of blocker dicts (kind, reference, message) that hold the handover back.
- `foames_commissioning_handed_over`: dotted paths called with the package after it is handed over,
  for example to open the qualification (IQ/OQ/PQ) record that follows.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from foames.foames_commissioning.commissioning import (
	PUNCH_CATEGORIES,
	package_status,
	readiness,
)

HANDOVER_ROLES = ("FoaMES Engineer", "FoaMES Supervisor", "System Manager")
REQUIRED_TEST_FIELDS = {
	"require_fat": "FAT",
	"require_mechanical_completion": "Mechanical Completion",
	"require_pre_commissioning": "Pre-Commissioning",
	"require_sat": "SAT",
	"require_functional_test": "Functional Test",
	"require_performance_test": "Performance Test",
}
ACCEPTANCE_SIDES = {
	"operations": ("operations_acceptor", "operations_accepted_on"),
	"maintenance": ("maintenance_acceptor", "maintenance_accepted_on"),
}


class CommissioningPackage(Document):
	def validate(self):
		tags = [row.equipment_tag.strip() for row in self.items if row.equipment_tag]
		duplicates = sorted({t for t in tags if tags.count(t) > 1})
		if duplicates:
			frappe.throw(_("Equipment tags must be unique in a package: {0}").format(", ".join(duplicates)))
		for row in self.items:
			row.equipment_tag = row.equipment_tag.strip()
		before = self.get_doc_before_save()
		if before and before.status == "Handed Over":
			if self.cancelled:
				frappe.throw(_("A package that was handed over cannot be cancelled"))
		# A new acceptor has not accepted yet.
		for acceptor, accepted_on in ACCEPTANCE_SIDES.values():
			if before and before.get(acceptor) != self.get(acceptor):
				self.set(accepted_on, None)
		if self.status != "Handed Over":
			self.status = (
				"Cancelled" if self.cancelled else ("Planning" if self.status == "Cancelled" else self.status)
			)
		self.apply_readiness(self.get_readiness())

	# Readiness

	def required_test_types(self) -> list[str]:
		return [test_type for field, test_type in REQUIRED_TEST_FIELDS.items() if self.get(field)]

	def get_readiness(self) -> dict:
		name = self.name if not self.is_new() else None
		tests = (
			frappe.get_all(
				"Commissioning Test",
				filters={"package": name},
				fields=["name", "test_type", "status", "equipment_tag"],
				order_by="creation",
			)
			if name
			else []
		)
		loops = (
			frappe.get_all(
				"Loop Check", filters={"package": name}, fields=["name", "tag", "status"], order_by="creation"
			)
			if name
			else []
		)
		punch = (
			frappe.get_all(
				"Punch Item",
				filters={"package": name},
				fields=["name", "category", "status", "deferred", "assigned_to", "due_on", "title"],
				order_by="creation",
			)
			if name
			else []
		)
		for p in punch:
			p["description"] = p.pop("title")
		extra = []
		if self.require_loop_checks and not [lc for lc in loops if lc.status != "Cancelled"]:
			extra.append(
				{
					"kind": "Required Test",
					"reference": "Loop Check",
					"message": _("No loop check is recorded"),
				}
			)
		for path in frappe.get_hooks("foames_commissioning_readiness_checks") or []:
			extra.extend(frappe.get_attr(path)(self) or [])
		return readiness(
			{
				"items": [{"tag": row.equipment_tag} for row in self.items],
				"required_test_types": self.required_test_types(),
				"tests": tests,
				"loop_checks": loops,
				"punch_items": punch,
				"operations_acceptor": self.operations_acceptor,
				"maintenance_acceptor": self.maintenance_acceptor,
				"extra_blockers": extra,
			}
		)

	def apply_readiness(self, result: dict):
		progress = result["progress"]
		self.percent_complete = progress["percent_complete"]
		self.tests_passed = _("{0} of {1}").format(progress["tests_passed"], progress["tests"])
		self.loop_checks_passed = _("{0} of {1}").format(
			progress["loop_checks_passed"], progress["loop_checks"]
		)
		for category in PUNCH_CATEGORIES:
			self.set(f"open_punch_{category.lower()}", progress["punch_open_by_category"][category])
		self.blocker_count = len(result["blockers"])
		self.blockers = "\n".join(b["message"] for b in result["blockers"][:50])
		started = bool(progress["tests"] or progress["loop_checks"] or progress["punch_open"])
		self.status = package_status(self.status, started, result["ready"])

	def refresh_progress(self):
		"""Recompute progress and status after a test, loop check or punch item changed."""
		self.apply_readiness(self.get_readiness())
		for field in (
			"percent_complete",
			"tests_passed",
			"loop_checks_passed",
			"open_punch_a",
			"open_punch_b",
			"open_punch_c",
			"blocker_count",
			"blockers",
			"status",
		):
			self.db_set(field, self.get(field), update_modified=False)

	def acceptance_blockers(self, result: dict) -> list[dict]:
		"""Blockers other than the acceptors' own sign-off."""
		return [b for b in result["blockers"] if b["kind"] != "Acceptance"]

	# Actions

	@frappe.whitelist()
	def accept(self, side: str):
		"""The named acceptor for operations or maintenance accepts the equipment. Only possible once
		nothing but acceptance blocks the handover."""
		if side not in ACCEPTANCE_SIDES:
			frappe.throw(_("Accept for operations or maintenance"))
		acceptor_field, accepted_field = ACCEPTANCE_SIDES[side]
		acceptor = self.get(acceptor_field)
		if not acceptor:
			frappe.throw(_("Name who accepts for {0} first").format(_(side)))
		if frappe.session.user != acceptor and "System Manager" not in frappe.get_roles():
			frappe.throw(_("Only {0} can accept for {1}").format(acceptor, _(side)), frappe.PermissionError)
		self.check_open()
		blockers = self.acceptance_blockers(self.get_readiness())
		if blockers:
			frappe.throw(
				_("The package cannot be accepted yet:<br>{0}").format(
					"<br>".join(b["message"] for b in blockers)
				)
			)
		self.set(accepted_field, now_datetime())
		self.save()
		return self.get(accepted_field)

	@frappe.whitelist()
	def hand_over(self):
		"""Hand the equipment over to operations and maintenance. Needs every blocker cleared and both
		acceptances. Deferred category B punch items stay open and go with the equipment."""
		frappe.only_for(HANDOVER_ROLES)
		self.check_open()
		result = self.get_readiness()
		missing = [_("Operations has not accepted")] if not self.operations_accepted_on else []
		if not self.maintenance_accepted_on:
			missing.append(_("Maintenance has not accepted"))
		messages = [b["message"] for b in result["blockers"]] + missing
		if messages:
			frappe.throw(_("The package cannot be handed over yet:<br>{0}").format("<br>".join(messages)))
		self.status = "Handed Over"
		self.handed_over_on = now_datetime()
		self.handed_over_by = frappe.session.user
		self.save()
		if self.enable_machines_on_handover:
			for row in self.items:
				if row.machine and frappe.db.get_value("Machine", row.machine, "disabled"):
					frappe.db.set_value("Machine", row.machine, "disabled", 0)
		for path in frappe.get_hooks("foames_commissioning_handed_over") or []:
			frappe.get_attr(path)(self)
		return self.status

	def check_open(self):
		if self.status in ("Handed Over", "Cancelled"):
			frappe.throw(_("Package {0} is {1}").format(self.name, _(self.status).lower()))


def refresh_package(name: str | None):
	if name and frappe.db.exists("Commissioning Package", name):
		frappe.get_doc("Commissioning Package", name).refresh_progress()


def check_package_open(name: str, what: str):
	"""Refuse new tests and loop checks on a package that was handed over or cancelled."""
	status = frappe.db.get_value("Commissioning Package", name, "status")
	if status in ("Handed Over", "Cancelled"):
		frappe.throw(
			_("Package {0} is {1}; {2} cannot be added or changed").format(name, _(status).lower(), what)
		)


def package_tags(name: str) -> dict[str, str | None]:
	"""equipment tag -> machine for the package's scope."""
	return {row.equipment_tag: row.machine for row in frappe.get_doc("Commissioning Package", name).items}


def check_tag_in_scope(package: str, tag: str | None) -> str | None:
	"""The machine of an equipment tag, after checking the tag is in the package's scope."""
	if not tag:
		return None
	tags = package_tags(package)
	if tag not in tags:
		frappe.throw(_("Equipment {0} is not in the scope of package {1}").format(tag, package))
	return tags[tag]


@frappe.whitelist()
def get_readiness(package: str) -> dict:
	doc = frappe.get_doc("Commissioning Package", package)
	doc.check_permission("read")
	return doc.get_readiness()


@frappe.whitelist()
def get_handover_dossier(package: str) -> dict:
	"""Everything about a package in one structure: scope, tests with their steps, loop checks with
	their points, punch items and the handover. For the handover certificate, for agents and for
	the qualification that follows."""
	doc = frappe.get_doc("Commissioning Package", package)
	doc.check_permission("read")
	tests = [
		frappe.get_doc("Commissioning Test", name).as_dict(no_default_fields=True)
		for name in frappe.get_all(
			"Commissioning Test", filters={"package": package}, pluck="name", order_by="creation"
		)
	]
	loops = [
		frappe.get_doc("Loop Check", name).as_dict(no_default_fields=True)
		for name in frappe.get_all(
			"Loop Check", filters={"package": package}, pluck="name", order_by="creation"
		)
	]
	punch = frappe.get_all(
		"Punch Item",
		filters={"package": package},
		fields=[
			"name",
			"title",
			"category",
			"status",
			"equipment_tag",
			"assigned_to",
			"due_on",
			"deferred",
			"action_taken",
			"verified_by",
			"closed_on",
		],
		order_by="creation",
	)
	return {
		"package": doc.as_dict(no_default_fields=True),
		"readiness": doc.get_readiness(),
		"tests": tests,
		"loop_checks": loops,
		"punch_items": punch,
	}


def check_commissioning(now=None) -> list[str]:
	"""Scheduled daily: raise suggestions for overdue punch items and for packages past their planned
	handover date. Returns the suggestions created or reopened."""
	from foames.foames_commissioning.commissioning import findings
	from foames.foames_mes.doctype.agent_suggestion.agent_suggestion import raise_suggestions

	now = now or now_datetime()
	punch = frappe.get_all(
		"Punch Item",
		filters={"status": ("in", ("Open", "Ready for Verification")), "due_on": ("is", "set")},
		fields=["name", "package", "category", "status", "due_on", "assigned_to", "title", "deferred"],
		order_by="name",
	)
	for p in punch:
		p["description"] = p.pop("title")
	packages = frappe.get_all(
		"Commissioning Package",
		filters={"status": ("not in", ("Handed Over", "Cancelled")), "planned_handover": ("is", "set")},
		fields=["name", "title", "status", "planned_handover", "blocker_count"],
		order_by="name",
	)
	for pkg in packages:
		pkg["blockers"] = pkg.pop("blocker_count") or 0
	return raise_suggestions(findings(punch, packages, now), agent="foames-commissioning")
