# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Standard operating procedures as controlled documents: the revision lifecycle, sign-off, periodic
review and who still has to acknowledge the current revision. No Frappe dependency.

Each revision of an SOP is its own record. A revision moves

    Draft -> In Review -> Approved -> Effective -> Superseded
                 |            |           |
                 v            v           v
               Draft       Obsolete    Obsolete

A rejected review goes back to Draft with its signatures cleared. Only a Draft can be edited; any
change to an approved text is a new revision. When a revision becomes Effective, the revision it
replaces becomes Superseded, so a code has at most one Effective revision at a time.

This is ordinary document control as ISO 9001 clause 7.5 and GMP practice describe it: identified,
reviewed and approved before use, current version at the point of use, obsolete versions withdrawn,
changes recorded, and people trained on the version in force.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

STATUSES = ("Draft", "In Review", "Approved", "Effective", "Superseded", "Obsolete")
OPEN_STATUSES = ("Draft", "In Review", "Approved")
FINAL_STATUSES = ("Superseded", "Obsolete")
TRANSITIONS = {
	None: ("Draft",),
	"Draft": ("In Review", "Obsolete"),
	"In Review": ("Draft", "Approved"),
	"Approved": ("Effective", "Obsolete"),
	"Effective": ("Superseded", "Obsolete"),
	"Superseded": (),
	"Obsolete": (),
}
REVIEW_STATUSES = ("Current", "Review Due Soon", "Review Overdue")
ACK_STATUSES = ("Current", "Outdated", "Missing")
DEFAULT_REVIEW_MONTHS = 12
DEFAULT_REVIEW_WARN_DAYS = 30
DEFAULT_ACKNOWLEDGE_DAYS = 14
REVIEW_SEVERITY = {"Review Due Soon": "Info", "Review Overdue": "Warning"}
CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._/-]*$")


def allowed_transition(previous: str | None, new: str) -> bool:
	"""Whether a revision may move from `previous` to `new`. Staying put is always allowed."""
	if previous == new:
		return True
	return new in TRANSITIONS.get(previous, ())


def normalise_code(code: str | None) -> str:
	"""Upper case, outer spaces removed; inner spaces become hyphens. Raises ValueError when empty or
	when it holds characters other than letters, digits and . _ / -."""
	value = re.sub(r"\s+", "-", (code or "").strip().upper())
	if not value:
		raise ValueError("an SOP needs a code")
	if not CODE_PATTERN.match(value):
		raise ValueError("an SOP code may hold letters, digits and . _ / - only")
	return value


def revision_name(code: str, revision: int) -> str:
	"""The record name of one revision, for example SOP-QA-001-R3."""
	return f"{code}-R{int(revision)}"


def next_revision(existing: list[int] | tuple[int, ...]) -> int:
	return max((int(r) for r in existing if r), default=0) + 1


# Sign-off


def signable_rows(approvals: list[dict], user: str, user_roles, author: str | None) -> list[int]:
	"""Indexes of the unsigned approval rows `user` may sign.

	A user signs a row when they hold its role. The author of the revision cannot sign it, and nobody
	signs two rows of one revision, so a two-row sign-off always takes two people besides the author.
	"""
	roles = set(user_roles or ())
	if author and user == author:
		return []
	if any(row.get("signed_by") == user for row in approvals):
		return []
	return [i for i, row in enumerate(approvals) if not row.get("signed_by") and row.get("role") in roles]


def approvals_complete(approvals: list[dict]) -> bool:
	"""A revision is approved when it has at least one approval row and every row is signed."""
	return bool(approvals) and all(row.get("signed_by") for row in approvals)


def missing_approvals(approvals: list[dict]) -> list[str]:
	return [row.get("role") for row in approvals if not row.get("signed_by")]


# Periodic review


def add_months(day: date, months: int) -> date:
	"""`day` moved by whole months, clamped to the end of a shorter month (31 Jan + 1 = 28/29 Feb)."""
	month_index = day.month - 1 + int(months)
	year, month = day.year + month_index // 12, month_index % 12 + 1
	for last in (31, 30, 29, 28):
		try:
			return date(year, month, min(day.day, last))
		except ValueError:
			continue
	raise ValueError("unreachable")


def as_date(value) -> date | None:
	if value is None or value == "":
		return None
	if isinstance(value, datetime):
		return value.date()
	if isinstance(value, date):
		return value
	return date.fromisoformat(str(value)[:10])


