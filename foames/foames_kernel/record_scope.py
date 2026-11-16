# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Record scope for reads made on behalf of a person or an agent. Pure: imports nothing from Frappe.

A read that aggregates many records (the floor snapshot, the qualification status, a report) is
assembled from several DocTypes. Frappe's role and user permissions filter each `frappe.get_list`,
but a row that is built from one DocType can still point at a record of another one the reader may
not see: an Agent Suggestion about a machine outside the reader's area, an Andon Call on such a
machine, a section an extension added. These helpers take the set of machines the reader may read
and drop every row that names another one, so an aggregate never says more than its parts.

`None` as the allowed set means "no restriction" (a system read, such as the scheduler's rules).
"""

from __future__ import annotations

from collections.abc import Iterable

# Keys a row uses to name the machine it is about.
MACHINE_KEYS = ("machine",)
# A row that names its subject as (reference_doctype, reference_name).
REFERENCE_PAIRS = (("reference_doctype", "reference_name"), ("subject_type", "subject"))


def _get(row, key):
	if isinstance(row, dict):
		return row.get(key)
	return getattr(row, key, None)


def row_machine(row) -> str | None:
	"""The machine a row is about, or None when it names none."""
	for key in MACHINE_KEYS:
		value = _get(row, key)
		if value:
			return value
	for doctype_key, name_key in REFERENCE_PAIRS:
		if _get(row, doctype_key) == "Machine" and _get(row, name_key):
			return _get(row, name_key)
	return None


def in_scope(row, allowed: set[str] | None) -> bool:
	"""True when the reader may see the row: no restriction, the row names no machine, or the
	machine it names is allowed."""
	if allowed is None:
		return True
	machine = row_machine(row)
	return machine is None or machine in allowed


def filter_rows(rows: Iterable, allowed: set[str] | None) -> list:
	"""The rows the reader may see, in their order."""
	return [row for row in rows if in_scope(row, allowed)]


def scrub(value, allowed: set[str] | None):
	"""Drop, at every depth of a dict or list, each dict that names a machine outside `allowed`.
	Used as the last step of an aggregate read, so a section an extension added cannot leak a
	machine the reader may not see. Returns a new structure of the same types; scalars are kept as
	they are."""
	if allowed is None:
		return value
	if isinstance(value, dict):
		# Keep the mapping's own class (frappe._dict rows stay attribute-readable).
		return type(value)({key: scrub(item, allowed) for key, item in value.items()})
	if isinstance(value, (list, tuple)):
		return [
			scrub(item, allowed) for item in value if not isinstance(item, dict) or in_scope(item, allowed)
		]
	return value


def project(row: dict, fields: Iterable[str]) -> dict:
	"""Only the named fields of a row (an authorised projection)."""
	keep = set(fields)
	return {key: value for key, value in row.items() if key in keep}


# The order of strictness of a Connector Write Policy's "when read-only" choice; a later entry is
# stricter. The site's own choice is Queue for sign-off or Block, so "Site default" sits between.
WHEN_READ_ONLY_STRICTNESS = ("Queue for sign-off", "Site default", "Block")


def policy_loosening(before: dict | None, after: dict) -> list[str]:
	"""Why a change to a Connector Write Policy weakens the gate; empty when it does not.

	A new policy that starts writable, turning read-only off, moving "when read-only" to a less
	strict choice, and changing who signs off all loosen it. Tightening is never refused here."""
	reasons = []
	if before is None:
		if not after.get("read_only"):
			reasons.append("a new policy that lets the connector write")
		return reasons
	if before.get("read_only") and not after.get("read_only"):
		reasons.append("read-only turned off")
	was = before.get("when_read_only") or "Site default"
	now = after.get("when_read_only") or "Site default"
	if (
		was in WHEN_READ_ONLY_STRICTNESS
		and now in WHEN_READ_ONLY_STRICTNESS
		and WHEN_READ_ONLY_STRICTNESS.index(now) < WHEN_READ_ONLY_STRICTNESS.index(was)
	):
		reasons.append(f"when read-only changed from {was} to {now}")
	if (before.get("sign_off_role") or "") != (after.get("sign_off_role") or ""):
		reasons.append("sign-off role changed")
	return reasons
