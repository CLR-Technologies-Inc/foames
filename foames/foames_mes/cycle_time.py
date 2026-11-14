# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Automatic and manual time: an operation's cycle split into machine time and operator time, its
projection over a quantity, what-if scenarios such as automating a manual step, and a comparison
with what the machine actually did. No Frappe dependency.

This is the arithmetic of a standard work combination sheet (time study practice):

- An **element** is one step of the operation with a standard time in seconds. It is **Automatic**
  (the machine works, the operator is free) or **Manual** (an operator works).
- A manual element is **external** when the machine must wait for it (loading and unloading a
  machine that is stopped), and **internal** when the operator does it while the machine runs
  (deburring the previous part, inspecting, walking to the next machine). The same split is the
  internal and external setup of SMED.
- An element happens every cycle, or once every N cycles (a gauge check every 10 parts), or once
  per batch (setup, first-article inspection, warm-up).
- Manual time carries a personal, fatigue and delay allowance in percent. Machine time does not.

For one cycle:

    cycle = manual external + max(automatic, manual internal)

When internal manual work is longer than the machine's automatic time the machine waits for the
operator (interference); when it is shorter the operator waits for the machine. The number of
identical machines one operator can tend is cycle / operator time (Groover's n'), rounded down.

Observed time comes from the state ledger FoaMES already keeps: Running time is automatic time;
Idle time between counted cycles is an upper bound on external manual time plus waiting, since a
machine cannot tell an operator loading it from a starved machine. Unknown time is never counted.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

KINDS = ("Manual", "Automatic")
PER = ("Cycle", "Batch")
DEFAULT_MIN_CYCLES = 20


@dataclass(frozen=True)
class Element:
	name: str
	kind: str = "Manual"
	seconds: float = 0.0
	per: str = "Cycle"
	internal: bool = False
	every: float = 1.0

	def per_cycle(self) -> float:
		"""Standard seconds this element adds to one cycle (before allowance)."""
		if self.per != "Cycle":
			return 0.0
		return self.seconds / (self.every or 1.0)


@dataclass(frozen=True)
class Standard:
	elements: tuple[Element, ...] = ()
	parts_per_cycle: float = 1.0
	allowance_percent: float = 0.0
	labor_rate: float = 0.0
	machine_rate: float = 0.0
	name: str = ""

	@property
	def allowance(self) -> float:
		return 1.0 + max(self.allowance_percent or 0.0, 0.0) / 100.0


@dataclass
class CycleBreakdown:
	automatic: float = 0.0
	manual_external: float = 0.0
	manual_internal: float = 0.0
	cycle: float = 0.0
	operator: float = 0.0
	machine_waits: float = 0.0
	operator_waits: float = 0.0
	machines_per_operator: float | None = None
	setup_manual: float = 0.0
	setup_automatic: float = 0.0
	notes: list[str] = field(default_factory=list)

	@property
	def manual(self) -> float:
		return self.manual_external + self.manual_internal

	def as_dict(self) -> dict:
		return {
			"automatic_seconds": self.automatic,
			"manual_seconds": self.manual,
			"manual_external_seconds": self.manual_external,
			"manual_internal_seconds": self.manual_internal,
			"cycle_seconds": self.cycle,
			"operator_seconds": self.operator,
			"machine_waits_seconds": self.machine_waits,
			"operator_waits_seconds": self.operator_waits,
			"machines_per_operator": self.machines_per_operator,
			"automation_percent": automation_percent(self),
			"setup_manual_seconds": self.setup_manual,
			"setup_automatic_seconds": self.setup_automatic,
			"notes": list(self.notes),
		}


def automation_percent(b: CycleBreakdown) -> float:
	"""Share of the cycle the machine works without an operator, in percent."""
	return b.automatic / b.cycle * 100.0 if b.cycle > 0 else 0.0


def problems(standard: Standard) -> list[str]:
	"""What is wrong with a standard, in words; empty when it can be used."""
	out = []
	if not standard.parts_per_cycle or standard.parts_per_cycle <= 0:
		out.append("parts per cycle must be positive")
	if (standard.allowance_percent or 0) < 0:
		out.append("the allowance cannot be negative")
	seen = set()
	for e in standard.elements:
		label = e.name or "an element"
		if e.kind not in KINDS:
			out.append(f"{label}: kind must be one of {', '.join(KINDS)}")
		if e.per not in PER:
			out.append(f"{label}: per must be one of {', '.join(PER)}")
		if e.seconds is None or e.seconds < 0:
			out.append(f"{label}: seconds cannot be negative")
		if e.every is not None and e.every <= 0:
			out.append(f"{label}: every N cycles must be positive")
		if e.name and e.name in seen:
			out.append(f"{label}: element names must be unique")
		seen.add(e.name)
	if not any(e.per == "Cycle" and e.seconds > 0 for e in standard.elements):
		out.append("the standard has no element with time per cycle")
	return out


