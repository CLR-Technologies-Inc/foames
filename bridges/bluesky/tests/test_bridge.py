# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Tests for the Bluesky bridge. Standard library only; no Bluesky, Tiled or Frappe needed.

	cd bridges/bluesky && python -m unittest discover -s tests -v

The documents below follow the Bluesky event model (start, descriptor, event, event_page, stop).
When the FoaMES app is importable (run from the repository root with `PYTHONPATH=.:bridges/bluesky`)
the mapped events are also passed through FoaMES's own `normalise_event` and the signature is
checked against `foames.foames_mes.signing.verify`. When Bluesky is installed, a real RunEngine
run is mapped as well.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from foames_bluesky import (
	FoaMESCallback,
	MappingError,
	RunMapper,
	SendError,
	WebhookSender,
	jsonl_documents,
	map_documents,
	sign,
	tiled_documents,
	unpack_event_page,
)
from foames_bluesky.__main__ import main

RUN = "6b2c0a1e-0000-4000-8000-000000000001"
DESC = "6b2c0a1e-0000-4000-8000-0000000000d1"
BASE = "6b2c0a1e-0000-4000-8000-0000000000d2"
T0 = 1763136000.0


def documents(exit_status="success", page=False):
	start = {
		"uid": RUN,
		"time": T0,
		"scan_id": 42,
		"plan_name": "count",
		"beamline_id": "uvvis-1",
		"sample": "AuNR-batch-7",
		"proposal_id": "public-demo",
		"detectors": ["spec"],
	}
	descriptor = {
		"uid": DESC,
		"run_start": RUN,
		"time": T0 + 0.1,
		"name": "primary",
		"data_keys": {
			"lspr_nm": {"dtype": "number", "shape": [], "source": "PV:SPEC:LSPR", "units": "nm"},
			"ratio": {"dtype": "number", "shape": [], "source": "PV:SPEC:RATIO"},
			"frames": {"dtype": "integer", "shape": [], "source": "PV:SPEC:N"},
			"spectrum": {"dtype": "array", "shape": [1024], "source": "PV:SPEC:Y"},
			"image": {"dtype": "number", "shape": [], "source": "HDF5", "external": "STREAM:"},
			"label": {"dtype": "string", "shape": [], "source": "PV:SPEC:LABEL"},
			"shutter": {"dtype": "boolean", "shape": [], "source": "PV:SHUTTER"},
		},
		"object_keys": {"spec": ["lspr_nm", "ratio", "frames", "spectrum", "image", "label"]},
	}
	baseline = {
		"uid": BASE,
		"run_start": RUN,
		"time": T0 + 0.05,
		"name": "baseline",
		"data_keys": {"temp_c": {"dtype": "number", "shape": [], "source": "PV:T", "units": "degC"}},
	}
	rows = [
		{"lspr_nm": 780.0, "ratio": 3.9, "frames": 10, "label": "a", "shutter": True},
		{"lspr_nm": 782.0, "ratio": 4.0, "frames": 10, "label": "b", "shutter": True},
		{"lspr_nm": 784.0, "ratio": float("nan"), "frames": 10, "label": "c", "shutter": False},
	]
	docs = [("start", start), ("descriptor", baseline), ("descriptor", descriptor)]
	docs.append(
		(
			"event",
			{
				"uid": "base-ev-1",
				"descriptor": BASE,
				"seq_num": 1,
				"time": T0 + 0.2,
				"data": {"temp_c": 24.5},
				"timestamps": {"temp_c": T0 + 0.2},
			},
		)
	)
	events = [
		{
			"uid": f"ev-{i + 1}",
			"descriptor": DESC,
			"seq_num": i + 1,
			"time": T0 + 1 + i,
			"data": {**row, "spectrum": [0.0] * 4, "image": "datum-id"},
			"timestamps": {k: T0 + 1 + i for k in row},
			"filled": {"image": False},
		}
		for i, row in enumerate(rows)
	]
	if page:
		keys = events[0]["data"].keys()
		docs.append(
			(
				"event_page",
				{
					"descriptor": DESC,
					"uid": [e["uid"] for e in events],
					"seq_num": [e["seq_num"] for e in events],
					"time": [e["time"] for e in events],
					"data": {k: [e["data"][k] for e in events] for k in keys},
					"timestamps": {k: [e["timestamps"][k] for e in events] for k in events[0]["timestamps"]},
					"filled": {},
				},
			)
		)
	else:
		docs.extend(("event", e) for e in events)
	docs.append(
		(
			"stop",
			{
				"uid": "stop-1",
				"run_start": RUN,
				"time": T0 + 10,
				"exit_status": exit_status,
				"reason": "" if exit_status == "success" else "user abort",
				"num_events": {"primary": 3, "baseline": 1},
			},
		)
	)
	return docs


