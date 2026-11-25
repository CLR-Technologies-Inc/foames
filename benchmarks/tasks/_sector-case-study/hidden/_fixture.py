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

"""Synthetic FoaMES machine events for one sector case study.

A sector file (hidden/sector.json in each task) describes one improvement reported in a public US
government document: the plant's line and its meter, how they ran before and after the change,
and the figure the document claims. This module turns it into what FoaMES would have recorded: a
case file and a Machine Event export, in arrival order, for a baseline week and an after week.

The data is invented. Only the claim, the units and the scale come from the cited source, and the
after week's energy use is calibrated so that the measured result lands at `target_ratio` times
the claim. Everything is deterministic for a given sector file, so the hidden tests can rebuild
the exact data the agent saw.

Planted conditions (`traps`), each of which FoaMES's rules decide:
  plc_reset        the line's counters restart from zero in one window
  duplicate        a counter reading arrives twice
  out_of_order     a counter reading arrives after later ones
  network_gap      the line's gateway is silent for some hours; it re-sends its state on return
  meter_rollover   the energy meter wraps at its rollover value inside a window
"""

import copy
import csv
import io
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

FIELDS = ["seq", "source_id", "timestamp", "event_type", "state", "planned", "counter_name", "counter_value"]
WINDOWS = ("baseline", "after")
PREROLL = timedelta(hours=3)
POSTROLL = timedelta(hours=1)


def parse_ts(text: str) -> datetime:
	return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def fmt_ts(ts: datetime) -> str:
	return ts.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_sector(path) -> dict:
	return json.loads(Path(path).read_text(encoding="utf-8"))


def window_bounds(sector: dict, window: str) -> tuple[datetime, datetime]:
	start = parse_ts(sector["windows"][window]["start"])
	return start, start + timedelta(days=sector["windows"][window]["days"])


def is_planned(sector: dict, ts: datetime) -> bool:
	if ts.weekday() not in sector["planned_weekdays"]:
		return False
	hour = ts.hour + ts.minute / 60 + ts.second / 3600
	return any(h0 <= hour < h1 for h0, h1 in sector["planned_hours"])


def case_json(sector: dict) -> dict:
	"""What the agent is given about the case: no generator parameters, no planted conditions."""
	line, meter = sector["line"], sector["meter"]
	return {
		"case_id": sector["case_id"],
		"sector": sector["sector"],
		"naics": sector["naics"],
		"plant": "Plant A (anonymised, illustrative)",
		"data": "Illustrative: synthetic events grounded in the cited source's figures",
		"source": sector["source"],
		"windows": {
			w: {"start": sector["windows"][w]["start"], "end": fmt_ts(window_bounds(sector, w)[1])}
			for w in WINDOWS
		},
		"planned_hours": sector["planned_hours"],
		"planned_weekdays": sector["planned_weekdays"],
		"mark_unknown_after_minutes": sector["mark_unknown_after_minutes"],
		"production_unit": sector["production_unit"],
		"energy_unit": sector["energy_unit"],
		"energy_price": sector["energy_price"],
		"machines": [
			{
				"source_id": line["source_id"],
				"role": "line",
				"description": line["description"],
				"ideal_cycle_seconds": line["ideal_cycle_seconds"],
				"counter_rollover": None,
				"counters": {"good": sector["production_unit"], "scrap": sector["production_unit"]},
			},
			{
				"source_id": meter["source_id"],
				"role": "meter",
				"description": meter["description"],
				"ideal_cycle_seconds": None,
				"counter_rollover": meter.get("rollover"),
				"counters": {meter["counter"]: sector["energy_unit"]},
			},
		],
		"claim": sector["claim"],
	}


# --- state timeline ---------------------------------------------------------------------------


def _jitter(rng, minutes: float) -> int:
	return max(1, round(minutes * rng.uniform(0.8, 1.2)))


def _count(rng, per_day: float) -> int:
	whole = int(per_day)
	return whole + (1 if rng.random() < per_day - whole else 0)


