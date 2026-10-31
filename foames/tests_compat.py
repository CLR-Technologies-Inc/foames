# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Test base classes that work on both Frappe v15 and v16."""

import frappe

try:
	from frappe.tests import IntegrationTestCase as _IntegrationTestCase
except ImportError:  # Frappe v15
	from frappe.tests.utils import FrappeTestCase as _IntegrationTestCase


class IntegrationTestCase(_IntegrationTestCase):
	"""Rolls each test back to a savepoint, so tests in one class do not see each other's records."""

	SAVEPOINT = "foames_test"

	def setUp(self):
		super().setUp()
		frappe.db.savepoint(self.SAVEPOINT)

	def tearDown(self):
		try:
			frappe.db.rollback(save_point=self.SAVEPOINT)
		except Exception:
			# A test that committed (an outbox run does) released the savepoint; roll back what is left.
			frappe.db.rollback()
		super().tearDown()


__all__ = ["IntegrationTestCase"]
