# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The arithmetic of rolling machine data up to an S/4HANA order operation: what a window produced
and the partial confirmation that reports it. No Frappe dependency; `rollup.py` feeds it the counts
and run stretches it has read and queues what it returns.

A machine's current job names the operation as `ORDER|OPERATION` (for example `1000123|0010`), the
same order number and operation number a person types into a confirmation in S/4HANA. An operation
in an alternative or parallel sequence is `ORDER|SEQUENCE|OPERATION`; without one it is in the
standard sequence 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from foames.foames_adapters.s4hana import confirmations
from foames.foames_adapters.s4hana.entities import KEY_SEPARATOR
from foames.foames_adapters.s4hana.values import parse_date, parse_time
from foames.foames_mes.counters import good_and_scrap

# Units S/4HANA commonly uses for activity time, with the minutes in one of them.
MINUTES_PER_UNIT = {"MIN": 1.0, "H": 60.0, "S": 1 / 60.0, "SEC": 1 / 60.0}


@dataclass
class RollUpOptions:
	"""How a window becomes a confirmation, from S4HANA Settings."""

	unit: str  # the confirmation unit of the yield and scrap quantities, for example PC or KG
	process_order: bool = False
	activity_position: int = 0  # position of machine time in the standard value key, 0 = do not send
	activity_unit: str = "MIN"
	no_goods_movements: bool = False

	@property
	def operation(self) -> str:
		return confirmations.PROCESS if self.process_order else confirmations.PRODUCTION


STANDARD_SEQUENCE = "0"


def parse_job(external_id: str) -> tuple[str, str, str]:
	"""`(order, operation, sequence)` out of `ORDER|OPERATION` or `ORDER|SEQUENCE|OPERATION`."""
	parts = [part.strip() for part in (external_id or "").split(KEY_SEPARATOR)]
	if len(parts) not in (2, 3) or not all(parts):
		raise ValueError(
			f"{external_id!r} is not an order operation; write it as ORDER{KEY_SEPARATOR}OPERATION, "
			f"for example 1000123{KEY_SEPARATOR}0010, or ORDER{KEY_SEPARATOR}SEQUENCE{KEY_SEPARATOR}OPERATION"
		)
	if len(parts) == 2:
		return parts[0], parts[1], STANDARD_SEQUENCE
	return parts[0], parts[2], normal_sequence(parts[1])


def normal_sequence(sequence) -> str:
	"""Sequences compare without leading zeros, and an empty one is the standard sequence."""
	return str(sequence or "").strip().lstrip("0") or STANDARD_SEQUENCE


def job_id(order: str, operation: str, sequence: str = STANDARD_SEQUENCE) -> str:
	"""The external ID of an order operation, the inverse of `parse_job`."""
	if normal_sequence(sequence) == STANDARD_SEQUENCE:
		return f"{order}{KEY_SEPARATOR}{operation}"
	return f"{order}{KEY_SEPARATOR}{sequence}{KEY_SEPARATOR}{operation}"


def activity_quantity(minutes: float, unit: str) -> float:
	"""Running minutes in the activity's unit, rounded to what S/4HANA keeps (three decimals)."""
	per_unit = MINUTES_PER_UNIT.get((unit or "MIN").upper())
	if per_unit is None:
		raise ValueError(
			f"Machine time cannot be written in {unit!r}; use one of {', '.join(MINUTES_PER_UNIT)}"
		)
	return round(minutes / per_unit, 3)


def confirmation_payload(
	order: str,
	operation: str,
	start: datetime,
	end: datetime,
	totals: dict[str, float],
	intervals: list[tuple[datetime, datetime]],
	options: RollUpOptions,
	sequence: str = STANDARD_SEQUENCE,
) -> dict | None:
	"""The partial confirmation for a window, or None when the window has nothing to report.

	Good counts become the yield and scrap counts the scrap. Running time is sent as the machine
	activity only when a position is configured, so a window with run time but no counts and no
	activity position queues nothing. The confirmation is never final: S/4HANA decides that from the
	operation quantity, or a person confirms the operation finished.
	"""
	good, scrap = good_and_scrap(totals)
	run_minutes = sum((b - a).total_seconds() for a, b in intervals) / 60.0
	activities = []
	if options.activity_position and run_minutes > 0:
		activities.append(
			confirmations.Activity(
				int(options.activity_position),
				activity_quantity(run_minutes, options.activity_unit),
				(options.activity_unit or "MIN").upper(),
			)
		)
	if good <= 0 and scrap <= 0 and not activities:
		return None
	if (good > 0 or scrap > 0) and not options.unit:
		raise ValueError("A confirmation unit is needed to confirm machine counts")
	return confirmations.confirmation(
		order,
		operation,
		yield_quantity=good if good > 0 else None,
		unit=options.unit if good > 0 or scrap > 0 else "",
		scrap_quantity=scrap if scrap > 0 else None,
		sequence=normal_sequence(sequence),
		posting_date=end,
		activities=activities or None,
		times=confirmations.ExecutionTimes(start=start, end=end),
		no_goods_movements=True if options.no_goods_movements else None,
	)


def window_end(payload: dict) -> datetime | None:
	"""Where a roll-up confirmation's window ended, read back from its execution end."""
	day = parse_date(payload.get("ConfirmedExecutionEndDate"))
	if day is None:
		return None
	moment = parse_time(payload.get("ConfirmedExecutionEndTime"))
	return datetime.combine(day, moment) if moment else datetime(day.year, day.month, day.day)


def window_key(
	order: str, operation: str, machine: str, end: datetime, sequence: str = STANDARD_SEQUENCE
) -> str:
	"""Idempotency key of a window: a window that ends at the same moment is the same window."""
	job = job_id(order, operation, sequence)
	return f"{job}:{machine}:confirm:{end.isoformat(sep=' ', timespec='seconds')}"
