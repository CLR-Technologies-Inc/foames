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

"""Tests for the historian bridge. Standard library only; no historian, driver or Frappe needed.

	cd bridges/historian && python -m unittest discover -s tests -v

PI Web API, InfluxDB and the Ignition WebDev endpoint are stood in for by a fake HTTP opener that
answers with the JSON those servers publish in their documentation. The Ignition SQL historian
and the generic SQL source run against real tables in an in-memory sqlite3 database, laid out as
Ignition documents them. When the FoaMES app is importable (run from the repository root with
`PYTHONPATH=.:bridges/historian`), every mapped event is also passed through FoaMES's own
`normalise_event`.
"""

from __future__ import annotations

import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
from contextlib import redirect_stderr
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from foames_historian import (
	Checkpoint,
	HistorianError,
	IgnitionSQLSource,
	IgnitionWebDevSource,
	InfluxQLSource,
	MappingError,
	PIWebAPISource,
	Sample,
	SampleMapper,
	SQLSource,
	TagMapping,
	aggregate,
	from_dict,
	load_tag_map,
	parse_duration,
	parse_time,
	sync_once,
)
from foames_historian.__main__ import main
from foames_historian.http import HttpClient
from foames_historian.model import epoch_ms, floor_time, iso, opc_quality
from foames_historian.sources.influx import build_query, parse_tag
from foames_historian.sources.sql import Placeholders, ident
from foames_historian.sync import window_for

UTC = timezone.utc
T0 = datetime(2026, 11, 14, 10, 0, tzinfo=UTC)


def at(minutes=0, seconds=0):
	return T0 + timedelta(minutes=minutes, seconds=seconds)


# fakes


class FakeResponse(io.BytesIO):
	def __enter__(self):
		return self

	def __exit__(self, *exc):
		return False


class FakeHTTP:
	"""Answers GETs from a function of (path, query dict); records every request."""

	def __init__(self, answer):
		self.answer = answer
		self.requests = []

	def __call__(self, request, timeout=None):
		self.requests.append(request)
		parsed = urllib.parse.urlparse(request.full_url)
		query = dict(urllib.parse.parse_qsl(parsed.query))
		result = self.answer(parsed.path, query)
		if isinstance(result, Exception):
			raise result
		return FakeResponse(json.dumps(result).encode())


def http(answer, base="https://hist.example.com/api"):
	fake = FakeHTTP(answer)
	return HttpClient(base, opener=fake), fake


# model


class ModelTests(unittest.TestCase):
	def test_parse_time_forms(self):
		self.assertEqual(parse_time("2026-11-14T10:00:00Z"), T0)
		self.assertEqual(parse_time("2026-11-14T10:00:00"), T0)  # naive is UTC
		self.assertEqual(parse_time("2026-11-14T11:00:00+01:00"), T0)
		self.assertEqual(parse_time(T0.timestamp()), T0)
		self.assertEqual(parse_time(str(T0.timestamp())), T0)
		self.assertEqual(parse_time("now-90m", now=at(90)), T0)
		self.assertEqual(parse_time("now", now=T0), T0)
		with self.assertRaises(ValueError):
			parse_time("yesterday")

	def test_parse_time_reads_any_fraction_length(self):
		# PI writes seven digits; Python 3.10 reads only three or six.
		self.assertEqual(parse_time("2026-11-14T10:00:00.1234567Z"), T0 + timedelta(microseconds=123456))
		self.assertEqual(parse_time("2026-11-14T10:00:00.5Z"), T0 + timedelta(milliseconds=500))

	def test_durations(self):
		self.assertEqual(parse_duration("500ms"), timedelta(milliseconds=500))
		self.assertEqual(parse_duration("5m"), timedelta(minutes=5))
		self.assertEqual(parse_duration("1d"), timedelta(days=1))
		self.assertEqual(parse_duration(30), timedelta(seconds=30))
		for bad in ("0s", "5 parsecs", "", -1):
			with self.assertRaises(ValueError):
				parse_duration(bad)

	def test_epoch_ms_is_exact(self):
		moment = T0 + timedelta(microseconds=999)
		self.assertEqual(epoch_ms(moment), epoch_ms(T0))
		self.assertEqual(iso(T0 + timedelta(milliseconds=7)), "2026-11-14T10:00:00.007Z")

	def test_floor_time(self):
		self.assertEqual(floor_time(at(7, 30), timedelta(minutes=5)), at(5))
		self.assertEqual(floor_time(at(5), timedelta(minutes=5)), at(5))

	def test_opc_quality(self):
		self.assertEqual(opc_quality(192), "good")
		self.assertEqual(opc_quality(216), "good")
		self.assertEqual(opc_quality(64), "uncertain")
		self.assertEqual(opc_quality(0), "bad")
		self.assertEqual(opc_quality(None), "good")
		self.assertEqual(opc_quality("x"), "bad")

	def test_aggregate_buckets_good_numbers_only(self):
		samples = [
			Sample("t", at(0, 10), 1.0),
			Sample("t", at(0, 50), 3.0),
			Sample("t", at(1, 0), 10.0, quality="uncertain"),
			Sample("t", at(1, 30), 99.0, quality="bad"),
			Sample("t", at(1, 40), "text"),
			Sample("t", at(3, 0), 7.0),
		]
		out = aggregate(samples, at(0), at(4), timedelta(minutes=1), "mean")
		self.assertEqual(
			[(s.timestamp, s.value, s.quality) for s in out],
			[
				(at(0), 2.0, "good"),
				(at(1), 10.0, "uncertain"),
				(at(3), 7.0, "good"),  # minute 2 had nothing: no value is invented
			],
		)
		self.assertEqual(out[0].extra, {"aggregate": "mean", "samples": 2})
		self.assertEqual(
			[s.value for s in aggregate(samples, at(0), at(4), timedelta(minutes=4), "count")], [4.0]
		)
		self.assertEqual(
			[s.value for s in aggregate(samples, at(0), at(4), timedelta(minutes=4), "last")], [7.0]
		)
		with self.assertRaises(ValueError):
			aggregate(samples, at(0), at(4), timedelta(minutes=1), "median")


