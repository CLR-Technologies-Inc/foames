# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""An independent computation of a sector case study's measurement and verification, written
from FoaMES's rules rather than from its code, to check the agent's script against.

The rules, as the task prompt states them:
  - Count readings are processed in arrival order. A reading is compared with the latest reading
    of the same machine and counter received so far, by timestamp; one older than that counts
    zero. Otherwise the delta follows counters.counter_delta: a first reading, a reset or a drop
    counts zero, and a drop wraps only when the machine has a rollover and the previous reading
    was at or below it. A delta belongs to the window that contains the reading's timestamp.
  - A state holds from its event until the next state event. It is trusted for at most
    `mark_unknown_after_minutes` after the latest event of any type from that machine; beyond
    that, until the next event, the time is Unknown. Only planned time counts.
  - OEE follows oee.compute_oee.
"""

from datetime import datetime, timedelta, timezone

YEAR_MINUTES = 525600.0
SUPPORTED = (0.8, 1.25)


def _ts(text: str) -> datetime:
	return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def _delta(previous, current, rollover):
	if previous is None:
		return 0.0
	if current >= previous:
		return current - previous
	if rollover and rollover > 0 and previous <= rollover:
		return rollover - previous + current
	return 0.0


def _planned_minutes(case: dict, a: datetime, b: datetime) -> float:
	"""Minutes of [a, b) inside the plant's planned hours."""
	if b <= a:
		return 0.0
	total = 0.0
	day = a.replace(hour=0, minute=0, second=0, microsecond=0)
	while day < b:
		if day.weekday() in case["planned_weekdays"]:
			for h0, h1 in case["planned_hours"]:
				s = max(a, day + timedelta(hours=h0))
				e = min(b, day + timedelta(hours=h1))
				if e > s:
					total += (e - s).total_seconds() / 60.0
		day += timedelta(days=1)
	return total


def _is_planned(case: dict, ts: datetime) -> bool:
	return _planned_minutes(case, ts, ts + timedelta(seconds=1)) > 0


def _deltas(case: dict, rows: list[dict]) -> list[tuple]:
	rollover = {m["source_id"]: m.get("counter_rollover") for m in case["machines"]}
	latest = {}
	out = []
	for r in sorted(rows, key=lambda r: int(r["seq"])):
		if r["event_type"] != "Count":
			continue
		key = (r["source_id"], r["counter_name"])
		ts, value = _ts(r["timestamp"]), float(r["counter_value"])
		prev = latest.get(key)
		if prev is not None and prev[0] > ts:
			out.append((key, ts, 0.0))
			continue
		out.append((key, ts, _delta(prev[1] if prev else None, value, rollover[key[0]])))
		latest[key] = (ts, value)
	return out


def _ledger(case: dict, rows: list[dict], line: str, start: datetime, end: datetime) -> dict:
	stale = timedelta(minutes=case["mark_unknown_after_minutes"])
	events = sorted(
		(r for r in rows if r["source_id"] == line), key=lambda r: (_ts(r["timestamp"]), int(r["seq"]))
	)
	minutes = {k: 0.0 for k in ("run", "idle", "setup", "planned_down", "unplanned_down", "unknown")}

	def add(kind, a, b):
		a, b = max(a, start), min(b, end)
		if b > a:
			minutes[kind] += _planned_minutes(case, a, b)

	state = None
	cursor = start - timedelta(days=3650)
	if events:
		add("unknown", start, _ts(events[0]["timestamp"]))
	for i, ev in enumerate(events):
		at = _ts(ev["timestamp"])
		if ev["event_type"] == "State":
			state = (ev["state"], str(ev["planned"]).strip() in ("1", "true", "True"))
		nxt = _ts(events[i + 1]["timestamp"]) if i + 1 < len(events) else max(end, at)
		trusted = min(nxt, at + stale)
		kind = "unknown"
		if state is not None:
			kind = {
				"Running": "run",
				"Idle": "idle",
				"Setup": "setup",
				"Down": "planned_down" if state[1] else "unplanned_down",
			}.get(state[0], "unknown")
		add(kind, at, trusted)
		add("unknown", trusted, nxt)
		cursor = nxt
	if cursor < end:
		add("unknown", max(cursor, start), end)
	planned = _planned_minutes(case, start, end)
	# Changeovers: entries into Setup inside the window's planned time.
	changeovers, previous = 0, None
	for ev in events:
		if ev["event_type"] != "State":
			continue
		at = _ts(ev["timestamp"])
		if ev["state"] == "Setup" and previous != "Setup" and start <= at < end and _is_planned(case, at):
			changeovers += 1
		previous = ev["state"]
	return {"planned": planned, "changeovers": changeovers, **minutes}


