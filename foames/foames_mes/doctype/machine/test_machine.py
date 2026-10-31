# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The machine's current job on any Frappe site: its reference type, its start time, the API and
the hook other apps (and the ERPNext adapter) use to close the books on a job that ended."""

from unittest.mock import patch

import frappe
from frappe.utils import get_datetime

from foames.foames_mes.api import set_current_job
from foames.foames_mes.doctype.oee_period.test_oee_period import make_machine
from foames.foames_mes.floor import floor_snapshot
from foames.tests_compat import IntegrationTestCase

CHANGES = []


def remember(machine, previous, at):
	CHANGES.append((machine.name, previous, machine.current_job_reference, at))


def reference(reference_type: str, external_id: str) -> str:
	name = frappe.db.exists(
		"External Reference",
		{"erp_system": "ERPNext", "reference_type": reference_type, "external_id": external_id},
	)
	if name:
		return name
	return (
		frappe.get_doc(
			{
				"doctype": "External Reference",
				"erp_system": "ERPNext",
				"reference_type": reference_type,
				"external_id": external_id,
			}
		)
		.insert(ignore_permissions=True)
		.name
	)


class TestMachineCurrentJob(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.machine = make_machine("T-JOB")
		CHANGES.clear()

	def test_current_job_must_be_a_job_card_reference(self):
		self.machine.current_job_reference = reference("Work Order", "MFG-WO-T-1")
		with self.assertRaisesRegex(frappe.ValidationError, "Job Card"):
			self.machine.save()

	def test_setting_and_clearing_the_job_fires_the_hook(self):
		card = reference("Job Card", "PO-JOB-T-1")
		with patch.object(
			frappe, "get_hooks", side_effect=_hooks({"foames_machine_job_changed": [f"{__name__}.remember"]})
		):
			result = set_current_job("T-JOB", card, at="2026-10-20 08:00:00")
			self.assertEqual(result["current_job_reference"], card)
			self.assertEqual(get_datetime(result["current_job_since"]), get_datetime("2026-10-20 08:00:00"))
			# Setting the same job again changes nothing and fires nothing.
			set_current_job("T-JOB", card)
			set_current_job("T-JOB", None, at="2026-10-20 12:00:00")
		self.assertEqual(
			CHANGES,
			[
				("T-JOB", None, card, get_datetime("2026-10-20 08:00:00")),
				("T-JOB", card, None, get_datetime("2026-10-20 12:00:00")),
			],
		)
		self.assertIsNone(frappe.db.get_value("Machine", "T-JOB", "current_job_since"))

	def test_floor_snapshot_shows_the_job(self):
		card = reference("Job Card", "PO-JOB-T-2")
		set_current_job("T-JOB", card)
		tile = next(m for m in floor_snapshot()["machines"] if m["name"] == "T-JOB")
		self.assertEqual(tile["current_job"]["external_id"], "PO-JOB-T-2")
		self.assertEqual(tile["current_job"]["reference"], card)
		self.assertTrue(tile["current_job"]["since"])
		set_current_job("T-JOB", None)
		tile = next(m for m in floor_snapshot()["machines"] if m["name"] == "T-JOB")
		self.assertIsNone(tile["current_job"])


def _hooks(overrides: dict):
	original = frappe.get_hooks

	def get_hooks(hook=None, *args, **kwargs):
		if hook in overrides:
			return overrides[hook]
		return original(hook, *args, **kwargs)

	return get_hooks
