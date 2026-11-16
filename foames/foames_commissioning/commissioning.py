# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Equipment commissioning as pure rules: test steps, loop checks, punch items and handover
readiness. No Frappe dependency.

The flow follows common commissioning practice for process and packaging equipment:

1. Factory Acceptance Test (FAT) at the vendor's works.
2. Installation and Mechanical Completion on site.
3. Pre-Commissioning: loop checks from field device to control system, one tag at a time.
4. Site Acceptance Test (SAT) and functional tests on the installed equipment.
5. Performance test at rate, where the contract asks for one.
6. Handover to operations and maintenance.

Anything found along the way becomes a punch item with a category:

- A: must be cleared before start-up or handover. It cannot be deferred.
- B: must be cleared before handover, unless it is deferred with an owner and a due date, in which
  case it is handed over as an open item.
- C: cosmetic or minor; it never blocks handover.

Qualification (IQ, OQ, PQ) comes after handover and is not modelled here; the package carries a
link to the qualification record and calls the `foames_commissioning_handed_over` hook.
"""

from __future__ import annotations

from datetime import date, datetime

TEST_TYPES = (
	"FAT",
	"Mechanical Completion",
	"Pre-Commissioning",
	"SAT",
	"Functional Test",
	"Performance Test",
)
# Where each test type sits in the sequence. A package that enforces the sequence refuses to start
# a test while a test of an earlier stage on the same equipment has not passed.
STAGE = {t: i for i, t in enumerate(TEST_TYPES)}
STAGE["Functional Test"] = STAGE["SAT"]

STEP_KINDS = ("Check", "Value", "Text")
STEP_RESULTS = ("Pending", "Pass", "Fail", "N/A")
TEST_STATUSES = ("Not Started", "In Progress", "Awaiting Sign-off", "Passed", "Failed", "Cancelled")

LOOP_TYPES = ("Analog Input", "Analog Output", "Digital Input", "Digital Output")
ANALOG = ("Analog Input", "Analog Output")
DEFAULT_ANALOG_POINTS = (0.0, 25.0, 50.0, 75.0, 100.0)
DEFAULT_TOLERANCE_PERCENT = 1.0
LOOP_STATUSES = ("Not Started", "In Progress", "Passed", "Failed", "Cancelled")

PUNCH_CATEGORIES = ("A", "B", "C")
PUNCH_STATUSES = ("Open", "Ready for Verification", "Closed", "Cancelled")
PUNCH_OPEN = ("Open", "Ready for Verification")
PUNCH_SEVERITY = {"A": "Critical", "B": "Warning", "C": "Info"}

PACKAGE_STATUSES = ("Planning", "In Progress", "Ready for Handover", "Handed Over", "Cancelled")


# Test steps and tests


def evaluate_step(kind: str, measured=None, low=None, high=None, result: str | None = None) -> str:
	"""The result of one test step.

	A Value step is judged from its measured value against its limits (either limit may be open); a
	missing reading is Pending. Check and Text steps keep the result the tester chose. N/A is kept for
	every kind, so a step that does not apply can be set aside."""
	if result == "N/A":
		return "N/A"
	if kind == "Value":
		if measured is None or measured == "":
			return "Pending"
		value = float(measured)
		if low is not None and low != "" and value < float(low):
			return "Fail"
		if high is not None and high != "" and value > float(high):
			return "Fail"
		return "Pass"
	return result if result in STEP_RESULTS else "Pending"


def status_of_test(
	results: list[str],
	performed_by: str | None = None,
	witness_required: bool = False,
	witnessed_by: str | None = None,
	cancelled: bool = False,
) -> str:
	"""A test's status from its step results and its sign-offs.

	Any failed step fails the test, even with steps still pending, so the failure is seen at once.
	A test whose steps all pass (or are N/A) waits for the performer's sign-off, and for the witness's
	when the test needs one, before it is Passed."""
	if cancelled:
		return "Cancelled"
	if not results:
		return "Not Started"
	if "Fail" in results:
		return "Failed"
	if all(r == "Pending" for r in results):
		return "Not Started"
	if "Pending" in results:
		return "In Progress"
	if all(r == "N/A" for r in results):
		return "In Progress"
	if not performed_by or (witness_required and not witnessed_by):
		return "Awaiting Sign-off"
	return "Passed"


def sequence_blockers(test_type: str, earlier: list[dict]) -> list[dict]:
	"""Tests of an earlier stage that have not passed, which hold back a test of this type.

	`earlier` lists the other tests on the same equipment, each with name, test_type and status;
	cancelled tests are ignored."""
	stage = STAGE.get(test_type)
	if stage is None:
		return []
	return [
		t
		for t in earlier
		if STAGE.get(t.get("test_type"), stage) < stage and t.get("status") not in ("Passed", "Cancelled")
	]


# Loop checks


def default_points(loop_type: str) -> list[dict]:
	"""The usual check points: five points across the span for an analog loop, both states for a
	digital one."""
	if loop_type in ANALOG:
		return [{"percent_of_span": p} for p in DEFAULT_ANALOG_POINTS]
	return [{"expected_state": "On"}, {"expected_state": "Off"}]


def expected_value(range_low: float, range_high: float, percent_of_span: float) -> float:
	"""The engineering value at a share of the calibrated range."""
	return float(range_low) + (float(range_high) - float(range_low)) * float(percent_of_span) / 100.0


def span_error_percent(reading: float, expected: float, range_low: float, range_high: float) -> float:
	"""The reading's error as a percent of span, the way instrument loops are toleranced."""
	span = float(range_high) - float(range_low)
	if span == 0:
		raise ValueError("the range must have a span")
	return (float(reading) - float(expected)) / abs(span) * 100.0