# PI Web API


def pi_answer(recorded=None, summary=None, page_size=None):
	def answer(path, query):
		if path.endswith("/points"):
			if query["path"] == "\\\\PI01\\Missing":
				return urllib.error.HTTPError(
					path, 404, "Not Found", {}, io.BytesIO(b'{"Errors":["not found"]}')
				)
			return {"WebId": "P1AbC", "Name": "P1.Temp"}
		if path.endswith("/attributes"):
			return {"WebId": "A1xYz", "Name": "Temperature"}
		if path.endswith("/recorded"):
			items = [i for i in recorded if parse_time(i["Timestamp"]) >= parse_time(query["startTime"])]
			items = [i for i in items if parse_time(i["Timestamp"]) < parse_time(query["endTime"])]
			return {"Items": items[: int(query["maxCount"])], "Links": {}}
		if path.endswith("/summary"):
			return {"Items": summary}
		raise AssertionError(path)

	return answer


class PIWebAPITests(unittest.TestCase):
	def test_recorded_values_and_quality(self):
		recorded = [
			{"Timestamp": "2026-11-14T10:00:00Z", "Value": 71.5, "Good": True, "UnitsAbbreviation": "°C"},
			{"Timestamp": "2026-11-14T10:01:00.1234567Z", "Value": 72.0, "Good": True, "Questionable": True},
			{
				"Timestamp": "2026-11-14T10:02:00Z",
				"Value": {"Name": "Running", "Value": 1, "IsSystem": False},
				"Good": True,
			},
			{
				"Timestamp": "2026-11-14T10:03:00Z",
				"Value": {"Name": "Shutdown", "Value": 248, "IsSystem": True},
				"Good": False,
			},
			{"Timestamp": "2026-11-14T10:04:00Z", "Value": 73.0, "Good": True, "Substituted": True},
		]
		client, fake = http(pi_answer(recorded), "https://pi.example.com/piwebapi")
		source = PIWebAPISource("pi-main", client)
		samples = source.read("\\\\PI01\\P1.Temp", at(0), at(10))
		self.assertEqual([s.value for s in samples], [71.5, 72.0, "Running", "Shutdown", 73.0])
		self.assertEqual([s.quality for s in samples], ["good", "uncertain", "good", "bad", "good"])
		self.assertEqual(samples[0].units, "°C")
		self.assertEqual(samples[2].extra, {"digital_code": 1})
		self.assertTrue(samples[4].extra["substituted"])
		points = urllib.parse.urlparse(fake.requests[0].full_url)
		self.assertEqual(points.path, "/piwebapi/points")
		self.assertIn("/piwebapi/streams/P1AbC/recorded", fake.requests[1].full_url)
		# the WebId is cached
		source.read("\\\\PI01\\P1.Temp", at(0), at(10))
		self.assertEqual(sum("/points" in r.full_url for r in fake.requests), 1)
		# every request is a GET
		self.assertEqual({r.get_method() for r in fake.requests}, {"GET"})

	def test_af_attributes_and_webids(self):
		client, fake = http(pi_answer([]), "https://pi.example.com/piwebapi")
		source = PIWebAPISource("pi", client)
		self.assertEqual(source.web_id("\\\\AF01\\Plant\\Line1\\Press1|Temperature"), "A1xYz")
		self.assertEqual(source.web_id("webid:F1DPxyz"), "F1DPxyz")
		self.assertIn("/attributes", fake.requests[0].full_url)
		self.assertEqual(len(fake.requests), 1)

	def test_paging_does_not_repeat_or_lose_values_at_the_boundary(self):
		recorded = [{"Timestamp": iso(at(0, i)), "Value": float(i), "Good": True} for i in range(7)]
		# two values share the instant where a page ends
		recorded.insert(3, {"Timestamp": iso(at(0, 2)), "Value": 2.5, "Good": True})
		client, fake = http(pi_answer(recorded), "https://pi.example.com/piwebapi")
		samples = PIWebAPISource("pi", client, max_count=3).read("\\\\PI01\\P1.Temp", at(0), at(1))
		self.assertEqual([s.value for s in samples], [0.0, 1.0, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0])
		self.assertGreater(len(fake.requests), 3)

	def test_summary(self):
		summary = [
			{"Type": "Average", "Value": {"Timestamp": "2026-11-14T10:00:00Z", "Value": 71.9, "Good": True}},
			{"Type": "Average", "Value": {"Timestamp": "2026-11-14T10:05:00Z", "Value": 72.4, "Good": True}},
		]
		client, fake = http(pi_answer([], summary), "https://pi.example.com/piwebapi")
		samples = PIWebAPISource("pi", client).read(
			"\\\\PI01\\P1.Temp", at(0), at(10), interval=timedelta(minutes=5), aggregate="mean"
		)
		self.assertEqual([(s.timestamp, s.value) for s in samples], [(at(0), 71.9), (at(5), 72.4)])
		query = dict(urllib.parse.parse_qsl(urllib.parse.urlparse(fake.requests[-1].full_url).query))
		self.assertEqual(query["summaryType"], "Average")
		self.assertEqual(query["summaryDuration"], "300s")
		self.assertEqual(query["calculationBasis"], "TimeWeighted")

	def test_count_uses_event_weighting_and_first_falls_back_to_raw(self):
		recorded = [{"Timestamp": iso(at(m)), "Value": float(m), "Good": True} for m in range(4)]
		summary = [{"Type": "Count", "Value": {"Timestamp": iso(at(0)), "Value": 4, "Good": True}}]
		client, fake = http(pi_answer(recorded, summary), "https://pi.example.com/piwebapi")
		source = PIWebAPISource("pi", client)
		source.read("\\\\PI01\\P1.Temp", at(0), at(4), interval=timedelta(minutes=4), aggregate="count")
		self.assertIn("calculationBasis=EventWeighted", fake.requests[-1].full_url)
		first = source.read(
			"\\\\PI01\\P1.Temp", at(0), at(4), interval=timedelta(minutes=2), aggregate="first"
		)
		self.assertEqual([s.value for s in first], [0.0, 2.0])
		self.assertIn("/recorded", fake.requests[-1].full_url)

	def test_errors(self):
		client, _ = http(pi_answer([]), "https://pi.example.com/piwebapi")
		with self.assertRaises(HistorianError) as caught:
			PIWebAPISource("pi", client).read("\\\\PI01\\Missing", at(0), at(1))
		self.assertIn("404", str(caught.exception))
		client, _ = http(lambda p, q: {"WebId": "X"} if p.endswith("/points") else {"Errors": ["bad time"]})
		with self.assertRaises(HistorianError):
			PIWebAPISource("pi", client).read("\\\\PI01\\P1", at(0), at(1))


