# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""End-to-end tests against an ERPNext installed on the same site. They skip elsewhere; CI runs
them in the "Frappe v16 + ERPNext" job.

The outbox commits after each posting, so these tests leave their Work Orders and Stock Entries in
the test site's FoaMES Test Co company.
"""

import json
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
		# References are resolved on save here; an earlier test may have committed the skip flag.
		frappe.db.set_single_value("FoaMES Settings", "skip_resolution_on_save", 0)

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
		# Whole seconds: ERPNext stores time log boundaries without microseconds.
		start = add_to_date(now_datetime().replace(microsecond=0), hours=-26)
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
			# Recent ERPNext derives the field as planned minus completed minus pending when the
			# Job Card is saved; the posting sets the pending quantity so the scrap comes out exact.
			self.assertEqual(card.process_loss_qty, 1)
		self.assertIn(rules.marker(record.idempotency_key), card.remarks)
		self.assertIn("scrap 1", card.remarks)

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
		if card.meta.has_field("process_loss_qty"):
			self.assertEqual(card.process_loss_qty, 1)

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


class TestWorkstationStatus(ERPNextTestCase):
	"""A machine's state shows on its ERPNext Workstation, through the outbox, latest state only."""

	def setUp(self):
		super().setUp()
		from foames.foames_mes.doctype.oee_period.test_oee_period import make_machine

		settings = frappe.get_single("ERPNext Adapter Settings")
		settings.sync_machine_state_to_workstations = 1
		settings.save()
		self.machine = make_machine(
			"FOAMES-TEST-WS-SYNC",
			workstation_reference=get_reference("Workstation", self.fixtures.WORKSTATION, ADAPTER_KEY),
		)
		frappe.db.set_value("Workstation", self.fixtures.WORKSTATION, "status", "Off")

	def test_state_changes_reach_the_workstation(self):
		at = add_to_date(now_datetime(), minutes=-5)
		self.machine.set_state("Running", at)
		queued = frappe.get_all(
			"ERPNext Outbox", {"operation": "Workstation Status", "status": "Queued"}, pluck="name"
		)
		self.assertEqual(len(queued), 1)
		self.assertEqual(self.run_outbox(), 1)
		record = self.outbox(queued[0])
		self.assertEqual(record.status, "Posted", record.last_error)
		self.assertEqual(
			frappe.db.get_value("Workstation", self.fixtures.WORKSTATION, "status"), "Production"
		)
		# Down shows as Problem; a lost signal as Off.
		self.machine.set_state("Down", add_to_date(at, minutes=1))
		self.run_outbox()
		self.assertEqual(frappe.db.get_value("Workstation", self.fixtures.WORKSTATION, "status"), "Problem")
		self.machine.set_state("Unknown", add_to_date(at, minutes=2))
		self.run_outbox()
		self.assertEqual(frappe.db.get_value("Workstation", self.fixtures.WORKSTATION, "status"), "Off")

	def test_only_the_latest_state_is_posted(self):
		at = add_to_date(now_datetime(), minutes=-5)
		self.machine.set_state("Running", at)
		self.machine.set_state("Idle", add_to_date(at, minutes=1))
		self.machine.set_state("Running", add_to_date(at, minutes=2))
		rows = frappe.get_all(
			"ERPNext Outbox", {"operation": "Workstation Status"}, ["status", "payload"], order_by="creation"
		)
		self.assertEqual([r.status for r in rows], ["Cancelled", "Cancelled", "Queued"])
		self.assertEqual(self.run_outbox(), 1)
		self.assertEqual(
			frappe.db.get_value("Workstation", self.fixtures.WORKSTATION, "status"), "Production"
		)
		# Repeating the state the Workstation already shows is done without a write.
		self.machine.set_state("Idle", add_to_date(at, minutes=3))
		frappe.db.set_value("Workstation", self.fixtures.WORKSTATION, "status", "Idle")
		self.run_outbox()
		latest = frappe.get_all(
			"ERPNext Outbox",
			{"operation": "Workstation Status"},
			["status", "response"],
			order_by="creation desc",
		)[0]
		self.assertEqual(latest.status, "Posted")

	def test_nothing_is_queued_when_the_switch_is_off(self):
		settings = frappe.get_single("ERPNext Adapter Settings")
		settings.sync_machine_state_to_workstations = 0
		settings.save()
		self.machine.set_state("Running", now_datetime())
		self.assertEqual(frappe.db.count("ERPNext Outbox", {"operation": "Workstation Status"}), 0)


