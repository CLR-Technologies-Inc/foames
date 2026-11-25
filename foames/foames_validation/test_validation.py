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

"""Validation protocols and executions on a Frappe site: approval, machine-data evaluation, the
IQ-OQ-PQ sequence, consecutive PPQ runs, requalification suggestions, the report and the API."""

import json
import random

import frappe
from frappe.utils import add_days, add_to_date, get_datetime, getdate, nowdate

from foames.foames_validation import qualification as q
from foames.foames_validation.api import get_qualification_status, subject_status
from foames.foames_validation.commissioning import on_handover
from foames.foames_validation.report.qualification_status.qualification_status import execute as status_report
from foames.foames_validation.tasks import check_requalification
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import as_user, make_machine, make_user

MACHINE = "T-VAL-1"
OPERATOR = "val-operator@example.com"
START = get_datetime("2026-11-01 08:00:00")


def criterion(name, check_type="Pass/Fail", **values):
	return {"criterion": name, "check_type": check_type, **values}


def make_protocol(protocol_type="IQ", criteria=None, submit=True, **overrides):
	values = {
		"doctype": "Validation Protocol",
		"title": f"{protocol_type} of {MACHINE}",
		"protocol_type": protocol_type,
		"machine": MACHINE,
		"criteria": criteria or [criterion("Installed per drawing")],
	}
	values.update(overrides)
	doc = frappe.get_doc(values).insert()
	if submit:
		doc.submit()
	return doc


def make_execution(protocol, **overrides):
	values = {
		"doctype": "Validation Execution",
		"protocol": protocol.name,
		"executed_by": OPERATOR,
		"started_on": START,
		"ended_on": add_to_date(START, hours=2),
	}
	values.update(overrides)
	return frappe.get_doc(values).insert()


def passing(execution):
	"""Record every manual result as met and approve the execution as Administrator."""
	for row in execution.results:
		if row.check_type == "Pass/Fail":
			row.checked = "Yes"
	execution.save()
	execution.submit()
	return execution


def qualify(protocol_type, **protocol_overrides):
	return passing(make_execution(make_protocol(protocol_type, **protocol_overrides)))


def measure(values, name="fill weight", machine=MACHINE, start=START):
	for i, value in enumerate(values):
		frappe.get_doc(
			{
				"doctype": "Machine Event",
				"machine": machine,
				"event_type": "Measurement",
				"source": "Manual",
				"measurement_name": name,
				"value": value,
				"timestamp": add_to_date(start, minutes=i + 1),
			}
		).insert(ignore_permissions=True)


def normal(n, mean, sd, seed=11):
	rng = random.Random(seed)
	return [round(rng.gauss(mean, sd), 4) for _ in range(n)]