def _segment_events(rng, params: dict, length: int, planned_days_per_week: int) -> list:
	"""Stops inside one planned segment: (state, minutes, planned) in a random order."""
	share = length / (60 * sum(h1 - h0 for h0, h1 in params["_planned_hours"]))
	stops = []
	for state, key, planned in (
		("Down", "down", False),
		("Idle", "idle", False),
		("Setup", "setup", False),
	):
		for _ in range(_count(rng, params[f"{key}_per_day"] * share)):
			stops.append((state, _jitter(rng, params[f"{key}_minutes"]), planned))
	per_week = params.get("planned_down_per_week", 0)
	if per_week and rng.random() < per_week * share / max(planned_days_per_week, 1):
		stops.append(("Down", _jitter(rng, params["planned_down_minutes"]), True))
	rng.shuffle(stops)
	total = sum(m for _, m, _ in stops)
	limit = int(length * 0.7)
	while stops and total > limit:
		total -= stops.pop()[1]
	return stops


def _timeline(sector: dict, window: str, rng) -> list:
	"""(start, state, planned) changes from the pre-roll to the post-roll, state held until next."""
	start, end = window_bounds(sector, window)
	params = dict(sector[window], _planned_hours=sector["planned_hours"])
	changes = []
	day = (start - PREROLL).replace(hour=0, minute=0, second=0)
	while day < end + POSTROLL:
		if day.weekday() in sector["planned_weekdays"]:
			for h0, h1 in sector["planned_hours"]:
				seg_start = day + timedelta(hours=h0)
				length = int((h1 - h0) * 60)
				stops = _segment_events(rng, params, length, len(sector["planned_weekdays"]))
				free = length - sum(m for _, m, _ in stops)
				offsets = sorted(rng.randint(0, free) for _ in stops)
				changes.append((seg_start, "Running", False))
				used = 0
				for (state, minutes, planned), offset in zip(stops, offsets, strict=True):
					at = seg_start + timedelta(minutes=offset + used)
					changes.append((at, state, planned))
					used += minutes
					changes.append((at + timedelta(minutes=minutes), "Running", False))
				changes.append((seg_start + timedelta(minutes=length), "Idle", False))
		day += timedelta(days=1)
	changes.sort(key=lambda c: c[0])
	merged = []
	for change in changes:
		if merged and merged[-1][0] == change[0]:
			merged[-1] = change
		elif merged and merged[-1][1:] == change[1:]:
			continue
		else:
			merged.append(change)
	return [c for c in merged if start - PREROLL <= c[0] < end + POSTROLL]


def _state_at(timeline: list, ts: datetime):
	current = ("Idle", False)
	for at, state, planned in timeline:
		if at > ts:
			break
		current = (state, planned)
	return current


# --- counters ---------------------------------------------------------------------------------


def _production(sector: dict, window: str, timeline: list, rng) -> dict:
	"""Cumulative production at each minute of the simulated span, keyed by minute index."""
	start, end = window_bounds(sector, window)
	t0, t1 = start - PREROLL, end + POSTROLL
	rate = sector[window]["rate_per_run_hour"] / 60.0
	cumulative, total, i, idx = {}, 0.0, 0, 0
	factor = 1.0
	state = "Idle"
	ts = t0
	while ts <= t1:
		while idx < len(timeline) and timeline[idx][0] <= ts:
			state = timeline[idx][1]
			factor = rng.uniform(0.95, 1.05)
			idx += 1
		cumulative[i] = total
		if state == "Running":
			total += rate * factor
		ts += timedelta(minutes=1)
		i += 1
	return cumulative


def _value(x: float, integer: bool) -> float:
	return float(math.floor(x)) if integer else round(x, 3)