class TestDowntimeEntries(ERPNextTestCase):
	"""A closed Downtime Record becomes an ERPNext Downtime Entry, and follows the record's reason."""

	def setUp(self):
		super().setUp()
		from foames.foames_mes.doctype.oee_period.test_oee_period import make_machine
		from foames.tests_helpers import make_reason

		settings = frappe.get_single("ERPNext Adapter Settings")
		settings.post_downtime_to_erpnext = 1
		settings.downtime_operator = self.fixtures.ensure_employee()
		settings.save()
		self.machine = make_machine(
			"FOAMES-TEST-DT-SYNC",
			workstation_reference=get_reference("Workstation", self.fixtures.WORKSTATION, ADAPTER_KEY),
		)
		self.reason = make_reason("FOAMES-TEST-BRK", category="Breakdown", title="Spindle failure")
		frappe.db.delete("Downtime Entry", {"workstation": self.fixtures.WORKSTATION})
		frappe.db.delete("Downtime Record", {"machine": self.machine.name})

	def test_closed_downtime_is_posted_and_updated(self):
		# Well in the past: ERPNext refuses overlapping entries on a workstation and the outbox commits.
		start = add_to_date(now_datetime(), days=-3).replace(microsecond=0)
		self.machine.set_state("Down", start)
		self.assertEqual(frappe.db.count("ERPNext Outbox", {"operation": "Downtime Entry"}), 0)
		self.machine.set_state("Running", add_to_date(start, minutes=45))
		queued = frappe.get_all("ERPNext Outbox", {"operation": "Downtime Entry"}, pluck="name")
		self.assertEqual(len(queued), 1)
		self.assertEqual(self.run_outbox(), 1)
		record = self.outbox(queued[0])
		self.assertEqual(record.status, "Posted", record.last_error)
		entry = frappe.get_doc("Downtime Entry", record.erp_document)
		self.assertEqual(entry.workstation, self.fixtures.WORKSTATION)
		self.assertEqual(
			(get_datetime(entry.from_time), get_datetime(entry.to_time)),
			(start, add_to_date(start, minutes=45)),
		)
		self.assertEqual(entry.downtime, 45)
		self.assertEqual(entry.stop_reason, "Other")
		self.assertEqual(entry.operator, self.fixtures.ensure_employee())
		self.assertIn(rules.downtime_marker(record.reference_name), entry.remarks)

		# A person assigns the reason afterwards: the same entry is updated, not a second one made.
		downtime = frappe.get_doc("Downtime Record", record.reference_name)
		downtime.reason = self.reason.name
		downtime.notes = "Bearing seized"
		downtime.save()
		later = frappe.get_all(
			"ERPNext Outbox", {"operation": "Downtime Entry", "status": "Queued"}, pluck="name"
		)
		self.assertEqual(len(later), 1)
		self.assertEqual(self.run_outbox(), 1)
		self.assertEqual(self.outbox(later[0]).status, "Posted", self.outbox(later[0]).last_error)
		self.assertEqual(frappe.db.count("Downtime Entry", {"workstation": self.fixtures.WORKSTATION}), 1)
		entry.reload()
		self.assertEqual(entry.stop_reason, "Machine malfunction")
		self.assertIn("Spindle failure", entry.remarks)
		self.assertIn("Bearing seized", entry.remarks)
		# Saving the record again without a change queues nothing new.
		downtime.save()
		self.assertEqual(frappe.db.count("ERPNext Outbox", {"operation": "Downtime Entry"}), 2)

	def test_without_an_operator_the_posting_fails_with_a_clear_message(self):
		settings = frappe.get_single("ERPNext Adapter Settings")
		settings.downtime_operator = None
		settings.save()
		start = add_to_date(now_datetime(), days=-4).replace(microsecond=0)
		self.machine.set_state("Down", start)
		self.machine.set_state("Idle", add_to_date(start, minutes=5))
		[name] = frappe.get_all("ERPNext Outbox", {"operation": "Downtime Entry"}, pluck="name")
		self.run_outbox()
		self.assertEqual(self.outbox(name).status, "Failed")
		self.assertIn("operator", self.outbox(name).last_error)
		self.assertEqual(frappe.db.count("Downtime Entry", {"workstation": self.fixtures.WORKSTATION}), 0)