def _window(case: dict, rows: list[dict], deltas: list[tuple], name: str) -> dict:
	start, end = _ts(case["windows"][name]["start"]), _ts(case["windows"][name]["end"])
	line = next(m for m in case["machines"] if m["role"] == "line")
	meters = {m["source_id"] for m in case["machines"] if m["role"] == "meter"}
	inside = [(k, d) for k, ts, d in deltas if start <= ts < end]
	good = sum(d for (src, c), d in inside if src == line["source_id"] and c == "good")
	scrap = sum(d for (src, c), d in inside if src == line["source_id"] and c == "scrap")
	energy = sum(d for (src, _), d in inside if src in meters)
	ledger = _ledger(case, rows, line["source_id"], start, end)
	run = ledger["run"]
	base = ledger["planned"] - ledger["planned_down"]
	availability = max(0.0, min(run / base, 1.0)) if base > 0 else 0.0
	total = good + scrap
	ideal = line.get("ideal_cycle_seconds")
	if ideal and run > 0:
		performance = min(ideal * total / 60.0 / run, 1.0)
	elif run > 0 and total > 0:
		performance = 1.0
	else:
		performance = 0.0
	quality = good / total if total > 0 else 0.0
	return {
		"planned_minutes": ledger["planned"],
		"run_minutes": run,
		"idle_minutes": ledger["idle"],
		"setup_minutes": ledger["setup"],
		"planned_downtime_minutes": ledger["planned_down"],
		"unplanned_downtime_minutes": ledger["unplanned_down"],
		"unknown_minutes": ledger["unknown"],
		"good": good,
		"scrap": scrap,
		"energy": energy,
		"availability": availability,
		"performance": performance,
		"quality": quality,
		"oee": availability * performance * quality,
		"specific_energy": energy / good if good > 0 else None,
		"good_per_planned_hour": good / (ledger["planned"] / 60.0) if ledger["planned"] > 0 else None,
		"changeovers": ledger["changeovers"],
		"mean_setup_minutes": ledger["setup"] / ledger["changeovers"] if ledger["changeovers"] else None,
	}


def _ratio(a, b):
	return a / b if a is not None and b not in (None, 0) else None


def analyse(case: dict, rows: list[dict]) -> dict:
	deltas = _deltas(case, rows)
	b = _window(case, rows, deltas, "baseline")
	a = _window(case, rows, deltas, "after")
	after_start, after_end = _ts(case["windows"]["after"]["start"]), _ts(case["windows"]["after"]["end"])
	scale = YEAR_MINUTES / ((after_end - after_start).total_seconds() / 60.0)
	saving = None
	if b["specific_energy"] is not None and a["specific_energy"] is not None:
		saving = (b["specific_energy"] - a["specific_energy"]) * a["good"] * scale
	claim = case["claim"]
	measured = {
		"annual_energy_saving": saving,
		"oee_after": a["oee"],
		"setup_reduction": None
		if a["mean_setup_minutes"] is None or not b["mean_setup_minutes"]
		else 1.0 - a["mean_setup_minutes"] / b["mean_setup_minutes"],
		"throughput_ratio": _ratio(a["good_per_planned_hour"], b["good_per_planned_hour"]),
		"specific_energy_reduction": None
		if a["specific_energy"] is None or not b["specific_energy"]
		else 1.0 - a["specific_energy"] / b["specific_energy"],
	}.get(claim["kind"])
	ratio = _ratio(measured, claim["value"])
	if ratio is None:
		verdict = "not measurable"
	elif SUPPORTED[0] <= ratio <= SUPPORTED[1]:
		verdict = "supported"
	else:
		verdict = "not supported"
	return {
		"case_id": case["case_id"],
		"windows": {"baseline": b, "after": a},
		"annual_energy_saving": saving,
		"annual_cost_saving": saving * case["energy_price"] if saving is not None else None,
		"claim_check": {
			"kind": claim["kind"],
			"claimed": claim["value"],
			"measured": measured,
			"ratio": ratio,
			"verdict": verdict,
		},
	}