class TestValidation(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_machine(MACHINE)
		make_user(OPERATOR, "FoaMES Operator")

	# Protocols

	def test_protocol_rules(self):
		with self.assertRaises(frappe.ValidationError):
			make_protocol("IQ", machine=None, submit=False)
		with self.assertRaises(frappe.ValidationError):
			make_protocol("PPQ", machine=None, submit=False)
		with self.assertRaises(frappe.ValidationError):
			make_protocol(
				"OQ",
				criteria=[criterion("Spindle speed", "Capability", limits="Upper Only", upper_limit=5)],
				submit=False,
			)
		with self.assertRaises(frappe.ValidationError):
			make_protocol(
				"OQ",
				criteria=[criterion("Torque", "Numeric Range", lower_limit=5, upper_limit=4)],
				submit=False,
			)
		ppq = make_protocol("PPQ", machine=None, process_name="Fill and seal", submit=False)
		self.assertEqual(ppq.required_runs, 3)
		self.assertEqual(ppq.validation_stage, "Stage 2: Process Qualification")
		cap = make_protocol(
			"OQ",
			criteria=[
				criterion(
					"Fill weight", "Capability", measurement="fill weight", lower_limit=9, upper_limit=11
				)
			],
		)
		row = cap.criteria[0]
		self.assertEqual(
			(row.source, row.capability_index, row.min_index, row.min_points),
			("Machine Data", "Cpk", 1.33, 25),
		)
		self.assertEqual(cap.approved_by, "Administrator")

	def test_execution_needs_an_approved_protocol_and_copies_its_criteria(self):
		draft = make_protocol(submit=False)
		with self.assertRaises(frappe.ValidationError):
			make_execution(draft)
		protocol = make_protocol(
			criteria=[criterion("Utilities connected"), criterion("Manuals on file", critical=1)]
		)
		execution = make_execution(protocol)
		self.assertEqual([r.criterion for r in execution.results], ["Utilities connected", "Manuals on file"])
		self.assertEqual(execution.run_number, 1)
		self.assertEqual(execution.status, "In Progress")
		self.assertIn("has no result yet", execution.open_items)
		self.assertEqual(make_execution(protocol).run_number, 2)

	def test_manual_results(self):
		protocol = make_protocol(
			criteria=[
				criterion("Supply voltage", "Numeric Range", lower_limit=220, upper_limit=240, units="V"),
				criterion("Earth bonded"),
			]
		)
		execution = make_execution(protocol)
		voltage, earth = execution.results
		voltage.recorded_value = "231.5"
		earth.checked = "Yes"
		execution.save()
		self.assertEqual((voltage.result, voltage.observed_value), ("Pass", 231.5))
		self.assertEqual(earth.result, "Pass")
		self.assertEqual(execution.status, "Ready for Review")
		voltage.recorded_value = "250"
		execution.save()
		self.assertEqual(voltage.result, "Fail")
		voltage.recorded_value = "abc"
		with self.assertRaises(frappe.ValidationError):
			execution.save()

	# Approval

	def test_the_executor_cannot_approve(self):
		execution = make_execution(make_protocol(), executed_by="Administrator")
		execution.results[0].checked = "Yes"
		execution.save()
		with self.assertRaises(frappe.ValidationError):
			execution.submit()

	def test_failures_need_a_deviation_and_disposition(self):
		protocol = make_protocol(criteria=[criterion("Guard interlock"), criterion("Labels fitted")])
		execution = make_execution(protocol)
		interlock, labels = execution.results
		interlock.checked = "Yes"
		labels.checked = "No"
		execution.save()
		with self.assertRaises(frappe.ValidationError):
			execution.submit()
		execution.reload()
		labels = execution.results[1]
		labels.deviation = "DEV-17: labels on back order; temporary labels fitted"
		labels.disposition = q.ACCEPT_DEVIATION
		execution.save()
		execution.submit()
		self.assertEqual(execution.outcome, q.PASSED_WITH_DEVIATIONS)
		self.assertEqual(execution.status, q.PASSED_WITH_DEVIATIONS)
		self.assertEqual(execution.reviewed_by, "Administrator")
		self.assertEqual(getdate(execution.qualified_until), q.qualified_until(getdate(nowdate()), 12))

	def test_a_critical_failure_fails_the_execution(self):
		execution = make_execution(make_protocol(criteria=[criterion("Emergency stop", critical=1)]))
		row = execution.results[0]
		row.checked = "No"
		row.deviation = "E-stop circuit open"
		row.disposition = q.ACCEPT_DEVIATION
		execution.save()
		execution.submit()
		self.assertEqual(execution.outcome, q.FAILED)
		self.assertIsNone(execution.qualified_until)
		self.assertEqual(subject_status("Machine", MACHINE, "IQ")["status"], q.NOT_QUALIFIED)

	def test_evidence_required(self):
		execution = make_execution(
			make_protocol(criteria=[criterion("Calibration certificate", evidence_required=1)])
		)
		execution.results[0].checked = "Yes"
		execution.save()
		self.assertIn("needs evidence", execution.open_items)
		with self.assertRaises(frappe.ValidationError):
			execution.submit()
		execution.reload()
		execution.results[0].evidence_file = "/files/cal-cert.pdf"
		execution.save()
		execution.submit()
		self.assertEqual(execution.outcome, q.PASSED)

	# Machine data

	def test_capability_and_control_from_machine_data(self):
		qualify("IQ")
		# seed 3 is a sample with no run-rule signal; with 8 Nelson rules a random sample can signal by chance
		measure(normal(40, 10.0, 0.08, seed=3))
		protocol = make_protocol(
			"OQ",
			criteria=[
				criterion(
					"Fill weight capable",
					"Capability",
					measurement="fill weight",
					lower_limit=9.5,
					upper_limit=10.5,
				),
				criterion("Fill weight in control", "Statistical Control", measurement="fill weight"),
				criterion(
					"All fills in range",
					"Numeric Range",
					source="Machine Data",
					measurement="fill weight",
					lower_limit=9.5,
					upper_limit=10.5,
				),
			],
		)
		execution = make_execution(protocol)
		frappe.get_attr(
			"foames.foames_validation.doctype.validation_execution.validation_execution.evaluate"
		)(execution.name)
		execution.reload()
		capable, control, in_range = execution.results
		self.assertEqual(capable.result, "Pass", capable.summary)
		self.assertEqual(capable.points, 40)
		self.assertGreater(capable.observed_value, 1.33)
		evidence = json.loads(capable.evidence_data)
		self.assertEqual(evidence["measurement"], "fill weight")
		self.assertEqual(evidence["index"], "Cpk")
		self.assertEqual(control.result, "Pass", control.summary)
		self.assertEqual(in_range.result, "Pass")
		self.assertEqual(execution.status, "Ready for Review")
		execution.submit()
		self.assertEqual(execution.outcome, q.PASSED)

	def test_too_few_readings_stay_pending(self):
		qualify("IQ")
		measure(normal(10, 10.0, 0.08))
		protocol = make_protocol(
			"OQ",
			criteria=[
				criterion(
					"Fill weight capable",
					"Capability",
					measurement="fill weight",
					lower_limit=9.5,
					upper_limit=10.5,
				)
			],
		)
		execution = make_execution(protocol)
		with self.assertRaises(frappe.ValidationError):
			execution.submit()  # evaluated on approval: 10 readings, 25 needed
		execution.reload()
		self.assertEqual(execution.results[0].result, "Pending")

	def test_readings_outside_the_window_are_ignored(self):
		qualify("IQ")
		measure(normal(30, 10.0, 0.08), start=add_days(START, -2))
		protocol = make_protocol(
			"OQ",
			criteria=[
				criterion(
					"Fill weight capable",
					"Capability",
					measurement="fill weight",
					lower_limit=9.5,
					upper_limit=10.5,
				)
			],
		)
		execution = make_execution(protocol)
		execution.evaluate_machine_data()
		self.assertEqual(execution.results[0].points, 0)

	# Sequence and runs

	def test_oq_waits_for_iq(self):
		oq = make_protocol("OQ")
		with self.assertRaises(frappe.ValidationError):
			passing(make_execution(oq))
		qualify("IQ")
		self.assertEqual(passing(make_execution(oq)).outcome, q.PASSED)
		free = make_protocol("PQ", enforce_sequence=0)
		self.assertEqual(passing(make_execution(free)).outcome, q.PASSED)

	def test_an_expired_prerequisite_blocks(self):
		iq = qualify("IQ")
		iq.db_set("qualified_until", add_days(nowdate(), -1))
		with self.assertRaises(frappe.ValidationError):
			passing(make_execution(make_protocol("OQ")))

	def test_ppq_needs_consecutive_runs(self):
		ppq = make_protocol("PPQ", machine=None, process_name="T-Fill and seal", enforce_sequence=0)
		for _run in range(2):
			passing(make_execution(ppq))
			self.assertEqual(subject_status("Process", "T-Fill and seal", "PPQ")["status"], q.RUNS_PENDING)
		passing(make_execution(ppq))
		status = subject_status("Process", "T-Fill and seal", "PPQ")
		self.assertEqual((status["status"], status["runs_passed"]), (q.QUALIFIED, 3))
		cpv = make_protocol("CPV", machine=None, process_name="T-Fill and seal")
		self.assertEqual(passing(make_execution(cpv)).outcome, q.PASSED)

	def test_cancelled_execution(self):
		execution = qualify("IQ")
		execution.cancel()
		self.assertEqual(execution.status, "Cancelled")
		self.assertEqual(subject_status("Machine", MACHINE, "IQ")["status"], q.NOT_QUALIFIED)

	# Requalification, report and API

	def test_requalification_suggestions(self):
		qualify("IQ").db_set("qualified_until", add_days(nowdate(), -3))
		created = check_requalification()
		self.assertEqual(len(created), 1)
		suggestion = frappe.get_doc("Agent Suggestion", created[0])
		self.assertEqual(suggestion.rule_key, f"validation:Machine:{MACHINE}:IQ")
		self.assertEqual((suggestion.category, suggestion.severity), ("Quality", "Critical"))
		self.assertEqual(suggestion.reference_doctype, "Validation Protocol")
		self.assertEqual(check_requalification(), [])  # still open, not raised again

	def test_report_and_api(self):
		qualify("IQ")
		make_protocol("OQ")
		_columns, rows = status_report({"machine": MACHINE})
		by_type = {r["protocol_type"]: r for r in rows}
		self.assertEqual(by_type["IQ"]["status"], q.QUALIFIED)
		self.assertEqual(by_type["OQ"]["status"], q.NOT_QUALIFIED)
		self.assertEqual(
			status_report({"machine": MACHINE, "status": "Not Qualified"})[1][0]["protocol_type"], "OQ"
		)
		api_rows = get_qualification_status(machine=MACHINE, protocol_type="IQ")
		self.assertEqual(len(api_rows), 1)
		self.assertIsInstance(api_rows[0]["qualified_until"], str)
		with as_user(OPERATOR):
			self.assertTrue(get_qualification_status(machine=MACHINE))

	def test_operator_executes_but_cannot_approve(self):
		protocol = make_protocol()
		with as_user(OPERATOR):
			execution = frappe.get_doc(
				{"doctype": "Validation Execution", "protocol": protocol.name, "started_on": START}
			)
			execution.insert()
			execution.results[0].checked = "Yes"
			execution.save()
			self.assertEqual(execution.executed_by, OPERATOR)
			with self.assertRaises(frappe.PermissionError):
				execution.submit()


def make_package(machine=MACHINE):
	return frappe.get_doc(
		{
			"doctype": "Commissioning Package",
			"title": "T-VAL handover",
			"items": [
				{"equipment_tag": "VAL-1", "description": "Filler", "machine": machine},
				{"equipment_tag": "VAL-2", "description": "Conveyor without a machine record"},
			],
			"require_fat": 0,
			"require_mechanical_completion": 0,
			"require_pre_commissioning": 0,
			"require_sat": 0,
			"require_functional_test": 0,
			"require_performance_test": 0,
		}
	).insert()


class TestCommissioningHandover(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_machine(MACHINE)
		make_user(OPERATOR, "FoaMES Operator")

	def test_the_hook_is_registered(self):
		self.assertIn(
			"foames.foames_validation.commissioning.on_handover",
			frappe.get_hooks("foames_commissioning_handed_over"),
		)

	def test_handover_opens_the_iq(self):
		protocol = make_protocol("IQ")
		package = make_package()
		result = on_handover(package)
		self.assertEqual(len(result["executions"]), 1)
		execution = frappe.get_doc("Validation Execution", result["executions"][0])
		self.assertEqual((execution.protocol, execution.docstatus), (protocol.name, 0))
		self.assertEqual(execution.commissioning_package, package.name)
		self.assertEqual(
			frappe.db.get_value(
				"Commissioning Package", package.name, ["qualification_doctype", "qualification_name"]
			),
			("Validation Execution", execution.name),
		)
		self.assertEqual(on_handover(package)["executions"], [execution.name])  # the draft is reused

	def test_a_machine_without_an_iq_protocol_gets_a_suggestion(self):
		package = make_package()
		result = on_handover(package)
		self.assertEqual(result["executions"], [])
		suggestion = frappe.get_doc("Agent Suggestion", result["suggestions"][0])
		self.assertEqual(suggestion.rule_key, f"validation:iq-after-handover:{MACHINE}")
		self.assertEqual(suggestion.reference_name, package.name)
		self.assertFalse(frappe.db.get_value("Commissioning Package", package.name, "qualification_name"))
