# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Andon Call on a site: the status flow and its timestamps, escalation into Agent Suggestions,
the floor snapshot and the Andon Response report."""

import frappe
from frappe.utils import add_to_date, now_datetime

from foames.foames_mes.doctype.andon_call.andon_call import (
	acknowledge_andon,
	escalate_andon_calls,
	list_open_andon_calls,
	raise_andon,
	resolve_andon,
)
from foames.foames_mes.doctype.andon_call_type.andon_call_type import create_default_call_types
from foames.foames_mes.floor import floor_snapshot
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import as_user, make_machine, make_user


def backdate(name, minutes):
	frappe.db.set_value("Andon Call", name, "raised_at", add_to_date(now_datetime(), minutes=-minutes))


class TestAndonCall(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		create_default_call_types()
		make_machine("T-ANDON", line="T-ANDON-LINE")

	def test_default_call_types_exist(self):
		for code in ("Maintenance", "Material", "Quality", "Supervisor", "Safety"):
			self.assertTrue(frappe.db.exists("Andon Call Type", code), code)
		self.assertEqual(frappe.db.get_value("Andon Call Type", "Safety", "escalation_severity"), "Critical")

	def test_flow_stamps_times_and_users(self):
		name = raise_andon("T-ANDON", "Maintenance", "Spindle noise")["name"]
		doc = frappe.get_doc("Andon Call", name)
		self.assertEqual((doc.status, doc.raised_by), ("Open", "Administrator"))
		backdate(name, 4)
		out = acknowledge_andon(name)
		self.assertEqual(out["status"], "Acknowledged")
		self.assertAlmostEqual(out["response_minutes"], 4, delta=0.5)
		out = resolve_andon(name, "Replaced bearing")
		doc.reload()
		self.assertEqual((doc.status, doc.resolution), ("Resolved", "Replaced bearing"))
		self.assertTrue(doc.resolved_at and doc.resolved_by)
		self.assertAlmostEqual(doc.resolution_minutes, 4, delta=0.5)

	def test_resolved_without_acknowledge_counts_response_to_resolution(self):
		name = raise_andon("T-ANDON", "Material")["name"]
		backdate(name, 3)
		resolve_andon(name)
		doc = frappe.get_doc("Andon Call", name)
		self.assertAlmostEqual(doc.response_minutes, 3, delta=0.5)

	def test_cancel_and_final_states(self):
		name = raise_andon("T-ANDON", "Quality")["name"]
		self.assertEqual(resolve_andon(name, cancel=1)["status"], "Cancelled")
		doc = frappe.get_doc("Andon Call", name)
		doc.status = "Open"
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_disabled_call_type_is_refused(self):
		frappe.db.set_value("Andon Call Type", "Supervisor", "disabled", 1)
		with self.assertRaises(frappe.ValidationError):
			raise_andon("T-ANDON", "Supervisor")

	def test_escalation_once_per_target_and_closed_by_the_call(self):
		name = raise_andon("T-ANDON", "Maintenance")["name"]
		backdate(name, 70)  # past both the 5 and the 60 minute targets
		created = escalate_andon_calls()
		self.assertEqual(len(created), 2)
		keys = {
			s.rule_key: s.status
			for s in frappe.get_all(
				"Agent Suggestion",
				filters={"reference_doctype": "Andon Call", "reference_name": name},
				fields=["rule_key", "status"],
			)
		}
		self.assertEqual(keys, {f"andon:{name}:acknowledge": "Open", f"andon:{name}:resolve": "Open"})
		self.assertEqual(escalate_andon_calls(), [])
		# Dismissing the suggestion does not bring it back while the call stays open.
		frappe.db.set_value(
			"Agent Suggestion", {"rule_key": f"andon:{name}:acknowledge"}, "status", "Dismissed"
		)
		self.assertEqual(escalate_andon_calls(), [])
		acknowledge_andon(name)
		resolve_andon(name, "Done")
		self.assertEqual(
			frappe.db.get_value("Agent Suggestion", {"rule_key": f"andon:{name}:resolve"}, "status"), "Done"
		)

	def test_snapshot_and_list(self):
		name = raise_andon("T-ANDON", "Safety", "Guard open")["name"]
		snapshot = floor_snapshot(days=1)
		machine = next(m for m in snapshot["machines"] if m["name"] == "T-ANDON")
		self.assertEqual([c["name"] for c in machine["andon"]], [name])
		self.assertIn(name, [c["name"] for c in snapshot["andon_calls"]])
		self.assertEqual(list_open_andon_calls("T-ANDON")[0]["call_type"], "Safety")

	def test_operator_can_raise_and_acknowledge(self):
		operator = make_user("t-andon-op@foames.test", "FoaMES Operator")
		with as_user(operator.name):
			name = raise_andon("T-ANDON", "Material")["name"]
			self.assertEqual(acknowledge_andon(name)["status"], "Acknowledged")

	def test_report(self):
		from foames.foames_mes.report.andon_response.andon_response import execute

		first = raise_andon("T-ANDON", "Maintenance")["name"]
		backdate(first, 10)
		acknowledge_andon(first)
		raise_andon("T-ANDON", "Maintenance")
		_columns, rows, _msg, _chart, summary = execute({"line": "T-ANDON-LINE", "group_by": "Call Type"})
		(row,) = rows
		self.assertEqual((row["group"], row["calls"], row["open"]), ("Maintenance", 2, 2))
		self.assertAlmostEqual(row["median_response"], 10, delta=0.5)
		self.assertEqual(summary[0]["value"], 2)
