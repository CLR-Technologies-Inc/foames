# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""End-to-end tests against an ERPNext installed on the same site. They skip elsewhere; CI runs
them in the "Frappe v16 + ERPNext" job.

The outbox commits after each posting, so these tests leave their Work Orders and Stock Entries in
the test site's FoaMES Test Co company.
"""

import unittest

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime

from foames.foames_adapters import get_adapter
from foames.foames_adapters.doctype.erpnext_outbox.erpnext_outbox import enqueue, process_outbox
from foames.foames_adapters.erpnext import ADAPTER_KEY, erpnext_installed
from foames.foames_adapters.erpnext import postings as rules
from foames.foames_kernel.doctype.external_reference.external_reference import get_reference
from foames.tests_compat import IntegrationTestCase


class ERPNextTestCase(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		if not erpnext_installed():
			raise unittest.SkipTest("ERPNext is not installed on this site")
		super().setUpClass()
		from foames.foames_adapters.erpnext import fixtures

		cls.fixtures = fixtures
		fixtures.ensure_manufacturing_setup()
		settings = frappe.get_single("ERPNext Adapter Settings")
		settings.update({"enable_postings": 1, "outbox_paused": 0, "show_job_cards_on_floor": 1})
		settings.save()
		frappe.db.commit()  # nosemgrep

	def setUp(self):
		super().setUp()
		frappe.db.delete("ERPNext Outbox")

	def run_outbox(self):
		return process_outbox()

	def outbox(self, name):
		return frappe.get_doc("ERPNext Outbox", name)


class TestResolution(ERPNextTestCase):
	def test_work_order_resolves_with_operations_and_items(self):
		wo = self.fixtures.make_work_order(qty=3)
		resolved = get_adapter(ADAPTER_KEY).resolve("Work Order", wo.name)
		self.assertEqual(resolved.label, self.fixtures.FINISHED_GOOD)
		self.assertEqual(resolved.data["qty"], 3)
		self.assertEqual(resolved.data["status"], "Not Started")
		self.assertEqual([op["operation"] for op in resolved.data["operations"]], [self.fixtures.OPERATION])
		self.assertEqual(resolved.data["required_items"][0]["item_code"], self.fixtures.RAW_MATERIAL)

	def test_bom_and_routing_details(self):
		bom = get_adapter(ADAPTER_KEY).resolve("Bill of Materials", self.fixtures.ensure_bom())
		self.assertEqual(bom.data["items"][0]["item_code"], self.fixtures.RAW_MATERIAL)
		self.assertEqual(bom.data["operations"][0]["workstation"], self.fixtures.WORKSTATION)
		self.assertIsNone(get_adapter(ADAPTER_KEY).resolve("Routing", "foames-no-such-routing"))

	def test_job_card_details(self):
		wo = self.fixtures.make_work_order(qty=2)
		job_card = self.fixtures.job_card_for(wo.name)
		resolved = get_adapter(ADAPTER_KEY).resolve("Job Card", job_card)
		self.assertEqual(resolved.data["work_order"], wo.name)
		self.assertEqual(resolved.data["for_quantity"], 2)
		self.assertEqual(resolved.data["time_logs"], [])


class TestStockEntryPostings(ERPNextTestCase):
	def test_transfer_then_manufacture_in_order(self):
		wo = self.fixtures.make_work_order(qty=4, operations=False)
		transfer = enqueue(
			"Material Transfer for Manufacture", {"work_order": wo.name}, f"{wo.name}:transfer", wo.name
		)
		manufacture = enqueue(
			"Manufacture", {"work_order": wo.name, "qty": 4}, f"{wo.name}:manufacture", wo.name
		)
		self.assertEqual(self.run_outbox(), 2)

		transfer_doc, manufacture_doc = self.outbox(transfer), self.outbox(manufacture)
		self.assertEqual(transfer_doc.status, "Posted", transfer_doc.last_error)
		self.assertEqual(manufacture_doc.status, "Posted", manufacture_doc.last_error)
		self.assertEqual(transfer_doc.erp_doctype, "Stock Entry")
		for doc in (transfer_doc, manufacture_doc):
			entry = frappe.get_doc("Stock Entry", doc.erp_document)
			self.assertEqual(entry.docstatus, 1)
			self.assertEqual(entry.work_order, wo.name)
			self.assertTrue(entry.remarks.startswith(rules.marker(doc.idempotency_key)))
			reference = frappe.get_doc("External Reference", doc.external_reference)
			self.assertEqual(
				(reference.erp_system, reference.reference_type), (ADAPTER_KEY, "Stock Movement")
			)
			self.assertEqual(reference.external_id, entry.name)
		wo.reload()
		self.assertEqual(wo.produced_qty, 4)
		self.assertEqual(wo.status, "Completed")

	def test_rejected_posting_fails_and_holds_its_group(self):
		wo = self.fixtures.make_work_order(qty=2, operations=False)
		# Manufacturing more than the Work Order allows is rejected by ERPNext.
		bad = enqueue("Manufacture", {"work_order": wo.name, "qty": 500}, f"{wo.name}:too-many", wo.name)
		later = enqueue(
			"Work Order Status", {"work_order": wo.name, "status": "Stopped"}, f"{wo.name}:stop", wo.name
		)
		self.run_outbox()
		self.assertEqual(self.outbox(bad).status, "Failed")
		self.assertTrue(self.outbox(bad).last_error)
		self.assertEqual(self.outbox(later).status, "Queued")
		# Nothing was left behind in ERPNext.
		self.assertFalse(frappe.db.exists("Stock Entry", {"work_order": wo.name}))

		self.outbox(bad).cancel_posting()
		frappe.db.commit()  # nosemgrep
		self.run_outbox()
		self.assertEqual(self.outbox(later).status, "Posted")
		self.assertEqual(frappe.db.get_value("Work Order", wo.name, "status"), "Stopped")

	def test_existing_document_is_found_by_marker(self):
		wo = self.fixtures.make_work_order(qty=1, skip_transfer=True, operations=False)
		name = enqueue("Manufacture", {"work_order": wo.name, "qty": 1}, f"{wo.name}:manufacture")
		self.run_outbox()
		first = self.outbox(name).erp_document
		# Simulate a lost outbox update: the Stock Entry exists, the record says Queued.
		frappe.db.set_value("ERPNext Outbox", name, {"status": "Queued", "erp_document": None, "attempts": 0})
		frappe.db.commit()  # nosemgrep
		self.run_outbox()
		self.assertEqual(self.outbox(name).erp_document, first)
		self.assertEqual(frappe.db.count("Stock Entry", {"work_order": wo.name}), 1)


class TestJobCardAndStatusPostings(ERPNextTestCase):
	def test_job_card_flow_then_manufacture(self):
		"""The sequence a machine or an agent drives: transfer materials, start the job card, complete
		it (which submits it), then book the finished goods. ERPNext refuses the Manufacture entry
		until the operation is complete, so the order inside the group matters."""
		wo = self.fixtures.make_work_order(qty=2)
		job_card = self.fixtures.job_card_for(wo.name)
		self.assertTrue(job_card)
		start = add_to_date(now_datetime(), minutes=-30)
		postings = [
			enqueue(
				"Material Transfer for Manufacture", {"work_order": wo.name}, f"{wo.name}:transfer", wo.name
			),
			enqueue(
				"Job Card Time Log", {"job_card": job_card, "start_time": start}, f"{job_card}:start", wo.name
			),
			enqueue(
				"Job Card Time Log",
				{"job_card": job_card, "complete_time": now_datetime(), "completed_qty": 2, "submit": True},
				f"{job_card}:complete",
				wo.name,
			),
			enqueue("Manufacture", {"work_order": wo.name, "qty": 2}, f"{wo.name}:manufacture", wo.name),
		]
		sent = self.run_outbox()
		# Check the statuses before the count, so a rejected posting fails with ERPNext's message
		# rather than with a bare count.
		for name in postings:
			self.assertEqual(self.outbox(name).status, "Posted", f"{name}: {self.outbox(name).last_error}")
		self.assertEqual(sent, 4)
		card = frappe.get_doc("Job Card", job_card)
		self.assertEqual(card.total_completed_qty, 2)
		self.assertEqual(card.docstatus, 1)
		self.assertIn(rules.marker(f"{job_card}:start"), card.remarks)
		self.assertIn(rules.marker(f"{job_card}:complete"), card.remarks)
		wo.reload()
		self.assertEqual(wo.produced_qty, 2)
		self.assertEqual(wo.status, "Completed")

	def test_completion_without_an_open_time_log_fails(self):
		wo = self.fixtures.make_work_order(qty=1)
		job_card = self.fixtures.job_card_for(wo.name)
		enqueue("Material Transfer for Manufacture", {"work_order": wo.name}, f"{wo.name}:transfer", wo.name)
		complete = enqueue(
			"Job Card Time Log",
			{"job_card": job_card, "complete_time": now_datetime(), "completed_qty": 1},
			f"{job_card}:complete-only",
			wo.name,
		)
		self.run_outbox()
		self.assertEqual(self.outbox(complete).status, "Failed")
		self.assertIn("no open time log", self.outbox(complete).last_error)
		self.assertEqual(frappe.db.get_value("Job Card", job_card, "total_completed_qty"), 0)

	def test_both_times_in_one_posting(self):
		wo = self.fixtures.make_work_order(qty=1)
		job_card = self.fixtures.job_card_for(wo.name)
		enqueue("Material Transfer for Manufacture", {"work_order": wo.name}, f"{wo.name}:transfer", wo.name)
		both = enqueue(
			"Job Card Time Log",
			{
				"job_card": job_card,
				"start_time": add_to_date(now_datetime(), minutes=-10),
				"complete_time": now_datetime(),
				"completed_qty": 1,
				"submit": False,
			},
			f"{job_card}:both",
			wo.name,
		)
		self.run_outbox()
		self.assertEqual(self.outbox(both).status, "Posted", self.outbox(both).last_error)
		card = frappe.get_doc("Job Card", job_card)
		self.assertEqual(card.docstatus, 0)
		self.assertEqual(card.total_completed_qty, 1)
		self.assertAlmostEqual(card.total_time_in_mins, 10, delta=1)

	def test_manufacture_before_the_operation_is_complete_fails(self):
		wo = self.fixtures.make_work_order(qty=2)
		enqueue("Material Transfer for Manufacture", {"work_order": wo.name}, f"{wo.name}:transfer", wo.name)
		early = enqueue("Manufacture", {"work_order": wo.name, "qty": 2}, f"{wo.name}:manufacture", wo.name)
		self.run_outbox()
		self.assertEqual(self.outbox(early).status, "Failed")
		self.assertIn("Job Card", self.outbox(early).last_error)

	def test_work_order_status_is_idempotent(self):
		wo = self.fixtures.make_work_order(qty=1, operations=False)
		enqueue("Work Order Status", {"work_order": wo.name, "status": "Stopped"}, f"{wo.name}:stop-1")
		again = enqueue(
			"Work Order Status", {"work_order": wo.name, "status": "Stopped"}, f"{wo.name}:stop-2"
		)
		resume = enqueue(
			"Work Order Status", {"work_order": wo.name, "status": "Resumed"}, f"{wo.name}:resume"
		)
		self.run_outbox()
		self.assertEqual(self.outbox(again).status, "Posted")
		self.assertEqual(self.outbox(resume).status, "Posted")
		self.assertEqual(frappe.db.get_value("Work Order", wo.name, "status"), "Not Started")


class TestReferenceSync(ERPNextTestCase):
	def test_deleting_the_record_marks_the_reference_missing(self):
		workstation = frappe.get_doc(
			{"doctype": "Workstation", "workstation_name": "FOAMES-TEST-TEMP-WS", "hour_rate": 1}
		).insert()
		reference = get_reference("Workstation", workstation.name, ADAPTER_KEY)
		self.assertEqual(frappe.db.get_value("External Reference", reference, "status"), "Resolved")
		workstation.delete()
		self.assertEqual(frappe.db.get_value("External Reference", reference, "status"), "Missing")

	def test_saving_the_record_refreshes_the_label(self):
		item = frappe.get_doc("Item", self.fixtures.FINISHED_GOOD)
		reference = get_reference("Item", item.name, ADAPTER_KEY)
		frappe.db.set_value("External Reference", reference, {"label": "stale", "status": "Unverified"})
		item.description = "touched"
		item.save()
		row = frappe.db.get_value("External Reference", reference, ["label", "status"], as_dict=True)
		self.assertEqual((row.label, row.status), (item.item_name, "Resolved"))

	def test_daily_refresh_resolves_unverified_references(self):
		from foames.foames_kernel.tasks import refresh_external_references

		reference = get_reference("Item", self.fixtures.RAW_MATERIAL, ADAPTER_KEY)
		frappe.db.set_value("External Reference", reference, {"status": "Unverified", "label": None})
		checked = refresh_external_references()
		self.assertGreaterEqual(checked.get(ADAPTER_KEY, 0), 1)
		self.assertEqual(frappe.db.get_value("External Reference", reference, "status"), "Resolved")


class TestFloor(ERPNextTestCase):
	def test_job_cards_appear_on_the_machine(self):
		from foames.foames_adapters.erpnext.floor import running_without_job_card
		from foames.foames_mes.floor import floor_snapshot

		wo = self.fixtures.make_work_order(qty=1)
		machine = frappe.get_doc(
			{
				"doctype": "Machine",
				"code": "FOAMES-TEST-M1",
				"title": "Test machine",
				"workstation_reference": get_reference("Workstation", self.fixtures.WORKSTATION, ADAPTER_KEY),
			}
		).insert()
		snapshot = floor_snapshot()
		tile = next(m for m in snapshot["machines"] if m["name"] == machine.name)
		self.assertEqual(tile["workstation"], self.fixtures.WORKSTATION)
		self.assertIn(wo.name, [jc["work_order"] for jc in tile["job_cards"]])
		self.assertEqual(snapshot["erp"]["system"], ADAPTER_KEY)
		self.assertIn(wo.name, [row["name"] for row in snapshot["erp"]["open_work_orders"]])
		# A running machine with job cards raises nothing; without them it does.
		tile["status"] = "Running"
		self.assertEqual(running_without_job_card(snapshot), [])
		tile["job_cards"] = []
		findings = running_without_job_card(snapshot)
		self.assertEqual(len(findings), 1)
		self.assertEqual(findings[0]["reference_name"], machine.name)


class TestJobCardRollUp(ERPNextTestCase):
	"""A machine assigned to a Job Card: its counts and running time end up on the card."""

	def setUp(self):
		super().setUp()
		from foames.foames_mes.doctype.oee_period.test_oee_period import make_machine

		settings = frappe.get_single("ERPNext Adapter Settings")
		settings.roll_up_counts_to_job_cards = 1
		settings.save()
		self.machine = make_machine("FOAMES-TEST-RU", counter_rollover=0)
		frappe.db.delete("Machine Event", {"machine": self.machine.name})

	def events(self, rows):
		from foames.foames_mes.api import record_events

		result = record_events([{"machine": self.machine.name, **row} for row in rows], source="Manual")
		self.assertFalse(result["rejected"], result["rejected"])

	def test_window_rolls_counts_and_run_time_to_the_job_card(self):
		from foames.foames_adapters.erpnext.rollup import roll_up
		from foames.foames_mes.api import set_current_job

		wo = self.fixtures.make_work_order(qty=10)
		job_card = self.fixtures.job_card_for(wo.name)
		# Well clear of the time logs other tests leave on the same workstation, which would overlap.
		start = add_to_date(now_datetime(), hours=-26)
		t = lambda minutes: add_to_date(start, minutes=minutes)  # noqa: E731
		set_current_job(self.machine.name, get_reference("Job Card", job_card, ADAPTER_KEY), at=t(0))
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
		self.assertEqual(self.run_outbox(), 1)
		record = self.outbox(posting)
		self.assertEqual(record.status, "Posted", record.last_error)
		self.assertEqual(record.erp_document, job_card)
		card = frappe.get_doc("Job Card", job_card)
		self.assertEqual(len(card.time_logs), 1)
		self.assertEqual(
			(get_datetime(card.time_logs[0].from_time), get_datetime(card.time_logs[0].to_time)),
			(get_datetime(t(5)), get_datetime(t(40))),
		)
		self.assertEqual(card.total_completed_qty, 4)
		self.assertEqual(card.total_time_in_mins, 35)
		if card.meta.has_field("process_loss_qty"):
			self.assertEqual(card.process_loss_qty, 1)
		self.assertIn(rules.marker(record.idempotency_key), card.remarks)

		# The next window starts where this one ended and has nothing to report.
		self.assertIsNone(roll_up(self.machine.name, until=t(90)))
		# Ending the job rolls up what came after, up to the moment the job changed.
		self.events([{"type": "Count", "counter": "good", "value": 106, "timestamp": t(100)}])
		set_current_job(self.machine.name, None, at=t(120))
		later = frappe.get_all(
			"ERPNext Outbox", {"reference_name": self.machine.name, "status": "Queued"}, pluck="name"
		)
		self.assertEqual(len(later), 1)
		payload = self.outbox(later[0]).get_payload()
		self.assertEqual(
			(payload["completed_qty"], get_datetime(payload["to_time"])), (2, get_datetime(t(120)))
		)
		self.run_outbox()
		card.reload()
		self.assertEqual(card.total_completed_qty, 6)
		self.assertEqual(len(card.time_logs), 2)

	def test_machine_on_a_closed_job_card_is_flagged(self):
		from foames.foames_adapters.erpnext.rollup import current_job_card_not_open
		from foames.foames_mes.api import set_current_job
		from foames.foames_mes.floor import floor_snapshot

		wo = self.fixtures.make_work_order(qty=1)
		job_card = self.fixtures.job_card_for(wo.name)
		set_current_job(self.machine.name, get_reference("Job Card", job_card, ADAPTER_KEY))
		tile = next(m for m in floor_snapshot()["machines"] if m["name"] == self.machine.name)
		self.assertTrue(tile["current_job"]["open"])
		self.assertEqual(current_job_card_not_open(floor_snapshot()), [])
		frappe.delete_doc("Job Card", job_card, force=True)
		snapshot = floor_snapshot()
		findings = current_job_card_not_open(snapshot)
		self.assertEqual([f["reference_name"] for f in findings], [self.machine.name])
