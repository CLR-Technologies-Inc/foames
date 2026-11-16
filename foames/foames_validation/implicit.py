# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Implicit validation: requirement, metrology and statistical checks with reproducible evidence.

Pure: imports nothing from Frappe. Everything is a function of its inputs, including the time of
evaluation (`as_of`), so the same definition and dataset always give the same result and the same
hashes. The Frappe side (`implicit_api.py`, the Implicit Validation Run DocType) stores the bundle and
lets the write gate and other gates check it by ID.

A check returns one of four outcomes:

- Pass: the evidence is there and meets the criterion.
- Fail: the evidence is there and does not meet it.
- Indeterminate: the evidence is missing, too thin or not trustworthy (too few points, unknown time,
  no calibration record, an undeclared unit). Never Pass.
- Manual Review: a person has to inspect or decide; no automated result exists.

A run fails closed: any blocking check that is not Pass keeps the run from passing. A green run is
engineering evidence that a change behaved as expected. It is not a regulatory qualification, an
electronic signature, a production release or an authorisation to write; formal IQ, OQ, PQ, PPQ and
CPV stay in Validation Protocol and Validation Execution.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
from datetime import datetime, timezone
from itertools import pairwise

from foames.foames_validation import qualification as q

SCHEMA = "foames.implicit-validation/1.0"
EVALUATOR_VERSION = "1.0.0"

PASS = "Pass"
FAIL = "Fail"
INDETERMINATE = "Indeterminate"
MANUAL = "Manual Review"
OUTCOMES = (PASS, FAIL, INDETERMINATE, MANUAL)

KINDS = ("requirement", "metrology", "statistical", "manual")
CRITICALITIES = ("Low", "Medium", "High", "Critical")
TRIGGERS = (
	"On Demand",
	"Sandbox Change",
	"Configuration Proposal",
	"Pre-production Promotion",
	"Post-change Monitoring",
	"Scheduled CPV",
)
ENVIRONMENTS = ("Sandbox", "Integration", "Production Candidate", "Production")

# Requirement operators.
OPERATORS = ("eq", "ne", "lt", "le", "gt", "ge", "in", "not_in", "present", "absent")

# Metrology defaults.
DEFAULT_MIN_TUR = 4.0  # test uncertainty ratio: tolerance half-width over expanded uncertainty
GRR_ACCEPT = 10.0  # %GRR below: acceptable (AIAG MSA guidance)
GRR_REJECT = 30.0  # %GRR above: unacceptable; between: needs a person's decision

# Linear units: unit -> (dimension, factor to the dimension's base unit).
UNITS = {
	"m": ("length", 1.0),
	"cm": ("length", 1e-2),
	"mm": ("length", 1e-3),
	"um": ("length", 1e-6),
	"nm": ("length", 1e-9),
	"in": ("length", 0.0254),
	"kg": ("mass", 1.0),
	"g": ("mass", 1e-3),
	"mg": ("mass", 1e-6),
	"lb": ("mass", 0.45359237),
	"s": ("time", 1.0),
	"min": ("time", 60.0),
	"h": ("time", 3600.0),
	"Pa": ("pressure", 1.0),
	"kPa": ("pressure", 1e3),
	"MPa": ("pressure", 1e6),
	"bar": ("pressure", 1e5),
	"psi": ("pressure", 6894.757293168),
	"L": ("volume", 1e-3),
	"mL": ("volume", 1e-6),
	"m3": ("volume", 1.0),
	"%": ("ratio", 1e-2),
	"ppm": ("ratio", 1e-6),
}
# Temperatures have an offset: unit -> (factor, offset) to kelvin.
TEMPERATURES = {"K": (1.0, 0.0), "degC": (1.0, 273.15), "degF": (5.0 / 9.0, 459.67 * 5.0 / 9.0)}
UNIT_ALIASES = {"°C": "degC", "C": "degC", "°F": "degF", "F": "degF", "µm": "um", "l": "L", "ml": "mL"}


class DefinitionError(ValueError):
	"""The definition itself is malformed; nothing is evaluated."""


