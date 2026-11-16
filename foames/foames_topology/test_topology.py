# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""The topology records, the sync from FoaMES records, the API and tenant isolation, on a site."""

import frappe
from frappe.utils import add_to_date, now_datetime

from foames.foames_topology import api, sync
from foames.foames_topology.floor import extend_snapshot
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import as_user, make_machine, make_user


def tenant(name):
	if not frappe.db.exists("Topology Tenant", name):
		frappe.get_doc({"doctype": "Topology Tenant", "tenant_name": name}).insert()
	return name


def make_asset(asset_id, layer, kind, **kw):
	return frappe.get_doc(
		{"doctype": "Topology Asset", "asset_id": asset_id, "layer": layer, "kind": kind, **kw}
	).insert()


class TestRecords(IntegrationTestCase):
	def test_kind_must_match_layer(self):
		with self.assertRaises(frappe.ValidationError):
			make_asset("t-topo:bad", "Data", "Machine")

	def test_parent_loop_is_refused(self):
		make_asset("t-topo:a", "Physical", "Line")
		make_asset("t-topo:b", "Physical", "Machine", parent_asset="t-topo:a")
		a = frappe.get_doc("Topology Asset", "t-topo:a")
		a.parent_asset = "t-topo:b"
		with self.assertRaises(frappe.ValidationError):
			a.save()

	def test_binding_needs_data_to_physical(self):
		make_asset("t-topo:m", "Physical", "Machine")
		make_asset("t-topo:s", "Data", "Signal")
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{"doctype": "Signal Binding", "signal": "t-topo:m", "physical_asset": "t-topo:s"}
			).insert()
		b = frappe.get_doc(
			{"doctype": "Signal Binding", "signal": "t-topo:s", "physical_asset": "t-topo:m"}
		).insert()
		self.assertEqual(b.binding_key, "t-topo:s|Read|t-topo:m")

	def test_link_across_tenants_is_refused(self):
		make_asset("t-topo:x", "Physical", "Machine", tenant=tenant("T-Topo A"))
		make_asset("t-topo:y", "Physical", "Machine", tenant=tenant("T-Topo B"))
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Topology Link",
					"from_asset": "t-topo:x",
					"to_asset": "t-topo:y",
					"link_type": "Pipe",
				}
			).insert()

	def test_link_takes_its_assets_tenant_and_layer(self):
		make_asset("t-topo:p", "Physical", "Machine", tenant=tenant("T-Topo A"))
		make_asset("t-topo:q", "Physical", "Machine", tenant="T-Topo A")
		link = frappe.get_doc(
			{
				"doctype": "Topology Link",
				"from_asset": "t-topo:p",
				"to_asset": "t-topo:q",
				"link_type": "Pipe",
			}
		).insert()
		self.assertEqual(link.tenant, "T-Topo A")
		self.assertEqual(link.layer, "Physical")


