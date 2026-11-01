# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""A machine assigned to an S/4HANA order operation: its counts and running time end up as partial
confirmations in the S4HANA Outbox, and from there in S/4HANA (the scripted fake here)."""

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime

from foames.foames_adapters.doctype.s4hana_outbox.s4hana_outbox import process_outbox
from foames.foames_adapters.doctype.s4hana_outbox.test_s4hana_outbox import (
	confirmation_posted,
	enable_s4hana,
)
from foames.foames_adapters.s4hana.adapter import ADAPTER_KEY
from foames.foames_adapters.s4hana.fake import FakeS4HANA, csrf, sap_error
from foames.foames_kernel.doctype.external_reference.external_reference import get_reference
from foames.tests_compat import IntegrationTestCase

ORDER, OPERATION = "1000123", "0010"


class TestConfirmationRollUp(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		from foames.foames_mes.doctype.oee_period.test_oee_period import make_machine

		enable_s4hana()
		settings = frappe.get_single("S4HANA Settings")
		settings.update(
			{
				"roll_up_counts_to_confirmations": 1,
				"confirmation_unit": "PC",
				"machine_time_activity_position": 2,
				"machine_time_unit": "MIN",
			}
		)
		settings.save()
		# The test operation does not exist anywhere; do not look it up in S/4HANA on save.
		frappe.db.set_single_value("FoaMES Settings", "skip_resolution_on_save", 1)
		self.machine = make_machine("FOAMES-TEST-S4RU", counter_rollover=0)
		if self.machine.current_job_reference:
			self.machine.set_current_job(None)
		frappe.db.delete("Machine Event", {"machine": self.machine.name})
		frappe.db.delete("S4HANA Outbox")
		frappe.db.commit()  # nosemgrep
		self.addCleanup(self.clean_up)

	def clean_up(self):
		# The outbox commits after each posting, so a rollback alone does not undo a test.
		frappe.db.rollback()
		frappe.db.delete("S4HANA Outbox")
		settings = frappe.get_single("S4HANA Settings")
		settings.update({"enabled": 0, "roll_up_counts_to_confirmations": 0})
		settings.save()
		frappe.db.set_single_value("FoaMES Settings", "skip_resolution_on_save", 0)
		frappe.db.commit()  # nosemgrep

	def events(self, rows):
		from foames.foames_mes.api import record_events

		result = record_events([{"machine": self.machine.name, **row} for row in rows], source="Manual")
		self.assertFalse(result["rejected"], result["rejected"])

	def outbox(self, name):
		return frappe.get_doc("S4HANA Outbox", name)

	def operation_reference(self):
		return get_reference("Job Card", f"{ORDER}|{OPERATION}", ADAPTER_KEY)

	def test_window_rolls_counts_and_run_time_into_a_confirmation(self):
		from foames.foames_adapters.s4hana.rollup import roll_up
		from foames.foames_mes.api import set_current_job

		start = add_to_date(now_datetime().replace(microsecond=0), hours=-26)
		t = lambda minutes: add_to_date(start, minutes=minutes)  # noqa: E731
		set_current_job(self.machine.name, self.operation_reference(), at=t(0))
		self.events(
			[
				{"type": "Count", "counter": "good", "value": 100, "timestamp": t(0)},
				{"type": "State", "state": "Running", "timestamp": t(5)},
				{"type": "Count", "counter": "good", "value": 104, "timestamp": t(30)},
				{"type": "Count", "counter": "scrap", "value": 7, "timestamp": t(30)},
				{"type": "Count", "counter": "scrap", "value": 8, "timestamp": t(31)},
				{"type": "State", "state": "Idle", "timestamp": t(40)},
			]
		)
		posting = roll_up(self.machine.name, until=t(60))
		self.assertTrue(posting)
		record = self.outbox(posting)
		self.assertEqual(record.operation, "Production Order Confirmation")
		self.assertEqual((record.sequence_group, record.reference_name), (ORDER, self.machine.name))
		payload = record.get_payload()
		self.assertEqual((payload["OrderID"], payload["OrderOperation"]), (ORDER, OPERATION))
		self.assertEqual(payload["ConfirmationYieldQuantity"], "4")
		self.assertEqual(payload["ConfirmationScrapQuantity"], "1")
		self.assertEqual(payload["ConfirmationUnit"], "PC")
		self.assertEqual((payload["OpConfirmedWorkQuantity2"], payload["OpWorkQuantityUnit2"]), ("35", "MIN"))
		self.assertNotIn("IsFinalConfirmation", payload)

		process_outbox(transport=confirmation_posted())
		record.reload()
		self.assertEqual(record.status, "Posted", record.last_error)
		self.assertEqual(record.sap_document, "77|1")

		# The next window starts where this one ended and has nothing to report.
		self.assertIsNone(roll_up(self.machine.name, until=t(90)))
		# Ending the job rolls up what came after, up to the moment the job changed.
		self.events([{"type": "Count", "counter": "good", "value": 106, "timestamp": t(100)}])
		set_current_job(self.machine.name, None, at=t(120))
		later = frappe.get_all(
			"S4HANA Outbox", {"reference_name": self.machine.name, "status": "Queued"}, pluck="name"
		)
		self.assertEqual(len(later), 1)
		payload = self.outbox(later[0]).get_payload()
		self.assertEqual(payload["ConfirmationYieldQuantity"], "2")
		self.assertNotIn("OpConfirmedWorkQuantity2", payload)
		from foames.foames_adapters.s4hana.production import window_end

		self.assertEqual(window_end(payload), get_datetime(t(120)))

	def test_nothing_happens_when_switched_off(self):
		from foames.foames_adapters.s4hana.rollup import roll_up_all
		from foames.foames_mes.api import set_current_job

		start = add_to_date(now_datetime().replace(microsecond=0), hours=-2)
		set_current_job(self.machine.name, self.operation_reference(), at=start)
		self.events(
			[
				{"type": "Count", "counter": "good", "value": 1, "timestamp": add_to_date(start, minutes=1)},
				{"type": "Count", "counter": "good", "value": 9, "timestamp": add_to_date(start, minutes=9)},
			]
		)
		frappe.db.set_single_value("S4HANA Settings", "roll_up_counts_to_confirmations", 0)
		frappe.clear_document_cache("S4HANA Settings", "S4HANA Settings")
		self.assertEqual(roll_up_all(), [])
		frappe.db.set_single_value("S4HANA Settings", "roll_up_counts_to_confirmations", 1)
		frappe.clear_document_cache("S4HANA Settings", "S4HANA Settings")
		queued = roll_up_all()
		self.assertEqual(len(queued), 1)
		self.assertEqual(self.outbox(queued[0]).get_payload()["ConfirmationYieldQuantity"], "8")

	def test_rejected_confirmation_is_flagged(self):
		from foames.foames_adapters.doctype.s4hana_outbox.s4hana_outbox import enqueue
		from foames.foames_adapters.s4hana.rollup import confirmation_rejected

		name = enqueue(
			"Production Order Confirmation",
			{
				"OrderID": ORDER,
				"OrderOperation": OPERATION,
				"ConfirmationYieldQuantity": "1",
				"ConfirmationUnit": "PC",
			},
			"s4ru-rejected",
			sequence_group=ORDER,
			reference_doctype="Machine",
			reference_name=self.machine.name,
		)
		locked = (
			FakeS4HANA()
			.on("FETCH", "CONFIRMATION", csrf())
			.on("POST", "ProdnOrdConf2", sap_error(400, "RU/100", "Order is locked"))
		)
		process_outbox(transport=locked)
		self.assertEqual(self.outbox(name).status, "Failed")
		# The machine has left the job: the confirmation that closed it can be the one that failed.
		snapshot = {"machines": [{"name": self.machine.name, "current_job": None}]}
		findings = confirmation_rejected(snapshot)
		self.assertEqual([f["reference_name"] for f in findings], [name])
		self.assertIn("Order is locked", findings[0]["suggestion"])

	def test_a_cancelled_window_is_not_rolled_up_again(self):
		from foames.foames_adapters.s4hana.rollup import roll_up
		from foames.foames_mes.api import set_current_job

		start = add_to_date(now_datetime().replace(microsecond=0), hours=-5)
		t = lambda minutes: add_to_date(start, minutes=minutes)  # noqa: E731
		set_current_job(self.machine.name, self.operation_reference(), at=t(0))
		self.events(
			[
				{"type": "Count", "counter": "good", "value": 10, "timestamp": t(1)},
				{"type": "Count", "counter": "good", "value": 15, "timestamp": t(10)},
			]
		)
		first = roll_up(self.machine.name, until=t(20))
		frappe.db.set_value("S4HANA Outbox", first, "status", "Cancelled")
		self.events([{"type": "Count", "counter": "good", "value": 18, "timestamp": t(30)}])
		second = roll_up(self.machine.name, until=t(40))
		# Only what came after the cancelled window: its 5 stay dropped.
		self.assertEqual(self.outbox(second).get_payload()["ConfirmationYieldQuantity"], "3")

	def test_an_operation_known_to_be_missing_is_not_rolled_up(self):
		from foames.foames_adapters.s4hana.rollup import job_for_reference

		reference = self.operation_reference()
		self.assertEqual(job_for_reference(reference), (ORDER, OPERATION, "0"))
		frappe.db.set_value("External Reference", reference, "status", "Missing")
		self.assertIsNone(job_for_reference(reference))
		frappe.db.set_value("External Reference", reference, "status", "Unverified")
		self.assertEqual(job_for_reference(reference), (ORDER, OPERATION, "0"))

	def test_settings_need_a_unit_and_a_valid_position(self):
		settings = frappe.get_single("S4HANA Settings")
		settings.confirmation_unit = ""
		with self.assertRaises(frappe.ValidationError):
			settings.save()
		settings.reload()
		settings.machine_time_activity_position = 7
		with self.assertRaises(frappe.ValidationError):
			settings.save()