# Hashing -----------------------------------------------------------------------------------------


def canonical(value) -> str:
	"""Canonical JSON: sorted keys, no whitespace, so the same content always hashes the same."""
	return json.dumps(
		value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False, default=str
	)


def digest(value) -> str:
	return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


# Small helpers -----------------------------------------------------------------------------------


def _num(value):
	if value is None or value == "" or isinstance(value, bool):
		return None
	try:
		number = float(value)
	except (TypeError, ValueError):
		return None
	return number if math.isfinite(number) else None


def _time(value):
	"""A time as naive UTC. An aware time is converted; a naive one is taken to be UTC already."""
	if not value:
		return None
	if not isinstance(value, datetime):
		try:
			value = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
		except ValueError:
			return None
	if value.tzinfo is not None:
		value = value.astimezone(timezone.utc)
	return value.replace(tzinfo=None)


def _result(key, kind, outcome, summary, blocking=True, **evidence) -> dict:
	return {
		"key": key,
		"kind": kind,
		"outcome": outcome,
		"blocking": bool(blocking),
		"summary": summary,
		"evidence": evidence,
	}


def worst(outcomes) -> str:
	"""Fail before Indeterminate before Manual Review before Pass; Indeterminate when empty."""
	outcomes = list(outcomes)
	if not outcomes:
		return INDETERMINATE
	for outcome in (FAIL, INDETERMINATE, MANUAL):
		if outcome in outcomes:
			return outcome
	return PASS


def normalise_unit(unit):
	if unit is None:
		return None
	unit = str(unit).strip()
	return UNIT_ALIASES.get(unit, unit) or None


def convert(value: float, from_unit: str, to_unit: str) -> float:
	"""`value` in `from_unit` expressed in `to_unit`. Raises ValueError when the units are unknown
	or measure different things."""
	a, b = normalise_unit(from_unit), normalise_unit(to_unit)
	if a == b:
		return value
	if a in TEMPERATURES and b in TEMPERATURES:
		fa, oa = TEMPERATURES[a]
		fb, ob = TEMPERATURES[b]
		return (value * fa + oa - ob) / fb
	if a not in UNITS or b not in UNITS:
		raise ValueError(f"unknown unit {a if a not in UNITS else b!r}")
	(da, fa), (db, fb) = UNITS[a], UNITS[b]
	if da != db:
		raise ValueError(f"{a} measures {da}, {b} measures {db}")
	return value * fa / fb


def _path(config: dict, path: str):
	"""(found, value) for a dotted path into nested dicts and lists."""
	current = config
	for part in str(path).split("."):
		if isinstance(current, dict) and part in current:
			current = current[part]
		elif isinstance(current, list) and re.fullmatch(r"\d+", part) and int(part) < len(current):
			current = current[int(part)]
		else:
			return False, None
	return True, current


# Definition --------------------------------------------------------------------------------------


