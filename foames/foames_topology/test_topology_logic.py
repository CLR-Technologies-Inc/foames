# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""The topology graph, its checks, lineage, layout, exports and the collector report rules.
No Frappe site needed."""

import json
import os
import unittest
from datetime import datetime, timedelta

from foames.foames_topology import graph as topo
from foames.foames_topology import ingest, model

NOW = datetime(2026, 11, 15, 12, 0, 0)
HERE = os.path.dirname(__file__)


def asset(
	asset_id, layer, kind, parent=None, status="OK", last_seen=None, tenant="Plant A", provider="test", **kw
):
	return {
		"asset_id": asset_id,
		"title": kw.pop("title", asset_id),
		"layer": layer,
		"kind": kind,
		"parent_asset": parent,
		"status": status,
		"last_seen": last_seen,
		"tenant": tenant,
		"provider": provider,
		**kw,
	}


def link(a, link_type, b, tenant="Plant A"):
	return {"from_asset": a, "to_asset": b, "link_type": link_type, "tenant": tenant, "provider": "test"}


def bind(signal, physical, direction="Read", tag=None, **kw):
	return {
		"signal": signal,
		"physical_asset": physical,
		"direction": direction,
		"tag": tag,
		"tenant": "Plant A",
		**kw,
	}


def plant():
	"""A line with a reactor that has a temperature transmitter on it, and the data path from that
	transmitter through OPC UA to the reactor's events, its OEE and the ERP job card."""
	fresh = NOW - timedelta(seconds=30)
	old = NOW - timedelta(hours=2)
	assets = [
		asset("line:L1", "Physical", "Line"),
		asset("machine:R-101", "Physical", "Machine", parent="line:L1", status="Running", last_seen=fresh),
		asset("pid:TT-101", "Physical", "Instrument", parent="machine:R-101"),
		asset("pid:PT-102", "Physical", "Instrument", parent="machine:R-101"),
		asset("machine:P-201", "Physical", "Machine", parent="line:L1", status="Down"),
		asset("signal:TT-101", "Data", "Signal", last_seen=fresh),
		asset("signal:PT-102", "Data", "Signal", last_seen=old),
		asset("connector:opc-ua", "Data", "Connector", tenant=None),
		asset("events:R-101", "Data", "Event Stream", last_seen=fresh),
		asset("kpi:oee:R-101", "Data", "KPI", last_seen=fresh),
		asset("erp:JC-1", "Data", "ERP Record"),
	]
	links = [
		link("signal:TT-101", "Data Flow", "connector:opc-ua"),
		link("signal:PT-102", "Data Flow", "connector:opc-ua"),
		link("connector:opc-ua", "Data Flow", "events:R-101"),
		link("events:R-101", "Derives", "kpi:oee:R-101"),
		link("events:R-101", "Posts To", "erp:JC-1"),
		link("pid:TT-101", "Wiring", "pid:PT-102"),
	]
	bindings = [
		bind("signal:TT-101", "pid:TT-101", tag="TT-101", unit="degC", last_value=71.5),
		bind("signal:PT-102", "pid:PT-102", tag="PT-102", unit="bar"),
	]
	return assets, links, bindings


def build(**kw):
	assets, links, bindings = plant()
	return topo.build_graph(assets, links, bindings, now=NOW, stale_after_seconds=900, **kw)


class TestVocabulary(unittest.TestCase):
	def test_doctype_options_match_the_model(self):
		def options(doctype, field):
			folder = doctype.lower().replace(" ", "_")
			with open(os.path.join(HERE, "doctype", folder, folder + ".json")) as f:
				meta = json.load(f)
			return [
				o
				for o in next(x for x in meta["fields"] if x["fieldname"] == field)["options"].split("\n")
				if o
			]

		self.assertEqual(options("Topology Asset", "layer"), list(model.LAYERS))
		self.assertEqual(options("Topology Asset", "kind"), list(model.KINDS))
		self.assertEqual(options("Topology Asset", "status"), list(model.STATUSES))
		self.assertEqual(
			options("Topology Link", "link_type"), [t for t in model.LINK_TYPES if t != "Contains"]
		)
		self.assertEqual(options("Topology Link", "layer"), list(model.EDGE_LAYERS))
		self.assertEqual(options("Signal Binding", "direction"), list(model.DIRECTIONS))

	def test_every_kind_has_one_layer(self):
		self.assertFalse(set(model.PHYSICAL_KINDS) & set(model.DATA_KINDS))
		self.assertEqual(model.kind_layer("Instrument"), "Physical")
		self.assertEqual(model.kind_layer("KPI"), "Data")
		self.assertIsNone(model.kind_layer("Other"))