# InfluxDB


class InfluxTests(unittest.TestCase):
	def test_tag_syntax(self):
		self.assertEqual(
			parse_tag("machine_data/temp?line=L1&machine=press-1"),
			("machine_data", "temp", {"line": "L1", "machine": "press-1"}),
		)
		self.assertEqual(parse_tag("a/b/c"), ("a/b", "c", {}))
		with self.assertRaises(HistorianError):
			parse_tag("no-field")

	def test_query_quotes_everything(self):
		query = build_query("m\"x/f?k=v' OR 1=1", at(0), at(1), retention_policy="autogen")
		self.assertEqual(
			query,
			'SELECT "f" FROM "autogen"."m\\"x" WHERE time >= \'2026-11-14T10:00:00.000Z\' '
			"AND time < '2026-11-14T10:01:00.000Z' AND \"k\" = 'v\\' OR 1=1' ORDER BY time ASC",
		)
		grouped = build_query("m/f", at(0), at(10), function="MEAN", interval=timedelta(minutes=1))
		self.assertIn('SELECT MEAN("f") FROM "m"', grouped)
		self.assertIn("GROUP BY time(60000ms) fill(none)", grouped)

	def test_reads_series(self):
		t0 = epoch_ms(at(0))

		def answer(path, query):
			self.assertEqual(path, "/query")
			self.assertEqual(query["db"], "plant")
			self.assertEqual(query["epoch"], "ms")
			self.assertTrue(query["q"].startswith("SELECT"))
			return {
				"results": [
					{
						"statement_id": 0,
						"series": [
							{
								"name": "m",
								"columns": ["time", "f"],
								"values": [[t0, 1.5], [t0 + 1000, None], [t0 + 2000, True]],
							}
						],
					}
				]
			}

		client, fake = http(answer, "http://influx:8086")
		samples = InfluxQLSource("influx", client, database="plant").read("m/f", at(0), at(1))
		self.assertEqual([(s.timestamp, s.value) for s in samples], [(at(0), 1.5), (at(0, 2), 1.0)])
		self.assertEqual(fake.requests[0].get_method(), "GET")

	def test_errors_are_reported(self):
		client, _ = http(
			lambda p, q: {"results": [{"statement_id": 0, "error": "database not found: plant"}]}
		)
		with self.assertRaises(HistorianError) as caught:
			InfluxQLSource("influx", client, database="plant").read("m/f", at(0), at(1))
		self.assertIn("database not found", str(caught.exception))
		with self.assertRaises(HistorianError):
			InfluxQLSource("influx", client, database="")


# Ignition


def ignition_db():
	"""An in-memory Ignition SQL historian: one gateway, two providers, two monthly partitions."""
	db = sqlite3.connect(":memory:")
	db.executescript(
		"""
		CREATE TABLE sqlth_drv (id INTEGER, name TEXT, provider TEXT);
		CREATE TABLE sqlth_scinfo (id INTEGER, scname TEXT, drvid INTEGER);
		CREATE TABLE sqlth_te (id INTEGER, tagpath TEXT, scid INTEGER, datatype INTEGER, querymode INTEGER, created INTEGER, retired INTEGER);
		CREATE TABLE sqlth_partitions (pname TEXT, drvid INTEGER, start_time INTEGER, end_time INTEGER, blocksize INTEGER, flags INTEGER);
		CREATE TABLE sqlt_data_1_2026_10 (tagid INTEGER, intvalue INTEGER, floatvalue REAL, stringvalue TEXT, datevalue INTEGER, dataintegrity INTEGER, t_stamp INTEGER);
		CREATE TABLE sqlt_data_1_2026_11 (tagid INTEGER, intvalue INTEGER, floatvalue REAL, stringvalue TEXT, datevalue INTEGER, dataintegrity INTEGER, t_stamp INTEGER);
		CREATE TABLE sqlt_data_2_2026_11 (tagid INTEGER, intvalue INTEGER, floatvalue REAL, stringvalue TEXT, datevalue INTEGER, dataintegrity INTEGER, t_stamp INTEGER);
		"""
	)
	nov = epoch_ms(datetime(2026, 11, 1, tzinfo=UTC))
	oct_ = epoch_ms(datetime(2026, 10, 1, tzinfo=UTC))
	dec = epoch_ms(datetime(2026, 12, 1, tzinfo=UTC))
	db.executemany(
		"INSERT INTO sqlth_drv VALUES (?,?,?)", [(1, "plant-gw", "default"), (2, "plant-gw", "edge")]
	)
	db.executemany("INSERT INTO sqlth_scinfo VALUES (?,?,?)", [(1, "_exempt_", 1), (2, "_exempt_", 2)])
	db.executemany(
		"INSERT INTO sqlth_te VALUES (?,?,?,?,?,?,?)",
		[
			# the Good counter was retired at the month boundary and re-created with a new id
			(10, "line1/press1/good", 1, 0, 0, oct_, nov),
			(11, "line1/press1/good", 1, 0, 0, nov, None),
			(12, "line1/press1/temp", 1, 1, 0, oct_, None),
			(13, "line1/press1/state", 1, 2, 0, oct_, None),
			(14, "line1/press1/temp", 2, 1, 0, oct_, None),  # same path, other provider
		],
	)
	db.executemany(
		"INSERT INTO sqlth_partitions VALUES (?,?,?,?,?,?)",
		[
			("sqlt_data_1_2026_10", 1, oct_, nov, 0, 0),
			("sqlt_data_1_2026_11", 1, nov, dec, 0, 0),
			("sqlt_data_2_2026_11", 2, nov, dec, 0, 0),
		],
	)
	last_oct = nov - 60_000
	db.executemany(
		"INSERT INTO sqlt_data_1_2026_10 VALUES (?,?,?,?,?,?,?)",
		[(10, 1000, None, None, None, 192, last_oct)],
	)
	t = epoch_ms(T0)
	db.executemany(
		"INSERT INTO sqlt_data_1_2026_11 VALUES (?,?,?,?,?,?,?)",
		[
			(11, 1005, None, None, None, 192, nov + 60_000),
			(11, 1200, None, None, None, 192, t),
			(12, None, 71.5, None, None, 192, t),
			(12, None, 72.5, None, None, 64, t + 60_000),
			(12, None, None, None, None, 0, t + 120_000),
			(13, None, None, "Running", None, 192, t),
		],
	)
	db.execute("INSERT INTO sqlt_data_2_2026_11 VALUES (14, NULL, 20.0, NULL, NULL, 192, ?)", (t,))
	db.commit()
	return db