def validate_definition(definition: dict) -> dict:
	"""Check the shape of a definition and return it with defaults filled in. Raises DefinitionError."""
	if not isinstance(definition, dict):
		raise DefinitionError("a definition is a JSON object")
	if definition.get("schema", SCHEMA) != SCHEMA:
		raise DefinitionError(
			f"unsupported schema {definition.get('schema')!r}; this evaluator reads {SCHEMA}"
		)
	checks = definition.get("checks")
	if not isinstance(checks, list) or not checks:
		raise DefinitionError("a definition needs at least one check")
	seen = set()
	out = []
	for raw in checks:
		if not isinstance(raw, dict):
			raise DefinitionError("each check is a JSON object")
		check = dict(raw)
		key = str(check.get("key") or "").strip()
		if not key:
			raise DefinitionError("each check needs a key")
		if key in seen:
			raise DefinitionError(f"check key {key!r} is used twice")
		seen.add(key)
		if check.get("kind") not in KINDS:
			raise DefinitionError(f"check {key}: kind must be one of {', '.join(KINDS)}")
		check["key"] = key
		check["blocking"] = bool(check.get("blocking", True))
		criticality = check.get("criticality") or "Medium"
		if criticality not in CRITICALITIES:
			raise DefinitionError(f"check {key}: criticality must be one of {', '.join(CRITICALITIES)}")
		check["criticality"] = criticality
		# A critical check always blocks: it cannot be made advisory by its own definition.
		if criticality == "Critical":
			check["blocking"] = True
		if check["kind"] == "requirement":
			assertion = check.get("assert") or {}
			if assertion.get("op") not in OPERATORS or not assertion.get("path"):
				raise DefinitionError(f"check {key}: assert needs a path and an op ({', '.join(OPERATORS)})")
		if check["kind"] in ("metrology", "statistical") and not check.get("measurement"):
			raise DefinitionError(f"check {key}: name the measurement it reads")
		if check["kind"] == "statistical":
			check_type = check.get("check_type") or "Capability"
			if check_type not in ("Numeric Range", "Capability", "Statistical Control"):
				raise DefinitionError(
					f"check {key}: check_type must be Numeric Range, Capability or Statistical Control"
				)
			check["check_type"] = check_type
		out.append(check)
	return {
		"schema": SCHEMA,
		"name": str(definition.get("name") or ""),
		"version": str(definition.get("version") or "1"),
		"checks": out,
	}


# Evaluators --------------------------------------------------------------------------------------


def evaluate_requirement(check: dict, configuration: dict | None) -> dict:
	"""A configuration assertion: {"path": "a.b", "op": "le", "value": 5}. A missing path is
	Indeterminate (except for `absent`); a value of the wrong type is Fail."""
	key, blocking = check["key"], check["blocking"]
	assertion = check["assert"]
	op, path, expected = assertion["op"], assertion["path"], assertion.get("value")
	if configuration is None:
		return _result(key, "requirement", INDETERMINATE, "No configuration to check", blocking, path=path)
	found, actual = _path(configuration, path)
	# The value at the path is evidence, except where it may be a secret: `absent` exists to catch a
	# value that should not be there, and `sensitive: true` marks any other such path.
	hide = op == "absent" or bool(check.get("sensitive"))
	shown = "(not recorded)" if hide else actual
	evidence = {"path": path, "op": op, "expected": expected, "actual": shown if found else None}
	if op == "absent":
		outcome = FAIL if found else PASS
		return _result(
			key, "requirement", outcome, f"{path} {'is set' if found else 'is not set'}", blocking, **evidence
		)
	if not found:
		return _result(
			key, "requirement", INDETERMINATE, f"{path} is not in the configuration", blocking, **evidence
		)
	if op == "present":
		met = actual is not None and actual != ""
	elif op in ("in", "not_in"):
		if not isinstance(expected, list):
			raise DefinitionError(f"check {key}: {op} needs a list value")
		met = (actual in expected) == (op == "in")
	elif op in ("eq", "ne"):
		met = (actual == expected) == (op == "eq")
	else:
		a, e = _num(actual), _num(expected)
		if a is None or e is None:
			return _result(key, "requirement", FAIL, f"{path} is not a number", blocking, **evidence)
		met = {"lt": a < e, "le": a <= e, "gt": a > e, "ge": a >= e}[op]
	return _result(
		key,
		"requirement",
		PASS if met else FAIL,
		f"{path} = {shown!r} ({op} {expected!r}): {'met' if met else 'violated'}",
		blocking,
		**evidence,
	)


def _series(dataset: dict | None, name: str) -> dict | None:
	measurements = (dataset or {}).get("measurements") or {}
	return measurements.get(name)


def _points(series: dict) -> list[dict]:
	return [p for p in series.get("points") or [] if isinstance(p, dict)]


