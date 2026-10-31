# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import frappe
from frappe.utils import get_datetime

from foames.foames_mes.doctype.downtime_record.downtime_record import close_open_downtime, open_downtime
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import make_machine, make_reason


class TestDowntimeRecord(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_machine("T-DT")

	def record(self, start="2026-10-20 08:00:00", end=None, **overrides):
		values = {"doctype": "Downtime Record", "machine": "T-DT", "start_time": start, "end_time": end}
		values.update(overrides)
		return frappe.get_doc(values).insert()

	def test_open_record_has_no_duration(self):
		record = self.record()
		self.assertEqual((record.status, record.duration_minutes, record.source), ("Open", None, "Manual"))

	def test_closed_record_gets_its_duration(self):
		record = self.record(end="2026-10-20 09:30:00")
		self.assertEqual((record.status, record.duration_minutes), ("Closed", 90))

	def test_end_before_start_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			self.record(end="2026-10-20 07:59:59")

	def test_zero_length_downtime_is_closed(self):
		record = self.record(end="2026-10-20 08:00:00")
		self.assertEqual((record.status, record.duration_minutes), ("Closed", 0))

	def test_clearing_the_end_reopens(self):
		record = self.record(end="2026-10-20 09:00:00")
		record.end_time = None
		record.save()
		self.assertEqual((record.status, record.duration_minutes), ("Open", None))

	def test_status_is_derived_not_chosen(self):
		record = self.record(status="Closed")
		self.assertEqual(record.status, "Open")

	def test_close_sets_the_end(self):
		record = self.record()
		record.close(get_datetime("2026-10-20 08:45:00"))
		record.reload()
		self.assertEqual((record.status, record.duration_minutes), ("Closed", 45))

	def test_open_downtime_is_idempotent_per_machine(self):
		first = open_downtime("T-DT", get_datetime("2026-10-20 08:00:00"))
		second = open_downtime("T-DT", get_datetime("2026-10-20 08:05:00"))
		self.assertEqual(first, second)
		self.assertEqual(frappe.db.count("Downtime Record", {"machine": "T-DT"}), 1)
		self.assertEqual(frappe.db.get_value("Downtime Record", first, "source"), "Automatic")

	def test_open_downtime_after_a_closed_one_is_new(self):
		first = open_downtime("T-DT", get_datetime("2026-10-20 08:00:00"))
		close_open_downtime("T-DT", get_datetime("2026-10-20 08:30:00"))
		second = open_downtime("T-DT", get_datetime("2026-10-20 09:00:00"))
		self.assertNotEqual(first, second)

	def test_close_open_downtime_closes_every_open_record_of_that_machine_only(self):
		make_machine("T-DT-OTHER")
		self.record()
		self.record(start="2026-10-20 08:10:00")
		other = frappe.get_doc(
			{"doctype": "Downtime Record", "machine": "T-DT-OTHER", "start_time": "2026-10-20 08:00:00"}
		).insert()
		close_open_downtime("T-DT", get_datetime("2026-10-20 09:00:00"))
		self.assertEqual(frappe.db.count("Downtime Record", {"machine": "T-DT", "status": "Open"}), 0)
		self.assertEqual(frappe.db.get_value("Downtime Record", other.name, "status"), "Open")
		durations = sorted(frappe.get_all("Downtime Record", {"machine": "T-DT"}, pluck="duration_minutes"))
		self.assertEqual(durations, [50, 60])

	def test_close_without_open_records_does_nothing(self):
		close_open_downtime("T-DT", get_datetime("2026-10-20 09:00:00"))
		self.assertEqual(frappe.db.count("Downtime Record", {"machine": "T-DT"}), 0)

	def test_reason_is_optional_and_linked(self):
		make_reason("T-DT-JAM", "Breakdown")
		record = self.record(reason="T-DT-JAM")
		self.assertEqual(record.reason, "T-DT-JAM")
		with self.assertRaises(frappe.LinkValidationError):
			self.record(reason="T-DT-NO-SUCH-REASON")


class TestDowntimeReason(IntegrationTestCase):
	def test_title_defaults_to_code(self):
		reason = make_reason("T-DR-PLAIN")
		self.assertEqual(
			(reason.title, reason.category, reason.counts_as_planned), ("T-DR-PLAIN", "Unplanned", 0)
		)

	def test_planned_and_changeover_count_as_planned(self):
		self.assertEqual(make_reason("T-DR-PM", "Planned").counts_as_planned, 1)
		self.assertEqual(make_reason("T-DR-CO", "Changeover").counts_as_planned, 1)

	def test_other_categories_may_be_marked_planned_by_hand(self):
		self.assertEqual(make_reason("T-DR-BD", "Breakdown").counts_as_planned, 0)
		self.assertEqual(make_reason("T-DR-NM", "No Material", counts_as_planned=1).counts_as_planned, 1)

	def test_code_is_the_name_and_unique(self):
		reason = make_reason("T-DR-NAME")
		self.assertEqual(reason.name, "T-DR-NAME")
		with self.assertRaises((frappe.DuplicateEntryError, frappe.UniqueValidationError)):
			frappe.get_doc({"doctype": "Downtime Reason", "code": "T-DR-NAME"}).insert()
