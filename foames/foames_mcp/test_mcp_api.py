# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Site tests for the MCP endpoint: tools run as the calling user with Frappe's permissions.

bench --site <site> run-tests --app foames --module foames.foames_mcp.test_mcp_api
"""

import json

import frappe
from frappe.utils import add_days, now_datetime

from foames.foames_mcp import api
from foames.foames_mcp.tools import TOOLS
from foames.foames_mes.api import record_events
from foames.foames_mes.doctype.oee_period.test_oee_period import make_machine
from foames.tests_compat import IntegrationTestCase

READER = "foames-mcp-reader@example.com"
NOBODY = "foames-mcp-nobody@example.com"


def call(name, arguments=None, request_id=1):
	return api.handle(
		{
			"jsonrpc": "2.0",
			"id": request_id,
			"method": "tools/call",
			"params": {"name": name, "arguments": arguments or {}},
		}
	)


def content(response):
	result = response["result"]
	return json.loads(result["content"][0]["text"]) if result["content"][0]["text"][:1] in "[{" else result


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
	return email


class TestMCPEndpoint(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.machine = "T-MCP-" + frappe.generate_hash(length=6).upper()
		make_machine(self.machine, ideal_cycle_seconds=30)
		record_events(
			[
				{
					"machine": self.machine,
					"type": "State",
					"state": "Running",
					"timestamp": "2026-10-22T08:00:00",
				},
				{"machine": self.machine, "type": "Count", "value": 0, "timestamp": "2026-10-22T08:00:00"},
				{"machine": self.machine, "type": "Count", "value": 100, "timestamp": "2026-10-22T09:00:00"},
				{
					"machine": self.machine,
					"type": "State",
					"state": "Down",
					"timestamp": "2026-10-22T09:00:00",
				},
				{
					"machine": self.machine,
					"type": "State",
					"state": "Running",
					"timestamp": "2026-10-22T09:30:00",
				},
			]
		)
		make_user(READER, ["FoaMES Operator"])
		make_user(NOBODY, [])

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def test_initialize_and_list(self):
		init = api.handle(
			{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}
		)
		self.assertEqual(init["result"]["protocolVersion"], "2025-06-18")
		self.assertEqual(init["result"]["serverInfo"]["name"], "foames")
		tools = api.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
		self.assertEqual(len(tools), len(TOOLS))

	def test_every_tool_binds_a_whitelisted_method(self):
		for tool in TOOLS:
			method = frappe.get_attr(tool.method)
			frappe.is_whitelisted(method)  # raises when it is not

	def test_machine_reads(self):
		machines = content(call("foames_list_machines", {"status": "Running"}))
		self.assertIn(self.machine, [m["name"] for m in machines])
		detail = call("foames_get_machine", {"machine": self.machine})["result"]["structuredContent"]
		self.assertEqual(detail["status"], "Running")
		self.assertEqual(
			[e["state"] for e in detail["recent_state_events"]][:3], ["Running", "Down", "Running"]
		)
		events = content(call("foames_list_machine_events", {"machine": self.machine, "event_type": "Count"}))
		self.assertEqual(sorted(e["delta"] for e in events), [0, 100])

	def test_downtime_and_oee(self):
		downtime = content(call("foames_list_downtime", {"machine": self.machine}))
		self.assertEqual(len(downtime), 1)
		self.assertEqual(downtime[0]["duration_minutes"], 30)
		by_reason = call(
			"foames_downtime_by_reason",
			{"machine": self.machine, "since": "2026-10-22 00:00:00", "until": "2026-10-23 00:00:00"},
		)["result"]["structuredContent"]
		self.assertEqual(by_reason["unclassified_minutes"], 30)
		oee = call(
			"foames_get_oee",
			{"machine": self.machine, "from_time": "2026-10-22 08:00:00", "to_time": "2026-10-22 10:00:00"},
		)["result"]["structuredContent"]
		self.assertAlmostEqual(oee["availability"], 75)
		self.assertEqual(oee["good_count"], 100)

	def test_floor_snapshot_and_suggestions(self):
		snapshot = call("foames_get_floor_snapshot", {"days": 1})["result"]["structuredContent"]
		self.assertIn("machines", snapshot)
		posted = call(
			"foames_post_suggestion",
			{
				"title": "Check the press",
				"category": "Downtime",
				"suggestion": "Thirty unclassified minutes this morning.",
				"agent": "test-agent",
				"reference_doctype": "Machine",
				"reference_name": self.machine,
				"evidence": {"unclassified_minutes": 30},
				"rule_key": f"test:{self.machine}",
			},
		)
		name = posted["result"]["content"][0]["text"]
		self.assertTrue(frappe.db.exists("Agent Suggestion", name))
		listed = content(call("foames_list_suggestions", {"agent": "test-agent"}))
		self.assertEqual([s["name"] for s in listed], [name])
		full = call("foames_get_suggestion", {"name": name})["result"]["structuredContent"]
		self.assertEqual(full["evidence"], {"unclassified_minutes": 30})
		# The same rule_key while open is not raised twice.
		again = call(
			"foames_post_suggestion",
			{
				"title": "Check the press",
				"category": "Downtime",
				"suggestion": "x",
				"agent": "test-agent",
				"rule_key": f"test:{self.machine}",
			},
		)
		self.assertEqual(again["result"]["content"][0]["text"], name)

	def test_process_mining_tools(self):
		window = {"since": "2026-10-22 00:00:00", "until": "2026-10-23 00:00:00"}
		summary = call("foames_mining_summary", window)["result"]["structuredContent"]
		self.assertGreaterEqual(summary["events"], 3)
		discovered = call("foames_mining_discover", window)["result"]["structuredContent"]
		self.assertIn("dfg", discovered)
		conformance = call("foames_mining_conformance", {"model": ["Running", "Down", "Running"], **window})
		self.assertFalse(conformance["result"]["isError"])
		xes = call("foames_mining_export", {**window, "fmt": "xes"})["result"]["content"][0]["text"]
		self.assertTrue(xes.lstrip().startswith("<"))

	def test_erp_reference_tools(self):
		systems = call("foames_list_erp_systems")["result"]["structuredContent"]
		self.assertIn("ERPNext", [s["key"] for s in systems["systems"]])
		self.assertIn("Work Order", systems["reference_types"])
		lookup = call(
			"foames_lookup_erp_record",
			{"reference_type": "Item", "external_id": "NOPE-404", "erp_system": "ERPNext"},
		)["result"]
		if "erpnext" in frappe.get_installed_apps():
			self.assertFalse(lookup["isError"])
			self.assertFalse(lookup["structuredContent"]["found"])
		else:
			self.assertTrue(lookup["isError"])
			self.assertIn("not available", lookup["content"][0]["text"])
		self.assertFalse(frappe.db.exists("External Reference", {"external_id": "NOPE-404"}))

	def test_permissions_follow_the_user(self):
		frappe.set_user(READER)
		machines = content(call("foames_list_machines"))
		self.assertIn(self.machine, [m["name"] for m in machines])
		refs = call("foames_list_external_references")["result"]
		self.assertTrue(refs["isError"])
		self.assertIn("Not permitted", refs["content"][0]["text"])
		frappe.set_user(NOBODY)
		denied = call("foames_list_machines")["result"]
		self.assertTrue(denied["isError"])
		denied = call(
			"foames_post_suggestion",
			{
				"title": "t",
				"category": "Other",
				"suggestion": "s",
				"agent": "nobody",
			},
		)["result"]
		self.assertTrue(denied["isError"])
		self.assertFalse(frappe.db.exists("Agent Suggestion", {"agent": "nobody"}))

	def test_protocol_errors(self):
		unknown = call("foames_delete_everything")
		self.assertEqual(unknown["error"]["code"], -32602)
		bad = call("foames_get_oee", {"machine": self.machine})
		self.assertEqual(bad["error"]["code"], -32602)
		self.assertIsNone(api.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))

	def test_http_endpoint_returns_raw_jsonrpc(self):
		from werkzeug.test import EnvironBuilder
		from werkzeug.wrappers import Request

		body = json.dumps({"jsonrpc": "2.0", "id": 7, "method": "ping"})
		builder = EnvironBuilder(method="POST", data=body, content_type="application/json")
		previous = getattr(frappe.local, "request", None)
		frappe.local.request = Request(builder.get_environ())
		try:
			response = api.mcp()
		finally:
			frappe.local.request = previous
		self.assertEqual(response.status_code, 200)
		self.assertEqual(
			json.loads(response.get_data(as_text=True)), {"jsonrpc": "2.0", "id": 7, "result": {}}
		)
		self.assertEqual(response.headers["MCP-Protocol-Version"], "2025-11-25")
