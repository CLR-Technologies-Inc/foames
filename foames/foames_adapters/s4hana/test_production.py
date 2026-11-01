# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The roll-up arithmetic for S/4HANA: which confirmation a window of machine data becomes. No
S/4HANA system needed."""

import unittest
from datetime import datetime

from foames.foames_adapters.s4hana import outbox
from foames.foames_adapters.s4hana.production import (
	RollUpOptions,
	activity_quantity,
	confirmation_payload,
	parse_job,
	window_end,
	window_key,
)

T = datetime(2026, 10, 31, 8, 0, 0)


def at(minutes: int) -> datetime:
	return T.replace(hour=8 + minutes // 60, minute=minutes % 60)


class TestParseJob(unittest.TestCase):
	def test_order_and_operation(self):
		self.assertEqual(parse_job("1000123|0010"), ("1000123", "0010"))
		self.assertEqual(parse_job(" 1000123 | 0010 "), ("1000123", "0010"))

	def test_anything_else_is_refused(self):
		for value in ("1000123", "1000123|", "|0010", "1000123|0|0010", "", None):
			with self.assertRaises(ValueError, msg=value):
				parse_job(value)


class TestConfirmationPayload(unittest.TestCase):
	def payload(self, totals, intervals, **options):
		return confirmation_payload(
			"1000123", "0010", at(0), at(30), totals, intervals, RollUpOptions(**{"unit": "PC", **options})
		)

	def test_nothing_to_report_queues_nothing(self):
		self.assertIsNone(self.payload({}, []))
		self.assertIsNone(self.payload({"good": 0, "temperature": 80}, []))
		# Run time alone is reported only as an activity, and no activity position is set.
		self.assertIsNone(self.payload({}, [(at(0), at(30))]))

	def test_counts_become_yield_and_scrap(self):
		payload = self.payload({"good": 12, "scrap": 1, "reject": 1}, [(at(5), at(25))])
		self.assertEqual(payload["OrderID"], "1000123")
		self.assertEqual(payload["OrderOperation"], "0010")
		self.assertEqual(payload["ConfirmationYieldQuantity"], "12")
		self.assertEqual(payload["ConfirmationScrapQuantity"], "2")
		self.assertEqual(payload["ConfirmationUnit"], "PC")
		self.assertEqual(payload["PostingDate"], "2026-10-31T00:00:00")
		self.assertEqual(
			(payload["ConfirmedExecutionStartTime"], payload["ConfirmedExecutionEndTime"]),
			("PT08H00M00S", "PT08H30M00S"),
		)
		# A roll-up never finishes the operation, never sends activities unless asked, and leaves
		# goods movements to the order's settings.
		self.assertNotIn("IsFinalConfirmation", payload)
		self.assertNotIn("OpConfirmedWorkQuantity2", payload)
		self.assertNotIn("APIConfHasNoGoodsMovements", payload)
		self.assertNotIn("ConfirmationText", payload)
		# What the window builds is a valid posting.
		prepared = outbox.prepare(outbox.operation("Production Order Confirmation"), payload, "k1")
		self.assertTrue(prepared["ConfirmationText"].startswith("FOAMES-"))

	def test_scrap_alone_is_confirmed(self):
		payload = self.payload({"scrap": 3}, [])
		self.assertEqual(payload["ConfirmationScrapQuantity"], "3")
		self.assertNotIn("ConfirmationYieldQuantity", payload)

	def test_machine_time_as_activity(self):
		payload = self.payload({"good": 5}, [(at(5), at(25))], activity_position=2)
		self.assertEqual((payload["OpConfirmedWorkQuantity2"], payload["OpWorkQuantityUnit2"]), ("20", "MIN"))
		hours = self.payload({}, [(at(0), at(30))], activity_position=2, activity_unit="H")
		self.assertEqual((hours["OpConfirmedWorkQuantity2"], hours["OpWorkQuantityUnit2"]), ("0.5", "H"))
		# Run time without counts is still confirmed when it goes into an activity, with no unit.
		self.assertNotIn("ConfirmationUnit", hours)

	def test_options(self):
		payload = self.payload({"good": 1}, [], no_goods_movements=True)
		self.assertIs(payload["APIConfHasNoGoodsMovements"], True)
		self.assertEqual(RollUpOptions("PC").operation, "Production Order Confirmation")
		self.assertEqual(RollUpOptions("PC", process_order=True).operation, "Process Order Confirmation")

	def test_counts_need_a_unit(self):
		with self.assertRaisesRegex(ValueError, "unit"):
			self.payload({"good": 1}, [], unit="")

	def test_activity_units(self):
		self.assertEqual(activity_quantity(90, "H"), 1.5)
		self.assertEqual(activity_quantity(90, "min"), 90)
		with self.assertRaises(ValueError):
			activity_quantity(90, "DAY")


class TestWindow(unittest.TestCase):
	def test_window_end_reads_back_the_execution_end(self):
		payload = confirmation_payload("1", "0010", at(0), at(45), {"good": 1}, [], RollUpOptions("PC"))
		self.assertEqual(window_end(payload), at(45))
		self.assertIsNone(window_end({}))

	def test_window_key_names_the_window(self):
		self.assertEqual(
			window_key("1000123", "0010", "M1", at(30)), "1000123|0010:M1:confirm:2026-10-31 08:30:00"
		)


if __name__ == "__main__":
	unittest.main()
