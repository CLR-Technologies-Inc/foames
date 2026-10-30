# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""OEE as pure arithmetic, with a time ledger that accounts for every minute.

Availability = run time / (planned time - planned downtime)
Performance  = (ideal cycle time x total count) / run time, capped at 100 percent
Quality      = good count / total count
OEE          = availability x performance x quality

Time with no machine signal is "unknown" and counts as loss, never as run time. Planned downtime
(changeovers, scheduled maintenance) is excluded from the availability base. No Frappe dependency.
"""

from dataclasses import dataclass, field


@dataclass
class TimeLedger:
	planned_minutes: float
	run_minutes: float = 0.0
	planned_downtime_minutes: float = 0.0
	unplanned_downtime_minutes: float = 0.0
	idle_minutes: float = 0.0
	setup_minutes: float = 0.0
	unknown_minutes: float = 0.0

	@property
	def accounted_minutes(self) -> float:
		return (
			self.run_minutes
			+ self.planned_downtime_minutes
			+ self.unplanned_downtime_minutes
			+ self.idle_minutes
			+ self.setup_minutes
			+ self.unknown_minutes
		)

	@property
	def coverage(self) -> float:
		"""Share of the planned period with a known machine state."""
		if self.planned_minutes <= 0:
			return 0.0
		known = self.accounted_minutes - self.unknown_minutes
		return max(0.0, min(known / self.planned_minutes, 1.0))


@dataclass
class OEEResult:
	availability: float
	performance: float
	quality: float
	oee: float
	ledger: TimeLedger
	good_count: float = 0.0
	scrap_count: float = 0.0
	notes: list[str] = field(default_factory=list)


def compute_oee(
	ledger: TimeLedger, good_count: float, scrap_count: float, ideal_cycle_seconds: float | None
) -> OEEResult:
	notes = []
	available_base = ledger.planned_minutes - ledger.planned_downtime_minutes
	availability = ledger.run_minutes / available_base if available_base > 0 else 0.0
	availability = max(0.0, min(availability, 1.0))

	total = (good_count or 0) + (scrap_count or 0)
	if ideal_cycle_seconds and ideal_cycle_seconds > 0 and ledger.run_minutes > 0:
		performance = (ideal_cycle_seconds * total / 60.0) / ledger.run_minutes
		if performance > 1.0:
			notes.append("performance above 100 percent: check the ideal cycle time or the counters")
			performance = 1.0
	elif ledger.run_minutes > 0 and total > 0:
		performance = 1.0
		notes.append("no ideal cycle time on the machine: performance assumed 100 percent")
	else:
		performance = 0.0

	quality = (good_count or 0) / total if total > 0 else 0.0
	if ledger.unknown_minutes > 0:
		notes.append(f"{ledger.unknown_minutes:.0f} minutes without a machine signal counted as loss")
	return OEEResult(
		availability,
		performance,
		quality,
		availability * performance * quality,
		ledger,
		good_count,
		scrap_count,
		notes,
	)


def ledger_from_states(intervals: list[tuple[float, str, bool]], planned_minutes: float) -> TimeLedger:
	"""Build a ledger from (minutes, state, downtime_is_planned) intervals covering the period.

	States are Running, Idle, Down, Setup or Unknown. Any planned minutes the intervals do not
	cover are unknown.
	"""
	ledger = TimeLedger(planned_minutes=planned_minutes)
	for minutes, state, planned in intervals:
		if state == "Running":
			ledger.run_minutes += minutes
		elif state == "Down":
			if planned:
				ledger.planned_downtime_minutes += minutes
			else:
				ledger.unplanned_downtime_minutes += minutes
		elif state == "Idle":
			ledger.idle_minutes += minutes
		elif state == "Setup":
			ledger.setup_minutes += minutes
		else:
			ledger.unknown_minutes += minutes
	gap = planned_minutes - ledger.accounted_minutes
	if gap > 1e-9:
		ledger.unknown_minutes += gap
	return ledger
