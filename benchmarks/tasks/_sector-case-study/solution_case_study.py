# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Measure a case study's baseline and after windows from a FoaMES Machine Event export.

Usage: python analysis/case_study.py [--data data/case] [--out case_study.json]

Counter deltas come from foames.foames_mes.counters.counter_delta, compared the way the Machine
Event DocType compares them (with the latest reading by timestamp; an older one counts zero), and
OEE from foames.foames_mes.oee.compute_oee. The state ledger keeps time without a signal as Unknown.
"""

import argparse
import csv
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from foames.foames_mes.counters import counter_delta
from foames.foames_mes.oee import TimeLedger, compute_oee

ROOT = Path(__file__).resolve().parent.parent
STATE_FIELD = {"Running": "run_minutes", "Idle": "idle_minutes", "Setup": "setup_minutes"}


def ts(text):
	return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def planned_segments(case, a, b):
	"""The planned parts of [a, b) as (start, end) pairs."""
	day = a.replace(hour=0, minute=0, second=0, microsecond=0)
	while day < b:
		if day.weekday() in case["planned_weekdays"]:
			for h0, h1 in case["planned_hours"]:
				s, e = max(a, day + timedelta(hours=h0)), min(b, day + timedelta(hours=h1))
				if e > s:
					yield s, e
		day += timedelta(days=1)


def planned_minutes(case, a, b):
	return sum((e - s).total_seconds() / 60 for s, e in planned_segments(case, a, b))


def counter_deltas(case, rows):
	"""(source_id, counter, timestamp, delta) for every Count row, in arrival order."""
	rollover = {m["source_id"]: m.get("counter_rollover") for m in case["machines"]}
	latest, out = {}, []
	for row in rows:
		if row["event_type"] != "Count":
			continue
		key = (row["source_id"], row["counter_name"])
		at, value = ts(row["timestamp"]), float(row["counter_value"])
		previous = latest.get(key)
		if previous and previous[0] > at:
			delta = 0.0  # arrived after a later reading: out of order, counts nothing
		else:
			delta = counter_delta(previous[1] if previous else None, value, rollover[key[0]])
			latest[key] = (at, value)
		out.append((key[0], key[1], at, delta))
	return out


def ledger(case, rows, line, start, end):
	"""A FoaMES TimeLedger for the line over the window's planned time, and its changeovers."""
	stale = timedelta(minutes=case["mark_unknown_after_minutes"])
	events = sorted(
		(r for r in rows if r["source_id"] == line), key=lambda r: (ts(r["timestamp"]), int(r["seq"]))
	)
	book = TimeLedger(planned_minutes=planned_minutes(case, start, end))
	state, planned_down = None, False
	for i, row in enumerate(events):
		at = ts(row["timestamp"])
		if row["event_type"] == "State":
			state, planned_down = row["state"], row["planned"] == "1"
		until = ts(events[i + 1]["timestamp"]) if i + 1 < len(events) else max(at, end)
		known = planned_minutes(case, max(at, start), min(min(until, at + stale), end))
		if state in STATE_FIELD:
			field = STATE_FIELD[state]
		elif state == "Down":
			field = "planned_downtime_minutes" if planned_down else "unplanned_downtime_minutes"
		else:
			field = "unknown_minutes"
		setattr(book, field, getattr(book, field) + known)
	# Whatever the events do not cover (before the first, after the stale limit) is unknown.
	book.unknown_minutes += max(book.planned_minutes - book.accounted_minutes, 0.0)
	changeovers, previous = 0, None
	for row in events:
		if row["event_type"] == "State":
			at = ts(row["timestamp"])
			if (
				row["state"] == "Setup"
				and previous != "Setup"
				and start <= at < end
				and planned_minutes(case, at, at + timedelta(seconds=1))
			):
				changeovers += 1
			previous = row["state"]
	return book, changeovers