def evaluate_metrology(check: dict, dataset: dict | None, as_of: datetime) -> dict:
	"""Whether a measurement can be trusted: unit, calibration and traceability, time stamps and
	sampling interval, uncertainty against tolerance, bias against a reference, and %GRR from an MSA
	study. Each part is a sub-check; the metrology result is the worst of them."""
	key, blocking = check["key"], check["blocking"]
	name = check["measurement"]
	series = _series(dataset, name)
	parts: list[dict] = []

	def part(label, outcome, summary, **evidence):
		parts.append({"part": label, "outcome": outcome, "summary": summary, **evidence})

	if series is None:
		return _result(key, "metrology", INDETERMINATE, f"No data for {name}", blocking, parts=[])

	# Unit
	expected_unit, data_unit = normalise_unit(check.get("unit")), normalise_unit(series.get("unit"))
	if not expected_unit or not data_unit:
		part("unit", INDETERMINATE, "Unit not declared", expected=expected_unit, data=data_unit)
	else:
		try:
			convert(1.0, data_unit, expected_unit)
			part(
				"unit",
				PASS,
				f"{data_unit} is compatible with {expected_unit}",
				expected=expected_unit,
				data=data_unit,
			)
		except ValueError as error:
			part("unit", FAIL, f"Wrong unit: {error}", expected=expected_unit, data=data_unit)

	# Calibration and traceability
	instrument = check.get("instrument") or series.get("instrument") or {}
	due, calibrated = _time(instrument.get("calibration_due")), _time(instrument.get("calibrated_on"))
	if not instrument.get("id") or due is None:
		part("calibration", INDETERMINATE, "No instrument or calibration due date on record")
	elif due < as_of:
		part(
			"calibration",
			FAIL,
			f"Calibration of {instrument['id']} lapsed on {due:%Y-%m-%d}",
			instrument=instrument.get("id"),
		)
	elif calibrated is not None and calibrated > as_of:
		part(
			"calibration",
			INDETERMINATE,
			"Calibration date is after the evaluation time",
			instrument=instrument.get("id"),
		)
	else:
		part(
			"calibration",
			PASS,
			f"{instrument['id']} calibrated until {due:%Y-%m-%d}",
			instrument=instrument.get("id"),
		)
	if check.get("require_traceability", True):
		if instrument.get("traceability"):
			part("traceability", PASS, "Calibration traceable", reference=instrument["traceability"])
		else:
			part("traceability", INDETERMINATE, "No calibration certificate or traceability reference")

	# Time stamps and sampling interval
	points = _points(series)
	times = [_time(p.get("t")) for p in points]
	if not points:
		part("time", INDETERMINATE, "No readings")
	elif any(t is None for t in times):
		part(
			"time",
			INDETERMINATE,
			f"{sum(t is None for t in times)} readings have no or an unreadable time stamp",
		)
	elif any(t > as_of for t in times):
		part("time", INDETERMINATE, "Readings stamped after the evaluation time")
	elif any(b < a for a, b in pairwise(times)):
		part("time", FAIL, "Readings are out of time order")
	else:
		max_interval = _num(check.get("max_interval_seconds"))
		gaps = [(b - a).total_seconds() for a, b in pairwise(times)]
		worst_gap = max(gaps) if gaps else 0.0
		if max_interval is not None and worst_gap > max_interval:
			part(
				"time",
				FAIL,
				f"Sampling gap of {worst_gap:g} s exceeds {max_interval:g} s",
				worst_gap=worst_gap,
			)
		else:
			part("time", PASS, f"{len(points)} readings in order", worst_gap=worst_gap)
		max_age = _num(check.get("max_age_seconds"))
		if max_age is not None:
			age = (as_of - times[-1]).total_seconds()
			if age > max_age:
				part("freshness", FAIL, f"Latest reading is {age:g} s old (limit {max_age:g} s)", age=age)
			else:
				part("freshness", PASS, f"Latest reading is {age:g} s old", age=age)

	# Data-side numbers are compared with check-side numbers in the check's unit. A difference
	# (an uncertainty) scales without the temperature offset; a reading converts in full.
	def in_check_unit(value, difference=False):
		if value is None or not expected_unit or not data_unit:
			return value
		try:
			if difference:
				return value * (
					convert(1.0, data_unit, expected_unit) - convert(0.0, data_unit, expected_unit)
				)
			return convert(value, data_unit, expected_unit)
		except ValueError:
			return None  # the unit part has already failed

	# Uncertainty against tolerance (test uncertainty ratio)
	tolerance = _num(check.get("tolerance"))
	if check.get("uncertainty") is not None:
		uncertainty = _num(check.get("uncertainty"))
	else:
		uncertainty = in_check_unit(_num(series.get("uncertainty")), difference=True)
	if tolerance is not None:
		if uncertainty is None or uncertainty <= 0:
			part("uncertainty", INDETERMINATE, "No expanded measurement uncertainty on record")
		else:
			tur = tolerance / uncertainty
			minimum = _num(check.get("min_tur")) or DEFAULT_MIN_TUR
			part(
				"uncertainty",
				PASS if tur >= minimum else FAIL,
				f"Test uncertainty ratio {tur:.2f} (needs {minimum:g})",
				tur=tur,
			)

	# Bias against a reference standard
	reference, bias_limit = _num(check.get("reference_value")), _num(check.get("bias_limit"))
	if reference is not None and bias_limit is not None:
		values = [in_check_unit(_num(p.get("v"))) for p in points]
		values = [v for v in values if v is not None]
		if len(values) < 2:
			part("bias", INDETERMINATE, "Too few readings of the reference to judge bias")
		else:
			bias = statistics.fmean(values) - reference
			part(
				"bias",
				PASS if abs(bias) <= bias_limit else FAIL,
				f"Bias {bias:.4g} (limit ±{bias_limit:g})",
				bias=bias,
			)

	# Gauge repeatability and reproducibility from an MSA study
	if "grr_percent" in check:
		grr = _num(check.get("grr_percent"))
		if grr is None:
			part("grr", INDETERMINATE, "No gauge R&R study result")
		elif grr < GRR_ACCEPT:
			part("grr", PASS, f"%GRR {grr:g} (acceptable below {GRR_ACCEPT:g})", grr=grr)
		elif grr <= GRR_REJECT:
			part("grr", MANUAL, f"%GRR {grr:g}: marginal, a person decides", grr=grr)
		else:
			part("grr", FAIL, f"%GRR {grr:g} (unacceptable above {GRR_REJECT:g})", grr=grr)

	outcome = worst(p["outcome"] for p in parts)
	failing = [p["summary"] for p in parts if p["outcome"] != PASS]
	summary = "; ".join(failing) if failing else f"{name}: measurement fit for use"
	return _result(key, "metrology", outcome, summary, blocking, parts=parts)


