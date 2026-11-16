# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Lineside bins, material queues, MPC profiles and the material check, on a Frappe site."""

import frappe
from frappe.utils import add_to_date, get_datetime

from foames.foames_adapters.erpnext.stock import read_stock as erpnext_read_stock
from foames.foames_mes.api import (
	get_dispatch_list,
	get_material_readiness,
	get_material_status,
	record_events,
)
from foames.foames_mes.floor import floor_snapshot
from foames.foames_mes.material_flow import check_material_flow, refresh_bin, refresh_queue
from foames.foames_mes.report.line_dry_forecast.line_dry_forecast import execute as dry_forecast
from foames.foames_mes.report.material_queue_status.material_queue_status import execute as queue_status
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import extra_hooks, make_machine

DAY = "2026-10-21"
STOCK = {"T-RESIN": 80.0}


def at(time):
	return get_datetime(f"{DAY} {time}")


def fake_stock(item, location=None):
	if item in STOCK:
		return {"actual_qty": STOCK[item]}
	return None


def make_profile(**factors):
	return frappe.get_doc(
		{"doctype": "Material Handling Profile", "title": "Test material", **factors}
	).insert()


def make_bin(**overrides):
	values = {
		"doctype": "Lineside Bin",
		"title": "Resin at T-MAT",
		"machine": "T-MAT",
		"item": "T-RESIN",
		"uom": "kg",
		"stock_source": "Manual",
		"read_qty": 500,
		"quantity_per_unit": 1,
		"replenishment_lead_minutes": 120,
		"reorder_qty": 100,
		"max_qty": 600,
		"replenishment_method": "Min-Max",
	}
	values.update(overrides)
	return frappe.get_doc(values).insert()


def make_queue(**overrides):
	values = {"doctype": "Material Queue", "title": "T-MAT queue", "machine": "T-MAT", "discipline": "FIFO"}
	values.update(overrides)
	return frappe.get_doc(values).insert()


def make_entry(queue, **overrides):
	values = {"doctype": "Material Queue Entry", "queue": queue, "item": "T-PANEL", "quantity": 1}
	values.update(overrides)
	return frappe.get_doc(values).insert()


class TestMaterialHandlingProfile(IntegrationTestCase):
	def test_level_and_drivers(self):
		profile = make_profile(storage_temperature="Frozen", conditioning_minutes=90)
		self.assertEqual(profile.mpc_level, 4)
		self.assertEqual(profile.expert_oversight, "single")
		self.assertIn("Storage temperature", profile.mpc_drivers)
		self.assertTrue(profile.mpc_label.startswith("MPC 4"))

	def test_blank_profile_is_mpc_1(self):
		self.assertEqual(make_profile().mpc_level, 1)

	def test_level_follows_the_profile_onto_bins(self):
		make_machine("T-MAT")
		profile = make_profile(esd_sensitivity="ESD sensitive")
		bin_ = make_bin(material_profile=profile.name)
		self.assertEqual(bin_.mpc_level, 3)
		profile.exposure_band = "OEB 5"
		profile.save()
		self.assertEqual(frappe.db.get_value("Lineside Bin", bin_.name, "mpc_level"), 5)