def evaluate_analog_point(
	percent_of_span: float,
	range_low: float,
	range_high: float,
	tolerance_percent: float | None,
	as_found=None,
	as_left=None,
) -> dict:
	"""Expected value, error and result of one analog check point.

	The as-left reading, when there is one, decides the result (the loop was adjusted); otherwise
	the as-found reading does. With no reading the point is Pending."""
	tolerance = DEFAULT_TOLERANCE_PERCENT if tolerance_percent in (None, "") else float(tolerance_percent)
	expected = expected_value(range_low, range_high, percent_of_span)
	reading = as_left if as_left not in (None, "") else as_found
	if reading in (None, ""):
		return {"expected": expected, "error_percent": None, "result": "Pending"}
	error = span_error_percent(reading, expected, range_low, range_high)
	# Round away float noise so a reading exactly at the tolerance passes.
	result = "Pass" if round(abs(error), 9) <= tolerance else "Fail"
	return {"expected": expected, "error_percent": error, "result": result}


def evaluate_digital_point(expected_state: str | None, observed_state: str | None) -> str:
	if not observed_state:
		return "Pending"
	return "Pass" if observed_state == expected_state else "Fail"


def loop_status(results: list[str], checked_by: str | None = None, cancelled: bool = False) -> str:
	"""A loop check's status from its points: failed if any point failed, passed once every point
	passed and the technician signed it."""
	if cancelled:
		return "Cancelled"
	if not results or all(r == "Pending" for r in results):
		return "Not Started"
	if "Fail" in results:
		return "Failed"
	if "Pending" in results or not checked_by:
		return "In Progress"
	return "Passed"


# Punch items


def punch_blocks_handover(item: dict) -> bool:
	"""Whether an open punch item holds the handover back.

	A blocks while open. B blocks while open unless it is deferred with an owner and a due date.
	C never blocks."""
	if item.get("status") not in PUNCH_OPEN:
		return False
	category = item.get("category")
	if category == "A":
		return True
	if category == "B":
		return not (item.get("deferred") and item.get("assigned_to") and item.get("due_on"))
	return False


def punch_deferral_problem(category: str, deferred: bool, assigned_to, due_on) -> str | None:
	"""Why a deferral is not allowed, or None."""
	if not deferred:
		return None
	if category == "A":
		return "A category A punch item cannot be deferred past handover"
	if not assigned_to or not due_on:
		return "A deferred punch item needs an owner and a due date"
	return None


# Handover readiness


def readiness(package: dict) -> dict:
	"""Whether a package can be handed over, and what holds it back.

	`package` carries:
	  items: the equipment in scope, each with tag
	  required_test_types: test types the package must have passed at least once
	  tests: name, test_type, status, equipment_tag
	  loop_checks: name, tag, status
	  punch_items: name, category, status, deferred, assigned_to, due_on, description
	  operations_acceptor, maintenance_acceptor: who accepts the equipment
	  extra_blockers: blockers raised by other apps through the readiness hook

	Returns ready, blockers (kind, reference, message) and progress figures."""
	blockers: list[dict] = []
	items = package.get("items") or []
	tests = [t for t in package.get("tests") or [] if t.get("status") != "Cancelled"]
	loops = [lc for lc in package.get("loop_checks") or [] if lc.get("status") != "Cancelled"]
	punch = package.get("punch_items") or []

	if not items:
		blockers.append(
			{"kind": "Scope", "reference": None, "message": "No equipment is in the package's scope"}
		)

	for test_type in package.get("required_test_types") or []:
		if not any(t.get("test_type") == test_type and t.get("status") == "Passed" for t in tests):
			blockers.append(
				{
					"kind": "Required Test",
					"reference": test_type,
					"message": f"No {test_type} has passed for this package",
				}
			)
	for t in tests:
		if t.get("status") != "Passed":
			blockers.append(
				{
					"kind": "Test",
					"reference": t.get("name"),
					"message": f"{t.get('test_type')} {t.get('name')} is {str(t.get('status')).lower()}",
				}
			)
	for lc in loops:
		if lc.get("status") != "Passed":
			blockers.append(
				{
					"kind": "Loop Check",
					"reference": lc.get("name"),
					"message": f"Loop check of {lc.get('tag')} is {str(lc.get('status')).lower()}",
				}
			)
	for p in punch:
		if punch_blocks_handover(p):
			blockers.append(
				{
					"kind": "Punch Item",
					"reference": p.get("name"),
					"message": f"Category {p.get('category')} punch item {p.get('name')} is open: {p.get('description') or ''}".rstrip(
						": "
					),
				}
			)
	if not package.get("operations_acceptor"):
		blockers.append(
			{"kind": "Acceptance", "reference": None, "message": "Name who accepts for operations"}
		)
	if not package.get("maintenance_acceptor"):
		blockers.append(
			{"kind": "Acceptance", "reference": None, "message": "Name who accepts for maintenance"}
		)
	blockers.extend(package.get("extra_blockers") or [])

	open_punch = [p for p in punch if p.get("status") in PUNCH_OPEN]
	return {
		"ready": not blockers,
		"blockers": blockers,
		"progress": {
			"tests": len(tests),
			"tests_passed": sum(1 for t in tests if t.get("status") == "Passed"),
			"loop_checks": len(loops),
			"loop_checks_passed": sum(1 for lc in loops if lc.get("status") == "Passed"),
			"punch_open": len(open_punch),
			"punch_open_by_category": {
				c: sum(1 for p in open_punch if p.get("category") == c) for c in PUNCH_CATEGORIES
			},
			"percent_complete": percent_complete(tests, loops, punch),
		},
	}


