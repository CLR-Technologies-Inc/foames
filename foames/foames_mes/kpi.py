# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The arithmetic behind the FoaMES reports: OEE roll-ups, the downtime Pareto, MTBF and MTTR.

Pure functions over plain dicts and numbers, so the reports stay thin and the formulas can be tested
without a site. Percentages come out on the 0-100 scale the OEE Period stores.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime
from math import ceil
from statistics import median


def roll_up_oee(periods: list[dict]) -> dict:
	"""Combine OEE Periods into one time-weighted result.

	Averaging percentages would let a two-hour trial run count as much as a full shift, so the
	components are recomputed from the summed ledgers instead:

	availability = sum(run) / sum(planned - planned downtime)
	performance  = sum(ideal cycle time x total count) / sum(run)
	quality      = sum(good) / sum(good + scrap)

	A period without an ideal cycle time contributes its run time to the performance base at the
	performance it was stored with, so the roll-up never credits more than each period did.
	"""
	planned = run = planned_dt = unplanned_dt = unknown = 0.0
	good = scrap = 0.0
	ideal_minutes = 0.0
	for p in periods:
		planned += float(p.get("planned_minutes") or 0)
		run += float(p.get("run_minutes") or 0)
		planned_dt += float(p.get("planned_downtime_minutes") or 0)
		unplanned_dt += float(p.get("unplanned_downtime_minutes") or 0)
		unknown += float(p.get("unknown_minutes") or 0)
		p_good = float(p.get("good_count") or 0)
		p_scrap = float(p.get("scrap_count") or 0)
		good += p_good
		scrap += p_scrap
		ideal = float(p.get("ideal_cycle_seconds") or 0)
		if ideal > 0:
			ideal_minutes += ideal * (p_good + p_scrap) / 60.0
		else:
			ideal_minutes += float(p.get("run_minutes") or 0) * float(p.get("performance") or 0) / 100.0
	base = planned - planned_dt
	availability = run / base if base > 0 else 0.0
	performance = ideal_minutes / run if run > 0 else 0.0
	performance = max(0.0, min(performance, 1.0))
	total = good + scrap
	quality = good / total if total > 0 else 0.0
	return {
		"periods": len(periods),
		"planned_minutes": planned,
		"run_minutes": run,
		"planned_downtime_minutes": planned_dt,
		"unplanned_downtime_minutes": unplanned_dt,
		"unknown_minutes": unknown,
		"good_count": good,
		"scrap_count": scrap,
		"availability": availability * 100,
		"performance": performance * 100,
		"quality": quality * 100,
		"oee": availability * performance * quality * 100,
	}


def pareto(rows: list[dict], key: str = "label", value: str = "minutes") -> list[dict]:
	"""Sort groups by value, largest first, and add each one's share and the running share.

	Groups whose key is empty are kept under the label "Unclassified" so unexplained downtime stays
	visible instead of disappearing from the chart.
	"""
	totals: OrderedDict[str, dict] = OrderedDict()
	for row in rows:
		label = row.get(key) or "Unclassified"
		entry = totals.setdefault(label, {key: label, value: 0.0, "occurrences": 0})
		entry[value] += float(row.get(value) or 0)
		entry["occurrences"] += int(row.get("occurrences") or 1)
	ordered = sorted(totals.values(), key=lambda r: r[value], reverse=True)
	grand_total = sum(r[value] for r in ordered)
	running = 0.0
	for r in ordered:
		running += r[value]
		r["share"] = (r[value] / grand_total * 100) if grand_total > 0 else 0.0
		r["cumulative_share"] = (running / grand_total * 100) if grand_total > 0 else 0.0
	return ordered


def clip_minutes(
	start: datetime, end: datetime | None, window_start: datetime, window_end: datetime
) -> float:
	"""Minutes of [start, end) that fall inside [window_start, window_end). An open interval runs to
	the end of the window."""
	a = max(start, window_start)
	b = min(end or window_end, window_end)
	if b <= a:
		return 0.0
	return (b - a).total_seconds() / 60.0


def reliability(failures: int, downtime_minutes: float, window_minutes: float) -> dict:
	"""MTBF, MTTR and the availability they imply, in minutes.

	MTBF is the operating time between failures: the window less the time spent down, divided by the
	number of failures. MTTR is the downtime per failure. A machine that never failed has no MTBF
	(None) rather than an infinite one, and a repair time of zero.
	"""
	uptime = max(window_minutes - downtime_minutes, 0.0)
	if failures <= 0:
		return {
			"failures": 0,
			"downtime_minutes": downtime_minutes,
			"uptime_minutes": uptime,
			"mtbf_minutes": None,
			"mttr_minutes": 0.0,
			"availability": 100.0 if window_minutes > 0 else 0.0,
		}
	mtbf = uptime / failures
	mttr = downtime_minutes / failures
	return {
		"failures": failures,
		"downtime_minutes": downtime_minutes,
		"uptime_minutes": uptime,
		"mtbf_minutes": mtbf,
		"mttr_minutes": mttr,
		"availability": (mtbf / (mtbf + mttr) * 100) if (mtbf + mttr) > 0 else 0.0,
	}


def resolution_hours(pairs: list[tuple[datetime, datetime | None]]) -> dict:
	"""Median and mean hours from creation to resolution over the resolved pairs."""
	hours = [(b - a).total_seconds() / 3600.0 for a, b in pairs if a and b and b >= a]
	if not hours:
		return {"resolved": 0, "median_hours": None, "mean_hours": None}
	return {
		"resolved": len(hours),
		"median_hours": median(hours),
		"mean_hours": sum(hours) / len(hours),
	}


def percentile(values: list[float], share: float) -> float | None:
	"""The nearest-rank percentile: the smallest value such that at least `share` (0-1) of the values
	are less than or equal to it."""
	if not values:
		return None
	ordered = sorted(values)
	rank = max(0, min(len(ordered) - 1, ceil(share * len(ordered)) - 1))
	return ordered[rank]