class TestLinesideBin(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_machine("T-MAT")
		record_events(
			[
				{"machine": "T-MAT", "type": "Count", "value": 100, "timestamp": f"{DAY}T08:00:00"},
				{"machine": "T-MAT", "type": "Count", "value": 400, "timestamp": f"{DAY}T09:00:00"},
				{"machine": "T-MAT", "type": "Count", "value": 450, "timestamp": f"{DAY}T10:00:00"},
			]
		)

	def test_manual_bin_estimates_consumption_from_counts(self):
		bin_ = make_bin()
		frappe.db.set_value("Lineside Bin", bin_.name, "last_read_at", at("08:30:00"))
		row = refresh_bin(bin_.name, at("10:00:01"))
		a = row["assessment"]
		self.assertAlmostEqual(a["on_hand"], 150.0)  # 500 less 300 + 50 counted since the read
		self.assertAlmostEqual(a["per_hour"], 175.0)  # 350 over the 2 hour window
		self.assertEqual(a["status"], "Will Run Dry")  # under an hour left, 2 hour lead
		stored = frappe.db.get_value("Lineside Bin", bin_.name, ["status", "on_hand", "dry_at"], as_dict=True)
		self.assertEqual(stored.status, "Will Run Dry")
		self.assertAlmostEqual(stored.on_hand, 150.0)
		self.assertIsNotNone(stored.dry_at)

	def test_manual_count_resets_the_estimate(self):
		bin_ = make_bin()
		frappe.db.set_value(
			"Lineside Bin", bin_.name, {"last_read_at": at("08:30:00"), "consumed_since_read": 40}
		)
		bin_.reload()
		bin_.read_qty = 420
		bin_.save()
		self.assertEqual(bin_.consumed_since_read, 0)
		self.assertGreater(get_datetime(bin_.last_read_at), at("10:00:00"))

	def test_erp_bin_reads_stock_and_notices_a_replenishment(self):
		bin_ = make_bin(stock_source="ERP", location="Lineside - T", read_qty=0)
		with extra_hooks(foames_stock_readers=["foames.foames_mes.test_material_flow.fake_stock"]):
			row = refresh_bin(bin_.name, at("10:00:01"))
		self.assertAlmostEqual(row["assessment"]["on_hand"], 80.0)
		stored = frappe.db.get_value(
			"Lineside Bin", bin_.name, ["read_qty", "last_read_at", "last_replenished_at"], as_dict=True
		)
		self.assertAlmostEqual(stored.read_qty, 80.0)
		self.assertEqual(get_datetime(stored.last_replenished_at), at("10:00:01"))

	def test_unknown_item_is_not_read_from_erpnext(self):
		self.assertIsNone(erpnext_read_stock("T-NO-SUCH-ITEM"))

	def test_check_raises_one_suggestion_per_episode(self):
		bin_ = make_bin()
		frappe.db.set_value("Lineside Bin", bin_.name, "last_read_at", at("08:30:00"))
		first = check_material_flow(at("10:00:01"))
		mine = frappe.get_all(
			"Agent Suggestion",
			filters={"reference_doctype": "Lineside Bin", "reference_name": bin_.name},
			pluck="name",
		)
		self.assertEqual(len(mine), 1)
		self.assertIn(mine[0], first)
		suggestion = frappe.get_doc("Agent Suggestion", mine[0])
		self.assertEqual(suggestion.category, "Material")
		self.assertEqual(suggestion.severity, "Critical")
		self.assertEqual(suggestion.agent, "foames-material")
		self.assertNotIn(mine[0], check_material_flow(at("10:05:00")))

	def test_kanban_bin_recommends_cards(self):
		bin_ = make_bin(
			replenishment_method="Kanban", container_qty=50, kanban_cards=2, warn_margin_percent=0
		)
		frappe.db.set_value("Lineside Bin", bin_.name, "last_read_at", at("08:30:00"))
		refresh_bin(bin_.name, at("10:00:01"))
		# 175 an hour over a 2 hour loop in containers of 50: 7 cards.
		self.assertEqual(frappe.db.get_value("Lineside Bin", bin_.name, "recommended_kanban_cards"), 7)

	def test_invalid_bins_are_refused(self):
		with self.assertRaises(frappe.ValidationError):
			make_bin(max_qty=50, reorder_qty=100)
		with self.assertRaises(frappe.ValidationError):
			make_bin(replenishment_method="Kanban", container_qty=0)

	def test_snapshot_status_and_report(self):
		bin_ = make_bin()
		frappe.db.set_value("Lineside Bin", bin_.name, "last_read_at", at("08:30:00"))
		refresh_bin(bin_.name, at("10:00:01"))
		snapshot = floor_snapshot()
		self.assertIn(bin_.name, [b.name for b in snapshot["material"]["bins"]])
		machine = next(m for m in snapshot["machines"] if m.name == "T-MAT")
		self.assertEqual(machine["material"]["bins_at_risk"], 1)
		status = get_material_status("T-MAT")
		self.assertEqual(status["summary"]["bins"], 1)
		readiness = get_material_readiness("T-MAT", hours=4)
		self.assertFalse(readiness["ok"])
		columns, rows, *_ = dry_forecast({"machine": "T-MAT"})
		self.assertEqual(rows[0]["status"], "Will Run Dry")
		self.assertTrue(any(c["fieldname"] == "hours_to_dry" for c in columns))


class TestMaterialQueue(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_machine("T-MAT")

	def test_readiness_is_stored(self):
		queue = make_queue()
		now = get_datetime()
		entry = make_entry(queue.name, arrived_at=add_to_date(now, minutes=-5), min_wait_minutes=30)
		self.assertEqual(entry.readiness, "Conditioning")
		self.assertIsNotNone(entry.ready_at)

	def test_dispatch_list_follows_the_rule(self):
		queue = make_queue(discipline="Earliest Expiry")
		now = get_datetime()
		late = make_entry(queue.name, arrived_at=add_to_date(now, minutes=-60))
		soon = make_entry(
			queue.name, arrived_at=add_to_date(now, minutes=-10), expires_at=add_to_date(now, hours=1)
		)
		make_entry(queue.name, arrived_at=add_to_date(now, minutes=-2), min_wait_minutes=30)
		self.assertEqual([e["name"] for e in get_dispatch_list(queue.name)], [soon.name, late.name])

	def test_material_past_its_limit_needs_a_reason_to_start(self):
		queue = make_queue()
		now = get_datetime()
		entry = make_entry(queue.name, arrived_at=add_to_date(now, minutes=-130), max_wait_minutes=120)
		self.assertEqual(entry.readiness, "Q-time Exceeded")
		entry.status = "In Process"
		with self.assertRaises(frappe.ValidationError):
			entry.save()
		entry.reload()
		entry.status = "In Process"
		entry.override_reason = "Requalified by retest"
		entry.save()
		self.assertIsNotNone(entry.started_at)
		self.assertIsNotNone(frappe.db.get_value("Material Queue", queue.name, "last_activity"))

	def test_conditioning_material_cannot_start(self):
		queue = make_queue()
		entry = make_entry(queue.name, min_wait_minutes=60)
		entry.status = "In Process"
		with self.assertRaises(frappe.ValidationError):
			entry.save()

	def test_mpc_5_needs_an_expert_review(self):
		queue = make_queue()
		profile = make_profile(hazard_rating="4 - Severe")
		entry = make_entry(queue.name, material_profile=profile.name)
		self.assertEqual(entry.mpc_level, 5)
		entry.status = "In Process"
		with self.assertRaises(frappe.ValidationError):
			entry.save()
		entry.reload()
		entry.status = "In Process"
		entry.expert_review = "Process safety team, shift A"
		entry.save()

	def test_hold_needs_a_reason(self):
		entry = make_entry(make_queue().name)
		entry.status = "On Hold"
		with self.assertRaises(frappe.ValidationError):
			entry.save()

	def test_check_flags_qtime_and_a_full_buffer(self):
		queue = make_queue(capacity=1)
		now = get_datetime()
		entry = make_entry(queue.name, arrived_at=add_to_date(now, minutes=-130), max_wait_minutes=120)
		check_material_flow(now)
		keys = frappe.get_all("Agent Suggestion", filters={"category": "Material"}, pluck="rule_key")
		self.assertIn(f"material-queue:{entry.name}:Q-time Exceeded", keys)
		self.assertIn(f"material-blocked:{queue.name}:{entry.name}", keys)
		row = refresh_queue(queue.name, now)
		self.assertEqual(len(row["entries"]), 1)
		self.assertEqual(frappe.db.get_value("Material Queue", queue.name, "waiting_count"), 1)
		_columns, rows, *_ = queue_status({"queue": queue.name})
		self.assertEqual(rows[0]["readiness"], "Q-time Exceeded")
		self.assertIsNone(rows[0]["position"])
