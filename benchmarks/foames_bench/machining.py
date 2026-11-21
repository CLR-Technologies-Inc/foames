# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""The CNC equipment study: a CNC lathe and a fleet of CNC mills, replayed through FoaMES.

Two public datasets, one question: what does FoaMES see on machining equipment, and what should an
equipment agent tied to that equipment be allowed to say?

    cnc-turning-xquality     one CNC lathe, 62 parts, two operations (roughing and finishing), eight
                             sensors (spindle power, three cutting forces, vibration, microphone).
                             Parts are labelled normal or abnormal, and each abnormal batch has one
                             known cause: feedrate at 80 percent, the wrong material, or wrong tools.
    cnc-milling-vibration    three CNC milling machines, 15 operations each, tri-axial vibration
                             recorded over six timeframes between 2018 and 2021, files labelled good
                             or bad.

Graded checks compare FoaMES with values computed here from the raw signals: I-MR limits and
beyond-limit signals per feature, energy per part through FoaMES's specific-consumption KPI, and the
Equipment Complexity Level profile and agent eligibility FoaMES gives each machine class, against the
level floors in benchmarks/data/recommendations.json. The study itself (which sensor sees which
deviation, how often limits raise false alarms, whether one mill's limits carry over to another) is
reported, never graded: an out-of-control point is not a confirmed defect.

Standard library only. Imported by mfgdata, which owns fetch, stages and the report.
"""

from __future__ import annotations

import csv
import io
import json
import math
import random
import re
import statistics
from datetime import datetime
from pathlib import Path

from .paths import BENCH_ROOT

RECOMMENDATIONS = BENCH_ROOT / "data" / "recommendations.json"
TIERS = ("oss", "baseline", "frontier")


class SchemaMismatch(Exception):
	pass


# ----------------------------------------------------------------------------- shared


def _foames(*names):
	from . import mfgdata

	return mfgdata._foames(*names)


def _imr(values, baseline):
	from . import mfgdata

	return mfgdata.independent_imr(values, baseline)


def _visible(folder: Path, pattern: str):
	from . import mfgdata

	return [p for p in mfgdata._published_paths(folder, pattern) if p.is_file()]


def _float(value) -> float | None:
	try:
		v = float(str(value).strip())
	except (TypeError, ValueError):
		return None
	return v if math.isfinite(v) else None


def rms(values) -> float:
	return math.sqrt(sum(v * v for v in values) / len(values)) if values else 0.0


def trapezoid(times, values) -> float:
	"""Integral of values over times (for spindle power in W over seconds: joules)."""
	return sum(
		(t1 - t0) * (v0 + v1) / 2
		for t0, t1, v0, v1 in zip(times, times[1:], values, values[1:], strict=False)
	)


def cohens_d(a, b) -> float | None:
	"""Standardised mean difference of b from a (pooled standard deviation)."""
	if len(a) < 2 or len(b) < 2:
		return None
	va, vb = statistics.variance(a), statistics.variance(b)
	pooled = math.sqrt(((len(a) - 1) * va + (len(b) - 1) * vb) / (len(a) + len(b) - 2))
	if pooled == 0:
		return None
	return (statistics.fmean(b) - statistics.fmean(a)) / pooled


def _chart_check(spc, series: dict, baselines: dict) -> tuple[float, int, int, dict]:
	"""Chart every series with FoaMES and independently. Returns the worst relative limit difference,
	the number of series whose beyond-limit points differ, NaNs charted, and the independent signal
	indices per series (what the study's metrics are built from)."""
	worst, mismatch, nan_leaks, signals = 0.0, 0, 0, {}
	for key, values in series.items():
		b = baselines[key]
		chart = spc.imr_chart(values, baseline=b, rules=("N1",))
		ind = chart["individuals"]
		cl, ucl, lcl, sigma = _imr(values, b)
		for got, exp in (
			(ind["cl"], cl),
			(ind["ucl"], ucl),
			(ind["lcl"], lcl),
			(chart["sigma_within"], sigma),
		):
			worst = max(worst, abs(got - exp) / max(1.0, abs(exp)))
		got_idx = sorted({s["index"] for s in ind["signals"] if s["rule"] == "N1"})
		exp_idx = [k for k, v in enumerate(values) if v > ucl or v < lcl]
		mismatch += got_idx != exp_idx
		nan_leaks += sum(1 for v in ind["points"] if isinstance(v, float) and math.isnan(v))
		signals[key] = set(exp_idx)
	return worst, mismatch, nan_leaks, signals


def _spc_checks(Check, worst, mismatch, nan_leaks, n) -> list:
	return [
		Check(
			"spc/imr-limits",
			worst <= 1e-9,
			0.0,
			worst,
			f"max relative difference in CL, UCL, LCL, sigma over {n} charts",
		),
		Check(
			"spc/beyond-limit-signals",
			mismatch == 0,
			0,
			mismatch,
			"charts whose N1 points differ from an independent test",
		),
		Check("spc/no-missing-values-charted", nan_leaks == 0, 0, nan_leaks),
	]


def _varying(values) -> bool:
	return len(values) >= 2 and len(set(values)) > 2 and statistics.pstdev(values) > 0


# ------------------------------------------------------------------------ equipment (ECL)


def recommended_floors(path: Path | None = None) -> dict[int, str | None]:
	levels = json.loads(Path(path or RECOMMENDATIONS).read_text())["ecl"]["levels"]
	return {int(k): v.get("min_tier") for k, v in levels.items()}


def check_equipment(Check, equipment: list[dict]) -> tuple[list, dict]:
	"""What FoaMES's ECL module tells an equipment agent about each machine in the study, compared
	with the level floors the benchmark recommends. The ratings come from the public ECL list and
	are `ai-initial` drafts until a person reviews them."""
	ecl = _foames("ecl")
	floors = recommended_floors()
	checks, out, wrong = [], [], []
	for item in equipment:
		entry = {k: item.get(k) for k in ("ecl", "ecl_rationale", "confidence", "reviewed_by", "name")}
		entry["id"] = item["ecl_class"]
		rating = ecl.rating_from_class(entry)
		prof = ecl.profile(rating["ecl"])
		floor = floors.get(rating["ecl"])
		row = {
			"machine": item["machine"],
			"ecl_class": item["ecl_class"],
			"ecl": rating["ecl"],
			"draft_rating": rating["draft"],
			"min_tier": prof["min_tier"],
			"oversight": prof["oversight"],
			"agent_role": prof["agent_role"],
			"eligible": {},
		}
		if prof["min_tier"] != floor:
			wrong.append(f"{item['machine']}: min tier {prof['min_tier']} != recommended {floor}")
		for tier in TIERS:
			got = ecl.eligibility(tier, rating["ecl"])["eligible"]
			exp = floor is not None and TIERS.index(tier) >= TIERS.index(floor)
			row["eligible"][tier] = got
			if bool(got) != exp:
				wrong.append(f"{item['machine']}: tier {tier} eligible={got}, floor says {exp}")
		out.append(row)
	levels = [r["ecl"] for r in out]
	group = ecl.group_ecl(levels)
	checks.append(
		Check(
			"ecl/profile-matches-recommended-floors",
			not wrong,
			[],
			wrong,
			"min tier and eligibility per machine",
		)
	)
	checks.append(
		Check(
			"ecl/fleet-level",
			group == max(levels),
			max(levels),
			group,
			"a line's ECL is its most complex member's",
		)
	)
	return checks, {"equipment": out, "fleet_ecl": group}


# ---------------------------------------------------------------- CNC lathe (XQuality)


def read_crv(path: Path) -> tuple[list[float], list[float]]:
	"""A two-column `time;value` CRV file with one header line."""
	times, values = [], []
	text = path.read_text(encoding="utf-8-sig", errors="replace")
	for i, line in enumerate(text.splitlines()):
		parts = re.split(r"[;,\t]", line.strip())
		if len(parts) < 2:
			continue
		t, v = _float(parts[0]), _float(parts[1])
		if t is None or v is None:
			if i == 0:
				continue  # header
			continue
		times.append(t)
		values.append(v)
	return times, values


def _labels_file(folder: Path, name: str) -> Path:
	found = sorted(_visible(folder, name), key=lambda p: len(p.parts))
	if not found:
		raise SchemaMismatch(f"{folder}: no {name}")
	return found[0]


def load_turning(folder: Path, ds: dict, max_rows: int | None) -> dict:
	"""Per part: label, batch, deviation and, per operation and channel, the signal's mean, RMS and
	peak, its duration, and the spindle energy of the operation."""
	cols = ds["columns"]
	labels = _labels_file(folder, cols["labels_file"])
	text = labels.read_text(encoding="utf-8-sig", errors="replace")
	reader = csv.DictReader(io.StringIO(text))
	headers = list(reader.fieldnames or [])
	for key in ("part", "label", "batch"):
		if cols[key] not in headers:
			raise SchemaMismatch(f"{labels}: no {key} column {cols[key]!r}; headers are {headers}")
	data_root = labels.parent / cols.get("data_dir", "data")
	if not data_root.is_dir():
		data_root = labels.parent
	parts = []
	for row in reader:
		name = str(row[cols["part"]]).strip()
		if not name:
			continue
		pdir = data_root / name
		if not pdir.is_dir():
			continue
		feats, energy, duration = {}, {}, {}
		for op in cols["operations"]:
			for ch in cols["channels"]:
				f = pdir / op / cols["file_pattern"].format(channel=ch)
				if not f.is_file():
					continue
				t, v = read_crv(f)
				if len(v) < 2:
					continue
				feats[f"{op}/{ch}/mean"] = statistics.fmean(v)
				feats[f"{op}/{ch}/rms"] = rms(v)
				feats[f"{op}/{ch}/peak"] = max(abs(x) for x in v)
				if ch == cols["power_channel"]:
					energy[op] = trapezoid(t, v)
					duration[op] = t[-1] - t[0]
		if not feats:
			continue
		parts.append(
			{
				"part": name,
				"number": int(re.sub(r"\D", "", name) or 0),
				"abnormal": str(row[cols["label"]]).strip().lower() == cols["label_abnormal"],
				"batch": str(row[cols["batch"]]).strip(),
				"deviation": str(row.get(cols.get("deviation", ""), "") or "").strip(),
				"features": feats,
				"energy_j": energy,
				"duration_s": duration,
			}
		)
	if not parts:
		raise SchemaMismatch(
			f"{data_root}: no part folders with {cols['file_pattern']} files for {cols['operations']}"
		)
	parts.sort(key=lambda p: p["number"])
	return {"parts": parts[:max_rows] if max_rows else parts}


def check_turning(data: dict, ds: dict, max_features: int) -> tuple[list, dict, list[str]]:
	from .mfgdata import Check, _close

	spc, kpi = _foames("spc", "kpi")
	parts = data["parts"]
	study = ds.get("study", {})
	n_base = study.get("baseline_parts", 20)
	normal_idx = [i for i, p in enumerate(parts) if not p["abnormal"]]
	if len(normal_idx) < max(4, n_base // 2):
		raise SchemaMismatch(f"only {len(normal_idx)} normal parts; the baseline needs {n_base}")
	base_idx = normal_idx[:n_base]
	base_set = set(base_idx)
	rest = [i for i in range(len(parts)) if i not in base_set]
	order = base_idx + rest  # Phase I parts first, then every later part in production order

	# Spread a small feature budget over sensors and both operations rather than spending it all on
	# the first channel: means first, in the channel order the manifest gives, then peaks, then RMS.
	cols = ds["columns"]
	present = {k for p in parts for k in p["features"]}
	keys = [
		f"{op}/{ch}/{stat}"
		for stat in ("mean", "peak", "rms")
		for ch in cols["channels"]
		for op in cols["operations"]
		if f"{op}/{ch}/{stat}" in present
	]
	chosen = []
	for k in keys:
		vals = [parts[i]["features"].get(k) for i in order]
		if any(v is None for v in vals):
			continue
		if _varying([parts[i]["features"][k] for i in base_idx]):
			chosen.append(k)
	chosen = chosen[:max_features]
	if not chosen:
		raise SchemaMismatch("no feature present on every part with a varying baseline")
	series = {k: [parts[i]["features"][k] for i in order] for k in chosen}
	worst, mismatch, nan_leaks, signals = _chart_check(spc, series, {k: len(base_idx) for k in chosen})
	checks = _spc_checks(Check, worst, mismatch, nan_leaks, len(chosen))

	# Energy per part through FoaMES's specific-consumption KPI, per operation, normal parts only.
	energy_ok, energy = True, {}
	for op in ds["columns"]["operations"]:
		js = [parts[i]["energy_j"][op] for i in normal_idx if op in parts[i]["energy_j"]]
		if not js:
			continue
		kwh = sum(js) / 3.6e6
		got = kpi.specific_consumption(kwh, len(js))
		exp = kwh / len(js)
		energy_ok &= got is not None and _close(got, exp)
		energy[op] = {"parts": len(js), "kwh_per_part": exp, "foames": got}
	none_ok = kpi.specific_consumption(1.0, 0) is None
	checks.append(
		Check(
			"kpi/energy-per-part",
			energy_ok and none_ok and bool(energy),
			True,
			energy_ok and none_ok,
			"spindle energy per part, and no rate without output",
		)
	)

	eq_checks, eq_metrics = check_equipment(Check, ds.get("equipment", []))
	checks += eq_checks

	# The study: reported, not graded.
	pos = {i: n for n, i in enumerate(order)}
	evaluated = [i for i in rest]
	flagged = {i for i in evaluated if any(pos[i] in signals[k] for k in chosen)}
	by_batch = {}
	for i in evaluated:
		p = parts[i]
		b = by_batch.setdefault(
			p["batch"], {"deviation": p["deviation"], "abnormal": p["abnormal"], "parts": 0, "flagged": 0}
		)
		b["parts"] += 1
		b["flagged"] += i in flagged
	norm_eval = [i for i in evaluated if not parts[i]["abnormal"]]
	abn_eval = [i for i in evaluated if parts[i]["abnormal"]]
	base_vals = {k: [parts[i]["features"][k] for i in base_idx] for k in chosen}
	sensors = {}
	for batch, info in sorted(by_batch.items()):
		if not info["abnormal"]:
			continue
		members = [i for i in evaluated if parts[i]["batch"] == batch]
		ranked = []
		for k in chosen:
			d = cohens_d(base_vals[k], [parts[i]["features"][k] for i in members])
			hit = sum(pos[i] in signals[k] for i in members)
			if d is not None:
				ranked.append((abs(d), k, d, hit))
		ranked.sort(reverse=True)
		sensors[batch] = [
			{"feature": k, "cohens_d": round(d, 2), "parts_flagged": h, "of": len(members)}
			for _, k, d, h in ranked[:5]
		]
	energy_shift = {}
	for batch in by_batch:
		for op in ds["columns"]["operations"]:
			a = [parts[i]["energy_j"].get(op) for i in base_idx]
			b = [parts[i]["energy_j"].get(op) for i in evaluated if parts[i]["batch"] == batch]
			a, b = [x for x in a if x is not None], [x for x in b if x is not None]
			if a and b and statistics.fmean(a):
				energy_shift.setdefault(batch, {})[op] = round(
					100 * (statistics.fmean(b) / statistics.fmean(a) - 1), 1
				)
	metrics = {
		"parts": len(parts),
		"baseline_parts": [parts[i]["part"] for i in base_idx],
		"features_charted": len(chosen),
		"part_recall": (len(flagged & set(abn_eval)) / len(abn_eval)) if abn_eval else None,
		"false_alarm_rate": (len(flagged & set(norm_eval)) / len(norm_eval)) if norm_eval else None,
		"by_batch": by_batch,
		"sensors_by_deviation": sensors,
		"energy_change_percent": energy_shift,
		"energy_per_part": energy,
		**eq_metrics,
	}
	return checks, metrics, study_notes_turning(metrics)


def study_notes_turning(m: dict) -> list[str]:
	lines = ["### Equipment study: CNC lathe", ""]
	lines.append(
		f"{m['parts']} parts; limits from {len(m['baseline_parts'])} normal parts, {m['features_charted']} features charted. "
		+ "A part counts as flagged when any feature is beyond its limits."
	)
	lines += ["", "| Batch | Deviation | Abnormal | Parts | Flagged |", "| --- | --- | --- | --- | --- |"]
	for batch, b in sorted(m["by_batch"].items()):
		lines.append(
			f"| {batch} | {b['deviation'] or '-'} | {'yes' if b['abnormal'] else 'no'} | {b['parts']} | {b['flagged']} |"
		)
	fa, rc = m["false_alarm_rate"], m["part_recall"]
	lines += ["", f"Part recall {_pct(rc)}, false-alarm rate on later normal parts {_pct(fa)}."]
	if m["sensors_by_deviation"]:
		lines += ["", "Features that separate each deviation from the baseline most (Cohen's d):", ""]
		for batch, rows in m["sensors_by_deviation"].items():
			top = ", ".join(
				f"`{r['feature']}` d={r['cohens_d']} ({r['parts_flagged']}/{r['of']} flagged)"
				for r in rows[:3]
			)
			lines.append(f"- {batch}: {top}")
	if m["energy_change_percent"]:
		lines += [
			"",
			"Spindle energy per operation, change from the baseline mean (percent): "
			+ json.dumps(m["energy_change_percent"], sort_keys=True),
		]
	lines += _equipment_lines(m)
	return lines


def _pct(x) -> str:
	return "n/a" if x is None else f"{100 * x:.0f}%"


def _equipment_lines(m: dict) -> list[str]:
	lines = [
		"",
		"| Machine | ECL class | ECL | Minimum tier | Oversight | oss / baseline / frontier | Rating |",
		"| --- | --- | --- | --- | --- | --- | --- |",
	]
	for e in m.get("equipment", []):
		el = " / ".join("yes" if e["eligible"][t] else "no" for t in TIERS)
		lines.append(
			f"| {e['machine']} | {e['ecl_class']} | {e['ecl']} | {e['min_tier']} | {e['oversight']} | {el} | {'ai-initial draft' if e['draft_rating'] else 'reviewed'} |"
		)
	return lines


# ------------------------------------------------------------- CNC milling fleet (vibration)

FILE_RE = re.compile(r"(M\d{2})_([A-Za-z]{3})_(\d{4})_(OP\d{2})_(\d+)", re.I)


def _mill_rows(path: Path, columns: dict) -> list[tuple[float, float, float]]:
	text = path.read_text(encoding="utf-8-sig", errors="replace")
	lines = [ln for ln in text.splitlines() if ln.strip()]
	if not lines:
		return []
	delim = ";" if lines[0].count(";") > lines[0].count(",") else ","
	first = [c.strip() for c in lines[0].split(delim)]
	idx = None
	if any(_float(c) is None for c in first):
		for cand in columns["axes"]:
			if all(c in first for c in cand):
				idx = [first.index(c) for c in cand]
				break
		if idx is None:
			lower = [c.lower() for c in first]
			for cand in columns["axes"]:
				if all(c.lower() in lower for c in cand):
					idx = [lower.index(c.lower()) for c in cand]
					break
		body = lines[1:]
	else:
		body = lines
	out = []
	for ln in body:
		cells = ln.split(delim)
		if idx is None:
			nums = [_float(c) for c in cells]
			nums = [v for v in nums if v is not None]
			if len(nums) < 3:
				continue
			out.append(tuple(nums[-3:]))
		else:
			try:
				vals = tuple(_float(cells[j]) for j in idx)
			except IndexError:
				continue
			if None not in vals:
				out.append(vals)
	return out


def list_mill_files(folder: Path, ds: dict) -> list[dict]:
	files = []
	for p in _visible(folder, "*.csv"):
		m = FILE_RE.search(p.name)
		if not m:
			continue
		labels = {part.lower() for part in p.parts}
		if "bad" in labels:
			bad = True
		elif "good" in labels:
			bad = False
		else:
			continue
		machine, mon, year, op, n = m.groups()
		files.append(
			{
				"path": p,
				"machine": machine.upper(),
				"op": op.upper(),
				"when": datetime.strptime(f"{mon.title()} {year}", "%b %Y"),
				"n": int(n),
				"bad": bad,
			}
		)
	if not files:
		raise SchemaMismatch(f"{folder}: no CSV named like M01_Aug_2019_OP00_000.csv under good/ or bad/")
	files.sort(key=lambda f: (f["machine"], f["op"], f["when"], f["n"], f["bad"]))
	return files


def _spread(items, k):
	if k >= len(items):
		return items
	step = len(items) / k
	return [items[int(i * step)] for i in range(k)]


def load_milling(folder: Path, ds: dict, max_rows: int | None) -> dict:
	"""Per file: machine, operation, timeframe, label and per-axis RMS and peak acceleration. A stage
	limit spreads its file budget evenly over machines and operations, in time order."""
	files = list_mill_files(folder, ds)
	groups = {}
	for f in files:
		groups.setdefault((f["machine"], f["op"]), []).append(f)
	if max_rows:
		per = max(6, max_rows // len(groups))
		files = [f for g in groups.values() for f in _spread(g, per)]
	rate = ds["columns"].get("sample_rate_hz", 2000)
	records = []
	for f in files:
		rows = _mill_rows(f["path"], ds["columns"])
		if len(rows) < 2:
			continue
		feats = {}
		for a, axis in enumerate("xyz"):
			col = [r[a] for r in rows]
			centred = statistics.fmean(col)
			feats[f"rms_{axis}"] = rms([v - centred for v in col])
			feats[f"peak_{axis}"] = max(abs(v - centred) for v in col)
		feats["duration_s"] = len(rows) / rate
		records.append(
			{k: f[k] for k in ("machine", "op", "when", "n", "bad")}
			| {"features": feats, "file": f["path"].name}
		)
	if not records:
		raise SchemaMismatch(f"{folder}: mill files have no three numeric axis columns")
	return {"files": records}


def check_milling(data: dict, ds: dict, max_features: int) -> tuple[list, dict, list[str]]:
	from .mfgdata import Check

	spc = _foames("spc")
	share = ds.get("study", {}).get("baseline_share", 0.3)
	min_base = ds.get("study", {}).get("min_baseline", 8)
	groups = {}
	for r in data["files"]:
		groups.setdefault((r["machine"], r["op"]), []).append(r)
	feats = ds["columns"].get("features", ["rms_x", "rms_y", "rms_z"])[: max(1, max_features)]
	series, baselines, layout, limits = {}, {}, {}, {}
	for key, rs in sorted(groups.items()):
		good = [r for r in rs if not r["bad"]]
		nb = max(min_base, int(len(good) * share))
		if len(good) < nb + 1:
			continue
		base = good[:nb]
		ids = {id(r) for r in base}
		order = base + [r for r in rs if id(r) not in ids]
		layout[key] = order
		for f in feats:
			vals = [r["features"][f] for r in order]
			if not _varying(vals[:nb]):
				continue
			series[(key, f)] = vals
			baselines[(key, f)] = nb
			limits[(key, f)] = _imr(vals, nb)
	if not series:
		raise SchemaMismatch(f"no machine/operation group with {min_base}+ good files for a baseline")
	worst, mismatch, nan_leaks, signals = _chart_check(spc, series, baselines)
	checks = _spc_checks(Check, worst, mismatch, nan_leaks, len(series))
	eq_checks, eq_metrics = check_equipment(Check, ds.get("equipment", []))
	checks += eq_checks

	per_machine = {}
	for key, order in layout.items():
		nb = next(baselines[(key, f)] for f in feats if (key, f) in baselines)
		for pos, r in enumerate(order):
			if pos < nb:
				continue
			hit = any(pos in signals.get((key, f), ()) for f in feats)
			m = per_machine.setdefault(
				key[0], {"good": 0, "good_flagged": 0, "bad": 0, "bad_flagged": 0, "operations": set()}
			)
			m["operations"].add(key[1])
			kind = "bad" if r["bad"] else "good"
			m[kind] += 1
			m[f"{kind}_flagged"] += hit
	for m in per_machine.values():
		m["operations"] = len(m["operations"])
		m["recall"] = m["bad_flagged"] / m["bad"] if m["bad"] else None
		m["false_alarm_rate"] = m["good_flagged"] / m["good"] if m["good"] else None

	# Transfer: limits learned on one mill, applied to another mill's good files for the same operation.
	transfer = []
	ops = {}
	for machine, op in layout:
		ops.setdefault(op, []).append(machine)
	for op, machines in sorted(ops.items()):
		for a in machines:
			for b in machines:
				if a == b:
					continue
				goods = [r for r in groups[(b, op)] if not r["bad"]]
				flagged = 0
				for r in goods:
					flagged += any(
						not (limits[((a, op), f)][2] <= r["features"][f] <= limits[((a, op), f)][1])
						for f in feats
						if ((a, op), f) in limits
					)
				if goods:
					transfer.append(
						{
							"op": op,
							"limits_from": a,
							"applied_to": b,
							"good_files": len(goods),
							"flagged_share": flagged / len(goods),
						}
					)
	shares = [t["flagged_share"] for t in transfer]
	metrics = {
		"files": len(data["files"]),
		"machines": sorted({k[0] for k in groups}),
		"operations": len({k[1] for k in groups}),
		"charts": len(series),
		"per_machine": per_machine,
		"transfer_pairs": len(transfer),
		"transfer_median_good_flagged": statistics.median(shares) if shares else None,
		"transfer": transfer,
		**eq_metrics,
	}
	return checks, metrics, study_notes_milling(metrics)


def study_notes_milling(m: dict) -> list[str]:
	lines = ["### Equipment study: CNC milling fleet", ""]
	lines.append(
		f"{m['files']} recordings from {len(m['machines'])} machines and {m['operations']} operations; "
		+ f"{m['charts']} charts, limits from each machine and operation's earliest good recordings."
	)
	lines += [
		"",
		"| Machine | Operations | Bad flagged | Good flagged (false alarms) |",
		"| --- | --- | --- | --- |",
	]
	for machine, s in sorted(m["per_machine"].items()):
		lines.append(
			f"| {machine} | {s['operations']} | {s['bad_flagged']}/{s['bad']} ({_pct(s['recall'])}) | {s['good_flagged']}/{s['good']} ({_pct(s['false_alarm_rate'])}) |"
		)
	if m["transfer_pairs"]:
		share = m["transfer_median_good_flagged"]
		own = [s["false_alarm_rate"] for s in m["per_machine"].values() if s["false_alarm_rate"] is not None]
		line = (
			f"Limits carried from one mill to another for the same operation flag a median {_pct(share)} "
			+ f"of the other mill's good recordings ({m['transfer_pairs']} machine pairs), against "
			+ f"{_pct(statistics.median(own) if own else None)} on each mill's own later good recordings."
		)
		if own and share is not None and share >= max(0.25, 2 * statistics.median(own)):
			line += " Set limits per machine, not per machine model."
		lines += ["", line]
	lines += _equipment_lines(m)
	return lines


# ------------------------------------------------------------------------------ synthetic


def synthetic_turning(folder: Path, seed: int, points: int = 128) -> Path:
	"""Invented parts in XQuality's documented layout. Not real data."""
	rng = random.Random(seed)
	root = folder / "xquality-dataset"
	data = root / "data"
	data.mkdir(parents=True, exist_ok=True)
	batches = (
		[(n, "test 1", "normal", "standard production") for n in [*range(20, 61), 76, 77]]
		+ [(n, "test 2", "abnormal", "feedrate 80%") for n in range(61, 71)]
		+ [(n, "test 3", "abnormal", "material 316L") for n in range(71, 76)]
		+ [(n, "test 4", "abnormal", "wrong tools") for n in range(78, 82)]
	)
	batches.sort()
	scale = {
		"test 1": (1, 1, 1, 1),
		"test 2": (0.82, 0.85, 1.0, 1.25),
		"test 3": (1.15, 1.25, 1.05, 1.0),
		"test 4": (1.05, 1.05, 1.6, 1.0),
	}
	with (root / "labels.csv").open("w", newline="") as fh:
		w = csv.writer(fh)
		w.writerow(
			[
				"part_number",
				"part_folder",
				"test_batch",
				"label",
				"experiment_phase",
				"defect_detected",
				"explanation",
			]
		)
		for n, batch, label, phase in batches:
			w.writerow([f"{n:03d}", f"part_{n:03d}", batch, label, phase, "", "synthetic"])
			power, force, vib, slow = scale[batch]
			for op, secs in (("OP120", 6.0), ("OP130", 20.0)):
				d = data / f"part_{n:03d}" / op
				d.mkdir(parents=True, exist_ok=True)
				dur = secs * slow
				for ch, unit, level in (
					("AI1", "W", 900 * power),
					("FX", "N", 120 * force),
					("FY", "N", 80 * force),
					("FZ", "N", 300 * force),
					("VIB_1_RMS", "g", 0.8 * vib),
					("VIB_11_RMS", "Pa", 0.2 * vib),
				):
					lvl = level * rng.gauss(1, 0.02)
					with (d / f"{ch}_decimate.crv").open("w") as out:
						out.write(f"Time (s);{ch} ({unit})\n")
						for i in range(points):
							t = dur * i / (points - 1)
							out.write(
								f"{t:.6f};{lvl * (1 + 0.05 * math.sin(i / 5)) + rng.gauss(0, lvl * 0.01):.6f}\n"
							)
	return folder


def synthetic_milling(folder: Path, seed: int, rows: int = 200) -> Path:
	"""Invented vibration recordings in the CNC milling dataset's layout. Not real data."""
	rng = random.Random(seed)
	frames = [("Aug", 2019), ("Feb", 2020), ("Aug", 2020), ("Feb", 2021)]
	for mi, machine in enumerate(("M01", "M02", "M03")):
		for op in ("OP01", "OP04", "OP07"):
			for label in ("good", "bad"):
				(folder / "data" / machine / op / label).mkdir(parents=True, exist_ok=True)
			n = 0
			for mon, year in frames:
				for k in range(5):
					bad = k == 4 and (mon, year) != frames[0]
					amp = (1.0 + 0.25 * mi) * (2.2 if bad else 1.0)
					name = f"{machine}_{mon}_{year}_{op}_{n:03d}.csv"
					n += 1
					path = folder / "data" / machine / op / ("bad" if bad else "good") / name
					with path.open("w") as out:
						out.write("X,Y,Z\n")
						for i in range(rows):
							out.write(
								",".join(
									f"{amp * a * math.sin(i / (3 + a)) + rng.gauss(0, 0.05 * amp):.5f}"
									for a in (1, 2, 3)
								)
								+ "\n"
							)
	return folder