def evaluate_statistical(check: dict, dataset: dict | None) -> dict:
	"""Specification limits, capability (Cp/Cpk/Pp/Ppk) or statistical control (run rules) of one
	measurement, through the same rules as Validation Execution, plus an optional drift check
	against a baseline mean. Values are converted to the check's unit first. Control and
	capability are separate checks: a process can be in control and not capable, or the reverse."""
	key, blocking = check["key"], check["blocking"]
	name = check["measurement"]
	series = _series(dataset, name)
	if series is None:
		return _result(key, "statistical", INDETERMINATE, f"No data for {name}", blocking)
	values = [_num(p.get("v")) for p in _points(series)]
	missing = sum(v is None for v in values)
	values = [v for v in values if v is not None]
	unit, data_unit = normalise_unit(check.get("unit")), normalise_unit(series.get("unit"))
	if unit and data_unit and unit != data_unit:
		try:
			values = [convert(v, data_unit, unit) for v in values]
		except ValueError as error:
			return _result(key, "statistical", FAIL, f"Wrong unit: {error}", blocking)
	elif unit and not data_unit:
		return _result(key, "statistical", INDETERMINATE, f"Unit of {name} not declared", blocking)
	criterion = {
		"check_type": check["check_type"],
		"lower_limit": check.get("lower_limit"),
		"upper_limit": check.get("upper_limit"),
		"min_points": check.get("min_points"),
		"capability_index": check.get("capability_index"),
		"min_index": check.get("min_index"),
		"rule_set": check.get("rule_set"),
	}
	try:
		judged = q.evaluate(criterion, {"values": values})
	except ValueError as error:
		raise DefinitionError(f"check {key}: {error}") from error
	outcome = {q.PASS: PASS, q.FAIL: FAIL}.get(judged["result"], INDETERMINATE)
	evidence = {
		"points": judged["points"],
		"missing_values": missing,
		"observed": judged["observed_value"],
		**judged["evidence"],
	}
	summary = judged["summary"]
	baseline, max_shift = _num(check.get("baseline_mean")), _num(check.get("max_shift"))
	if outcome != INDETERMINATE and baseline is not None and max_shift is not None and values:
		shift = statistics.fmean(values) - baseline
		evidence["drift"] = shift
		if abs(shift) > max_shift:
			outcome = FAIL
			summary += f"; mean drifted {shift:.4g} from the baseline (limit ±{max_shift:g})"
	return _result(key, "statistical", outcome, summary, blocking, **evidence)