class IgnitionSQLTests(unittest.TestCase):
	def setUp(self):
		self.db = ignition_db()
		self.source = IgnitionSQLSource("ign", lambda: self.db, paramstyle="qmark")

	def test_reads_values_by_datatype_with_quality(self):
		temp = self.source.read("[default]Line1/Press1/Temp", at(0), at(10))
		self.assertEqual(
			[(s.value, s.quality) for s in temp], [(71.5, "good"), (72.5, "uncertain"), (None, "bad")]
		)
		state = self.source.read("[default]Line1/Press1/State", at(0), at(10))
		self.assertEqual([s.value for s in state], ["Running"])

	def test_provider_selects_the_tag_and_no_provider_reads_all(self):
		edge = self.source.read("[edge]Line1/Press1/Temp", at(0), at(1))
		self.assertEqual([s.value for s in edge], [20.0])
		# Ignition stores paths in lower case; the lookup is case-insensitive
		self.assertEqual(
			sorted(s.value for s in self.source.read("LINE1/PRESS1/TEMP", at(0), at(1))), [20.0, 71.5]
		)

	def test_spans_partitions_and_retired_ids(self):
		start = datetime(2026, 10, 31, 23, 0, tzinfo=UTC)
		good = self.source.read("[default]Line1/Press1/Good", start, at(1))
		self.assertEqual([s.value for s in good], [1000.0, 1005.0, 1200.0])

	def test_unknown_tag_and_odd_partition_names(self):
		with self.assertRaises(HistorianError):
			self.source.read("[default]Nope", at(0), at(1))
		self.db.execute(
			"UPDATE sqlth_partitions SET pname = 'x; DROP TABLE sqlth_te' WHERE pname = 'sqlt_data_1_2026_11'"
		)
		with self.assertRaises(HistorianError) as caught:
			self.source.read("[default]Line1/Press1/Temp", at(0), at(1))
		self.assertIn("unusual name", str(caught.exception))

	def test_gateway_filter(self):
		source = IgnitionSQLSource("ign", lambda: self.db, paramstyle="qmark", gateway="other-gw")
		with self.assertRaises(HistorianError):
			source.read("[default]Line1/Press1/Temp", at(0), at(1))

	def test_client_side_aggregate(self):
		out = self.source.read(
			"[default]Line1/Press1/Temp", at(0), at(10), interval=timedelta(minutes=10), aggregate="mean"
		)
		self.assertEqual([(s.timestamp, s.value, s.quality) for s in out], [(at(0), 72.0, "uncertain")])


class IgnitionWebDevTests(unittest.TestCase):
	def test_reads_and_aggregates(self):
		t = epoch_ms(T0)

		def answer(path, query):
			self.assertEqual(path, "/system/webdev/foames/history")
			self.assertEqual(query["path"], "[default]Line1/Press1/Temp")
			if "aggregate" in query:
				self.assertEqual(query["aggregate"], "SimpleAverage")
				self.assertEqual(query["intervalMs"], "60000")
				return [{"t": t, "v": 72.0, "q": 192}]
			return [
				{"t": t, "v": 71.5, "q": 192},
				{"t": t + 1000, "v": None, "q": 0},
				{"t": t + 2000, "v": 1, "q": 64},
			]

		client, _ = http(answer, "https://gw:8043/system/webdev/foames/history")
		source = IgnitionWebDevSource("ign", client)
		raw = source.read("[default]Line1/Press1/Temp", at(0), at(1))
		self.assertEqual(
			[(s.value, s.quality) for s in raw], [(71.5, "good"), (None, "bad"), (1.0, "uncertain")]
		)
		agg = source.read(
			"[default]Line1/Press1/Temp", at(0), at(1), interval=timedelta(minutes=1), aggregate="mean"
		)
		self.assertEqual([s.value for s in agg], [72.0])

	def test_refusal(self):
		client, _ = http(lambda p, q: {"error": "no such tag"}, "https://gw/system/webdev/foames/history")
		with self.assertRaises(HistorianError):
			IgnitionWebDevSource("ign", client).read("x", at(0), at(1))


# generic SQL and TimescaleDB


