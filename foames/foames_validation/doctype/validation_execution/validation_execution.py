# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""One execution of an approved Validation Protocol.

The protocol's criteria are copied into the results when the execution is created, so later
amendments of the protocol do not change what this run was judged against. People record manual
results and evidence; criteria on machine measurements are evaluated from the Measurement events
between Started On and Ended On, and evaluated again when the execution is approved, so the stored
evidence is what the approval rests on. Submitting is the approval: it needs every result, a
deviation and disposition for every failure, the prerequisite qualification to be current, and an
approver who is not the executor.
"""

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, get_datetime, getdate, now_datetime

from foames.foames_validation import qualification as q
from foames.foames_validation.doctype.validation_protocol.validation_protocol import criterion_limits

COPIED_FIELDS = (
	"criterion",
	"check_type",
	"critical",
	"evidence_required",
	"method",
	"source",
	"machine",
	"measurement",
	"units",
	"limits",
	"lower_limit",
	"upper_limit",
	"capability_index",
	"min_index",
	"rule_set",
	"min_points",
)


class ValidationExecution(Document):
	def before_insert(self):
		self.run_number = (
			frappe.db.count("Validation Execution", {"protocol": self.protocol, "docstatus": ("<", 2)}) + 1
		)
		self.executed_by = self.executed_by or frappe.session.user

	def validate(self):
		protocol = self.get_protocol()
		if protocol.docstatus != 1:
			frappe.throw(
				_("Protocol {0} must be approved (submitted) before it is executed").format(protocol.name)
			)
		self.title = protocol.title
		self.protocol_type = protocol.protocol_type
		self.validation_stage = protocol.validation_stage
		self.machine = protocol.machine
		self.process_name = protocol.process_name
		if not self.results:
			for criterion in protocol.criteria:
				self.append("results", {field: criterion.get(field) for field in COPIED_FIELDS})
		if self.started_on and self.ended_on and get_datetime(self.ended_on) < get_datetime(self.started_on):
			frappe.throw(_("Ended On cannot be before Started On"))
		for row in self.results:
			self.judge_manual(row)
		self.refresh_status()

	def get_protocol(self):
		if not getattr(self, "_protocol", None) or self._protocol.name != self.protocol:
			self._protocol = frappe.get_doc("Validation Protocol", self.protocol)
		return self._protocol

	# Results

	def judge_manual(self, row):
		if cint(row.not_applicable):
			row.result = q.NA
			row.summary = _("Not applicable")
			return
		if row.result == q.NA:
			row.result = q.PENDING
		if row.check_type == "Pass/Fail":
			outcome = q.evaluate(
				{"check_type": "Pass/Fail"}, {"passed": {"Yes": True, "No": False}.get(row.checked)}
			)
			self.store(row, outcome)
		elif row.check_type == "Numeric Range" and row.source != "Machine Data":
			lower, upper = criterion_limits(row)
			text = (row.recorded_value or "").strip()
			try:
				observation = {"value": float(text)} if text else {}
			except ValueError:
				frappe.throw(_("Row {0} ({1}): {2} is not a number").format(row.idx, row.criterion, text))
			criterion = {"check_type": "Numeric Range", "lower_limit": lower, "upper_limit": upper}
			self.store(row, q.evaluate(criterion, observation))

	def store(self, row, outcome, evaluated=False):
		row.result = outcome["result"]
		row.summary = outcome["summary"]
		row.points = outcome["points"]
		row.observed_value = outcome["observed_value"]
		if evaluated:
			row.evaluated_on = now_datetime()
			row.evidence_data = json.dumps(outcome["evidence"], indent=1, default=str, sort_keys=True)

	def machine_rows(self):
		return [r for r in self.results if r.source == "Machine Data" and not cint(r.not_applicable)]

	def evaluate_machine_data(self):
		"""Evaluate every machine-data criterion from the Measurement events in the window."""
		from foames.foames_mes.spc_monitor import measurement_series

		rows = self.machine_rows()
		if not rows:
			return
		if not (self.started_on and self.ended_on):
			frappe.throw(_("Set Started On and Ended On to evaluate criteria on machine data"))
		for row in rows:
			machine = row.machine or self.machine
			readings = measurement_series(machine, row.measurement, self.started_on, self.ended_on)
			lower, upper = criterion_limits(row)
			criterion = {
				"check_type": row.check_type,
				"lower_limit": lower,
				"upper_limit": upper,
				"capability_index": row.capability_index,
				"min_index": row.min_index,
				"min_points": row.min_points,
				"rule_set": row.rule_set,
			}
			try:
				outcome = q.evaluate(criterion, {"values": [v for _t, v in readings]})
			except ValueError as e:
				frappe.throw(_("Row {0} ({1}): {2}").format(row.idx, row.criterion, e))
			outcome["evidence"] = {
				**outcome["evidence"],
				"machine": machine,
				"measurement": row.measurement,
				"from": str(self.started_on),
				"to": str(self.ended_on),
				"first_reading_at": str(readings[0][0]) if readings else None,
				"last_reading_at": str(readings[-1][0]) if readings else None,
			}
			self.store(row, outcome, evaluated=True)

	def compute_outcome(self) -> dict:
		return q.execution_outcome(
			[
				{
					"criterion": f"{row.idx}. {row.criterion}",
					"result": row.result,
					"critical": cint(row.critical),
					"deviation": row.deviation,
					"disposition": row.disposition,
				}
				for row in self.results
			]
		)

	def evidence_problems(self) -> list[str]:
		return [
			_("{0}. {1} needs evidence attached").format(row.idx, row.criterion)
			for row in self.results
			if cint(row.evidence_required)
			and row.result in (q.PASS, q.FAIL)
			and not (row.evidence_file or row.evidence_data)
		]

	def refresh_status(self):
		if self.docstatus == 2:
			self.status = "Cancelled"
			return
		if self.docstatus == 1:
			return
		problems = self.compute_outcome()["problems"] + self.evidence_problems()
		self.open_items = "\n".join(problems) if problems else None
		if not self.started_on:
			self.status = "Draft"
		elif problems:
			self.status = "In Progress"
		else:
			self.status = "Ready for Review"

	# Approval

	def before_submit(self):
		approver = frappe.session.user
		if approver == (self.executed_by or self.owner):
			frappe.throw(_("The person who executed a protocol cannot also approve it; ask a reviewer"))
		if not self.started_on:
			frappe.throw(_("Set Started On before approving the execution"))
		self.evaluate_machine_data()
		result = self.compute_outcome()
		problems = result["problems"] + self.evidence_problems()
		if problems:
			frappe.throw(
				_("The execution cannot be approved yet:") + "<br>" + "<br>".join(problems),
				title=_("Open items"),
			)
		protocol = self.get_protocol()
		if result["outcome"] != q.FAILED and cint(protocol.enforce_sequence):
			problem = prerequisite_problem(protocol)
			if problem:
				frappe.throw(problem, title=_("Prerequisite not current"))
		now = now_datetime()
		self.outcome = result["outcome"]
		self.status = result["outcome"]
		self.open_items = None
		self.reviewed_by = approver
		self.reviewed_on = now
		self.qualified_until = (
			q.qualified_until(getdate(now), protocol.validity_months)
			if result["outcome"] in (q.PASSED, q.PASSED_WITH_DEVIATIONS)
			else None
		)

	def on_cancel(self):
		self.db_set("status", "Cancelled")


def prerequisite_problem(protocol) -> str | None:
	"""Why an execution of `protocol` may not be approved now because its prerequisite is not current."""
	from foames.foames_validation.api import subject_status

	prerequisite = q.protocol_type(protocol.protocol_type)["prerequisite"]
	if not prerequisite:
		return None
	if prerequisite in q.EQUIPMENT_TYPES:
		if not protocol.machine:
			return None  # a PPQ that names no equipment has no equipment qualification to check
		status = subject_status("Machine", protocol.machine, prerequisite)
	else:
		status = subject_status("Process", protocol.process_name, prerequisite)
	return q.prerequisite_problem(protocol.protocol_type, status)


@frappe.whitelist()
def evaluate(name: str) -> dict:
	"""Evaluate an execution's machine-data criteria now and save the results."""
	doc = frappe.get_doc("Validation Execution", name)
	doc.check_permission("write")
	if doc.docstatus != 0:
		frappe.throw(_("Only a draft execution can be evaluated"))
	doc.evaluate_machine_data()
	doc.save()
	return {"status": doc.status, "open_items": doc.open_items}