def measurements(events):
	return [e for e in events if e["type"] == "Measurement"]


class TestMapping(unittest.TestCase):
	def test_numeric_scalar_readings_of_the_primary_stream(self):
		events = map_documents(documents())
		names = [(e["name"], e["value"]) for e in measurements(events)]
		self.assertEqual(
			names,
			[
				("lspr_nm", 780.0),
				("ratio", 3.9),
				("frames", 10.0),
				("lspr_nm", 782.0),
				("ratio", 4.0),
				("frames", 10.0),
				("lspr_nm", 784.0),
				("frames", 10.0),
			],
			"arrays, external data, strings, booleans, NaN and the baseline stream are left out",
		)

	def test_machine_comes_from_the_start_document_or_the_caller(self):
		self.assertEqual({e["machine"] for e in map_documents(documents())}, {"uvvis-1"})
		self.assertEqual({e["machine"] for e in map_documents(documents(), machine="spec-2")}, {"spec-2"})

	def test_run_without_a_machine_is_skipped_and_reported(self):
		mapper = RunMapper(machine_keys=("foames_machine",))
		self.assertEqual(map_documents(documents(), mapper), [])
		self.assertEqual(len(mapper.skipped), 1)
		self.assertIn(RUN, mapper.skipped[0])

	def test_ids_are_unique_and_stable(self):
		first = [e["id"] for e in map_documents(documents(), summaries=("mean",))]
		second = [e["id"] for e in map_documents(documents(), summaries=("mean",))]
		self.assertEqual(first, second)
		self.assertEqual(len(first), len(set(first)))
		self.assertIn("bluesky:ev-1:lspr_nm", first)
		self.assertTrue(all(len(i) <= 140 for i in first), "Machine Event.event_key is a Data field")

	def test_provenance_and_timestamps(self):
		event = measurements(map_documents(documents()))[0]
		self.assertEqual(event["timestamp"], T0 + 1)
		p = event["provenance"]
		self.assertEqual(p["system"], "bluesky")
		self.assertEqual(p["run_uid"], RUN)
		self.assertEqual(p["scan_id"], 42)
		self.assertEqual(p["plan_name"], "count")
		self.assertEqual(p["sample"], "AuNR-batch-7")
		self.assertEqual(p["units"], "nm")
		self.assertEqual(p["source"], "PV:SPEC:LSPR")
		self.assertEqual(p["stream"], "primary")
		self.assertEqual(p["seq_num"], 1)
		self.assertEqual(p["event_uid"], "ev-1")

	def test_event_page_equals_events(self):
		self.assertEqual(
			map_documents(documents(page=True), summaries=("mean",)),
			map_documents(documents(), summaries=("mean",)),
		)

	def test_unpack_event_page(self):
		page = dict(documents(page=True))["event_page"]
		events = list(unpack_event_page(page))
		self.assertEqual([e["uid"] for e in events], ["ev-1", "ev-2", "ev-3"])
		self.assertEqual(events[1]["data"]["lspr_nm"], 782.0)

	def test_summaries_at_a_successful_stop(self):
		events = map_documents(
			documents(), readings=False, messages=False, summaries=("mean", "max", "count")
		)
		got = {e["name"]: e["value"] for e in events}
		self.assertEqual(
			got,
			{
				"lspr_nm.mean": 782.0,
				"lspr_nm.max": 784.0,
				"lspr_nm.count": 3.0,
				"ratio.mean": 3.95,
				"ratio.max": 4.0,
				"ratio.count": 2.0,
				"frames.mean": 10.0,
				"frames.max": 10.0,
				"frames.count": 3.0,
			},
		)
		self.assertTrue(all(e["timestamp"] == T0 + 10 for e in events))
		self.assertEqual(events[0]["id"], f"bluesky:{RUN}:lspr_nm:mean")

	def test_failed_run_gets_no_summaries_and_never_a_state(self):
		events = map_documents(documents("abort"), summaries=("mean",))
		self.assertFalse([e for e in events if e.get("name", "").endswith(".mean")])
		self.assertEqual({e["type"] for e in events}, {"Measurement", "Message"})
		self.assertEqual(events[-1]["text"], "Bluesky run ended (abort): user abort")
		self.assertEqual(events[-1]["provenance"]["exit_status"], "abort")

	def test_messages_for_start_and_stop(self):
		events = map_documents(documents())
		self.assertEqual(events[0]["text"], "Bluesky run started: count, scan 42")
		self.assertEqual(events[0]["id"], f"bluesky:{RUN}:start")
		self.assertEqual(events[-1]["text"], "Bluesky run ended (success)")

	def test_stream_field_and_prefix_options(self):
		events = map_documents(
			documents(), streams=None, fields=["temp_c", "lspr_nm"], prefix="uvvis.", messages=False
		)
		self.assertEqual(
			sorted({e["name"] for e in events}),
			["uvvis.lspr_nm", "uvvis.temp_c"],
		)

	def test_unknown_summary_is_refused(self):
		with self.assertRaises(MappingError):
			RunMapper(summaries=("median",))

	def test_resource_and_datum_documents_are_ignored(self):
		mapper = RunMapper("m")
		self.assertEqual(mapper("resource", {"uid": "r"}), [])
		self.assertEqual(mapper("datum", {"datum_id": "d"}), [])

	def test_interleaved_runs_stay_apart(self):
		a, b = documents(), documents()
		other = "6b2c0a1e-0000-4000-8000-000000000002"
		b = [
			(n, json.loads(json.dumps(d).replace(RUN, other).replace(DESC, "d-b").replace('"ev-', '"evb-')))
			for n, d in b
		]
		for _, d in b:
			if d.get("beamline_id"):
				d["beamline_id"] = "uvvis-2"
		mixed = [x for pair in zip(a, b, strict=False) for x in pair]
		events = map_documents(mixed, summaries=("count",))
		by_machine = {}
		for e in measurements(events):
			by_machine.setdefault(e["machine"], set()).add(e["provenance"]["run_uid"])
		self.assertEqual(by_machine, {"uvvis-1": {RUN}, "uvvis-2": {other}})


