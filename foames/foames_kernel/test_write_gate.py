# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Read-only mode on a site: outbox postings held and signed off, MCP writes held, registered
actions, blocking, the signature rules, the audit chain and the upgrade patch.

bench --site <site> run-tests --app foames --module foames.foames_kernel.test_write_gate
"""

import json
from unittest.mock import patch

import frappe
from frappe.utils.password import update_password

from foames.foames_adapters.doctype.erpnext_outbox.erpnext_outbox import claim, enqueue
from foames.foames_kernel import write_gate
from foames.foames_kernel import write_policy as policy
from foames.foames_mcp import api as mcp
from foames.foames_mes.doctype.machine.test_machine import reference
from foames.foames_mes.doctype.oee_period.test_oee_period import make_machine
from foames.tests_compat import IntegrationTestCase

SIGNER = "foames-ro-signer@example.com"
OPERATOR = "foames-ro-operator@example.com"
AGENT = "foames-ro-agent@example.com"
PASSWORD = "Ro-Mode-Test-9!x"
ACTIONS = []


def record_action(value: str):
	ACTIONS.append((frappe.session.user, value))
	return {"recorded": value}


def make_user(email, roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	user = frappe.get_doc("User", email)
	user.set("roles", [])
	for role in roles:
		user.append("roles", {"role": role})
	user.save(ignore_permissions=True)
	update_password(email, PASSWORD)
	return email


def set_mode(**values):
	defaults = {
		"read_only_mode": 1,
		"read_only_action": policy.QUEUE,
		"new_connectors_read_only": 1,
		"sign_off_role": "FoaMES Supervisor",
		"require_second_person": 1,
		"gate_agent_suggestions": 0,
	}
	defaults.update(values)
	for field, value in defaults.items():
		frappe.db.set_single_value("FoaMES Settings", field, value)


def events(**filters):
	return frappe.get_all(
		"Write Audit Log", filters=filters, pluck="event", order_by="creation asc, name asc"
	)


MANUFACTURE = {"work_order": "MFG-WO-RO-1", "qty": 5}


class TestWriteGate(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		for doctype in ("ERPNext Outbox", "Pending Write", "Write Audit Log", "Connector Write Policy"):
			frappe.db.delete(doctype)
		make_user(SIGNER, ["FoaMES Supervisor"])
		make_user(OPERATOR, ["FoaMES Operator"])
		make_user(AGENT, ["FoaMES Operator"])
		ACTIONS.clear()
		set_mode()

	def tearDown(self):
		frappe.set_user("Administrator")
		set_mode(read_only_mode=0, new_connectors_read_only=0)
		super().tearDown()

	def sign(
		self,
		name,
		meaning=policy.APPROVE,
		reason="Checked against the work order",
		user=SIGNER,
		password=PASSWORD,
	):
		frappe.set_user(user)
		try:
			return write_gate.sign_pending_write(name, meaning, reason, password)
		finally:
			frappe.set_user("Administrator")

	# Policies -----------------------------------------------------------------------------------

	def test_new_connector_starts_read_only(self):
		set_mode(read_only_mode=0)
		self.assertTrue(write_gate.is_read_only("NEW_ONE"))
		self.assertEqual(frappe.db.get_value("Connector Write Policy", "NEW_ONE", "read_only"), 1)
		self.assertIn(policy.EVENT_POLICY_CHANGED, events(connector="NEW_ONE"))

	def test_site_switch_makes_a_writable_connector_read_only(self):
		set_mode(read_only_mode=0, new_connectors_read_only=0)
		self.assertFalse(write_gate.is_read_only("OPEN_ONE"))
		set_mode(read_only_mode=1, new_connectors_read_only=0)
		self.assertTrue(write_gate.is_read_only("OPEN_ONE"))

	def test_turning_read_only_off_needs_an_approval_reference(self):
		set_mode(read_only_mode=0)
		write_gate.connector_policy("NEEDS_CC")
		doc = frappe.get_doc("Connector Write Policy", "NEEDS_CC")
		doc.read_only = 0
		with self.assertRaisesRegex(frappe.ValidationError, "change control"):
			doc.save()
		doc.approval_reference = "CC-2026-114"
		doc.save()
		self.assertFalse(write_gate.is_read_only("NEEDS_CC"))
		last = frappe.get_all(
			"Write Audit Log",
			filters={"connector": "NEEDS_CC"},
			fields=["reason", "details"],
			order_by="creation desc, name desc",
			limit=1,
		)[0]
		self.assertEqual(last.reason, "CC-2026-114")
		self.assertEqual(json.loads(last.details)["read_only"], {"from": 1, "to": 0})

	# Outbox postings -----------------------------------------------------------------------------

	def test_outbox_posting_is_held_then_released_after_sign_off(self):
		name = enqueue("Manufacture", MANUFACTURE, "ro:1:manufacture", "MFG-WO-RO-1")
		pending = frappe.get_doc(
			"Pending Write", {"reference_doctype": "ERPNext Outbox", "reference_name": name}
		)
		self.assertEqual(pending.status, policy.AWAITING)
		self.assertEqual(pending.connector, "ERPNext")
		self.assertEqual(pending.work_order, "MFG-WO-RO-1")
		self.assertEqual(pending.kind, policy.KIND_OUTBOX)
		self.assertIsNone(claim(name), "a held posting must not be sent")
		self.assertEqual(frappe.db.get_value("ERPNext Outbox", name, "status"), "Queued")

		result = self.sign(pending.name)
		self.assertEqual(result["status"], policy.APPROVED)
		pending.reload()
		self.assertEqual(pending.signed_by, SIGNER)
		self.assertEqual(pending.signature_meaning, policy.APPROVE)
		self.assertTrue(write_gate.verify_pending_write(pending.name)["signature_ok"])

		doc = claim(name)
		self.assertIsNotNone(doc)
		self.assertEqual(doc.status, "Sending")
		self.assertEqual(frappe.db.get_value("Pending Write", pending.name, "status"), policy.RELEASED)
		trail = events(work_order="MFG-WO-RO-1")
		for event in (policy.EVENT_HELD, policy.EVENT_SIGNED, policy.EVENT_RELEASED):
			self.assertIn(event, trail)

	def test_held_posting_holds_back_its_sequence_group(self):
		first = enqueue(
			"Material Transfer for Manufacture", {"work_order": "MFG-WO-RO-2"}, "ro:2:transfer", "MFG-WO-RO-2"
		)
		second = enqueue(
			"Manufacture", {"work_order": "MFG-WO-RO-2", "qty": 1}, "ro:2:manufacture", "MFG-WO-RO-2"
		)
		self.assertEqual(frappe.get_doc("ERPNext Outbox", second).blocking_posting(), first)

	def test_rejection_cancels_the_posting(self):
		name = enqueue("Manufacture", MANUFACTURE, "ro:3:manufacture")
		pending = frappe.db.get_value("Pending Write", {"reference_name": name}, "name")
		result = self.sign(pending, meaning=policy.REJECT, reason="Quantity does not match the count")
		self.assertEqual(result["status"], policy.REJECTED)
		row = frappe.db.get_value("ERPNext Outbox", name, ["status", "last_error"], as_dict=True)
		self.assertEqual(row.status, "Cancelled")
		self.assertIn("Quantity does not match", row.last_error)
		self.assertIn(policy.EVENT_REJECTED, events(pending_write=pending))

	def test_block_cancels_and_logs(self):
		set_mode(read_only_action=policy.BLOCK)
		name = enqueue("Manufacture", MANUFACTURE, "ro:4:manufacture")
		self.assertEqual(frappe.db.get_value("ERPNext Outbox", name, "status"), "Cancelled")
		self.assertFalse(frappe.db.exists("Pending Write", {"reference_name": name}))
		self.assertIn(policy.EVENT_BLOCKED, events(connector="ERPNext"))

	def test_read_write_connector_is_not_held(self):
		set_mode(read_only_mode=0, new_connectors_read_only=0)
		name = enqueue("Manufacture", MANUFACTURE, "ro:5:manufacture")
		self.assertFalse(frappe.db.exists("Pending Write", {"reference_name": name}))
		self.assertIsNotNone(claim(name))

	def test_mode_turned_on_after_queueing_still_holds(self):
		set_mode(read_only_mode=0, new_connectors_read_only=0)
		name = enqueue("Manufacture", MANUFACTURE, "ro:6:manufacture")
		set_mode(read_only_mode=1)
		self.assertIsNone(claim(name))
		self.assertTrue(
			frappe.db.exists("Pending Write", {"reference_name": name, "status": policy.AWAITING})
		)

	def test_cancelling_the_posting_withdraws_its_pending_write(self):
		name = enqueue("Manufacture", MANUFACTURE, "ro:7:manufacture")
		frappe.get_doc("ERPNext Outbox", name).cancel_posting()
		self.assertEqual(
			frappe.db.get_value("Pending Write", {"reference_name": name}, "status"), policy.WITHDRAWN
		)

	def test_payload_changed_after_holding_cannot_be_signed(self):
		name = enqueue("Manufacture", MANUFACTURE, "ro:8:manufacture")
		pending = frappe.db.get_value("Pending Write", {"reference_name": name}, "name")
		frappe.db.set_value(
			"ERPNext Outbox", name, "payload", json.dumps({"work_order": "MFG-WO-RO-1", "qty": 500})
		)
		with self.assertRaisesRegex(frappe.ValidationError, "payload changed"):
			self.sign(pending)
		self.assertEqual(frappe.db.get_value("Pending Write", pending, "status"), policy.AWAITING)
		self.assertIn(policy.EVENT_SIGNATURE_FAILED, events(pending_write=pending))

	# Signature rules -----------------------------------------------------------------------------

	def test_wrong_password_is_refused_and_logged(self):
		name = enqueue("Manufacture", MANUFACTURE, "ro:9:manufacture")
		pending = frappe.db.get_value("Pending Write", {"reference_name": name}, "name")
		with self.assertRaises(frappe.ValidationError):
			self.sign(pending, password="wrong")
		self.assertEqual(frappe.db.get_value("Pending Write", pending, "status"), policy.AWAITING)
		self.assertIn(policy.EVENT_SIGNATURE_FAILED, events(pending_write=pending))

	def test_signer_needs_the_role(self):
		name = enqueue("Manufacture", MANUFACTURE, "ro:10:manufacture")
		pending = frappe.db.get_value("Pending Write", {"reference_name": name}, "name")
		with self.assertRaisesRegex(frappe.ValidationError, "role"):
			self.sign(pending, user=OPERATOR)

	def test_requester_cannot_sign_their_own_write(self):
		frappe.set_user(SIGNER)
		try:
			held = write_gate.hold("TEST_CONN", policy.KIND_ACTION, "test.record", {"value": "x"})
		finally:
			frappe.set_user("Administrator")
		with self.assertRaisesRegex(frappe.ValidationError, "cannot also sign"):
			self.sign(held)

	def test_pending_write_cannot_be_edited_or_deleted(self):
		held = write_gate.hold("TEST_CONN", policy.KIND_ACTION, "test.record", {"value": "x"})
		doc = frappe.get_doc("Pending Write", held)
		doc.summary = "changed"
		with self.assertRaises(frappe.ValidationError):
			doc.save()
		with self.assertRaises(frappe.ValidationError):
			frappe.delete_doc("Pending Write", held)

	# Registered actions ---------------------------------------------------------------------------

	def test_registered_action_runs_after_sign_off_as_the_requester(self):
		actions = {"test.record": f"{__name__}.record_action"}
		with patch.object(write_gate, "registered_actions", return_value=actions):
			frappe.set_user(AGENT)
			try:
				answer = write_gate.request_write(
					"TEST_SCADA", "test.record", {"value": "setpoint 42"}, context={"work_order": "WO-77"}
				)
			finally:
				frappe.set_user("Administrator")
			self.assertEqual(answer["status"], policy.AWAITING)
			self.assertEqual(ACTIONS, [])
			result = self.sign(answer["pending_write"])
		self.assertEqual(result["status"], policy.EXECUTED)
		self.assertEqual(ACTIONS, [(AGENT, "setpoint 42")])
		self.assertIn(policy.EVENT_EXECUTED, events(work_order="WO-77"))

	def test_unregistered_action_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			write_gate.request_write("TEST_SCADA", "not.registered", {})

	def test_blocked_action_raises(self):
		set_mode(read_only_action=policy.BLOCK)
		with patch.object(
			write_gate, "registered_actions", return_value={"test.record": f"{__name__}.record_action"}
		):
			with self.assertRaises(write_gate.ReadOnlyModeError):
				write_gate.request_write("TEST_SCADA", "test.record", {"value": "x"})
		self.assertEqual(ACTIONS, [])

	# MCP ------------------------------------------------------------------------------------------

	def test_mcp_write_is_held_and_runs_after_sign_off(self):
		machine = make_machine("T-RO-MCP").name
		card = reference("Job Card", "PO-JOB-RO-1")
		frappe.set_user(AGENT)
		try:
			response = mcp.handle(
				{
					"jsonrpc": "2.0",
					"id": 1,
					"method": "tools/call",
					"params": {
						"name": "foames_set_current_job",
						"arguments": {"machine": machine, "reference": card},
					},
				}
			)
		finally:
			frappe.set_user("Administrator")
		answer = json.loads(response["result"]["content"][0]["text"])
		self.assertEqual(answer["status"], policy.AWAITING)
		self.assertFalse(frappe.db.get_value("Machine", machine, "current_job_reference"))
		pending = frappe.get_doc("Pending Write", answer["pending_write"])
		self.assertEqual(pending.job_card, "PO-JOB-RO-1")
		self.assertEqual(pending.machine, machine)
		self.assertEqual(self.sign(pending.name)["status"], policy.EXECUTED)
		self.assertEqual(frappe.db.get_value("Machine", machine, "current_job_reference"), card)

	def test_mcp_suggestions_run_unless_held(self):
		tool = next(t for t in mcp.catalogue() if t.name == "foames_post_suggestion")
		self.assertIsNone(write_gate.gate_tool_call(tool, {"title": "x"}))
		set_mode(gate_agent_suggestions=1)
		self.assertEqual(write_gate.gate_tool_call(tool, {"title": "x"})["status"], policy.AWAITING)

	def test_mcp_reads_are_never_held(self):
		tool = next(t for t in mcp.catalogue() if t.name == "foames_get_write_mode")
		self.assertIsNone(write_gate.gate_tool_call(tool, {}))
		mode = write_gate.get_write_mode()
		self.assertTrue(mode["site_read_only"])

	# Audit trail ----------------------------------------------------------------------------------

	def test_audit_chain_verifies_and_detects_tampering(self):
		write_gate.hold("TEST_CONN", policy.KIND_ACTION, "test.record", {"value": "a"})
		write_gate.hold("TEST_CONN", policy.KIND_ACTION, "test.record", {"value": "b"})
		self.assertTrue(write_gate.verify_audit_trail()["intact"])
		victim = frappe.get_all("Write Audit Log", pluck="name", order_by="creation asc, name asc")[0]
		frappe.db.set_value("Write Audit Log", victim, "reason", "edited", update_modified=False)
		self.assertEqual(write_gate.verify_audit_trail()["broken"], [victim])

	def test_audit_entries_cannot_be_changed(self):
		held = write_gate.hold("TEST_CONN", policy.KIND_ACTION, "test.record", {"value": "a"})
		entry = frappe.get_doc("Write Audit Log", {"pending_write": held})
		entry.reason = "changed"
		with self.assertRaises(frappe.ValidationError):
			entry.save(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Write Audit Log", "event": policy.EVENT_HELD}).insert(
				ignore_permissions=True
			)

	def test_settings_changes_are_logged(self):
		settings = frappe.get_doc("FoaMES Settings")
		settings.read_only_action = policy.BLOCK
		settings.save()
		self.assertIn(policy.EVENT_SETTINGS_CHANGED, events())

	# Upgrade --------------------------------------------------------------------------------------

	def test_upgrade_keeps_connectors_that_already_wrote_writable(self):
		set_mode(read_only_mode=0, new_connectors_read_only=0)
		enqueue("Manufacture", MANUFACTURE, "ro:11:manufacture")
		frappe.db.delete("Connector Write Policy")
		from foames.patches import introduce_read_only_mode

		introduce_read_only_mode.execute()
		self.assertEqual(frappe.db.get_single_value("FoaMES Settings", "read_only_mode"), 0)
		self.assertEqual(frappe.db.get_value("Connector Write Policy", "ERPNext", "read_only"), 0)
		self.assertEqual(frappe.db.get_value("Connector Write Policy", "mcp", "read_only"), 0)
		self.assertTrue(write_gate.is_read_only("SOMETHING_NEW"))
