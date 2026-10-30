# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Test base classes that work on both Frappe v15 and v16."""

try:
	from frappe.tests import IntegrationTestCase
except ImportError:  # Frappe v15
	from frappe.tests.utils import FrappeTestCase as IntegrationTestCase

__all__ = ["IntegrationTestCase"]