class SQLTests(unittest.TestCase):
	def test_identifiers_and_placeholders(self):
		self.assertEqual(ident("history.tag_values"), "history.tag_values")
		for bad in ("t; drop table x", "a.b.c", "", "1abc", None):
			with self.assertRaises(HistorianError):
				ident(bad)
		p = Placeholders("named")
		self.assertEqual((p(1), p(2)), (":p1", ":p2"))
		self.assertEqual(p.params, {"p1": 1, "p2": 2})
		with self.assertRaises(HistorianError):
			Placeholders("weird")

	def test_narrow_table_with_epoch_ms(self):
		db = sqlite3.connect(":memory:")
		db.execute("CREATE TABLE hist (ts INTEGER, tagname TEXT, val REAL, q INTEGER)")
		t = epoch_ms(T0)
		db.executemany(
			"INSERT INTO hist VALUES (?,?,?,?)",
			[
				(t, "P1.Temp", 71.0, 192),
				(t + 1000, "P1.Temp", 73.0, 0),
				(t + 2000, "P1.Temp", 75.0, 192),
				(t, "Other", 1.0, 192),
			],
		)
		source = SQLSource(
			"sql",
			lambda: db,
			table="hist",
			time_column="ts",
			tag_column="tagname",
			value_column="val",
			quality_column="q",
			time_type="epoch_ms",
			paramstyle="qmark",
		)
		samples = source.read("P1.Temp", at(0), at(1))
		self.assertEqual(
			[(s.value, s.quality) for s in samples], [(71.0, "good"), (73.0, "bad"), (75.0, "good")]
		)
		out = source.read("P1.Temp", at(0), at(1), interval=timedelta(minutes=1), aggregate="max")
		self.assertEqual([s.value for s in out], [75.0])  # the bad 73 does not count, 75 does

	def test_iso_text_times(self):
		db = sqlite3.connect(":memory:")
		db.execute("CREATE TABLE hist (time TEXT, tag TEXT, value REAL)")
		db.executemany(
			"INSERT INTO hist VALUES (?,?,?)",
			[("2026-11-14T10:00:00.000Z", "a", 1.0), ("2026-11-14T10:00:30.000Z", "a", 2.0)],
		)
		source = SQLSource("sql", lambda: db, table="hist", time_type="iso", paramstyle="qmark")
		self.assertEqual([s.value for s in source.read("a", at(0), at(0, 30))], [1.0])

	def test_timescale_builds_time_bucket(self):
		seen = {}

		class Cursor:
			def execute(self, sql, params):
				seen["sql"], seen["params"] = sql, params

			def fetchall(self):
				return [(T0, 71.75), (at(1), None)]

			def close(self):
				pass

		class Connection:
			def cursor(self):
				return Cursor()

			def close(self):
				seen["closed"] = True

		source = SQLSource("tsdb", Connection, table="metrics", dialect="timescale")
		with source:
			out = source.read("P1.Temp", at(0), at(2), interval=timedelta(minutes=1), aggregate="last")
		self.assertEqual([(s.timestamp, s.value) for s in out], [(T0, 71.75)])
		self.assertIn(
			"time_bucket(make_interval(secs => %s), time, TIMESTAMPTZ '1970-01-01 00:00:00+00')", seen["sql"]
		)
		self.assertIn("last(value, time)", seen["sql"])
		self.assertEqual(seen["params"], (60.0, "P1.Temp", at(0), at(2)))
		self.assertTrue(seen["closed"])
		with self.assertRaises(HistorianError):
			SQLSource("tsdb", Connection, table="metrics", dialect="timescale", time_type="epoch_ms")

	def test_connection_failure_is_a_historian_error(self):
		def refuse():
			raise OSError("connection refused")

		with self.assertRaises(HistorianError):
			SQLSource("sql", refuse, table="hist").read("a", at(0), at(1))


# mapping