class TestSync(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_machine("T-TOPO-1", line="T-TOPO-LINE", status="Running", last_seen=now_datetime())
		make_machine("T-TOPO-2", line="T-TOPO-LINE")
		settings = frappe.get_single("Machine Data Settings")
		settings.append(
			"node_map",
			{
				"machine": "T-TOPO-1",
				"source": "OPC UA",
				"node_id": "ns=2;s=T1.Temp",
				"event_type": "Measurement",
				"name_or_counter": "temp",
			},
		)
		settings.save()
		frappe.clear_document_cache("Machine Data Settings", "Machine Data Settings")

	def test_machines_and_signals_become_the_graph(self):
		sync.sync()
		self.assertEqual(
			frappe.db.get_value("Topology Asset", "machine:T-TOPO-1", "parent_asset"), "line:T-TOPO-LINE"
		)
		signal = "signal:opc-ua:ns=2;s=T1.Temp"
		self.assertTrue(frappe.db.exists("Topology Asset", signal))
		self.assertTrue(
			frappe.db.exists("Signal Binding", {"signal": signal, "physical_asset": "machine:T-TOPO-1"})
		)
		trace = api.trace("machine:T-TOPO-1", "downstream")
		self.assertIn("connector:opc-ua", trace["nodes"])
		self.assertIn("events:T-TOPO-1", trace["nodes"])
		self.assertIn("kpi:oee:T-TOPO-1", trace["nodes"])

	def test_sync_is_idempotent_and_retires_what_left(self):
		first = sync.sync()
		second = sync.sync()
		self.assertGreater(first["foames-mes"]["inserted"], 0)
		self.assertEqual(second["foames-mes"]["inserted"], 0)
		frappe.db.set_value("Machine", "T-TOPO-2", "disabled", 1)
		third = sync.sync()
		self.assertGreaterEqual(third["foames-mes"]["retired"], 1)
		self.assertEqual(frappe.db.get_value("Topology Asset", "machine:T-TOPO-2", "status"), "Retired")

	def test_hand_made_assets_are_never_overwritten(self):
		make_asset("machine:T-TOPO-1", "Physical", "Machine", title="Kept by hand")
		sync.sync()
		self.assertEqual(frappe.db.get_value("Topology Asset", "machine:T-TOPO-1", "title"), "Kept by hand")

	def test_floor_snapshot_gets_the_data_layer(self):
		sync.sync()
		snapshot = {}
		extend_snapshot(snapshot, add_to_date(now_datetime(), days=-1), now_datetime())
		self.assertEqual(snapshot["topology"]["T-TOPO-1"]["signals"], 1)
		self.assertEqual(snapshot["topology"]["T-TOPO-2"]["signals"], 0)

	def test_exports(self):
		sync.sync()
		self.assertIn("flowchart TB", api.get_mermaid())
		out = api.grafana()
		self.assertIn("machine:T-TOPO-1", {n["id"] for n in out["nodes"]})
		over = api.overlay(source_doctype="Machine", source_names="T-TOPO-1")
		self.assertEqual(list(over), ["T-TOPO-1"])
		self.assertEqual(len(over["T-TOPO-1"]["signals"]), 1)


class TestIngestAndIsolation(IntegrationTestCase):
	def report(self, provider="t-topo-collector", tenant_name=None):
		return {
			"provider": provider,
			"tenant": tenant_name,
			"assets": [
				{"asset_id": "t-topo:host", "kind": "Host", "status": "OK"},
				{"asset_id": "t-topo:agent", "kind": "Agent", "status": "Running"},
			],
			"links": [{"from_asset": "t-topo:agent", "to_asset": "t-topo:host", "link_type": "Runs On"}],
		}

	def test_ingest_writes_and_owns(self):
		out = api.apply_report(self.report(), writable_tenants=None)
		self.assertEqual(out["inserted"], 3)
		self.assertTrue(frappe.db.get_value("Topology Asset", "t-topo:host", "managed"))
		other = api.apply_report(self.report(provider="t-topo-other"), writable_tenants=None)
		self.assertEqual(len(other["rejected"]), 2)
		self.assertEqual(other["skipped"], 1)  # the link the first provider owns
		self.assertEqual(
			frappe.db.get_value(
				"Topology Link", {"link_key": "t-topo:agent|Runs On|t-topo:host"}, "provider"
			),
			"t-topo-collector",
		)

	def test_reserved_provider_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			api.apply_report(self.report(provider="foames-mes"), writable_tenants=None)

	def test_ingest_needs_a_writer_role(self):
		make_user("t-topo-reader@example.com", "FoaMES Operator")
		with as_user("t-topo-reader@example.com"), self.assertRaises(frappe.PermissionError):
			api.ingest(report=self.report())

	def test_tenant_restricted_user_sees_only_their_tenant(self):
		make_asset("t-topo:a1", "Physical", "Machine", tenant=tenant("T-Topo A"))
		make_asset("t-topo:b1", "Physical", "Machine", tenant=tenant("T-Topo B"))
		make_asset("t-topo:shared", "Data", "Connector")
		user = make_user("t-topo-a@example.com", "FoaMES Operator")
		frappe.get_doc(
			{
				"doctype": "User Permission",
				"user": user.name,
				"allow": "Topology Tenant",
				"for_value": "T-Topo A",
			}
		).insert(ignore_permissions=True)
		with as_user(user.name):
			ids = {n["id"] for n in api.get_graph()["nodes"]}
		self.assertIn("t-topo:a1", ids)
		self.assertIn("t-topo:shared", ids)
		self.assertNotIn("t-topo:b1", ids)