class TestBuild(unittest.TestCase):
	def test_containment_becomes_contains_edges(self):
		g = build()
		contains = {(e["source"], e["target"]) for e in g.edges if e["type"] == "Contains"}
		self.assertIn(("line:L1", "machine:R-101"), contains)
		self.assertIn(("machine:R-101", "pid:TT-101"), contains)

	def test_bindings_are_binding_layer_edges(self):
		g = build()
		edge = next(e for e in g.edges if e["source"] == "signal:TT-101" and e["target"] == "pid:TT-101")
		self.assertEqual(edge["type"], "Measured At")
		self.assertEqual(edge["layer"], "Binding")
		self.assertEqual(edge["tag"], "TT-101")

	def test_write_binding_is_acts_on(self):
		assets, links, bindings = plant()
		bindings.append(bind("signal:TT-101", "machine:P-201", "Write"))
		g = topo.build_graph(assets, links, bindings, now=NOW)
		self.assertIn("Acts On", {e["type"] for e in g.edges})

	def test_data_health(self):
		g = build()
		self.assertEqual(g.nodes["signal:TT-101"]["health"], "fresh")
		self.assertEqual(g.nodes["signal:PT-102"]["health"], "stale")
		self.assertEqual(g.nodes["erp:JC-1"]["health"], "no data")

	def test_only_streaming_kinds_go_stale(self):
		old = NOW - timedelta(days=1)
		g = topo.build_graph(
			[
				asset("k", "Data", "KPI", last_seen=old),
				asset("t", "Data", "Agent Task", status="Down", last_seen=old),
			],
			[],
			[],
			now=NOW,
		)
		self.assertEqual(g.nodes["k"]["health"], "fresh")
		self.assertEqual(g.nodes["t"]["health"], "fault")

	def test_physical_health_is_the_worst_bound_signal(self):
		g = build()
		self.assertEqual(g.nodes["pid:TT-101"]["health"], "fresh")
		self.assertEqual(g.nodes["pid:PT-102"]["health"], "stale")
		self.assertIsNone(g.nodes["machine:P-201"]["health"])
		self.assertEqual(g.nodes["pid:TT-101"]["signal_count"], 1)

	def test_binding_threshold_overrides_default(self):
		assets, links, bindings = plant()
		bindings[1]["stale_after_seconds"] = 3 * 3600
		g = topo.build_graph(assets, links, bindings, now=NOW, stale_after_seconds=900)
		self.assertEqual(g.nodes["signal:PT-102"]["health"], "fresh")

	def test_binding_reading_time_refreshes_signal(self):
		assets, links, bindings = plant()
		bindings[1]["last_value_at"] = (NOW - timedelta(seconds=5)).strftime("%Y-%m-%d %H:%M:%S")
		g = topo.build_graph(assets, links, bindings, now=NOW)
		self.assertEqual(g.nodes["signal:PT-102"]["health"], "fresh")

	def test_string_times_are_parsed(self):
		g = topo.build_graph(
			[asset("s", "Data", "Signal", last_seen="2026-11-15T11:59:00Z")], [], [], now=NOW
		)
		self.assertEqual(g.nodes["s"]["health"], "fresh")

	def test_disabled_assets_drop_off(self):
		assets, links, bindings = plant()
		assets[3]["disabled"] = 1  # PT-102 retired
		g = topo.build_graph(assets, links, bindings, now=NOW)
		self.assertNotIn("pid:PT-102", g.nodes)
		self.assertIn(
			"pid:PT-102", topo.build_graph(assets, links, bindings, now=NOW, include_disabled=True).nodes
		)