class MappingTests(unittest.TestCase):
	def mapper(self):
		return SampleMapper("pi-main", "pi")

	def test_measurement_event(self):
		m = TagMapping.from_dict({"tag": "\\\\PI01\\P1.Temp", "machine": "press-1", "name": "temperature"})
		event = self.mapper().event(m, Sample(m.tag, at(0), 71.5, units="°C"))
		self.assertEqual(event["machine"], "press-1")
		self.assertEqual(event["type"], "Measurement")
		self.assertEqual((event["name"], event["value"]), ("temperature", 71.5))
		self.assertEqual(event["timestamp"], "2026-11-14T10:00:00.000Z")
		self.assertTrue(event["id"].startswith("hist:pi-main:"))
		self.assertLessEqual(len(event["id"]), 140)
		self.assertEqual(event["provenance"]["tag"], m.tag)
		self.assertEqual(event["provenance"]["units"], "°C")

	def test_default_names(self):
		self.assertEqual(
			TagMapping.from_dict({"tag": "[default]L1/P1/Temp", "machine": "m"}).measurement_name, "Temp"
		)
		self.assertEqual(
			TagMapping.from_dict({"tag": "\\\\PI\\P1.Temp", "machine": "m"}).measurement_name, "Temp"
		)
		agg = TagMapping.from_dict({"tag": "m/f?x=1", "machine": "m", "interval": "1m"})
		self.assertEqual((agg.measurement_name, agg.aggregate), ("f.mean", "mean"))

	def test_count_scaled_and_never_aggregated(self):
		m = TagMapping.from_dict(
			{"tag": "t", "machine": "m", "type": "Count", "counter": "energy_kwh", "scale": 0.001}
		)
		event = self.mapper().event(m, Sample("t", at(0), 48213600.0))
		self.assertEqual((event["counter"], event["value"]), ("energy_kwh", 48213.6))
		self.assertEqual(event["provenance"]["raw_value"], 48213600.0)
		with self.assertRaises(MappingError):
			TagMapping.from_dict(
				{"tag": "t", "machine": "m", "type": "Count", "counter": "good", "interval": "1m"}
			)
		with self.assertRaises(MappingError):
			TagMapping.from_dict({"tag": "t", "machine": "m", "type": "Count"})

	def test_state_from_map_or_text_never_guessed(self):
		mapper = self.mapper()
		mapped = TagMapping.from_dict(
			{
				"tag": "s",
				"machine": "m",
				"type": "State",
				"states": {"0": "Down", "1": "Running", "2.5": "Setup"},
			}
		)
		self.assertEqual(mapper.event(mapped, Sample("s", at(0), 1.0))["state"], "Running")
		self.assertEqual(mapper.event(mapped, Sample("s", at(0), "0"))["state"], "Down")
		self.assertEqual(mapper.event(mapped, Sample("s", at(0), 2.5))["state"], "Setup")
		self.assertIsNone(mapper.event(mapped, Sample("s", at(0), 7.0)))
		text = TagMapping.from_dict({"tag": "s", "machine": "m", "type": "State"})
		self.assertEqual(mapper.event(text, Sample("s", at(0), "Running"))["state"], "Running")
		self.assertIsNone(mapper.event(text, Sample("s", at(0), 1.0)))
		self.assertEqual(len(mapper.skipped), 2)

	def test_quality_rules(self):
		mapper = self.mapper()
		m = TagMapping.from_dict({"tag": "t", "machine": "m"})
		self.assertIsNone(mapper.event(m, Sample("t", at(0), 1.0, quality="bad")))
		self.assertEqual(
			mapper.event(m, Sample("t", at(0), 1.0, quality="uncertain"))["provenance"]["quality"],
			"uncertain",
		)
		strict = TagMapping.from_dict({"tag": "t", "machine": "m", "uncertain": False})
		self.assertIsNone(mapper.event(strict, Sample("t", at(0), 1.0, quality="uncertain")))
		self.assertIsNone(mapper.event(m, Sample("t", at(0), "text")))

	def test_message(self):
		m = TagMapping.from_dict({"tag": "t", "machine": "m", "type": "Message"})
		self.assertEqual(self.mapper().event(m, Sample("t", at(0), 3.0))["text"], "3")
		self.assertEqual(
			self.mapper().event(m, Sample("t", at(0), "Batch B-17 started"))["text"], "Batch B-17 started"
		)

	def test_ids_are_stable_and_distinct(self):
		a = TagMapping.from_dict({"tag": "t", "machine": "m1"})
		b = TagMapping.from_dict({"tag": "t", "machine": "m2"})
		c = TagMapping.from_dict({"tag": "t", "machine": "m1", "interval": "1m"})
		sample = Sample("t", at(0), 1.0)
		ids = [self.mapper().event(m, sample)["id"] for m in (a, b, c)]
		self.assertEqual(len(set(ids)), 3)
		self.assertEqual(self.mapper().event(a, sample)["id"], ids[0])
		# sub-millisecond PI timestamps stay distinct
		self.assertNotEqual(
			self.mapper().event(a, Sample("t", at(0) + timedelta(microseconds=100), 1.0))["id"], ids[0]
		)

	def test_tag_map_validation(self):
		for bad in (
			[],
			[{"tag": "t"}],
			[{"tag": "t", "machine": "m", "type": "Alarmz"}],
			[{"tag": "t", "machine": "m", "aggregate": "mean"}],
			[{"tag": "t", "machine": "m", "interval": "1m", "aggregate": "median"}],
			[{"tag": "t", "machine": "m", "colour": "red"}],
			[{"tag": "t", "machine": "m"}, {"tag": "t", "machine": "m"}],
		):
			with self.assertRaises((MappingError, ValueError)):
				load_tag_map(bad)
		with self.assertRaises(MappingError):
			SampleMapper("has space")

	def test_events_pass_foames_normalise_event(self):
		try:
			from foames.foames_mes.gateway.mapping import normalise_event
		except ImportError:
			self.skipTest("the FoaMES app is not on the path")
		mapper = self.mapper()
		cases = [
			({"tag": "t", "machine": "m", "name": "temp"}, Sample("t", at(0), 1.5)),
			({"tag": "t", "machine": "m", "type": "Count", "counter": "good"}, Sample("t", at(0), 120.0)),
			(
				{"tag": "t", "machine": "m", "type": "State", "states": {"1": "Running"}},
				Sample("t", at(0), 1.0),
			),
			({"tag": "t", "machine": "m", "type": "Message"}, Sample("t", at(0), "hello")),
		]
		for entry, sample in cases:
			raw = mapper.event(TagMapping.from_dict(entry), sample)
			event = normalise_event(raw)
			self.assertEqual(event["source_id"], "m")
			self.assertEqual(event["event_key"], raw["id"])
			self.assertEqual(event["timestamp"], datetime(2026, 11, 14, 10, 0))


# sync


class FakeSource:
	"""A source whose history is a dict of tag -> [Sample]; records each window read."""

	kind = "fake"

	def __init__(self, history, name="fake", fail=()):
		self.history = history
		self.name = name
		self.fail = set(fail)
		self.windows = []

	def read(self, tag, start, end, *, interval=None, aggregate=None):
		self.windows.append((tag, start, end))
		if tag in self.fail:
			raise HistorianError("tag not found")
		samples = [s for s in self.history.get(tag, []) if start <= s.timestamp < end]
		if interval is not None:
			from foames_historian.model import aggregate as bucket

			return bucket(samples, start, end, interval, aggregate or "mean")
		return samples

	def close(self):
		pass


class FakeSender:
	def __init__(self, reject=None, fail=False):
		self.batches = []
		self.reject = reject or (lambda e: None)
		self.fail = fail

	def __call__(self, events):
		from foames_historian.sender import SendError

		if self.fail:
			raise SendError("cannot reach FoaMES")
		self.batches.append(events)
		answer = {"accepted": [], "rejected": []}
		for e in events:
			reason = self.reject(e)
			if reason:
				answer["rejected"].append({"reason": reason, "event": e})
			else:
				answer["accepted"].append(e["id"])
		return answer