def window(case, rows, deltas, name):
	start, end = ts(case["windows"][name]["start"]), ts(case["windows"][name]["end"])
	line = next(m for m in case["machines"] if m["role"] == "line")
	meters = {m["source_id"] for m in case["machines"] if m["role"] == "meter"}
	inside = [d for d in deltas if start <= d[2] < end]
	good = sum(d[3] for d in inside if d[0] == line["source_id"] and d[1] == "good")
	scrap = sum(d[3] for d in inside if d[0] == line["source_id"] and d[1] == "scrap")
	energy = sum(d[3] for d in inside if d[0] in meters)
	book, changeovers = ledger(case, rows, line["source_id"], start, end)
	oee = compute_oee(book, good, scrap, line.get("ideal_cycle_seconds"))
	hours = book.planned_minutes / 60
	return {
		"planned_minutes": book.planned_minutes,
		"run_minutes": book.run_minutes,
		"idle_minutes": book.idle_minutes,
		"setup_minutes": book.setup_minutes,
		"planned_downtime_minutes": book.planned_downtime_minutes,
		"unplanned_downtime_minutes": book.unplanned_downtime_minutes,
		"unknown_minutes": book.unknown_minutes,
		"good": good,
		"scrap": scrap,
		"energy": energy,
		"availability": oee.availability,
		"performance": oee.performance,
		"quality": oee.quality,
		"oee": oee.oee,
		"specific_energy": energy / good if good else None,
		"good_per_planned_hour": good / hours if hours else None,
		"changeovers": changeovers,
		"mean_setup_minutes": book.setup_minutes / changeovers if changeovers else None,
	}


def divide(a, b):
	return a / b if a is not None and b else None


def analyse(case, rows):
	deltas = counter_deltas(case, rows)
	base, after = (window(case, rows, deltas, w) for w in ("baseline", "after"))
	a0, a1 = ts(case["windows"]["after"]["start"]), ts(case["windows"]["after"]["end"])
	per_year = 525600 / ((a1 - a0).total_seconds() / 60)
	saving = None
	if base["specific_energy"] is not None and after["specific_energy"] is not None:
		saving = (base["specific_energy"] - after["specific_energy"]) * after["good"] * per_year
	claim = case["claim"]
	setup_ratio = divide(after["mean_setup_minutes"], base["mean_setup_minutes"])
	sec_ratio = divide(after["specific_energy"], base["specific_energy"])
	measured = {
		"annual_energy_saving": saving,
		"oee_after": after["oee"],
		"setup_reduction": None if setup_ratio is None else 1 - setup_ratio,
		"throughput_ratio": divide(after["good_per_planned_hour"], base["good_per_planned_hour"]),
		"specific_energy_reduction": None if sec_ratio is None else 1 - sec_ratio,
	}.get(claim["kind"])
	ratio = divide(measured, claim["value"])
	verdict = "not measurable" if ratio is None else "supported" if 0.8 <= ratio <= 1.25 else "not supported"
	return {
		"case_id": case["case_id"],
		"windows": {"baseline": base, "after": after},
		"annual_energy_saving": saving,
		"annual_cost_saving": None if saving is None else saving * case["energy_price"],
		"claim_check": {
			"kind": claim["kind"],
			"claimed": claim["value"],
			"measured": measured,
			"ratio": ratio,
			"verdict": verdict,
		},
	}


def main(argv=None):
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument("--data", default=str(ROOT / "data" / "case"))
	parser.add_argument("--out", default=str(ROOT / "case_study.json"))
	opts = parser.parse_args(argv)
	data = Path(opts.data)
	case = json.loads((data / "case.json").read_text(encoding="utf-8"))
	text = (data / "events.csv").read_text(encoding="utf-8")
	rows = sorted(csv.DictReader(io.StringIO(text, newline="")), key=lambda r: int(r["seq"]))
	Path(opts.out).write_text(json.dumps(analyse(case, rows), indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
	main()