def evaluate_check(check: dict, dataset: dict | None, configuration: dict | None, as_of: datetime) -> dict:
	kind = check["kind"]
	if kind == "requirement":
		result = evaluate_requirement(check, configuration)
	elif kind == "metrology":
		result = evaluate_metrology(check, dataset, as_of)
	elif kind == "statistical":
		result = evaluate_statistical(check, dataset)
	else:
		result = _result(
			check["key"],
			"manual",
			MANUAL,
			check.get("description") or "Needs a person's inspection or approval",
			check["blocking"],
		)
	result["criticality"] = check["criticality"]
	for field in ("owner", "source", "requirement"):
		if check.get(field):
			result[field] = check[field]
	return result


def run_outcome(results: list[dict]) -> str:
	"""Fail closed over the blocking checks: Fail, then Indeterminate, then Manual Review, else Pass.
	Non-blocking checks never make a run pass or fail; they are reported as warnings."""
	return worst(r["outcome"] for r in results if r["blocking"])


def evaluate(
	definition: dict,
	dataset: dict | None,
	configuration: dict | None,
	as_of,
	configuration_revision: str = "",
	environment: str = "",
) -> dict:
	"""Run every check of a definition and return the evidence bundle.

	`dataset`: {"id": ..., "measurements": {name: {"unit", "instrument", "uncertainty",
	"points": [{"t": iso time, "v": number}]}}}. `configuration`: the configuration under test (a
	dict). `as_of`: the evaluation time; it is part of the evidence, so a re-run with the same
	inputs reproduces the same hashes."""
	as_of = _time(as_of)
	if as_of is None:
		raise DefinitionError("an evaluation needs as_of")
	definition = validate_definition(definition)
	inputs = {
		"definition": definition,
		"dataset": dataset,
		"configuration": configuration,
		"configuration_revision": configuration_revision,
		"environment": environment,
		"as_of": as_of.isoformat(),
	}
	results = [evaluate_check(check, dataset, configuration, as_of) for check in definition["checks"]]
	outcome = run_outcome(results)
	bundle = {
		"schema": SCHEMA,
		"evaluator_version": EVALUATOR_VERSION,
		"definition": {
			"name": definition["name"],
			"version": definition["version"],
			"hash": digest(definition),
		},
		"dataset": {"id": (dataset or {}).get("id") or "", "hash": digest(dataset)},
		"configuration": {"revision": configuration_revision, "hash": digest(configuration)},
		"environment": environment,
		"as_of": as_of.isoformat(),
		"input_hash": digest(inputs),
		"outcome": outcome,
		"counts": {o: sum(r["outcome"] == o for r in results) for o in OUTCOMES},
		"manual_review": [r["key"] for r in results if r["outcome"] == MANUAL],
		"warnings": [r["key"] for r in results if not r["blocking"] and r["outcome"] != PASS],
		"checks": results,
	}
	bundle["result_hash"] = result_hash(bundle)
	return bundle


def result_hash(bundle: dict) -> str:
	"""SHA-256 of the bundle without its own result_hash: recomputed to detect a changed bundle."""
	return digest({k: v for k, v in bundle.items() if k != "result_hash"})


def verify_bundle(bundle: dict) -> bool:
	return bool(bundle) and bundle.get("result_hash") == result_hash(bundle)