class TestTraceability(ERPNextTestCase):
	"""The batch and serial numbers a Manufacture entry gives the finished good, and the External
	References FoaMES keeps for them."""

	def manufacture(self, wo, **extra):
		enqueue("Material Transfer for Manufacture", {"work_order": wo.name}, f"{wo.name}:transfer", wo.name)
		posting = enqueue(
			"Manufacture", {"work_order": wo.name, "qty": wo.qty, **extra}, f"{wo.name}:manufacture", wo.name
		)
		self.run_outbox()
		record = self.outbox(posting)
		self.assertEqual(record.status, "Posted", record.last_error)
		return record, json.loads(record.response)["finished_good"]

	def test_manufacture_names_the_batch(self):
		wo = self.fixtures.make_work_order(qty=3, operations=False, item=self.fixtures.FINISHED_GOOD_BATCHED)
		batch_no = f"FOAMES-TB-TEST-{frappe.generate_hash(length=6).upper()}"
		record, finished = self.manufacture(wo, batch_no=batch_no)
		self.assertEqual(finished["item_code"], self.fixtures.FINISHED_GOOD_BATCHED)
		self.assertEqual(finished["batch_no"], batch_no)
		self.assertEqual(frappe.db.get_value("Batch", batch_no, "item"), self.fixtures.FINISHED_GOOD_BATCHED)
		# The stock really went in under that batch, and FoaMES has a reference to it.
		ledger = frappe.get_all(
			"Stock Ledger Entry",
			{"voucher_no": record.erp_document, "item_code": self.fixtures.FINISHED_GOOD_BATCHED},
			["actual_qty"],
		)
		self.assertEqual(sum(row.actual_qty for row in ledger), 3)
		self.assertTrue(
			frappe.db.exists(
				"External Reference",
				{"erp_system": ADAPTER_KEY, "reference_type": "Batch", "external_id": batch_no},
			)
		)
		# A replay after a lost outbox update finds the entry by its marker and still reports the
		# finished good, and the posting's status read through the API carries the response.
		frappe.db.set_value(
			"ERPNext Outbox", record.name, {"status": "Queued", "erp_document": None, "attempts": 0}
		)
		frappe.db.commit()  # nosemgrep
		self.run_outbox()
		replayed = self.outbox(record.name)
		self.assertEqual(replayed.erp_document, record.erp_document)
		response = json.loads(replayed.response)
		self.assertEqual(response["found_by"], "marker")
		self.assertEqual(response["finished_good"]["batch_no"], batch_no)
		from foames.foames_adapters.erpnext.api import get_posting

		self.assertEqual(get_posting(record.name)["response"]["finished_good"]["batch_no"], batch_no)

	def test_manufacture_without_a_batch_reports_the_one_erpnext_made(self):
		wo = self.fixtures.make_work_order(qty=2, operations=False, item=self.fixtures.FINISHED_GOOD_BATCHED)
		_, finished = self.manufacture(wo)
		self.assertTrue(finished["batch_no"], finished)
		self.assertTrue(finished["batch_no"].startswith("FOAMES-TB-"))

	def test_manufacture_names_the_serial_numbers(self):
		wo = self.fixtures.make_work_order(qty=2, operations=False, item=self.fixtures.FINISHED_GOOD_SERIAL)
		suffix = frappe.generate_hash(length=6).upper()
		serials = [f"FOAMES-TS-TEST-{suffix}-1", f"FOAMES-TS-TEST-{suffix}-2"]
		_, finished = self.manufacture(wo, serial_nos=serials)
		self.assertEqual(sorted(finished["serial_nos"]), serials)
		for serial in serials:
			self.assertEqual(frappe.db.get_value("Serial No", serial, "warehouse"), self.fixtures.FINISHED)
			self.assertTrue(
				frappe.db.exists(
					"External Reference",
					{"erp_system": ADAPTER_KEY, "reference_type": "Serial Number", "external_id": serial},
				)
			)

	def test_a_batch_of_another_item_is_refused(self):
		wo = self.fixtures.make_work_order(qty=1, operations=False, item=self.fixtures.FINISHED_GOOD_BATCHED)
		other_item = "FOAMES-TEST-OTHER-B"
		if not frappe.db.exists("Item", other_item):
			frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": other_item,
					"item_name": other_item,
					"item_group": frappe.db.get_value("Item", self.fixtures.RAW_MATERIAL, "item_group"),
					"stock_uom": "Nos",
					"is_stock_item": 1,
					"has_batch_no": 1,
				}
			).insert(ignore_permissions=True)
		other = frappe.get_doc(
			{
				"doctype": "Batch",
				"batch_id": f"FOAMES-TB-OTHER-{frappe.generate_hash(length=6).upper()}",
				"item": other_item,
			}
		).insert(ignore_permissions=True)
		enqueue("Material Transfer for Manufacture", {"work_order": wo.name}, f"{wo.name}:transfer", wo.name)
		posting = enqueue(
			"Manufacture",
			{"work_order": wo.name, "qty": 1, "batch_no": other.name},
			f"{wo.name}:manufacture",
			wo.name,
		)
		self.run_outbox()
		self.assertEqual(self.outbox(posting).status, "Failed")
		self.assertIn("another item", self.outbox(posting).last_error)

	def test_draft_entry_gets_its_serial_references_on_submission(self):
		wo = self.fixtures.make_work_order(
			qty=2, skip_transfer=True, operations=False, item=self.fixtures.FINISHED_GOOD_SERIAL
		)
		serials = [f"FOAMES-TS-DRAFT-{frappe.generate_hash(length=5).upper()}-{i}" for i in (1, 2)]
		posting = enqueue(
			"Manufacture",
			{"work_order": wo.name, "qty": 2, "serial_nos": serials, "submit": False},
			f"{wo.name}:manufacture",
			wo.name,
		)
		self.run_outbox()
		record = self.outbox(posting)
		self.assertEqual(record.status, "Posted", record.last_error)
		reference = {"erp_system": ADAPTER_KEY, "reference_type": "Serial Number", "external_id": serials[0]}
		self.assertFalse(frappe.db.exists("External Reference", reference))
		# A person reviews the draft and submits it in ERPNext: the serial numbers now exist.
		frappe.get_doc("Stock Entry", record.erp_document).submit()
		self.assertTrue(frappe.db.exists("Serial No", serials[0]))
		for serial in serials:
			self.assertTrue(frappe.db.exists("External Reference", {**reference, "external_id": serial}))