def _rows_for_window(sector: dict, window: str, energy_per_unit: float, offsets: dict, rng) -> list:
	t0 = window_bounds(sector, window)[0] - PREROLL
	line, meter = sector["line"], sector["meter"]
	params = sector[window]
	timeline = _timeline(sector, window, rng)
	cumulative = _production(sector, window, timeline, rng)
	minutes = len(cumulative)
	scrap = params["scrap_fraction"]
	integer = sector.get("integer_counts", False)
	rows = []
	for at, state, planned in timeline:
		rows.append(
			{
				"source_id": line["source_id"],
				"timestamp": at,
				"event_type": "State",
				"state": state,
				"planned": int(planned),
			}
		)
	every = line["count_every_minutes"]
	for m in range(0, minutes, every):
		at = t0 + timedelta(minutes=m, seconds=rng.randint(0, 20))
		made = cumulative[m]
		for name, value in (("good", made * (1 - scrap)), ("scrap", made * scrap)):
			rows.append(
				{
					"source_id": line["source_id"],
					"timestamp": at,
					"event_type": "Count",
					"counter_name": name,
					"counter_value": _value(offsets[name] + value, integer),
				}
			)
	base = params["energy_base_per_hour"] / 60.0
	for m in range(0, minutes, meter["every_minutes"]):
		at = t0 + timedelta(minutes=m, seconds=rng.randint(0, 20))
		energy = offsets["energy"] + base * m + energy_per_unit * cumulative[m]
		rows.append(
			{
				"source_id": meter["source_id"],
				"timestamp": at,
				"event_type": "Count",
				"counter_name": meter["counter"],
				"counter_value": energy,
			}
		)
	offsets["good"] += cumulative[minutes - 1] * (1 - scrap) * 5
	offsets["scrap"] += cumulative[minutes - 1] * scrap * 5
	offsets["energy"] += base * minutes * 5
	return rows, timeline


# --- planted conditions -----------------------------------------------------------------------


def _line_counts(rows, sector, window, name=None):
	start, end = window_bounds(sector, window)
	return [
		i
		for i, r in enumerate(rows)
		if r["source_id"] == sector["line"]["source_id"]
		and r["event_type"] == "Count"
		and start <= r["timestamp"] < end
		and (name is None or r["counter_name"] == name)
	]


