# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Small builders shared by the integration tests."""

from contextlib import contextmanager
from unittest.mock import patch

import frappe


def make_machine(code, **overrides):
	"""An enabled machine with no counter rollover, or the existing one with that code."""
	if frappe.db.exists("Machine", code):
		return frappe.get_doc("Machine", code)
	values = {"doctype": "Machine", "code": code, "counter_rollover": 0}
	values.update(overrides)
	return frappe.get_doc(values).insert()


def make_reason(code, category="Unplanned", **overrides):
	if frappe.db.exists("Downtime Reason", code):
		return frappe.get_doc("Downtime Reason", code)
	values = {"doctype": "Downtime Reason", "code": code, "category": category}
	values.update(overrides)
	return frappe.get_doc(values).insert()


def make_user(email, *roles):
	"""A System User with exactly these roles."""
	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
		user.set("roles", [])
	else:
		user = frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "FoaMES Test", "send_welcome_email": 0}
		)
	for role in roles:
		user.append("roles", {"role": role})
	user.save(ignore_permissions=True) if not user.is_new() else user.insert(ignore_permissions=True)
	return user


@contextmanager
def as_user(email):
	"""Run the block as another user, then return to Administrator."""
	previous = frappe.session.user
	frappe.set_user(email)
	try:
		yield
	finally:
		frappe.set_user(previous)


@contextmanager
def extra_hooks(**hooks):
	"""Add entries to the named hooks for the block, keeping every other hook as configured.

	Each value is a list of dotted paths (or, for dict hooks, a dict) appended to what hooks.py gives."""
	original = frappe.get_hooks

	def get_hooks(hook=None, default="_KEEP_DEFAULT_", app_name=None):
		if hook in hooks:
			current = original(hook) if default == "_KEEP_DEFAULT_" else original(hook, default)
			extra = hooks[hook]
			if isinstance(extra, dict):
				merged = dict(current or {})
				for key, value in extra.items():
					merged[key] = list(merged.get(key, [])) + list(value)
				return merged
			return list(current or []) + list(extra)
		if default == "_KEEP_DEFAULT_":
			return original(hook) if hook else original()
		return original(hook, default)

	with patch.object(frappe, "get_hooks", side_effect=get_hooks):
		yield


@contextmanager
def fake_request(body: bytes, headers: dict | None = None):
	"""Make `frappe.request` carry this body and these headers for the block."""
	request = frappe._dict(get_data=lambda *a, **k: body, headers=headers or {}, method="POST")
	previous = getattr(frappe.local, "request", None)
	frappe.local.request = request
	try:
		yield request
	finally:
		if previous is None:
			try:
				delattr(frappe.local, "request")
			except AttributeError:
				pass
		else:
			frappe.local.request = previous