class FakeResponse(io.BytesIO):
	def __enter__(self):
		return self

	def __exit__(self, *exc):
		return False


class FakeOpener:
	def __init__(self, answers):
		self.answers = list(answers)
		self.requests = []

	def __call__(self, request, timeout=None):
		self.requests.append(request)
		answer = self.answers.pop(0)
		if isinstance(answer, Exception):
			raise answer
		return FakeResponse(json.dumps({"message": answer}).encode())


def ok(n):
	return {"accepted": [f"ME-{i}" for i in range(n)], "rejected": []}


class TestSender(unittest.TestCase):
	def test_signed_batches(self):
		opener = FakeOpener([ok(2), ok(1)])
		sender = WebhookSender(
			"https://foames.example.com/", "s3cret", batch_size=2, opener=opener, clock=lambda: 1763136000
		)
		events = [{"machine": "m", "type": "Message", "text": str(i), "id": str(i)} for i in range(3)]
		result = sender.send(events)
		self.assertEqual(len(result["accepted"]), 3)
		self.assertEqual(len(opener.requests), 2)
		request = opener.requests[0]
		self.assertEqual(
			request.full_url,
			"https://foames.example.com/api/method/foames.foames_mes.api.ingest_machine_events",
		)
		self.assertEqual(request.get_header("X-foames-timestamp"), "1763136000")
		self.assertEqual(request.get_header("X-foames-signature"), sign("s3cret", "1763136000", request.data))
		self.assertEqual(len(json.loads(request.data)["events"]), 2)

	def test_signature_matches_foames(self):
		try:
			from foames.foames_mes.signing import sign as foames_sign
			from foames.foames_mes.signing import verify
		except ImportError:
			self.skipTest("the FoaMES app is not on the path")
		body = b'{"events":[]}'
		self.assertEqual(sign("k", 100, body), foames_sign("k", 100, body))
		self.assertTrue(verify("k", 100, body, sign("k", 100, body), now=100))

	def test_retries_server_errors_then_succeeds(self):
		sleeps = []
		error = urllib.error.HTTPError("u", 503, "busy", {}, io.BytesIO(b"busy"))
		opener = FakeOpener([error, urllib.error.URLError("down"), ok(1)])
		sender = WebhookSender("https://f", "k", opener=opener, sleep=sleeps.append, backoff=0.5)
		self.assertEqual(len(sender.send([{"id": "1"}])["accepted"]), 1)
		self.assertEqual(sleeps, [0.5, 1.0])

	def test_client_error_raises_at_once(self):
		error = urllib.error.HTTPError("u", 401, "no", {}, io.BytesIO(b"Invalid or missing signature"))
		sender = WebhookSender("https://f", "k", opener=FakeOpener([error]), sleep=lambda s: None)
		with self.assertRaises(SendError) as caught:
			sender.send([{"id": "1"}])
		self.assertIn("401", str(caught.exception))

	def test_empty_secret_is_refused(self):
		with self.assertRaises(SendError):
			WebhookSender("https://f", "")


