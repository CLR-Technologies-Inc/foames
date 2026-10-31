# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Tests for the Frappe-free process-mining core. Runs with plain unittest."""

import json
import unittest
from datetime import datetime, timedelta, timezone

from foames.foames_process_mining import conformance, discovery
from foames.foames_process_mining.eventlog import COMPLETE, START, Event, EventLog
from foames.foames_process_mining.ocel import from_ocel, to_ocel, to_ocel_json
from foames.foames_process_mining.xes import from_xes, to_xes

T0 = datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc)


def trace(case_id, steps, start=T0, gap_minutes=10, resource=None):
	events = []
	for index, activity in enumerate(steps):
		events.append(Event(case_id, activity, start + timedelta(minutes=gap_minutes * index), resource))
	return events


def sample_log():
	events = []
	events += trace("WO-1", ["Setup", "Run", "Inspect", "Pack"])
	events += trace("WO-2", ["Setup", "Run", "Inspect", "Pack"], start=T0 + timedelta(hours=1))
	events += trace(
		"WO-3", ["Setup", "Run", "Inspect", "Rework", "Inspect", "Pack"], start=T0 + timedelta(hours=2)
	)
	events += trace("WO-4", ["Setup", "Run", "Pack"], start=T0 + timedelta(hours=3), gap_minutes=30)
	return EventLog(events, name="sample")


class TestEventLog(unittest.TestCase):
	def test_events_are_sorted_and_grouped(self):
		late = Event("A", "x", T0 + timedelta(hours=1))
		early = Event("A", "y", T0)
		log = EventLog([late, early])
		self.assertEqual([e.activity for e in log], ["y", "x"])
		self.assertEqual(list(log.traces()), ["A"])

	def test_naive_and_aware_timestamps_sort_together(self):
		log = EventLog([Event("A", "x", datetime(2026, 1, 1, 12)), Event("A", "y", T0)])
		self.assertEqual(len(log), 2)

	def test_mixed_timezones_still_yield_durations(self):
		# A naive Frappe timestamp next to an aware imported one must not break the arithmetic.
		log = EventLog(
			[Event("A", "x", datetime(2026, 10, 20, 8, 0)), Event("A", "y", T0 + timedelta(minutes=5))]
		)
		dfg = discovery.discover_dfg(log)
		self.assertEqual(dfg.edge_stats(("x", "y"))["median_seconds"], 300)
		self.assertEqual(discovery.throughput(log)["max_seconds"], 300)

	def test_variants_count_cases(self):
		variants = sample_log().variants()
		self.assertEqual(variants[("Setup", "Run", "Inspect", "Pack")], ["WO-1", "WO-2"])
		self.assertEqual(len(variants), 3)

	def test_summary_and_round_trip_dicts(self):
		log = sample_log()
		summary = log.summary()
		self.assertEqual((summary["events"], summary["cases"], summary["variants"]), (17, 4, 3))
		again = EventLog.from_dicts(json.loads(json.dumps(log.to_dicts())))
		self.assertEqual(again.summary()["events"], 17)
		self.assertEqual(again.events[0].timestamp, log.events[0].timestamp)

	def test_rejects_empty_case_or_activity(self):
		with self.assertRaises(ValueError):
			Event("", "x", T0)
		with self.assertRaises(ValueError):
			Event("A", "", T0)


class TestXES(unittest.TestCase):
	def test_round_trip(self):
		log = sample_log()
		log.add(
			Event("WO-5", "Run", T0, "press-1", START, {"shift": "A", "count": 3}, {"machine": ["press-1"]})
		)
		xml = to_xes(log)
		self.assertIn('xes.version="1849-2016"', xml)
		self.assertIn("lifecycle:transition", xml)
		back = from_xes(xml)
		self.assertEqual(back.summary()["events"], 18)
		run = next(e for e in back if e.case_id == "WO-5")
		self.assertEqual((run.resource, run.lifecycle, run.attributes["shift"]), ("press-1", START, "A"))
		self.assertEqual(run.objects, {"machine": ["press-1"]})
		self.assertEqual(run.timestamp, T0)

	def test_attribute_types_and_object_ids_survive(self):
		event = Event(
			"c",
			"a",
			T0,
			attributes={"n": 3, "x": 1.5, "ok": True, "when": T0, "s": "t"},
			objects={"lot": ["Lot, 1"]},
		)
		back = from_xes(to_xes(EventLog([event]))).events[0]
		self.assertEqual(back.attributes, {"n": 3, "x": 1.5, "ok": True, "when": T0, "s": "t"})
		self.assertEqual(back.objects, {"lot": ["Lot, 1"]})

	def test_reads_logs_from_other_tools(self):
		xml = """<?xml version="1.0"?><log xes.version="1.0"><trace><string key="concept:name" value="c1"/>
		<event><string key="concept:name" value="a"/><date key="time:timestamp" value="2026-01-01T00:00:00.000+00:00"/></event>
		<event><string key="concept:name" value="b"/><date key="time:timestamp" value="2026-01-01T01:00:00.000+00:00"/></event>
		</trace></log>"""
		log = from_xes(xml)
		self.assertEqual(log.variants(), {("a", "b"): ["c1"]})