class TestFilter(unittest.TestCase):
	def test_tenant_filter_keeps_shared_infrastructure(self):
		assets, links, bindings = plant()
		assets.append(asset("machine:X", "Physical", "Machine", tenant="Plant B"))
		g = topo.filter_graph(topo.build_graph(assets, links, bindings, now=NOW), tenants=["Plant A"])
		self.assertNotIn("machine:X", g.nodes)
		self.assertIn("connector:opc-ua", g.nodes)  # no tenant: shared

	def test_combined_view_reads_every_tenant(self):
		assets, links, bindings = plant()
		assets.append(asset("machine:X", "Physical", "Machine", tenant="Plant B"))
		g = topo.filter_graph(topo.build_graph(assets, links, bindings, now=NOW))
		self.assertIn("machine:X", g.nodes)

	def test_layer_filter(self):
		g = topo.filter_graph(build(), layers=["Physical"])
		self.assertEqual({n["layer"] for n in g.nodes.values()}, {"Physical"})
		self.assertFalse([e for e in g.edges if e["layer"] == "Binding"])

	def test_provider_filter(self):
		assets, links, bindings = plant()
		assets[0]["provider"] = "other-plugin"
		g = topo.filter_graph(topo.build_graph(assets, links, bindings, now=NOW), providers=["other-plugin"])
		self.assertEqual(list(g.nodes), ["line:L1"])


class TestFindings(unittest.TestCase):
	def rules(self, g):
		return {(f["rule"], f["asset"]) for f in topo.findings(g)}

	def test_unbound_and_stale(self):
		rules = self.rules(build())
		self.assertIn(("unbound", "machine:P-201"), rules)
		self.assertIn(("stale", "signal:PT-102"), rules)
		self.assertNotIn(("unbound", "pid:TT-101"), rules)
		# A line is not expected to carry signals of its own.
		self.assertNotIn(("unbound", "line:L1"), rules)

	def test_binding_to_retired_equipment_is_drift(self):
		assets, links, bindings = plant()
		assets[3]["disabled"] = 1
		rules = self.rules(topo.build_graph(assets, links, bindings, now=NOW))
		self.assertIn(("dangling", "signal:PT-102"), rules)

	def test_cross_tenant_link_is_critical(self):
		assets, links, bindings = plant()
		assets.append(asset("machine:X", "Physical", "Machine", tenant="Plant B"))
		links.append(link("pid:TT-101", "Wiring", "machine:X"))
		found = topo.findings(topo.build_graph(assets, links, bindings, now=NOW))
		self.assertEqual(found[0]["rule"], "cross-tenant")
		self.assertEqual(found[0]["severity"], "Critical")

	def test_write_binding_is_reported(self):
		assets, links, bindings = plant()
		bindings.append(bind("signal:TT-101", "machine:P-201", "Write"))
		self.assertIn(
			("write-binding", "machine:P-201"), self.rules(topo.build_graph(assets, links, bindings, now=NOW))
		)


class TestTrace(unittest.TestCase):
	def test_machine_downstream_reaches_kpi_and_erp(self):
		t = topo.trace(build(), "machine:R-101", "downstream")
		for node in (
			"pid:TT-101",
			"signal:TT-101",
			"connector:opc-ua",
			"events:R-101",
			"kpi:oee:R-101",
			"erp:JC-1",
		):
			self.assertIn(node, t["nodes"])
		self.assertNotIn("machine:P-201", t["nodes"])
		self.assertEqual(t["depth"]["machine:R-101"], 0)

	def test_kpi_upstream_reaches_the_instruments(self):
		t = topo.trace(build(), "kpi:oee:R-101", "upstream")
		self.assertIn("pid:TT-101", t["nodes"])
		self.assertIn("pid:PT-102", t["nodes"])
		self.assertNotIn("erp:JC-1", t["nodes"])

	def test_host_downstream_reaches_its_agents(self):
		assets = [
			asset("host:h", "Physical", "Host"),
			asset("agent:a", "Data", "Agent"),
			asset("task:t", "Data", "Agent Task"),
		]
		links = [link("agent:a", "Runs On", "host:h"), link("agent:a", "Delegates", "task:t")]
		t = topo.trace(topo.build_graph(assets, links, [], now=NOW), "host:h")
		self.assertEqual(t["nodes"], ["host:h", "agent:a", "task:t"])

	def test_cycle_terminates(self):
		assets, links, bindings = plant()
		links.append(link("kpi:oee:R-101", "Data Flow", "events:R-101"))
		t = topo.trace(topo.build_graph(assets, links, bindings, now=NOW), "events:R-101")
		self.assertEqual(len(t["nodes"]), len(set(t["nodes"])))

	def test_unknown_start(self):
		with self.assertRaises(KeyError):
			topo.trace(build(), "nope")
		with self.assertRaises(ValueError):
			topo.trace(build(), "erp:JC-1", "sideways")