def hasattr_erpnext_reading_parser() -> bool:
	"""Whether the installed ERPNext reads Quality Inspection readings in the user's number format."""
	try:
		frappe.get_attr("erpnext.stock.doctype.quality_inspection.quality_inspection.get_reading_separators")
	except (AttributeError, ImportError):
		return False
	return True


class TestQualityInspections(ERPNextTestCase):
	"""Floor readings become ERPNext Quality Inspections, judged by the template's limits."""

	LENGTH, COLOUR = "FOAMES-TEST-LENGTH", "FOAMES-TEST-COLOUR"

	def inspect(self, reference_type, reference_name, readings, key, group="reference", **extra):
		"""Queue one inspection and perform the outbox. Postings share the document's sequence group
		unless `group` is None: a Failed posting holds the later ones of its group back, which the
		tests that expect failures avoid."""
		name = enqueue(
			"Quality Inspection",
			{
				"reference_type": reference_type,
				"reference_name": reference_name,
				"readings": readings,
				**extra,
			},
			key,
			reference_name if group == "reference" else group,
		)
		self.run_outbox()
		return self.outbox(name)

	def test_job_card_inspection_is_accepted_and_linked(self):
		wo = self.fixtures.make_work_order(qty=2)
		job_card = self.fixtures.job_card_for(wo.name)
		self.assertEqual(
			frappe.db.get_value("Job Card", job_card, "quality_inspection_template"),
			self.fixtures.INSPECTION_TEMPLATE,
		)
		record = self.inspect(
			"Job Card",
			job_card,
			[
				{"specification": self.LENGTH, "values": [10.1, 9.9, 10.4]},
				{"specification": self.COLOUR, "value": "Blue"},
			],
			f"{job_card}:inspection",
		)
		self.assertEqual(record.status, "Posted", record.last_error)
		response = json.loads(record.response)
		self.assertEqual((response["status"], response["docstatus"]), ("Accepted", 1))
		self.assertEqual([r["status"] for r in response["readings"]], ["Accepted", "Accepted"])
		inspection = frappe.get_doc("Quality Inspection", record.erp_document)
		self.assertEqual(inspection.inspection_type, "In Process")
		self.assertEqual(inspection.item_code, self.fixtures.FINISHED_GOOD)
		self.assertEqual(inspection.sample_size, 3)
		self.assertEqual(inspection.readings[0].reading_1, "10.1")
		self.assertEqual((inspection.readings[0].min_value, inspection.readings[0].max_value), (9.5, 10.5))
		# ERPNext links the submitted inspection to the Job Card, which is what completing it checks.
		self.assertEqual(frappe.db.get_value("Job Card", job_card, "quality_inspection"), inspection.name)
		# A replay finds the inspection by its marker and reports the same outcome.
		frappe.db.set_value(
			"ERPNext Outbox", record.name, {"status": "Queued", "erp_document": None, "attempts": 0}
		)
		frappe.db.commit()  # nosemgrep
		self.run_outbox()
		replayed = self.outbox(record.name)
		self.assertEqual(replayed.erp_document, inspection.name)
		self.assertEqual(json.loads(replayed.response)["status"], "Accepted")
		self.assertEqual(frappe.db.count("Quality Inspection", {"reference_name": job_card}), 1)

	def test_out_of_range_reading_rejects_the_inspection(self):
		wo = self.fixtures.make_work_order(qty=1)
		job_card = self.fixtures.job_card_for(wo.name)
		record = self.inspect(
			"Job Card",
			job_card,
			[
				{"specification": self.LENGTH, "values": [10.1, 11.2]},
				{"specification": self.COLOUR, "value": "Red"},
			],
			f"{job_card}:inspection",
			submit=False,
		)
		self.assertEqual(record.status, "Posted", record.last_error)
		response = json.loads(record.response)
		self.assertEqual((response["status"], response["docstatus"]), ("Rejected", 0))
		self.assertEqual([r["status"] for r in response["readings"]], ["Rejected", "Rejected"])

	def test_readings_outside_the_template_need_their_own_limits(self):
		wo = self.fixtures.make_work_order(qty=1)
		job_card = self.fixtures.job_card_for(wo.name)
		parameter = "FOAMES-TEST-WEIGHT"
		if not frappe.db.exists("Quality Inspection Parameter", parameter):
			frappe.get_doc({"doctype": "Quality Inspection Parameter", "parameter": parameter}).insert()
		failed = self.inspect(
			"Job Card",
			job_card,
			[{"specification": parameter, "values": [250]}],
			f"{job_card}:weight-1",
			group=None,
		)
		self.assertEqual(failed.status, "Failed")
		self.assertIn("not in template", failed.last_error)
		unknown = self.inspect(
			"Job Card",
			job_card,
			[{"specification": "FOAMES-NO-SUCH", "values": [1]}],
			f"{job_card}:weight-2",
			group=None,
		)
		self.assertEqual(unknown.status, "Failed")
		self.assertIn("no Quality Inspection Parameter", unknown.last_error)
		# An item the Job Card does not produce cannot be inspected against it.
		other = self.inspect(
			"Job Card",
			job_card,
			[{"specification": self.LENGTH, "values": [10]}],
			f"{job_card}:other-item",
			group=None,
			item_code=self.fixtures.RAW_MATERIAL,
		)
		self.assertEqual(other.status, "Failed")
		self.assertIn("does not produce or move", other.last_error)
		# With limits of its own the reading is judged against them.
		record = self.inspect(
			"Job Card",
			job_card,
			[{"specification": parameter, "values": [250, 262], "min_value": 240, "max_value": 260}],
			f"{job_card}:weight-3",
			group=None,
		)
		self.assertEqual(record.status, "Posted", record.last_error)
		self.assertEqual(json.loads(record.response)["status"], "Rejected")

	def test_readings_follow_the_posting_users_number_format(self):
		from foames.foames_adapters.erpnext.executor import plain_number

		self.assertEqual(plain_number(10.1), "10.1")
		self.assertEqual((plain_number(250), plain_number(0.005)), ("250", "0.005"))
		frappe.defaults.set_user_default("number_format", "#.###,##")
		try:
			expected = "10,1" if hasattr_erpnext_reading_parser() else "10.1"
			self.assertEqual(plain_number(10.1), expected)
			wo = self.fixtures.make_work_order(qty=1)
			job_card = self.fixtures.job_card_for(wo.name)
			record = self.inspect(
				"Job Card",
				job_card,
				[{"specification": self.LENGTH, "values": [10.1, 9.75]}],
				f"{job_card}:comma",
			)
			self.assertEqual(record.status, "Posted", record.last_error)
			self.assertEqual(json.loads(record.response)["status"], "Accepted")
		finally:
			frappe.defaults.clear_user_default("number_format")

	def test_manufacture_entry_is_inspected_as_it_comes_in(self):
		wo = self.fixtures.make_work_order(qty=1, skip_transfer=True, operations=False)
		posting = enqueue("Manufacture", {"work_order": wo.name, "qty": 1}, f"{wo.name}:manufacture", wo.name)
		self.run_outbox()
		entry = self.outbox(posting).erp_document
		self.assertTrue(entry)
		record = self.inspect(
			"Stock Entry",
			entry,
			[{"specification": self.LENGTH, "values": [10.0]}],
			f"{entry}:inspection",
			template=self.fixtures.INSPECTION_TEMPLATE,
		)
		self.assertEqual(record.status, "Posted", record.last_error)
		inspection = frappe.get_doc("Quality Inspection", record.erp_document)
		self.assertEqual((inspection.inspection_type, inspection.status), ("Incoming", "Accepted"))
		self.assertEqual(inspection.item_code, self.fixtures.FINISHED_GOOD)
		self.assertEqual(
			frappe.db.get_value(
				"Stock Entry Detail",
				{"parent": entry, "item_code": self.fixtures.FINISHED_GOOD},
				"quality_inspection",
			),
			inspection.name,
		)

	def test_inspection_from_machine_measurements(self):
		from foames.foames_adapters.erpnext.api import post_inspection_from_measurements
		from foames.foames_adapters.erpnext.quality import measurement_readings
		from foames.foames_mes.api import record_events
		from foames.foames_mes.doctype.oee_period.test_oee_period import make_machine

		machine = make_machine("FOAMES-TEST-QI")
		frappe.db.delete("Machine Event", {"machine": machine.name})
		start = add_to_date(now_datetime().replace(microsecond=0), hours=-2)
		t = lambda minutes: add_to_date(start, minutes=minutes)  # noqa: E731
		rows = [
			{
				"type": "Measurement",
				"name": self.LENGTH,
				"value": 9.0,
				"timestamp": t(-5),
			},  # before the window
			*[
				{"type": "Measurement", "name": self.LENGTH, "value": 10 + i / 100, "timestamp": t(i)}
				for i in range(12)
			],
			{"type": "Measurement", "name": "temperature", "value": 71.5, "timestamp": t(3)},
		]
		result = record_events([{"machine": machine.name, **row} for row in rows], source="Manual")
		self.assertFalse(result["rejected"], result["rejected"])
		readings = measurement_readings(machine.name, t(0), t(30))
		self.assertEqual([r["specification"] for r in readings], [self.LENGTH, "temperature"])
		# The last ten values, in time order.
		self.assertEqual(readings[0]["values"], [round(10 + i / 100, 2) for i in range(2, 12)])
		self.assertEqual(
			measurement_readings(machine.name, t(0), t(30), specifications=[self.LENGTH]),
			[readings[0]],
		)

		wo = self.fixtures.make_work_order(qty=1)
		job_card = self.fixtures.job_card_for(wo.name)
		queued = post_inspection_from_measurements(
			"Job Card", job_card, machine.name, t(0), t(30), specifications=[self.LENGTH]
		)
		self.assertTrue(queued["created"])
		self.assertEqual(self.run_outbox(), 1)
		record = self.outbox(queued["name"])
		self.assertEqual(record.status, "Posted", record.last_error)
		self.assertEqual(json.loads(record.response)["status"], "Accepted")
		self.assertEqual(
			frappe.get_doc("Quality Inspection", record.erp_document).readings[0].reading_10, "10.11"
		)
		# The same measurements queue once; a later window is a new inspection even when a stable
		# gauge repeats the values; a window with none queues nothing.
		self.assertFalse(
			post_inspection_from_measurements(
				"Job Card", job_card, machine.name, t(0), t(30), specifications=[self.LENGTH]
			)["created"]
		)
		self.assertTrue(
			post_inspection_from_measurements(
				"Job Card", job_card, machine.name, t(2), t(30), specifications=[self.LENGTH]
			)["created"]
		)
		self.assertIsNone(
			post_inspection_from_measurements("Job Card", job_card, machine.name, t(40), t(50))["name"]
		)