def breakdown(standard: Standard) -> CycleBreakdown:
	"""One cycle of the standard, split into automatic and manual time."""
	b = CycleBreakdown()
	allowance = standard.allowance
	for e in standard.elements:
		if e.per == "Batch":
			if e.kind == "Automatic":
				b.setup_automatic += e.seconds
			else:
				b.setup_manual += e.seconds * allowance
			continue
		seconds = e.per_cycle()
		if e.kind == "Automatic":
			b.automatic += seconds
		elif e.internal:
			b.manual_internal += seconds * allowance
		else:
			b.manual_external += seconds * allowance
	b.cycle = b.manual_external + max(b.automatic, b.manual_internal)
	b.operator = b.manual
	b.machine_waits = max(b.manual_internal - b.automatic, 0.0)
	b.operator_waits = max(b.automatic - b.manual_internal, 0.0)
	b.machines_per_operator = b.cycle / b.operator if b.operator > 0 else None
	if b.machine_waits > 0:
		b.notes.append(
			f"internal manual work is {b.machine_waits:.1f} s longer than the machine's automatic time,"
			" so the machine waits for the operator every cycle"
		)
	if b.operator == 0:
		b.notes.append("the cycle has no manual time; machines per operator has no limit from this operation")
	return b


def project(standard: Standard, quantity: float, b: CycleBreakdown | None = None) -> dict:
	"""Time for `quantity` parts: elapsed machine time, operator time, automatic time, and cost.

	Batch elements are counted once. Cycles are whole: 7 parts at 2 per cycle take 4 cycles.
	"""
	b = b or breakdown(standard)
	quantity = max(float(quantity or 0), 0.0)
	cycles = math.ceil(quantity / standard.parts_per_cycle - 1e-9) if quantity else 0
	setup = b.setup_manual + b.setup_automatic
	run = cycles * b.cycle
	elapsed = setup + run
	operator = b.setup_manual + cycles * b.operator
	automatic = b.setup_automatic + cycles * b.automatic
	labor_cost = operator / 3600.0 * (standard.labor_rate or 0.0)
	machine_cost = elapsed / 3600.0 * (standard.machine_rate or 0.0)
	per_part = (labor_cost + machine_cost) / quantity if quantity else 0.0
	return {
		"standard": standard.name,
		"quantity": quantity,
		"cycles": cycles,
		"cycle": b.as_dict(),
		"setup_minutes": setup / 60.0,
		"run_minutes": run / 60.0,
		"elapsed_minutes": elapsed / 60.0,
		"automatic_minutes": automatic / 60.0,
		"manual_minutes": operator / 60.0,
		"operator_minutes": operator / 60.0,
		"machine_minutes": elapsed / 60.0,
		"operator_waits_minutes": cycles * b.operator_waits / 60.0,
		"machine_waits_minutes": cycles * b.machine_waits / 60.0,
		"parts_per_hour": quantity / (elapsed / 3600.0) if elapsed > 0 else 0.0,
		"labor_cost": labor_cost,
		"machine_cost": machine_cost,
		"cost_per_part": per_part,
		"notes": list(b.notes),
	}


def apply_changes(standard: Standard, changes: list[dict] | None) -> Standard:
	"""A copy of the standard with scenario changes applied.

	Each change names an `element` and sets any of `kind`, `seconds`, `internal`, `every`, `per`,
	or `remove: true`. A change naming an element that does not exist adds it. A change with no
	`element` may set `parts_per_cycle`, `allowance_percent`, `labor_rate` or `machine_rate`.
	"""
	elements = list(standard.elements)
	top = {}
	for change in changes or []:
		change = dict(change)
		name = change.pop("element", None)
		if not name:
			for key in ("parts_per_cycle", "allowance_percent", "labor_rate", "machine_rate"):
				if key in change:
					top[key] = float(change[key])
			continue
		remove = bool(change.pop("remove", False))
		fields = {k: change[k] for k in ("kind", "seconds", "internal", "every", "per") if k in change}
		for key in ("seconds", "every"):
			if key in fields:
				fields[key] = float(fields[key])
		if "internal" in fields:
			fields["internal"] = bool(fields["internal"])
		index = next((i for i, e in enumerate(elements) if e.name == name), None)
		if index is None:
			if not remove:
				elements.append(Element(name=name, **fields))
			continue
		if remove:
			elements.pop(index)
		else:
			elements[index] = replace(elements[index], **fields)
	return replace(standard, elements=tuple(elements), **top)


DELTA_KEYS = (
	"elapsed_minutes",
	"automatic_minutes",
	"manual_minutes",
	"operator_minutes",
	"parts_per_hour",
	"labor_cost",
	"machine_cost",
	"cost_per_part",
)


