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