class TestLayout(unittest.TestCase):
	def test_data_layer_sits_above_physical(self):
		g = build()
		pos = topo.layout(g)
		self.assertEqual(set(pos), set(g.nodes))
		top_physical = min(pos[k]["y"] for k, n in g.nodes.items() if n["layer"] == "Physical")
		low_data = max(pos[k]["y"] for k, n in g.nodes.items() if n["layer"] == "Data")
		self.assertLess(low_data, top_physical)

	def test_signal_is_over_its_instrument(self):
		pos = topo.layout(build())
		self.assertAlmostEqual(pos["signal:TT-101"]["x"], pos["pid:TT-101"]["x"], delta=topo.COLUMN)

	def test_downstream_is_higher(self):
		pos = topo.layout(build())
		self.assertLess(pos["kpi:oee:R-101"]["y"], pos["events:R-101"]["y"])
		self.assertLess(pos["events:R-101"]["y"], pos["signal:TT-101"]["y"])

	def test_deterministic_and_cycle_safe(self):
		assets, links, bindings = plant()
		assets[0]["parent_asset"] = "machine:R-101"  # line inside its own machine: a loop
		g = topo.build_graph(assets, links, bindings, now=NOW)
		self.assertEqual(topo.layout(g), topo.layout(g))


class TestExports(unittest.TestCase):
	def test_mermaid(self):
		text = topo.to_mermaid(build())
		self.assertTrue(text.startswith("flowchart TB\n"))
		self.assertIn('subgraph DATA["Data layer"]', text)
		self.assertIn('subgraph PHYSICAL["Physical layer"]', text)
		self.assertIn("-.->|measured at TT-101|", text)
		self.assertIn(":::datastale", text)
		self.assertIn(":::down", text)  # P-201
		self.assertEqual(text, topo.to_mermaid(build()))

	def test_mermaid_escapes_quotes(self):
		g = topo.build_graph([asset("a", "Physical", "Machine", title='Press "big"')], [], [], now=NOW)
		self.assertIn("#quot;big#quot;", topo.to_mermaid(g))

	def test_grafana_fields(self):
		out = topo.to_grafana(build())
		node = next(n for n in out["nodes"] if n["id"] == "signal:PT-102")
		self.assertEqual(node["secondarystat"], "stale")
		self.assertEqual(node["color"], model.HEALTH_COLORS["stale"])
		for field in ("id", "title", "subtitle", "mainstat", "detail__tenant"):
			self.assertIn(field, node)
		binding = next(e for e in out["edges"] if e["mainstat"] == "Measured At")
		self.assertEqual(binding["strokeDasharray"], "4 3")
		ids = {n["id"] for n in out["nodes"]}
		self.assertTrue(all(e["source"] in ids and e["target"] in ids for e in out["edges"]))

	def test_overlay(self):
		over = topo.overlay(build(), {"pid:TT-101", "machine:P-201"})
		self.assertEqual(set(over), {"pid:TT-101", "machine:P-201"})
		signal = over["pid:TT-101"]["signals"][0]
		self.assertEqual(signal["value"], 71.5)
		self.assertEqual(signal["unit"], "degC")
		self.assertEqual(signal["feeds"], ["connector:opc-ua"])
		self.assertEqual(over["machine:P-201"]["signals"], [])

	def test_graph_dict(self):
		out = topo.graph_dict(build())
		self.assertEqual(out["tenants"], ["Plant A"])
		self.assertIn("layout", out)
		self.assertIn("findings", out)
		json.dumps(out, default=str)


