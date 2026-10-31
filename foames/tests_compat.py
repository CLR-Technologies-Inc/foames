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
		# A savepoint taken before InnoDB has joined the transaction (the first statement after a
		# commit) is recorded by the SQL layer only, and ROLLBACK TO it then fails with error 1305.
		# Reading a table first makes the storage engine part of the transaction.
		frappe.db.sql("select name from `tabDocType` limit 1")
		frappe.db.savepoint(self.SAVEPOINT)
		self._savepoint_taken = True

	def tearDown(self):
		try:
			if self._savepoint_taken:
				frappe.db.rollback(save_point=self.SAVEPOINT)
		except Exception:
			# A test that committed (the outbox does) or rolled back fully has discarded the
			# savepoint. Everything after the last commit goes, which is the next best isolation.
			frappe.db.rollback()
		super().tearDown()


__all__ = ["IntegrationTestCase"]