class TestOCEL(unittest.TestCase):
	def test_objects_and_round_trip(self):
		log = EventLog(
			[
				Event(
					"WO-1",
					"Run",
					T0,
					"press-1",
					COMPLETE,
					{"good": 10},
					{"machine": ["press-1"], "lot": ["L1", "L2"]},
				),
				Event("WO-1", "Pack", T0 + timedelta(hours=1), None, COMPLETE, {}, {"lot": ["L1"]}),
			]
		)
		ocel = to_ocel(log)
		self.assertEqual({t["name"] for t in ocel["objectTypes"]}, {"case", "machine", "lot"})
		self.assertEqual(len(ocel["objects"]), 4)
		self.assertEqual(len(ocel["events"][0]["relationships"]), 4)
		back = from_ocel(to_ocel_json(log))
		self.assertEqual(back.summary()["events"], 2)
		run = back.events[0]
		self.assertEqual((run.case_id, run.resource, run.attributes["good"]), ("WO-1", "press-1", 10))
		self.assertEqual(sorted(run.objects["lot"]), ["L1", "L2"])

	def test_object_ids_are_unique_across_types(self):
		# The work order is both the case and a work_order object: two objects, two ids.
		log = EventLog([Event("WO-1", "Run", T0, objects={"work_order": ["WO-1"], "lot": ["L1"]})])
		ocel = to_ocel(log)
		ids = [o["id"] for o in ocel["objects"]]
		self.assertEqual(len(ids), len(set(ids)))
		self.assertIn("work_order:WO-1", ids)
		back = from_ocel(ocel).events[0]
		self.assertEqual((back.case_id, back.objects["work_order"]), ("WO-1", ["WO-1"]))

	def test_flatten_on_another_object_type(self):
		log = EventLog([Event("WO-1", "Run", T0, objects={"lot": ["L1", "L2"]})])
		by_lot = from_ocel(to_ocel(log), case_object_type="lot")
		self.assertEqual(sorted(by_lot.case_ids()), ["L1", "L2"])


class TestDiscovery(unittest.TestCase):
	def test_dfg_counts_and_durations(self):
		dfg = discovery.discover_dfg(sample_log())
		self.assertEqual(dfg.cases, 4)
		self.assertEqual(dfg.edges[("Setup", "Run")], 4)
		self.assertEqual(dfg.edges[("Inspect", "Rework")], 1)
		self.assertEqual(dfg.start_activities, {"Setup": 4})
		self.assertEqual(dfg.end_activities, {"Pack": 4})
		stats = dfg.edge_stats(("Run", "Pack"))
		self.assertEqual((stats["count"], stats["median_seconds"]), (1, 1800))
		self.assertEqual(dfg.edge_stats(("Setup", "Run"))["median_seconds"], 600)

	def test_filter_and_dict_round_trip(self):
		dfg = discovery.discover_dfg(sample_log()).filter(min_edge_count=2)
		self.assertNotIn(("Inspect", "Rework"), dfg.edges)
		self.assertIn(("Setup", "Run"), dfg.edges)
		again = discovery.DirectlyFollowsGraph.from_dict(json.loads(json.dumps(dfg.to_dict())))
		self.assertEqual(again.edges, dfg.edges)
		self.assertEqual(again.start_activities, dfg.start_activities)

	def test_dot_output(self):
		dot = discovery.discover_dfg(sample_log()).to_dot()
		self.assertTrue(dot.startswith("digraph dfg {"))
		self.assertIn('"Setup" -> "Run" [label="4\\n10m 0s"]', dot)

	def test_variant_table_and_throughput(self):
		rows = discovery.variant_table(sample_log())
		self.assertEqual(rows[0]["cases"], 2)
		self.assertAlmostEqual(rows[0]["share"], 0.5)
		self.assertEqual(rows[0]["median_duration_seconds"], 1800)
		stats = discovery.throughput(sample_log())
		self.assertEqual(stats["cases"], 4)
		self.assertEqual(stats["max_seconds"], 3600)
		self.assertGreater(stats["cases_per_day"], 0)
		# One instant is no observed span, so no rate is invented from it.
		self.assertIsNone(discovery.throughput(EventLog([Event("c", "a", T0)]))["cases_per_day"])

	def test_service_and_waiting_times_from_lifecycle_pairs(self):
		events = [
			Event("c", "Setup", T0, lifecycle=START),
			Event("c", "Setup", T0 + timedelta(minutes=5), lifecycle=COMPLETE),
			Event("c", "Run", T0 + timedelta(minutes=15), lifecycle=START),
			Event("c", "Run", T0 + timedelta(minutes=45), lifecycle=COMPLETE),
		]
		stats = discovery.activity_durations(EventLog(events))
		self.assertEqual(stats["Setup"]["median_service_seconds"], 300)
		self.assertEqual(stats["Run"]["median_service_seconds"], 1800)
		self.assertEqual(stats["Run"]["median_waiting_seconds"], 600)
		self.assertEqual(discovery.bottlenecks(EventLog(events))[0]["activity"], "Run")

	def test_bottleneck_total_uses_waiting_samples_only(self):
		# Setup is first in two cases (no wait) and waits once in a third; total waiting is that one wait.
		events = []
		for case in ("a", "b"):
			events += [
				Event(case, "Setup", T0, lifecycle=START),
				Event(case, "Setup", T0 + timedelta(minutes=5)),
			]
		events += [
			Event("c", "Run", T0),
			Event("c", "Setup", T0 + timedelta(minutes=10), lifecycle=START),
			Event("c", "Setup", T0 + timedelta(minutes=15)),
		]
		stats = discovery.activity_durations(EventLog(events))
		self.assertEqual((stats["Setup"]["count"], stats["Setup"]["waiting_count"]), (3, 1))
		top = discovery.bottlenecks(EventLog(events))[0]
		self.assertEqual((top["activity"], top["total_waiting_seconds"], top["count"]), ("Setup", 600, 1))

	def test_rework_detects_repeats(self):
		self.assertEqual(discovery.rework(sample_log()), {"Inspect": 1})

	def test_format_duration(self):
		self.assertEqual(discovery.format_duration(59), "59s")
		self.assertEqual(discovery.format_duration(3661), "1h 1m")
		self.assertEqual(discovery.format_duration(90000), "1d 1h")


