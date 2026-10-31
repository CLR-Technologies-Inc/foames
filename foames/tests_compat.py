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
		# InnoDB only joins the transaction on the first statement that touches a table. Right after
		# the class setup's commit, a bare SAVEPOINT would be taken outside it and ROLLBACK TO would
		# fail with error 1305, so read a row first.
		frappe.db.sql("select name from `tabDocType` limit 1")
		frappe.db.savepoint(self.SAVEPOINT)

	def tearDown(self):
		try:
			frappe.db.rollback(save_point=self.SAVEPOINT)
		except Exception:
			# The savepoint is gone when the connection's transaction ended under the test (Frappe v15
			# does this on some sites). Roll the whole transaction back instead: the class setup
			# committed, so this still leaves only the records the class started with.
			frappe.db.rollback()
		super().tearDown()


__all__ = ["IntegrationTestCase"]