def _apply_traps(rows: list, sector: dict, timelines: dict, rng) -> list:
	traps = sector.get("traps", {})
	line_id = sector["line"]["source_id"]
	reset = traps.get("plc_reset")
	if reset:
		# The PLC restarts just after a reading: from then on the line's counters count from zero,
		# so the first reading after the restart is below the last one before it.
		start, end = window_bounds(sector, reset["window"])
		at = start + (end - start) * reset["at"]
		integer = sector.get("integer_counts", False)
		ordered = sorted(
			(r for r in rows if r["source_id"] == line_id and r["event_type"] == "Count"),
			key=lambda r: r["timestamp"],
		)
		base = {}
		for r in ordered:
			if r["timestamp"] < at:
				base[r["counter_name"]] = r["counter_value"]
		for r in ordered:
			if r["timestamp"] >= at:
				r["counter_value"] = _value(r["counter_value"] - base.get(r["counter_name"], 0.0), integer)
	gap = traps.get("network_gap")
	if gap:
		start, end = window_bounds(sector, gap["window"])
		g0 = start + (end - start) * gap["at"]
		while not is_planned(sector, g0):
			g0 += timedelta(minutes=15)  # the gateway drops out while the plant is working
		g1 = g0 + timedelta(hours=gap["hours"])
		rows = [r for r in rows if not (r["source_id"] == line_id and g0 < r["timestamp"] < g1)]
		state, planned = _state_at(timelines[gap["window"]], g1)
		rows.append(
			{
				"source_id": line_id,
				"timestamp": g1,
				"event_type": "State",
				"state": state,
				"planned": int(planned),
			}
		)
	rows.sort(key=lambda r: (r["timestamp"], r["event_type"] != "State"))
	duplicate = traps.get("duplicate")
	if duplicate:
		picks = _line_counts(rows, sector, duplicate["window"], "good")
		i = picks[len(picks) // 3]
		rows.insert(i + 1, dict(rows[i]))
	late = traps.get("out_of_order")
	if late:
		# A reading taken while the line ran arrives after several later ones.
		picks = _line_counts(rows, sector, late["window"], "good")
		after = late.get("arrives_after", 3)
		j = next(
			k
			for k in range(len(picks) // 2, len(picks) - after - 1)
			if rows[picks[k + 1]]["counter_value"]
			> rows[picks[k]]["counter_value"]
			> rows[picks[k - 1]]["counter_value"]
		)
		row = rows[picks[j]]
		target = picks[j + after]
		rows.insert(target + 1, row)
		del rows[picks[j]]
	return rows


def _wrap_meter(rows: list, sector: dict) -> None:
	meter = sector["meter"]
	rollover = meter.get("rollover")
	traps = sector.get("traps", {})
	readings = [r for r in rows if r["source_id"] == meter["source_id"]]
	start_value = meter.get("start_value", 0.0)
	if rollover and traps.get("meter_rollover"):
		trap = traps["meter_rollover"]
		w0, w1 = window_bounds(sector, trap["window"])
		at = w0 + (w1 - w0) * trap["at"]
		before = [r for r in readings if r["timestamp"] <= at]
		start_value = rollover - before[-1]["counter_value"] - 0.5
	for r in readings:
		value = start_value + r["counter_value"]
		if rollover:
			value = value % rollover
		r["counter_value"] = round(value, 3)


# --- generation -------------------------------------------------------------------------------


def _generate(sector: dict, energy_per_unit_after: float) -> list:
	rng = random.Random(sector["seed"])
	offsets = {"good": 1000.0, "scrap": 10.0, "energy": 0.0}
	rows, timelines = [], {}
	for window in WINDOWS:
		epu = sector["baseline"]["energy_per_unit"] if window == "baseline" else energy_per_unit_after
		window_rows, timelines[window] = _rows_for_window(sector, window, epu, offsets, rng)
		rows += window_rows
	rows.sort(key=lambda r: (r["timestamp"], r["event_type"] != "State"))
	_wrap_meter(rows, sector)
	rows = _apply_traps(rows, sector, timelines, rng)
	out = []
	for seq, r in enumerate(rows, start=1):
		out.append(
			{
				"seq": seq,
				"source_id": r["source_id"],
				"timestamp": fmt_ts(r["timestamp"]),
				"event_type": r["event_type"],
				"state": r.get("state", ""),
				"planned": r.get("planned", "") if r["event_type"] == "State" else "",
				"counter_name": r.get("counter_name", ""),
				"counter_value": r.get("counter_value", ""),
			}
		)
	return out


ENERGY_KINDS = ("annual_energy_saving", "specific_energy_reduction")


def events(sector: dict) -> list[dict]:
	"""The Machine Event export, in arrival order. When the sector sets `target_ratio`, the after
	week's energy per unit is solved so the measured energy result is that share of the claim."""
	after = sector["after"]
	target = sector.get("target_ratio")
	if target is None or sector["claim"]["kind"] not in ENERGY_KINDS:
		return _generate(sector, after["energy_per_unit"])
	from _mv_reference import analyse

	case = case_json(sector)

	def saving(epu):
		return analyse(case, parse_rows(to_csv(_generate(sector, epu))))["claim_check"]["measured"]

	x0 = after["energy_per_unit"]
	x1 = x0 * 0.5 if x0 else 0.01
	s0, s1 = saving(x0), saving(x1)
	goal = target * sector["claim"]["value"]
	x = x0 + (goal - s0) * (x1 - x0) / (s1 - s0)
	if x < 0:
		raise ValueError(f"{sector['case_id']}: no energy per unit reaches the target; lower the base load")
	return _generate(sector, x)


def to_csv(rows: list[dict]) -> str:
	buffer = io.StringIO()
	writer = csv.DictWriter(buffer, fieldnames=FIELDS, lineterminator="\n")
	writer.writeheader()
	writer.writerows(rows)
	return buffer.getvalue()


def parse_rows(text: str) -> list[dict]:
	return list(csv.DictReader(io.StringIO(text)))


def write(sector: dict, dest: Path) -> None:
	"""Write data/case/case.json and data/case/events.csv under dest."""
	dest.mkdir(parents=True, exist_ok=True)
	(dest / "case.json").write_text(json.dumps(case_json(sector), indent=1) + "\n", encoding="utf-8")
	(dest / "events.csv").write_text(to_csv(events(sector)), encoding="utf-8")


def variant(sector: dict, **changes) -> dict:
	"""A copy of the sector with some fields replaced, for the invariant tests."""
	out = copy.deepcopy(sector)
	for key, value in changes.items():
		out[key] = value
	return out
