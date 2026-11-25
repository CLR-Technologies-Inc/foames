# Copyright 2026 CLR Technologies Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""Record-scope checks for reads made on behalf of a person or an agent.

The pure rules (which rows an aggregate may show, which policy changes weaken the gate) are in
`record_scope.py`; this module applies them to the session user.
"""

from __future__ import annotations

import frappe
from frappe import _

NOT_FOUND = "{0} {1} was not found or you may not read it"


def require_read(doctype: str, name: str | None) -> None:
	"""Raise the same PermissionError whether the record is missing or the user may not read it,
	so an error never tells a caller that a record outside their scope exists."""
	if not name or not frappe.db.exists(doctype, name) or not frappe.has_permission(doctype, "read", name):
		frappe.throw(_(NOT_FOUND).format(_(doctype), name or ""), frappe.PermissionError)


def readable_machines() -> set[str]:
	"""Names of the machines the session user may read."""
	return set(frappe.get_list("Machine", pluck="name", limit_page_length=0))


def readable(doctype: str, names: list[str]) -> list[str]:
	"""The subset of `names` the session user may read, in their order."""
	if not names:
		return []
	allowed = set(
		frappe.get_list(doctype, filters={"name": ("in", list(names))}, pluck="name", limit_page_length=0)
	)
	return [name for name in names if name in allowed]


# Records that name a machine through a Dynamic Link ------------------------------------------
#
# Frappe applies a user's User Permissions on Machine to every Link field that points at Machine,
# but not to a Dynamic Link. An Agent Suggestion names its subject as (reference_doctype,
# reference_name), so without these hooks a reader restricted to some machines would still list and
# open the suggestions about every other one. Registered in hooks.py.


def restricted_machines(user: str | None = None, doctype: str = "Agent Suggestion") -> set[str] | None:
	"""The machines a user's User Permissions allow on `doctype`, or None when they are not
	restricted there. A User Permission limited to other DocTypes does not count."""
	user = user or frappe.session.user
	if user == "Administrator":
		return None
	from frappe.permissions import get_user_permissions

	rows = [
		row
		for row in get_user_permissions(user).get("Machine") or []
		if not row.get("applicable_for") or row.get("applicable_for") == doctype
	]
	if not rows:
		return None
	return {row.get("doc") for row in rows if row.get("doc")}


def machine_reference_has_permission(doc, ptype=None, user=None, debug=False):
	allowed = restricted_machines(user, doc.doctype)
	if allowed is None or doc.get("reference_doctype") != "Machine":
		return True
	return doc.get("reference_name") in allowed


def machine_reference_query_conditions(user=None, doctype=None):
	doctype = doctype or "Agent Suggestion"
	allowed = restricted_machines(user, doctype)
	if allowed is None:
		return ""
	table = f"`tab{doctype}`"
	names = ", ".join(frappe.db.escape(name) for name in sorted(allowed)) or "''"
	return (
		f"(coalesce({table}.`reference_doctype`, '') != 'Machine' or {table}.`reference_name` in ({names}))"
	)