class SyncTests(unittest.TestCase):
	def setUp(self):
		self.history = {
			"temp": [Sample("temp", at(m), 70.0 + m) for m in range(0, 60)],
			"good": [Sample("good", at(m), 1000.0 + 10 * m) for m in range(0, 60, 5)],
		}
		self.mappings = load_tag_map(
			[
				{"tag": "temp", "machine": "press-1", "name": "temperature"},
				{"tag": "good", "machine": "press-1", "type": "Count", "counter": "good"},
			]
		)
		self.tmp = tempfile.TemporaryDirectory()
		self.path = os.path.join(self.tmp.name, "checkpoint.json")

	def tearDown(self):
		self.tmp.cleanup()

	def test_window_rules(self):
		raw, agg = TagMapping("t", "m"), TagMapping.from_dict({"tag": "t", "machine": "m", "interval": "5m"})
		opts = {"lag": timedelta(minutes=2), "initial": timedelta(hours=1), "max_window": timedelta(days=1)}
		self.assertEqual(window_for(raw, None, now=at(62), **opts), (at(0), at(60), True))
		self.assertEqual(window_for(agg, at(3), now=at(29), **opts), (at(0), at(25), True))
		self.assertIsNone(window_for(agg, at(25), now=at(29), **opts))
		short = dict(opts, max_window=timedelta(minutes=12))
		self.assertEqual(window_for(agg, at(0), now=at(62), **short), (at(0), at(10), False))

	def test_incremental_passes_post_each_value_once_in_order(self):
		source, send = FakeSource(self.history), FakeSender()
		result, _ = sync_once(
			source,
			self.mappings,
			send,
			Checkpoint(self.path),
			now=at(32),
			lag=timedelta(minutes=2),
			initial=timedelta(minutes=30),
		)
		self.assertTrue(result.ok)
		self.assertEqual(result.read, 30 + 6)
		stamps = [e["timestamp"] for e in send.batches[0]]
		self.assertEqual(stamps, sorted(stamps))
		# the checkpoint survives a restart: the next pass starts where this one ended
		result, _ = sync_once(
			source, self.mappings, send, Checkpoint(self.path), now=at(42), lag=timedelta(minutes=2)
		)
		self.assertEqual(result.read, 10 + 2)
		ids = [e["id"] for batch in send.batches for e in batch]
		self.assertEqual(len(ids), len(set(ids)))
		with open(self.path) as f:
			saved = json.load(f)["tags"]
		self.assertEqual({v["until"] for v in saved.values()}, {"2026-11-14T10:40:00.000Z"})

	def test_nothing_new_posts_nothing(self):
		source, send = FakeSource(self.history), FakeSender()
		sync_once(source, self.mappings, send, Checkpoint(self.path), now=at(32))
		result, _ = sync_once(source, self.mappings, send, Checkpoint(self.path), now=at(32))
		self.assertEqual((result.read, result.events, len(send.batches)), (0, 0, 1))

	def test_send_failure_keeps_the_checkpoint(self):
		from foames_historian.sender import SendError

		with self.assertRaises(SendError):
			sync_once(
				FakeSource(self.history),
				self.mappings,
				FakeSender(fail=True),
				Checkpoint(self.path),
				now=at(32),
			)
		self.assertFalse(os.path.exists(self.path))

	def test_one_failing_tag_does_not_stop_the_others(self):
		source, send = FakeSource(self.history, fail={"good"}), FakeSender()
		result, _ = sync_once(source, self.mappings, send, Checkpoint(self.path), now=at(32))
		self.assertFalse(result.ok)
		self.assertEqual(len(result.errors), 1)
		checkpoint = Checkpoint(self.path)
		self.assertIsNotNone(checkpoint.get(self.mappings[0]))
		self.assertIsNone(checkpoint.get(self.mappings[1]))

	def test_duplicates_are_fine_other_rejections_are_reported(self):
		def reject(event):
			return "duplicate event id" if event["type"] == "Count" else "unknown machine press-1"

		result, _ = sync_once(
			FakeSource(self.history), self.mappings, FakeSender(reject), Checkpoint(self.path), now=at(32)
		)
		self.assertEqual(result.duplicates, 6)
		self.assertEqual(len(result.rejected), 30)
		self.assertFalse(result.ok)

	def test_replay_leaves_the_checkpoint_alone(self):
		send = FakeSender()
		result, _ = sync_once(
			FakeSource(self.history), self.mappings, send, Checkpoint(self.path), start=at(10), end=at(20)
		)
		self.assertEqual(result.read, 10 + 2)
		self.assertFalse(os.path.exists(self.path))

	def test_aggregates_post_only_whole_buckets(self):
		mappings = load_tag_map(
			[{"tag": "temp", "machine": "press-1", "name": "temp.mean_10m", "interval": "10m"}]
		)
		send = FakeSender()
		sync_once(
			FakeSource(self.history),
			mappings,
			send,
			Checkpoint(self.path),
			now=at(37),
			lag=timedelta(minutes=2),
			initial=timedelta(minutes=30),
		)
		self.assertEqual(
			[(e["timestamp"], e["value"]) for e in send.batches[0]],
			[
				("2026-11-14T10:00:00.000Z", 74.5),
				("2026-11-14T10:10:00.000Z", 84.5),
				("2026-11-14T10:20:00.000Z", 94.5),
			],
		)
		self.assertTrue(all(e["id"].endswith(":mean") for e in send.batches[0]))

	def test_catching_up_in_steps(self):
		send = FakeSender()
		result, _ = sync_once(
			FakeSource(self.history),
			self.mappings,
			send,
			Checkpoint(self.path),
			now=at(62),
			lag=timedelta(0),
			initial=timedelta(hours=1),
			max_window=timedelta(minutes=20),
		)
		self.assertFalse(result.caught_up)
		self.assertEqual(Checkpoint(self.path).get(self.mappings[0]), at(22))


# configuration and command line