def compare(baseline: dict, scenario: dict, annual_quantity: float | None = None) -> dict:
	"""Scenario minus baseline for the headline figures, and what that is worth over a year."""
	delta = {key: scenario[key] - baseline[key] for key in DELTA_KEYS}
	delta["cycle_seconds"] = scenario["cycle"]["cycle_seconds"] - baseline["cycle"]["cycle_seconds"]
	delta["automation_percent"] = (
		scenario["cycle"]["automation_percent"] - baseline["cycle"]["automation_percent"]
	)
	out = {"baseline": baseline, "scenario": scenario, "delta": delta}
	if annual_quantity and baseline["quantity"]:
		scale = float(annual_quantity) / baseline["quantity"]
		out["annual"] = {
			"quantity": float(annual_quantity),
			"operator_hours_saved": -delta["operator_minutes"] * scale / 60.0,
			"machine_hours_saved": -delta["elapsed_minutes"] * scale / 60.0,
			"cost_saved": -(delta["labor_cost"] + delta["machine_cost"]) * scale,
		}
	return out


def observed(
	running_seconds: float,
	idle_seconds: float,
	setup_seconds: float,
	parts: float,
	parts_per_cycle: float = 1.0,
) -> dict:
	"""Observed automatic and between-cycle time per cycle from a machine's state ledger and counts.

	Running time over cycles is the observed automatic time. Idle time over cycles is an upper bound
	on external manual time (it also holds starvation and blocking). Setup time is reported apart.
	With no parts there is nothing to divide by and every per-cycle figure is None.
	"""
	parts_per_cycle = parts_per_cycle if parts_per_cycle and parts_per_cycle > 0 else 1.0
	cycles = max(float(parts or 0), 0.0) / parts_per_cycle
	out = {
		"parts": float(parts or 0),
		"cycles": cycles,
		"running_minutes": running_seconds / 60.0,
		"idle_minutes": idle_seconds / 60.0,
		"setup_minutes": setup_seconds / 60.0,
		"automatic_seconds": None,
		"idle_seconds_per_cycle": None,
		"cycle_seconds": None,
	}
	if cycles > 0:
		out["automatic_seconds"] = running_seconds / cycles
		out["idle_seconds_per_cycle"] = idle_seconds / cycles
		out["cycle_seconds"] = (running_seconds + idle_seconds) / cycles
	return out


def variance(standard_seconds: float, observed_seconds: float | None) -> float | None:
	"""Observed against standard, in percent; positive means slower than standard."""
	if observed_seconds is None or not standard_seconds:
		return None
	return (observed_seconds - standard_seconds) / standard_seconds * 100.0


def calibrate(
	standard: Standard, obs: dict, min_cycles: float = DEFAULT_MIN_CYCLES
) -> tuple[Standard, list[str]]:
	"""The standard with its automatic per-cycle elements scaled to the observed automatic time.

	Only automatic time is calibrated: a machine signal measures it directly. Manual time stays at
	standard, because Idle time cannot tell operator work from waiting. Below `min_cycles` observed
	cycles, or without automatic elements, the standard is returned unchanged with a note.
	"""
	notes = []
	auto_elements = [e for e in standard.elements if e.kind == "Automatic" and e.per == "Cycle"]
	standard_auto = sum(e.per_cycle() for e in auto_elements)
	if obs.get("automatic_seconds") is None or obs.get("cycles", 0) < min_cycles:
		notes.append(
			f"observed {obs.get('cycles', 0):.0f} cycles, fewer than {min_cycles:g}; using standard times"
		)
		return standard, notes
	if standard_auto <= 0:
		notes.append("the standard has no automatic time per cycle to calibrate")
		return standard, notes
	factor = obs["automatic_seconds"] / standard_auto
	elements = tuple(
		replace(e, seconds=e.seconds * factor) if e in auto_elements else e for e in standard.elements
	)
	notes.append(
		f"automatic time scaled by {factor:.3f} to the observed {obs['automatic_seconds']:.1f} s"
		f" per cycle over {obs['cycles']:.0f} cycles"
	)
	return replace(standard, elements=elements), notes


def standard_from_dict(data: dict) -> Standard:
	"""A Standard from plain values (a saved document's dict or an API body)."""
	elements = tuple(
		Element(
			name=row.get("element_name") or row.get("name") or "",
			kind=row.get("kind") or "Manual",
			seconds=float(row.get("seconds") or 0),
			per=row.get("per") or "Cycle",
			internal=bool(row.get("internal")),
			every=float(row.get("every_n_cycles") or row.get("every") or 1),
		)
		for row in data.get("elements") or []
	)
	return Standard(
		elements=elements,
		parts_per_cycle=float(data.get("parts_per_cycle") or 1),
		allowance_percent=float(data.get("allowance_percent") or 0),
		labor_rate=float(data.get("labor_rate") or 0),
		machine_rate=float(data.get("machine_rate") or 0),
		name=data.get("name") or "",
	)