class TestConformance(unittest.TestCase):
	def test_sequence_model(self):
		model = conformance.model_from_sequence(["Setup", "Run", "Inspect", "Pack"])
		report = conformance.check_conformance(sample_log(), model)
		self.assertEqual((report.cases, report.conforming_cases), (4, 2))
		kinds = {d["kind"] for t in report.traces for d in t.deviations}
		self.assertEqual(kinds, {"unknown_activity", "disallowed_transition"})
		wo4 = next(t for t in report.traces if t.case_id == "WO-4")
		self.assertEqual(
			wo4.deviations, [{"kind": "disallowed_transition", "from": "Run", "to": "Pack", "position": 2}]
		)
		self.assertAlmostEqual(wo4.fitness, 0.75)
		self.assertLess(report.fitness, 1.0)
		data = report.to_dict()
		self.assertEqual(data["deviation_counts"], {"unknown_activity": 1, "disallowed_transition": 1})
		self.assertEqual(len(data["traces"]), 2)

	def test_model_from_golden_log_accepts_itself(self):
		log = sample_log()
		model = conformance.model_from_log(log)
		report = conformance.check_conformance(log, model)
		self.assertEqual(report.conforming_cases, 4)
		self.assertEqual(report.fitness, 1.0)

	def test_wrong_start_and_end(self):
		model = conformance.model_from_sequence(["a", "b"])
		log = EventLog(trace("x", ["b", "a"]))
		report = conformance.check_conformance(log, model)
		self.assertEqual(
			[d["kind"] for d in report.traces[0].deviations],
			["wrong_start", "disallowed_transition", "wrong_end"],
		)
		self.assertEqual(report.traces[0].fitness, 0.0)

	def test_footprint_relations(self):
		model = discovery.discover_dfg(sample_log())
		fp = conformance.footprint(model)
		self.assertEqual(fp["Setup"]["Run"], "->")
		self.assertEqual(fp["Run"]["Setup"], "<-")
		self.assertEqual(fp["Inspect"]["Rework"], "||")
		self.assertEqual(fp["Setup"]["Pack"], "#")

	def test_compare_footprints(self):
		reference = conformance.model_from_sequence(["Setup", "Run", "Inspect", "Pack"])
		observed = discovery.discover_dfg(sample_log())
		result = conformance.compare_footprints(reference, observed)
		self.assertEqual(result["new_in_observed"], ["Rework"])
		self.assertLess(result["score"], 1.0)
		self.assertTrue(any(d["from"] == "Run" and d["to"] == "Pack" for d in result["differences"]))
		self.assertEqual(conformance.compare_footprints(reference, reference)["score"], 1.0)


if __name__ == "__main__":
	unittest.main()