def next_review(effective_on, review_months: int | None, last_reviewed_on=None) -> date | None:
	"""When the revision is next due for its periodic review: one interval after the later of its
	effective date and its last recorded review. None when no review interval is set."""
	dates = [d for d in (as_date(effective_on), as_date(last_reviewed_on)) if d]
	start = max(dates) if dates else None
	if not start or not review_months or int(review_months) <= 0:
		return None
	return add_months(start, int(review_months))


def review_status(due: date | None, today: date, warn_days: int = DEFAULT_REVIEW_WARN_DAYS) -> str:
	if not due:
		return "Current"
	if today > due:
		return "Review Overdue"
	if today >= due - timedelta(days=warn_days):
		return "Review Due Soon"
	return "Current"


# Acknowledgement and training


def acknowledgement_status(acknowledged_revision: int | None, current_revision: int) -> str:
	"""Current when the user acknowledged this revision (or a later one), Outdated when only an
	earlier revision, Missing when none."""
	if not acknowledged_revision:
		return "Missing"
	return "Current" if int(acknowledged_revision) >= int(current_revision) else "Outdated"


def training_matrix(required_users, acknowledged: dict[str, int], current_revision: int) -> dict[str, str]:
	"""user -> Current, Outdated or Missing for every user who must acknowledge the revision.

	`acknowledged` maps each user to the highest revision of the same SOP code they acknowledged."""
	return {
		user: acknowledgement_status(acknowledged.get(user), current_revision)
		for user in sorted(set(required_users))
	}


def training_due(effective_on, acknowledge_days: int | None, today: date) -> bool:
	"""Whether the grace period to acknowledge an Effective revision has run out."""
	start = as_date(effective_on)
	if not start:
		return False
	days = DEFAULT_ACKNOWLEDGE_DAYS if acknowledge_days is None else int(acknowledge_days)
	return today > start + timedelta(days=max(days, 0))


def applies(rows: list[dict], machine: str | None, line: str | None) -> bool:
	"""Whether an SOP with these applicability rows covers a machine on a line.

	An SOP with no rows is site-wide. A row naming a machine covers that machine; a row naming only a
	line covers every machine on it; a row naming neither (only a process reference or a note) covers
	nothing on its own."""
	if not rows:
		return True
	for row in rows:
		if row.get("machine"):
			if machine and row["machine"] == machine:
				return True
		elif row.get("line") and line and row["line"] == line:
			return True
	return False


# Suggestions


def review_rule_key(name: str, due, status: str) -> str:
	return f"sop-review:{name}:{due}:{status}"


def training_rule_key(name: str) -> str:
	return f"sop-training:{name}"


def findings(sops: list[dict]) -> list[dict]:
	"""Agent Suggestion dicts for Effective revisions whose periodic review is due or overdue, and for
	those whose acknowledgement period has passed with people still not trained on them.

	Each dict carries name, code, title, revision, review_status, next_review_on and, for the training
	finding, overdue_users (a list) and acknowledge_days.
	"""
	out = []
	for s in sops:
		label = f"{s['code']} rev {s['revision']} ({s.get('title') or s['code']})"
		status = s.get("review_status")
		if status in REVIEW_SEVERITY:
			due = s.get("next_review_on")
			out.append(
				{
					"rule_key": review_rule_key(s["name"], due, status),
					"category": "Quality",
					"severity": REVIEW_SEVERITY[status],
					"title": f"SOP {s['code']} {'is overdue for' if status == 'Review Overdue' else 'is due for'} periodic review",
					"suggestion": (
						f"{label} is due for its periodic review on {due}. Review it with the document owner: "
						"record the review if it is still right, or start a new revision if it needs to change."
					),
					"reference_doctype": "Standard Operating Procedure",
					"reference_name": s["name"],
					"evidence": {
						"code": s["code"],
						"revision": s["revision"],
						"next_review_on": str(due) if due else None,
						"review_status": status,
					},
				}
			)
		users = sorted(s.get("overdue_users") or ())
		if users:
			shown = ", ".join(users[:10]) + (f" and {len(users) - 10} more" if len(users) > 10 else "")
			out.append(
				{
					"rule_key": training_rule_key(s["name"]),
					"category": "Quality",
					"severity": "Warning",
					"title": f"{len(users)} people not yet trained on SOP {s['code']} rev {s['revision']}",
					"suggestion": (
						f"{label} has been effective for more than {s.get('acknowledge_days', DEFAULT_ACKNOWLEDGE_DAYS)} "
						f"days and these people have not acknowledged it: {shown}. Train them or have them read "
						"and acknowledge it before they next work under it."
					),
					"reference_doctype": "Standard Operating Procedure",
					"reference_name": s["name"],
					"evidence": {"code": s["code"], "revision": s["revision"], "users": users},
				}
			)
	return out
