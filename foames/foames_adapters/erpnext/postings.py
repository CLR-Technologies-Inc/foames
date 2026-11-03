# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Posting rules for the ERPNext outbox: which operations exist, what each needs, how a posting is
made idempotent, how an error is classified and when a failed posting is retried.

ERPNext lives on the same site as FoaMES, so a posting and the outbox record that tracks it are
written in one database transaction: either both are committed or neither is. That removes the
"did it arrive?" question a remote ERP has. Idempotency still matters for two reasons: a caller
may queue the same business event twice (every posting carries an idempotency key, and the queue
keeps one record per key), and a document may already exist in ERPNext from an earlier attempt or
a manual entry (every document FoaMES creates carries a marker, and the marker is looked up
before posting again).

This module has no Frappe imports; the ERPNext Outbox DocType applies these rules.
"""

import hashlib
from dataclasses import dataclass

MARKER_PREFIX = "FOAMES-"
BASE_DELAY_SECONDS = 60
MAX_DELAY_SECONDS = 6 * 3600
MAX_ATTEMPTS = 10

# Stock Entry purposes a Work Order accepts from FoaMES.
STOCK_ENTRY_PURPOSES = (
	"Material Transfer for Manufacture",
	"Manufacture",
	"Material Consumption for Manufacture",
)
WORK_ORDER_STATUSES = ("Stopped", "Resumed", "Closed")
# The statuses ERPNext's Workstation (and its Plant Floor page) knows.
WORKSTATION_STATUSES = ("Production", "Off", "Idle", "Problem", "Maintenance", "Setup")
# FoaMES machine state -> ERPNext Workstation status.
WORKSTATION_STATUS_BY_STATE = {
	"Running": "Production",
	"Idle": "Idle",
	"Down": "Problem",
	"Setup": "Setup",
	"Unknown": "Off",
}
# The stop reasons ERPNext's Downtime Entry offers, and the one used when nothing else fits.
STOP_REASONS = (
	"Excessive machine set up time",
	"Unplanned machine maintenance",
	"On-machine press checks",
	"Machine operator errors",
	"Machine malfunction",
	"Electricity down",
	"Other",
)
DEFAULT_STOP_REASON = "Other"
# FoaMES Downtime Reason category -> ERPNext stop reason, when the reason's own title is not one.
STOP_REASON_BY_CATEGORY = {
	"Changeover": "Excessive machine set up time",
	"Breakdown": "Machine malfunction",
	"Planned": "Unplanned machine maintenance",
}


@dataclass(frozen=True)
class Operation:
	label: str
	# Payload keys that must be present and non-empty.
	required: tuple[str, ...]
	# Payload keys the operation understands; anything else is rejected so typos surface early.
	optional: tuple[str, ...]
	# ERPNext DocType of the document the posting creates or changes.
	doctype: str
	# Kernel reference type of that document, if the kernel has one.
	reference_type: str | None = None
	# Whether the posting creates a new document (True) or changes an existing one (False).
	creates_document: bool = True


OPERATIONS: dict[str, Operation] = {
	"Material Transfer for Manufacture": Operation(
		label="Material Transfer for Manufacture",
		required=("work_order",),
		optional=("qty", "posting_date", "posting_time", "remarks", "submit"),
		doctype="Stock Entry",
		reference_type="Stock Movement",
	),
	"Manufacture": Operation(
		label="Manufacture",
		required=("work_order",),
		optional=("qty", "posting_date", "posting_time", "remarks", "submit", "batch_no", "serial_nos"),
		doctype="Stock Entry",
		reference_type="Stock Movement",
	),
	"Material Consumption for Manufacture": Operation(
		label="Material Consumption for Manufacture",
		required=("work_order",),
		optional=("qty", "posting_date", "posting_time", "remarks", "submit"),
		doctype="Stock Entry",
		reference_type="Stock Movement",
	),
	"Job Card Time Log": Operation(
		label="Job Card Time Log",
		required=("job_card",),
		optional=("start_time", "complete_time", "completed_qty", "employees", "submit"),
		doctype="Job Card",
		reference_type="Job Card",
		creates_document=False,
	),
	"Job Card Production Log": Operation(
		label="Job Card Production Log",
		required=("job_card", "from_time", "to_time"),
		optional=("completed_qty", "process_loss_qty", "run_intervals", "remarks", "submit"),
		doctype="Job Card",
		reference_type="Job Card",
		creates_document=False,
	),
	"Work Order Status": Operation(
		label="Work Order Status",
		required=("work_order", "status"),
		optional=(),
		doctype="Work Order",
		reference_type="Work Order",
		creates_document=False,
	),
	"Workstation Status": Operation(
		label="Workstation Status",
		required=("workstation", "status"),
		optional=(),
		doctype="Workstation",
		reference_type="Workstation",
		creates_document=False,
	),
	"Downtime Entry": Operation(
		label="Downtime Entry",
		required=("workstation", "from_time", "to_time"),
		optional=("operator", "stop_reason", "remarks", "downtime_record"),
		doctype="Downtime Entry",
	),
}


def workstation_status_for(state: str | None) -> str:
	"""The ERPNext Workstation status that shows a machine state; anything unknown shows as Off."""
	return WORKSTATION_STATUS_BY_STATE.get(state or "", "Off")


def stop_reason_for(title: str | None, category: str | None, options: tuple[str, ...] = STOP_REASONS) -> str:
	"""The ERPNext stop reason for a FoaMES Downtime Reason: its title when that is one of ERPNext's
	reasons (so a site can match them one to one by naming), otherwise by category, otherwise Other.
	`options` are the reasons the installed ERPNext offers, so a mapping never names one it lacks."""
	if title and title.strip() in options:
		return title.strip()
	mapped = STOP_REASON_BY_CATEGORY.get(category or "")
	if mapped and mapped in options:
		return mapped
	return DEFAULT_STOP_REASON if DEFAULT_STOP_REASON in options else (options[-1] if options else "")


def downtime_marker(downtime_record: str) -> str:
	"""The marker that ties an ERPNext Downtime Entry to its FoaMES Downtime Record, whatever
	posting created or last changed it."""
	return marker(f"downtime-record:{downtime_record}")


def marker(idempotency_key: str) -> str:
	"""A 23-character marker written into the remarks of every document FoaMES creates."""
	return MARKER_PREFIX + hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:16].upper()


def prepare(operation: Operation, payload: dict) -> dict:
	"""Check a payload against its operation and return a normalised copy.

	Raises ValueError with a message a person can act on. Quantities are coerced to float, the
	`submit` flag to bool, and a Work Order Status payload must name one of the allowed statuses.
	"""
	if not isinstance(payload, dict):
		raise ValueError(f"{operation.label} payload must be an object")
	missing = [name for name in operation.required if payload.get(name) in (None, "")]
	if missing:
		raise ValueError(f"{operation.label} needs {', '.join(missing)}")
	unknown = sorted(set(payload) - set(operation.required) - set(operation.optional))
	if unknown:
		raise ValueError(f"{operation.label} does not understand {', '.join(unknown)}")

	prepared = dict(payload)
	for name in ("qty", "completed_qty", "process_loss_qty"):
		if name in prepared and prepared[name] not in (None, ""):
			try:
				prepared[name] = float(prepared[name])
			except (TypeError, ValueError):
				raise ValueError(f"{name} must be a number")
			if prepared[name] < 0:
				raise ValueError(f"{name} cannot be negative")
	if "submit" in prepared:
		prepared["submit"] = _to_bool(prepared["submit"])
	if prepared.get("serial_nos") not in (None, ""):
		prepared["serial_nos"] = serial_number_list(prepared["serial_nos"])
		if len(set(prepared["serial_nos"])) != len(prepared["serial_nos"]):
			raise ValueError("serial_nos repeats a serial number")
		if prepared.get("qty") is not None and len(prepared["serial_nos"]) != int(prepared["qty"]):
			raise ValueError("serial_nos must name one serial number per unit of qty")
	elif "serial_nos" in prepared:
		del prepared["serial_nos"]
	if "batch_no" in prepared:
		prepared["batch_no"] = str(prepared["batch_no"] or "").strip()
		if not prepared["batch_no"]:
			del prepared["batch_no"]
	if operation.label == "Job Card Time Log" and not (
		prepared.get("start_time") or prepared.get("complete_time")
	):
		raise ValueError("Job Card Time Log needs start_time, complete_time or both")
	if operation.label == "Job Card Production Log":
		if str(prepared["from_time"]) >= str(prepared["to_time"]):
			raise ValueError("Job Card Production Log needs from_time before to_time")
		intervals = prepared.get("run_intervals")
		if intervals not in (None, ""):
			if not isinstance(intervals, list) or any(
				not isinstance(pair, (list, tuple)) or len(pair) != 2 or str(pair[0]) >= str(pair[1])
				for pair in intervals
			):
				raise ValueError("run_intervals must be a list of [from, to] pairs with from before to")
			prepared["run_intervals"] = [[str(a), str(b)] for a, b in intervals]
	if operation.label == "Work Order Status" and prepared["status"] not in WORK_ORDER_STATUSES:
		raise ValueError(f"Work Order Status must be one of {', '.join(WORK_ORDER_STATUSES)}")
	if operation.label == "Workstation Status" and prepared["status"] not in WORKSTATION_STATUSES:
		raise ValueError(f"Workstation Status must be one of {', '.join(WORKSTATION_STATUSES)}")
	if operation.label == "Downtime Entry" and str(prepared["from_time"]) >= str(prepared["to_time"]):
		raise ValueError("Downtime Entry needs from_time before to_time")
	return prepared


def serial_number_list(value) -> list[str]:
	"""Serial numbers as a list of strings, from a list or from text separated by newlines or
	commas (the way ERPNext's own serial number fields take them)."""
	if isinstance(value, str):
		parts = value.replace(",", "\n").split("\n")
	elif isinstance(value, (list, tuple)):
		parts = [str(v) for v in value]
	else:
		raise ValueError("serial_nos must be a list of serial numbers")
	serials = [part.strip() for part in parts if part and part.strip()]
	if not serials:
		raise ValueError("serial_nos must name at least one serial number")
	return serials


def _to_bool(value) -> bool:
	if isinstance(value, str):
		return value.strip().lower() in ("1", "true", "yes", "y")
	return bool(value)


# Exception class names (anywhere in the class hierarchy) that mean "try again later": lock and
# timing conflicts inside the database, and connection trouble from the driver.
TRANSIENT_ERRORS = frozenset(
	{
		"QueryDeadlockError",
		"QueryTimeoutError",
		"TimestampMismatchError",
		"DocumentLockedError",
		"RetryBackgroundJobError",
		"OperationalError",
		"InterfaceError",
		"InternalError",
	}
)
# Exception class names that mean ERPNext (or the payload) rejected the posting for good. A person
# has to change the payload or the ERPNext record before it is sent again.
REJECTION_ERRORS = frozenset(
	{
		"ValidationError",
		"PermissionError",
		"DoesNotExistError",
		"ValueError",
		"TypeError",
		"KeyError",
		"AttributeError",
	}
)


def classify(error_types: tuple[str, ...]) -> str:
	"""Retry or Failed, from the names of an exception's class and its bases.

	Transient names win over rejection names, because Frappe derives some of its lock errors from
	ValidationError. Anything unknown is retried, with the attempt cap as the backstop.
	"""
	names = set(error_types)
	if names & TRANSIENT_ERRORS:
		return "Retry"
	if names & REJECTION_ERRORS:
		return "Failed"
	return "Retry"


def error_types(error: BaseException) -> tuple[str, ...]:
	return tuple(cls.__name__ for cls in type(error).__mro__)


def retry_delay(attempts: int) -> int:
	"""Seconds to wait after the given number of failed attempts: 1, 2, 4 ... minutes, capped at 6 h."""
	return min(BASE_DELAY_SECONDS * 2 ** max(attempts - 1, 0), MAX_DELAY_SECONDS)


def give_up(attempts: int) -> bool:
	return attempts >= MAX_ATTEMPTS