def percent_complete(tests: list[dict], loops: list[dict], punch: list[dict]) -> float:
	"""Passed tests, passed loop checks and cleared punch items as a share of all of them."""
	live_punch = [p for p in punch if p.get("status") != "Cancelled"]
	total = len(tests) + len(loops) + len(live_punch)
	if not total:
		return 0.0
	done = (
		sum(1 for t in tests if t.get("status") == "Passed")
		+ sum(1 for lc in loops if lc.get("status") == "Passed")
		+ sum(1 for p in live_punch if p.get("status") == "Closed")
	)
	return done / total * 100.0


def package_status(current: str | None, started: bool, ready: bool) -> str:
	"""A package's status: Handed Over and Cancelled are set by people and stay; otherwise it is
	Planning until work starts, In Progress, and Ready for Handover once nothing blocks it."""
	if current in ("Handed Over", "Cancelled"):
		return current
	if ready:
		return "Ready for Handover"
	return "In Progress" if started else "Planning"


# Suggestions


def is_past(due, now: datetime) -> bool:
	"""Whether a due date or time has passed. A plain date is due through the end of that day."""
	if not due:
		return False
	if isinstance(due, datetime):
		return due < now
	if isinstance(due, date):
		return due < now.date()
	return False


def findings(punch_items: list[dict], packages: list[dict], now: datetime) -> list[dict]:
	"""Agent Suggestion dicts for overdue open punch items and for packages past their planned
	handover date.

	Punch dicts: name, package, category, status, due_on, assigned_to, description, deferred.
	Package dicts: name, title, status, planned_handover, blockers (count)."""
	out = []
	for p in punch_items:
		due = p.get("due_on")
		if p.get("status") not in PUNCH_OPEN or not is_past(due, now):
			continue
		owner = p.get("assigned_to") or "nobody"
		out.append(
			{
				"rule_key": f"commissioning:punch:{p['name']}:{due}",
				"category": "Commissioning",
				"severity": PUNCH_SEVERITY.get(p.get("category"), "Info"),
				"title": f"Category {p.get('category')} punch item {p['name']} is overdue",
				"suggestion": (
					f"Punch item {p['name']} on package {p.get('package')} was due on {due} and is still "
					f"{str(p.get('status')).lower()}; it is assigned to {owner}. "
					f"{p.get('description') or ''}".strip()
				),
				"reference_doctype": "Punch Item",
				"reference_name": p["name"],
				"evidence": {
					"package": p.get("package"),
					"category": p.get("category"),
					"due_on": str(due),
					"assigned_to": p.get("assigned_to"),
					"deferred": bool(p.get("deferred")),
				},
			}
		)
	for pkg in packages:
		planned = pkg.get("planned_handover")
		if pkg.get("status") in ("Handed Over", "Cancelled") or not is_past(planned, now):
			continue
		out.append(
			{
				"rule_key": f"commissioning:package:{pkg['name']}:{planned}",
				"category": "Commissioning",
				"severity": "Warning",
				"title": f"Commissioning of {pkg.get('title') or pkg['name']} is past its planned handover",
				"suggestion": (
					f"Package {pkg['name']} was planned to hand over on {planned} and is "
					f"{str(pkg.get('status')).lower()} with {pkg.get('blockers', 0)} open blockers. "
					"Review the blockers or move the planned date."
				),
				"reference_doctype": "Commissioning Package",
				"reference_name": pkg["name"],
				"evidence": {"planned_handover": str(planned), "blockers": pkg.get("blockers", 0)},
			}
		)
	return out