class ConfigTests(unittest.TestCase):
	def test_secrets_only_from_the_environment(self):
		spec = {
			"type": "pi",
			"url": "https://pi/piwebapi",
			"auth": "basic",
			"username": "svc",
			"password": "x",
		}
		with self.assertRaises(HistorianError):
			from_dict({"source": spec, "tags": [{"tag": "t", "machine": "m"}]})
		del spec["password"]
		with self.assertRaises(HistorianError):
			from_dict({"source": spec, "tags": [{"tag": "t", "machine": "m"}]}, env={})
		source, _ = from_dict(
			{"source": spec, "tags": [{"tag": "t", "machine": "m"}]}, env={"FOAMES_HISTORIAN_PASSWORD": "pw"}
		)
		self.assertTrue(source.http.headers["Authorization"].startswith("Basic "))
		with self.assertRaises(HistorianError):
			from_dict(
				{
					"source": {
						"type": "sql",
						"driver": "sqlite3",
						"table": "t",
						"connect": {"password": "x"},
					},
					"tags": [{"tag": "t", "machine": "m"}],
				}
			)

	def test_influx_token(self):
		spec = {
			"type": "influxdb",
			"name": "influx",
			"url": "http://influx:8086",
			"database": "plant",
			"auth": "token",
		}
		source, _ = from_dict(
			{"source": spec, "tags": [{"tag": "m/f", "machine": "m"}]}, env={"FOAMES_HISTORIAN_TOKEN": "tok"}
		)
		self.assertEqual(source.http.headers["Authorization"], "Token tok")
		self.assertIsInstance(source, InfluxQLSource)

	def test_rejects_unknown_types_and_keys(self):
		for spec in (
			{"type": "oracle"},
			{"type": "pi", "url": "https://x", "colour": 1},
			{"type": "pi", "url": "ftp://x"},
			{"type": "sql", "driver": "sqlite3"},
		):
			with self.assertRaises(HistorianError):
				from_dict({"source": spec, "tags": [{"tag": "t", "machine": "m"}]}, env={})

	def test_missing_driver(self):
		with self.assertRaises(HistorianError) as caught:
			from_dict(
				{
					"source": {"type": "ignition-sql", "driver": "no_such_driver_xyz"},
					"tags": [{"tag": "t", "machine": "m"}],
				},
				env={},
			)
		self.assertIn("not installed", str(caught.exception))


class ExampleConfigTests(unittest.TestCase):
	def test_every_example_loads(self):
		stub = type("Driver", (), {"paramstyle": "pyformat", "connect": staticmethod(lambda **kw: None)})
		env = {"FOAMES_HISTORIAN_PASSWORD": "pw", "FOAMES_HISTORIAN_TOKEN": "tok"}
		examples = sorted((Path(__file__).resolve().parents[1] / "examples").glob("*.json"))
		self.assertGreaterEqual(len(examples), 4)
		for path in examples:
			with self.subTest(path.name), open(path) as f:
				source, mappings = from_dict(json.load(f), env=env, driver_loader=lambda name: stub)
				self.assertTrue(mappings)
				self.assertTrue(source.name)


class CommandLineTests(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.TemporaryDirectory()
		self.db_path = os.path.join(self.tmp.name, "hist.sqlite")
		db = sqlite3.connect(self.db_path)
		db.execute("CREATE TABLE hist (ts INTEGER, tag TEXT, value REAL)")
		now = epoch_ms(datetime.now(UTC))
		db.executemany(
			"INSERT INTO hist VALUES (?,?,?)",
			[(now - 600_000 + i * 60_000, "P1.Temp", 70.0 + i) for i in range(5)],
		)
		db.commit()
		db.close()
		self.config = os.path.join(self.tmp.name, "historian.json")
		with open(self.config, "w") as f:
			json.dump(
				{
					"source": {
						"type": "sql",
						"name": "plant-sql",
						"driver": "sqlite3",
						"connect": {"database": self.db_path},
						"table": "hist",
						"time_column": "ts",
						"time_type": "epoch_ms",
					},
					"tags": [{"tag": "P1.Temp", "machine": "press-1", "name": "temperature"}],
				},
				f,
			)

	def tearDown(self):
		self.tmp.cleanup()

	def run_cli(self, *argv, **kwargs):
		out, err = io.StringIO(), io.StringIO()
		with redirect_stderr(err):
			code = main(list(argv), env={}, out=out, **kwargs)
		return code, out.getvalue(), err.getvalue()

	def test_read(self):
		code, out, _ = self.run_cli("read", "--config", self.config, "--tag", "P1.Temp", "--start", "now-1h")
		self.assertEqual(code, 0)
		rows = [json.loads(line) for line in out.splitlines()]
		self.assertEqual([r["value"] for r in rows], [70.0, 71.0, 72.0, 73.0, 74.0])

	def test_check(self):
		code, out, _ = self.run_cli("check", "--config", self.config)
		self.assertEqual(code, 0)
		self.assertIn("P1.Temp -> press-1 Measurement: 5 events", out)

	def test_sync_dry_run_and_real(self):
		code, out, _ = self.run_cli("sync", "--config", self.config, "--dry-run", "--lag", "1s")
		self.assertEqual(code, 0)
		self.assertEqual(len(json.loads(out)), 5)
		checkpoint = os.path.join(self.tmp.name, "state.json")
		sender = type("S", (), {"send": FakeSender()})()
		code, _, err = self.run_cli(
			"sync", "--config", self.config, "--checkpoint", checkpoint, "--lag", "1s", sender=sender
		)
		self.assertEqual(code, 0, err)
		self.assertIn("accepted 5", err)
		self.assertTrue(os.path.exists(checkpoint))

	def test_needs_a_site(self):
		code, _, err = self.run_cli("sync", "--config", self.config)
		self.assertEqual(code, 2)
		self.assertIn("--site", err)

	def test_bad_config(self):
		with open(self.config, "w") as f:
			json.dump({"source": {"type": "pi"}, "tags": []}, f)
		code, _, err = self.run_cli("check", "--config", self.config)
		self.assertEqual(code, 2)
		self.assertIn("configuration", err)


if __name__ == "__main__":
	unittest.main()