class FlakySender:
	def __init__(self, fail_times=0):
		self.fail_times = fail_times
		self.sent = []

	def send(self, events):
		if self.fail_times:
			self.fail_times -= 1
			raise SendError("down")
		self.sent.append(list(events))
		return {"accepted": [e["id"] for e in events], "rejected": [{"reason": "duplicate event id"}]}


class TestCallback(unittest.TestCase):
	def test_flushes_at_stop(self):
		sender = FlakySender()
		callback = FoaMESCallback(RunMapper(), sender)
		for name, doc in documents():
			callback(name, doc)
		self.assertEqual(len(sender.sent), 1)
		self.assertEqual(callback.pending, [])
		self.assertEqual(callback.rejected, [], "duplicates after a retry are not errors")

	def test_never_raises_and_keeps_events_for_the_next_flush(self):
		sender = FlakySender(fail_times=1)
		callback = FoaMESCallback(RunMapper(), sender)
		for name, doc in documents():
			callback(name, doc)
		self.assertTrue(callback.pending)
		callback("start", {"no": "uid"})  # a broken document is logged, not raised
		self.assertTrue(callback.flush())
		self.assertEqual(callback.pending, [])


class TestSources(unittest.TestCase):
	def test_jsonl_round_trip(self):
		with tempfile.TemporaryDirectory() as tmp:
			path = os.path.join(tmp, "run.jsonl")
			with open(path, "w", encoding="utf-8") as handle:
				for pair in documents():
					handle.write(json.dumps(list(pair)) + "\n\n")
			self.assertEqual(
				map_documents(jsonl_documents(path)),
				map_documents(json.loads(json.dumps(documents()))),
			)

	def test_tiled_runs_replay_their_documents(self):
		class Run:
			def documents(self):
				yield from documents()

		catalog = {RUN: Run()}
		events = map_documents(tiled_documents("unused", [RUN], client=catalog))
		self.assertEqual(len(measurements(events)), 8)

	def test_tiled_node_that_is_not_a_run(self):
		with self.assertRaises(RuntimeError):
			list(tiled_documents("unused", ["x"], client={"x": object()}))


class TestCommandLine(unittest.TestCase):
	def test_dry_run_prints_events(self):
		with tempfile.TemporaryDirectory() as tmp:
			path = os.path.join(tmp, "run.jsonl")
			with open(path, "w", encoding="utf-8") as handle:
				handle.writelines(json.dumps(list(p)) + "\n" for p in documents())
			out = io.StringIO()
			with redirect_stdout(out):
				code = main(
					["jsonl", path, "--summary", "mean", "--no-readings", "--no-messages", "--dry-run"]
				)
			self.assertEqual(code, 0)
			names = [e["name"] for e in json.loads(out.getvalue())]
			self.assertEqual(names, ["lspr_nm.mean", "ratio.mean", "frames.mean"])


class TestFoaMESAcceptsTheEvents(unittest.TestCase):
	def test_every_event_passes_normalise_event(self):
		try:
			from foames.foames_mes.gateway.mapping import normalise_event
		except ImportError:
			self.skipTest("the FoaMES app is not on the path")
		for raw in map_documents(documents(), summaries=("mean",)):
			event = normalise_event(raw)
			self.assertEqual(event["source_id"], "uvvis-1")
			self.assertEqual(event["event_key"], raw["id"])
			if event["event_type"] == "Measurement":
				self.assertEqual(event["measurement_name"], raw["name"])
				self.assertEqual(event["payload"]["provenance"]["run_uid"], RUN)


class TestRealRunEngine(unittest.TestCase):
	def test_a_bluesky_count_plan(self):
		try:
			from bluesky import RunEngine
			from bluesky.plans import count
			from ophyd.sim import det
		except ImportError:
			self.skipTest("bluesky and ophyd are not installed")
		collected = []
		RE = RunEngine({})
		RE.subscribe(lambda name, doc: collected.append((name, doc)))
		RE(count([det], num=3), beamline_id="sim-1")
		events = map_documents(collected, summaries=("mean",))
		self.assertEqual(len([e for e in events if e.get("name") == "det"]), 3)
		self.assertEqual(len([e for e in events if e.get("name") == "det.mean"]), 1)


if __name__ == "__main__":
	unittest.main()
