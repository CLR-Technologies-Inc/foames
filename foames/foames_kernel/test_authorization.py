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

"""Authorization boundaries on a site: two mutually isolated areas, each with its own reader, and
the reads a person or an agent makes across them (floor snapshot, MCP tools, validation status,
reports); plus who may weaken a connector write policy.

bench --site <site> run-tests --app foames --module foames.foames_kernel.test_authorization
"""

import frappe
from frappe.permissions import add_user_permission

from foames.foames_kernel import write_gate
from foames.foames_kernel.access import require_read
from foames.foames_mcp import reads
from foames.foames_mes.api import get_floor_snapshot, get_material_status
from foames.foames_validation.api import get_qualification_status
from foames.foames_validation.test_validation import make_protocol
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import as_user, make_machine, make_user

AREA_A = "T-AUTH-A"
AREA_B = "T-AUTH-B"
READER_A = "auth-reader-a@example.com"
READER_B = "auth-reader-b@example.com"
ENGINEER = "auth-engineer@example.com"
POLICY_ADMIN = "auth-policy-admin@example.com"


def suggestion(machine, title):
	return (
		frappe.get_doc(
			{
				"doctype": "Agent Suggestion",
				"title": title,
				"suggestion": title,
				"agent": "auth-test",
				"category": "Other",
				"reference_doctype": "Machine",
				"reference_name": machine,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


class TestRecordScope(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		for machine in (AREA_A, AREA_B):
			make_machine(machine)
		for user, machine in ((READER_A, AREA_A), (READER_B, AREA_B)):
			make_user(user, "FoaMES Operator", "FoaMES Engineer")
			frappe.db.delete("User Permission", {"user": user})
			add_user_permission("Machine", machine, user)
		self.hidden_a = suggestion(AREA_A, "Check the A press")
		self.hidden_b = suggestion(AREA_B, "Check the B press")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("User Permission", {"user": ("in", [READER_A, READER_B])})
		super().tearDown()

	def test_each_reader_sees_only_their_area_on_the_floor(self):
		for user, mine, other, mine_s, other_s in (
			(READER_A, AREA_A, AREA_B, self.hidden_a, self.hidden_b),
			(READER_B, AREA_B, AREA_A, self.hidden_b, self.hidden_a),
		):
			with as_user(user):
				snapshot = get_floor_snapshot()
			machines = {m["name"] for m in snapshot["machines"]}
			self.assertIn(mine, machines)
			self.assertNotIn(other, machines)
			self.assertEqual(snapshot["scope"]["user"], user)
			self.assertNotIn(other, snapshot["scope"]["machines"])
			suggestions = {s["name"] for s in snapshot["open_suggestions"]}
			self.assertIn(mine_s, suggestions)
			self.assertNotIn(other_s, suggestions)

	def test_a_system_read_still_sees_every_machine(self):
		from foames.foames_mes.floor import floor_snapshot

		machines = {m["name"] for m in floor_snapshot()["machines"]}
		self.assertTrue({AREA_A, AREA_B} <= machines)
		self.assertIsNone(floor_snapshot()["scope"]["machines"])

	def test_an_error_does_not_say_whether_another_area_record_exists(self):
		with as_user(READER_A):
			with self.assertRaises(frappe.PermissionError) as forbidden:
				require_read("Machine", AREA_B)
			with self.assertRaises(frappe.PermissionError) as missing:
				require_read("Machine", "T-AUTH-NOWHERE")
			require_read("Machine", AREA_A)
		self.assertEqual(
			str(forbidden.exception).replace(AREA_B, "X"),
			str(missing.exception).replace("T-AUTH-NOWHERE", "X"),
		)

	def test_mcp_reads_keep_to_the_area(self):
		with as_user(READER_A):
			names = {m["name"] for m in reads.list_machines()}
			self.assertIn(AREA_A, names)
			self.assertNotIn(AREA_B, names)
			with self.assertRaises(frappe.PermissionError):
				reads.get_machine(AREA_B)
			with self.assertRaises(frappe.PermissionError):
				reads.get_suggestion(self.hidden_b)
			self.assertEqual(reads.get_suggestion(self.hidden_a)["name"], self.hidden_a)
			with self.assertRaises(frappe.PermissionError):
				get_material_status(machine=AREA_B)

	def test_active_runs_keep_to_the_runs_a_reader_may_read(self):
		from foames.foames_mes.doctype.work_instruction_run.test_work_instruction_run import make_instruction
		from foames.foames_mes.doctype.work_instruction_run.work_instruction_run import (
			list_active_runs,
			start_run,
		)

		instruction = make_instruction("T-AUTH-WI").name
		mine, other = (start_run(instruction, AREA_A)["name"] for _ in range(2))
		add_user_permission("Work Instruction Run", mine, READER_A)
		with as_user(READER_A):
			self.assertEqual([r.name for r in list_active_runs(AREA_A)], [mine])
			self.assertEqual([r.name for r in list_active_runs()], [mine])
			snapshot = get_floor_snapshot()
			with self.assertRaises(frappe.PermissionError):
				list_active_runs(AREA_B)
		self.assertEqual({r["name"] for r in snapshot["work_instruction_runs"]} & {mine, other}, {mine})

	def test_validation_status_keeps_to_the_area(self):
		make_protocol("IQ", machine=AREA_A, title="IQ of A")
		make_protocol("IQ", machine=AREA_B, title="IQ of B")
		with as_user(READER_A):
			subjects = {row["subject"] for row in get_qualification_status(protocol_type="IQ")}
		self.assertIn(AREA_A, subjects)
		self.assertNotIn(AREA_B, subjects)


class TestPolicyAuthority(IntegrationTestCase):
	CONNECTOR = "T-AUTH-CONNECTOR"

	def setUp(self):
		super().setUp()
		make_user(ENGINEER, "FoaMES Engineer")
		make_user(POLICY_ADMIN, "FoaMES Engineer", "FoaMES Policy Administrator")
		frappe.db.delete("Connector Write Policy", {"connector": self.CONNECTOR})
		frappe.get_doc(
			{"doctype": "Connector Write Policy", "connector": self.CONNECTOR, "read_only": 1}
		).insert()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Connector Write Policy", {"connector": self.CONNECTOR})
		super().tearDown()

	def change(self, user, **values):
		with as_user(user):
			doc = frappe.get_doc("Connector Write Policy", self.CONNECTOR)
			doc.update({"approval_reference": "CC-AUTH-1", **values})
			doc.save()

	def test_an_engineer_cannot_lift_the_gate(self):
		for values in ({"read_only": 0}, {"sign_off_role": "FoaMES Operator"}):
			with self.assertRaises(frappe.PermissionError):
				self.change(ENGINEER, **values)
		self.assertTrue(write_gate.is_read_only(self.CONNECTOR))

	def test_an_engineer_cannot_create_a_policy_that_overrides_the_site_gate(self):
		frappe.db.delete("Connector Write Policy", {"connector": self.CONNECTOR})
		for values in ({"when_read_only": "Queue for sign-off"}, {"sign_off_role": "FoaMES Engineer"}):
			with as_user(ENGINEER), self.assertRaises(frappe.PermissionError):
				frappe.get_doc(
					{
						"doctype": "Connector Write Policy",
						"connector": self.CONNECTOR,
						"read_only": 1,
						**values,
					}
				).insert()

	def test_an_engineer_can_tighten(self):
		self.change(ENGINEER, when_read_only="Block")
		self.assertEqual(
			frappe.db.get_value("Connector Write Policy", self.CONNECTOR, "when_read_only"), "Block"
		)

	def test_a_policy_administrator_can_lift_the_gate(self):
		self.change(POLICY_ADMIN, read_only=0)
		self.assertEqual(frappe.db.get_value("Connector Write Policy", self.CONNECTOR, "read_only"), 0)

	def test_an_engineer_cannot_delete_a_read_only_policy(self):
		with as_user(ENGINEER):
			with self.assertRaises(frappe.PermissionError):
				frappe.delete_doc("Connector Write Policy", self.CONNECTOR)
		self.assertTrue(frappe.db.exists("Connector Write Policy", self.CONNECTOR))