class TestIngest(unittest.TestCase):
	def report(self, **kw):
		r = {
			"provider": "network-collector",
			"tenant": "Plant A",
			"assets": [
				{"asset_id": "host:gw1", "kind": "Host", "status": "OK"},
				{"asset_id": "agent:planner", "kind": "Agent", "status": "Running"},
			],
			"links": [{"from_asset": "agent:planner", "to_asset": "host:gw1", "link_type": "Runs On"}],
			"bindings": [],
		}
		r.update(kw)
		return r

	def test_clean_report(self):
		out = ingest.normalize_report(self.report(), {})
		self.assertEqual(len(out["assets"]), 2)
		self.assertEqual({a["layer"] for a in out["assets"]}, {"Physical", "Data"})
		self.assertEqual(out["links"][0]["link_key"], "agent:planner|Runs On|host:gw1")
		self.assertFalse(out["rejected"])

	def test_provider_is_stamped(self):
		r = self.report()
		r["assets"][0]["provider"] = "someone-else"
		out = ingest.normalize_report(r, {})
		self.assertEqual({a["provider"] for a in out["assets"]}, {"network-collector"})

	def test_reserved_provider(self):
		with self.assertRaises(ingest.ReportError):
			ingest.normalize_report(self.report(provider="foames-mes"), {})
		with self.assertRaises(ingest.ReportError):
			ingest.normalize_report(self.report(provider=""), {})

	def test_cannot_touch_another_providers_asset(self):
		existing = {"host:gw1": {"provider": "other", "tenant": "Plant A", "managed": 1, "layer": "Physical"}}
		out = ingest.normalize_report(self.report(), existing)
		self.assertEqual([r["id"] for r in out["rejected"]], ["host:gw1"])
		# The link to it still goes through: linking to an asset is not changing it.
		self.assertEqual(len(out["links"]), 1)

	def test_cannot_touch_hand_made_asset(self):
		existing = {"host:gw1": {"provider": "network-collector", "tenant": "Plant A", "managed": 0}}
		out = ingest.normalize_report(self.report(), existing)
		self.assertIn("by hand", out["rejected"][0]["reason"])

	def test_tenant_rules(self):
		existing = {
			"host:gw1": {
				"provider": "network-collector",
				"tenant": "Plant B",
				"managed": 1,
				"layer": "Physical",
			}
		}
		out = ingest.normalize_report(self.report(), existing)
		reasons = [r["reason"] for r in out["rejected"]]
		self.assertTrue(any("tenant Plant B" in r for r in reasons))
		self.assertTrue(any("joins tenant" in r for r in reasons))  # the link across tenants

		out = ingest.normalize_report(self.report(), {}, writable_tenants={"Plant B"})
		self.assertEqual(len(out["rejected"]), 3)

	def test_binding_layers(self):
		r = self.report(
			bindings=[
				{"signal": "host:gw1", "physical_asset": "agent:planner"},
				{"signal": "agent:planner", "physical_asset": "host:gw1", "direction": "Sideways"},
			]
		)
		out = ingest.normalize_report(r, {})
		self.assertEqual(len(out["rejected"]), 2)

	def test_unknown_ends_and_bad_items(self):
		r = self.report(
			links=[
				{"from_asset": "agent:planner", "to_asset": "host:missing", "link_type": "Runs On"},
				{"from_asset": "agent:planner", "to_asset": "host:gw1", "link_type": "Contains"},
			],
		)
		r["assets"].append({"asset_id": "", "kind": "Host"})
		r["assets"].append({"asset_id": "x", "layer": "Business"})
		out = ingest.normalize_report(r, {})
		self.assertEqual(len(out["rejected"]), 4)

	def test_unknown_kind_becomes_other_and_needs_layer(self):
		out = ingest.normalize_report(
			self.report(assets=[{"asset_id": "x", "kind": "Spaceship", "layer": "Data"}], links=[]), {}
		)
		self.assertEqual(out["assets"][0]["kind"], "Other")

	def test_size_limit(self):
		r = self.report(assets=[{"asset_id": f"a{i}", "kind": "Host"} for i in range(ingest.MAX_ITEMS + 1)])
		with self.assertRaises(ingest.ReportError):
			ingest.normalize_report(r, {})


if __name__ == "__main__":
	unittest.main()
