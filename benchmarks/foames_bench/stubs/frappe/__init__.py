# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""A minimal stand-in for the `frappe` package, so FoaMES's pure modules import without a bench.

Some package `__init__` files import frappe for their site-side helpers. The benchmark's pure tasks
never call those helpers; this stub only lets the import succeed. Anything that really needs a site
raises at call time, which marks the task as needing the Frappe tier.
"""

flags = type("Flags", (), {"in_test": True})()


class _NeedsSite(RuntimeError):
	pass


def _needs_site(*args, **kwargs):
	raise _NeedsSite("this code path needs a Frappe site; run it on the dev bench")


def whitelist(*args, **kwargs):
	if args and callable(args[0]) and len(args) == 1 and not kwargs:
		return args[0]
	return lambda fn: fn


def _(text, *args, **kwargs):
	return text


def get_hooks(*args, **kwargs):
	return []


get_attr = get_doc = get_all = get_value = db = throw = _needs_site
