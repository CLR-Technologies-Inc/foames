# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Counter deltas that never invent production.

Machines report running totals. Production is the difference between two readings of the same
counter. A first reading, a reset, or a reading older than the last one yields zero, and a
rollover is handled only when the machine's rollover value is known. No Frappe dependency.
"""

# Counter names the gateways and machines use for good and scrapped production. Any other counter
# name is stored and shown but counts towards neither.
GOOD_COUNTERS = ("good", "count", "total", "parts")
SCRAP_COUNTERS = ("scrap", "reject", "bad", "ng")

# Counter names for metered inputs a machine consumes: energy, water, feed gas or material, steam,
# compressed air. A meter reports a running total just as a parts counter does, so the same delta
# rules apply. A name matches exactly ("energy") or with a unit suffix ("energy_kwh", "water_m3").
RESOURCE_COUNTERS = ("energy", "kwh", "power", "electricity", "water", "gas", "feed", "steam", "air", "fuel")


def counter_delta(previous: float | None, current: float, rollover: int | float | None = None) -> float:
	"""Production between two readings of a running counter."""
	if previous is None or current is None:
		return 0.0
	if current >= previous:
		return float(current - previous)
	if rollover and rollover > 0 and previous <= rollover:
		# The counter wrapped: count up to the rollover, then from zero.
		return float(rollover - previous + current)
	# A reset or an out-of-order reading. Nothing is invented.
	return 0.0


def minutes_between(start, end) -> float:
	return max((end - start).total_seconds() / 60.0, 0.0)


def good_and_scrap(totals: dict[str, float]) -> tuple[float, float]:
	"""Good and scrap production from per-counter totals such as {"good": 120, "scrap": 3}."""
	good = sum(v or 0 for k, v in totals.items() if k in GOOD_COUNTERS)
	scrap = sum(v or 0 for k, v in totals.items() if k in SCRAP_COUNTERS)
	return float(good), float(scrap)


def is_resource_counter(name: str | None) -> bool:
	"""Whether a counter name is a metered input rather than production."""
	if not name:
		return False
	key = str(name).lower()
	return any(key == r or key.startswith(r + "_") for r in RESOURCE_COUNTERS)


def resource_totals(totals: dict[str, float]) -> dict[str, float]:
	"""The metered inputs in per-counter totals, such as {"energy_kwh": 42.0} out of
	{"good": 120, "scrap": 3, "energy_kwh": 42.0}."""
	return {k: float(v or 0) for k, v in totals.items() if is_resource_counter(k)}
