# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Tests for the confirmation and goods-movement payload builders, the value formatting they rely
on, and the cancellation and reversal actions. No Frappe site and no S/4HANA system are needed."""

import unittest
from datetime import date, datetime, time
from decimal import Decimal

from foames.foames_adapters.s4hana import actions, confirmations, goods_movements, outbox, values
from foames.foames_adapters.s4hana.fake import FakeS4HANA, csrf, ok, sap_error
from foames.foames_adapters.s4hana.odata import Connection, ODataClient, Response


def client(fake):
	return ODataClient(
		Connection(base_url="https://s4.example.com", client="100", username="U", password="P"),
		transport=fake,
	)


class TestValues(unittest.TestCase):
	def test_decimal_strings_have_no_exponent_or_trailing_zeros(self):
		self.assertEqual(values.decimal_string(12.5), "12.5")
		self.assertEqual(values.decimal_string(100.0), "100")
		self.assertEqual(values.decimal_string("0.0010"), "0.001")
		self.assertEqual(values.decimal_string(Decimal("1E+3")), "1000")
		self.assertEqual(values.decimal_string(0), "0")
		self.assertEqual(values.decimal_string("-2.50"), "-2.5")
		for bad in (None, "", "ten", "nan"):
			with self.assertRaises(ValueError):
				values.decimal_string(bad)

	def test_dates_and_times(self):
		self.assertEqual(values.date_string(date(2026, 10, 31)), "2026-10-31T00:00:00")
		self.assertEqual(values.date_string("2026-10-31 08:30:00"), "2026-10-31T00:00:00")
		self.assertEqual(
			values.datetime_string(datetime(2026, 10, 31, 8, 30, 15, 999)), "2026-10-31T08:30:15"
		)
		self.assertEqual(values.datetime_string("2026-10-31 08:30"), "2026-10-31T08:30:00")
		self.assertEqual(values.time_string(time(8, 30)), "PT08H30M00S")
		self.assertEqual(values.time_string("16:05:09"), "PT16H05M09S")
		self.assertEqual(values.time_string("PT01H00M00S"), "PT01H00M00S")
		with self.assertRaises(ValueError):
			values.time_string("25:00")
		with self.assertRaises(ValueError):
			values.date_string("")

	def test_parsing_sap_answers(self):
		self.assertEqual(values.parse_date("/Date(1793404800000)/"), date(2026, 10, 31))
		self.assertEqual(values.parse_date("/Date(1793404800000+0000)/"), date(2026, 10, 31))
		self.assertEqual(values.parse_date("2026-10-31T00:00:00"), date(2026, 10, 31))
		self.assertIsNone(values.parse_date(None))
		self.assertEqual(values.parse_datetime("/Date(1793435400000)/"), datetime(2026, 10, 31, 8, 30))
		self.assertEqual(values.parse_time("PT08H30M00S"), time(8, 30))
		self.assertEqual(values.parse_time("PT8H"), time(8, 0))
		self.assertEqual(values.parse_decimal("12.500"), Decimal("12.500"))
		self.assertEqual(values.parse_decimal(""), Decimal(0))
		self.assertEqual(values.parse_decimal("x"), Decimal(0))

	def test_clean_drops_none_only(self):
		self.assertEqual(
			values.clean({"a": None, "b": "", "c": 0, "d": False}), {"b": "", "c": 0, "d": False}
		)


class TestConfirmation(unittest.TestCase):
	def test_minimal_yield_confirmation(self):
		payload = confirmations.confirmation("1000123", "0010", 100, "KG")
		self.assertEqual(
			payload,
			{
				"OrderID": "1000123",
				"Sequence": "0",
				"OrderOperation": "0010",
				"ConfirmationYieldQuantity": "100",
				"ConfirmationUnit": "KG",
			},
		)

	def test_full_confirmation(self):
		payload = confirmations.confirmation(
			"1000123",
			"0020",
			yield_quantity="95.5",
			unit="KG",
			scrap_quantity=4.5,
			plant="1010",
			work_center="MIX01",
			posting_date=date(2026, 10, 31),
			final=True,
			personnel="00001234",
			variance_reason="0001",
			activities=[
				confirmations.Activity(1, 15, "MIN"),
				confirmations.Activity(2, "1.5", "H", no_further_expected=True),
			],
			times=confirmations.ExecutionTimes(start=datetime(2026, 10, 31, 6, 0), end="2026-10-31 07:45:30"),
			goods_movements=[
				confirmations.GoodsMovementItem(
					"RM-1", "1010", 50, "KG", "261", storage_location="0001", batch="B1"
				),
				confirmations.GoodsMovementItem(
					"FG-1", "1010", 95.5, "KG", "101", storage_location="0002", batch="L7"
				),
			],
			extra={"ConfirmationText": "must not survive", "OrderSuboperation": None},
		)
		self.assertEqual(payload["ConfirmationScrapQuantity"], "4.5")
		self.assertEqual(payload["PostingDate"], "2026-10-31T00:00:00")
		self.assertIs(payload["IsFinalConfirmation"], True)
		self.assertEqual(payload["OpConfirmedWorkQuantity1"], "15")
		self.assertEqual(payload["OpWorkQuantityUnit1"], "MIN")
		self.assertEqual(payload["OpConfirmedWorkQuantity2"], "1.5")
		self.assertIs(payload["NoFurtherOpWorkQuantity2IsExpd"], True)
		self.assertEqual(payload["ConfirmedExecutionStartDate"], "2026-10-31T00:00:00")
		self.assertEqual(payload["ConfirmedExecutionStartTime"], "PT06H00M00S")
		self.assertEqual(payload["ConfirmedExecutionEndTime"], "PT07H45M30S")
		self.assertNotIn("ConfirmedSetupEndDate", payload)
		self.assertEqual(payload["VarianceReasonCode"], "0001")
		self.assertEqual(payload["Personnel"], "00001234")
		items = payload["to_ProdnOrdConfMatlDocItm"]
		self.assertEqual(len(items), 2)
		self.assertEqual(
			items[0],
			{
				"Material": "RM-1",
				"Plant": "1010",
				"StorageLocation": "0001",
				"Batch": "B1",
				"GoodsMovementType": "261",
				"QuantityInEntryUnit": "50",
				"EntryUnit": "KG",
			},
		)
		# The outbox owns the confirmation text.
		self.assertNotIn("ConfirmationText", payload)
		self.assertNotIn("OrderSuboperation", payload)

	def test_outbox_writes_the_marker_into_the_confirmation_text(self):
		payload = confirmations.confirmation("1000123", "0010", 1, "PC", final=True)
		sent = outbox.prepare(outbox.OPERATIONS[confirmations.PRODUCTION], payload, "run-1:0010")
		self.assertEqual(sent["ConfirmationText"], outbox.marker("run-1:0010"))
		self.assertEqual(sent["OrderID"], "1000123")

	def test_final_only_confirmation_is_allowed(self):
		payload = confirmations.confirmation("1", "0010", final=True)
		self.assertEqual(
			payload, {"OrderID": "1", "Sequence": "0", "OrderOperation": "0010", "IsFinalConfirmation": True}
		)

	def test_validation(self):
		with self.assertRaises(ValueError):
			confirmations.confirmation("", "0010", 1, "PC")
		with self.assertRaises(ValueError):
			confirmations.confirmation("1", "0010", 1)  # no unit
		with self.assertRaises(ValueError):
			confirmations.confirmation("1", "0010")  # nothing to confirm
		with self.assertRaises(ValueError):
			confirmations.confirmation("1", "0010", 1, "PC", final_confirmation_type="Q")
		with self.assertRaises(ValueError):
			confirmations.confirmation("1", "0010", 1, "PC", activities=[confirmations.Activity(7, 1, "MIN")])
		with self.assertRaises(ValueError):
			confirmations.confirmation(
				"1",
				"0010",
				1,
				"PC",
				activities=[confirmations.Activity(1, 1, "MIN"), confirmations.Activity(1, 2, "MIN")],
			)
		with self.assertRaises(ValueError):
			confirmations.GoodsMovementItem("", "1010", 1, "KG", "261").fields()

	def test_summarize(self):
		entity = {
			"ConfirmationGroup": "77",
			"ConfirmationCount": "2",
			"OrderID": "1000123",
			"OrderOperation": "0010",
			"ConfirmationYieldQuantity": "10.000",
			"ConfirmationScrapQuantity": "0.000",
			"ConfirmationUnit": "KG",
			"PostingDate": "/Date(1793404800000)/",
			"IsFinalConfirmation": True,
			"IsReversed": False,
			"OpConfirmedWorkQuantity1": "0.000",
			"OpConfirmedWorkQuantity2": "1.500",
			"OpWorkQuantityUnit2": "H",
		}
		summary = confirmations.summarize(entity)
		self.assertEqual(summary["confirmation"], "77|2")
		self.assertEqual(summary["yield"], Decimal("10.000"))
		self.assertEqual(summary["posting_date"], date(2026, 10, 31))
		self.assertTrue(summary["final"])
		self.assertEqual(summary["activities"], [{"position": 2, "quantity": Decimal("1.500"), "unit": "H"}])


class TestGoodsMovements(unittest.TestCase):
	def test_goods_receipt_for_order(self):
		payload = goods_movements.goods_receipt_for_order(
			"1000123",
			"FG-1",
			"1010",
			95.5,
			"KG",
			storage_location="0002",
			batch="L7",
			posting_date="2026-10-31",
			is_completely_delivered=True,
		)
		self.assertEqual(payload["GoodsMovementCode"], "02")
		self.assertEqual(payload["PostingDate"], "2026-10-31T00:00:00")
		self.assertEqual(payload["DocumentDate"], "2026-10-31T00:00:00")
		item = payload["to_MaterialDocumentItem"][0]
		self.assertEqual(item["GoodsMovementType"], "101")
		self.assertEqual(item["ManufacturingOrder"], "1000123")
		self.assertEqual(item["QuantityInEntryUnit"], "95.5")
		self.assertEqual(item["EntryUnit"], "KG")
		self.assertEqual(item["Batch"], "L7")
		self.assertIs(item["IsCompletelyDelivered"], True)
		self.assertNotIn("MaterialDocumentHeaderText", payload)

	def test_goods_receipt_reversal_uses_102(self):
		payload = goods_movements.goods_receipt_for_order("1000123", "FG-1", "1010", 1, "KG", reversal=True)
		self.assertEqual(payload["GoodsMovementCode"], "02")
		self.assertEqual(payload["to_MaterialDocumentItem"][0]["GoodsMovementType"], "102")

	def test_goods_issue_to_order_from_dicts_and_items(self):
		payload = goods_movements.goods_issue_to_order(
			"1000123",
			[
				{
					"material": "RM-1",
					"plant": "1010",
					"quantity": "50",
					"unit": "KG",
					"batch": "B1",
					"reservation": "0000012345",
					"reservation_item": "0001",
				},
				goods_movements.Item("RM-2", "1010", 2, "L", movement_type=""),
			],
		)
		self.assertEqual(payload["GoodsMovementCode"], "03")
		items = payload["to_MaterialDocumentItem"]
		self.assertEqual([i["GoodsMovementType"] for i in items], ["261", "261"])
		self.assertEqual([i["ManufacturingOrder"] for i in items], ["1000123", "1000123"])
		self.assertEqual(items[0]["Reservation"], "0000012345")
		self.assertEqual(items[0]["ReservationItem"], "0001")
		reversal = goods_movements.goods_issue_to_order(
			"1000123", [{"material": "RM-1", "plant": "1010", "quantity": 1, "unit": "KG"}], reversal=True
		)
		self.assertEqual(reversal["to_MaterialDocumentItem"][0]["GoodsMovementType"], "262")

	def test_transfer_posting_and_scrap(self):
		payload = goods_movements.transfer_posting(
			"FG-1", "1010", 10, "KG", from_storage_location="0002", to_storage_location="0003", batch="L7"
		)
		self.assertEqual(payload["GoodsMovementCode"], "04")
		item = payload["to_MaterialDocumentItem"][0]
		self.assertEqual(item["GoodsMovementType"], "311")
		self.assertEqual(item["StorageLocation"], "0002")
		self.assertEqual(item["IssuingOrReceivingStorageLoc"], "0003")
		qi = goods_movements.transfer_posting(
			"FG-1", "1010", 10, "KG", movement_type="321", from_storage_location="0002", from_stock_type="2"
		)
		self.assertEqual(qi["to_MaterialDocumentItem"][0]["InventoryStockType"], "2")
		with self.assertRaises(ValueError):
			goods_movements.transfer_posting("FG-1", "1010", 10, "KG")
		scrap = goods_movements.scrap(
			"FG-1", "1010", 1, "KG", storage_location="0002", cost_center="CC100", reason_code="0002"
		)
		self.assertEqual(scrap["GoodsMovementCode"], "03")
		self.assertEqual(scrap["to_MaterialDocumentItem"][0]["GoodsMovementType"], "551")
		self.assertEqual(scrap["to_MaterialDocumentItem"][0]["CostCenter"], "CC100")

	def test_code_must_be_shared_or_given(self):
		items = [
			goods_movements.Item("A", "1010", 1, "KG", "101", order="1"),
			goods_movements.Item("B", "1010", 1, "KG", "261", order="1"),
		]
		with self.assertRaises(ValueError):
			goods_movements.material_document(items)
		with self.assertRaises(ValueError):
			goods_movements.material_document([goods_movements.Item("A", "1010", 1, "KG", "999")])
		self.assertEqual(
			goods_movements.material_document([goods_movements.Item("A", "1010", 1, "KG", "999")], code="05")[
				"GoodsMovementCode"
			],
			"05",
		)
		with self.assertRaises(ValueError):
			goods_movements.material_document([])
		with self.assertRaises(ValueError):
			goods_movements.material_document(items, code="07")

	def test_outbox_writes_the_marker_into_the_header_text(self):
		payload = goods_movements.goods_receipt_for_order("1000123", "FG-1", "1010", 1, "KG")
		sent = outbox.prepare(outbox.OPERATIONS["Goods Movement"], payload, "run-1:receipt")
		self.assertEqual(sent["MaterialDocumentHeaderText"], outbox.marker("run-1:receipt"))
		self.assertLessEqual(len(sent["MaterialDocumentHeaderText"]), 25)

	def test_posting_a_material_document_end_to_end(self):
		fake = (
			FakeS4HANA()
			.on("FETCH", "API_MATERIAL_DOCUMENT_SRV", csrf())
			.on(
				"POST",
				"A_MaterialDocumentHeader",
				ok({"MaterialDocumentYear": "2026", "MaterialDocument": "4900001234"}, 201),
			)
		)
		payload = goods_movements.goods_receipt_for_order("1000123", "FG-1", "1010", 1, "KG")
		operation = outbox.OPERATIONS["Goods Movement"]
		result = outbox.send(
			client(fake), operation, outbox.prepare(operation, payload, "k"), verify_first=False
		)
		self.assertEqual((result.status, result.document), ("Posted", "2026|4900001234"))
		body = fake.requests[-1]["body"]
		self.assertEqual(body["GoodsMovementCode"], "02")
		self.assertEqual(body["MaterialDocumentHeaderText"], outbox.marker("k"))

	def test_summarize_item(self):
		entity = {
			"MaterialDocumentYear": "2026",
			"MaterialDocument": "4900001234",
			"MaterialDocumentItem": "0001",
			"Material": "FG-1",
			"GoodsMovementType": "101",
			"QuantityInEntryUnit": "95.500",
			"EntryUnit": "KG",
			"ManufacturingOrder": "1000123",
			"ReversedMaterialDocumentYear": "2026",
			"ReversedMaterialDocument": "4900001200",
			"to_MaterialDocumentHeader": {"PostingDate": "/Date(1793404800000)/"},
		}
		summary = goods_movements.summarize_item(entity)
		self.assertEqual(summary["document"], "2026|4900001234")
		self.assertEqual(summary["reverses"], "2026|4900001200")
		self.assertEqual(summary["quantity"], Decimal("95.500"))
		self.assertEqual(summary["posting_date"], date(2026, 10, 31))


class TestActions(unittest.TestCase):
	def test_operation_lookup_covers_creates_and_functions(self):
		self.assertIs(outbox.operation("Goods Movement"), outbox.OPERATIONS["Goods Movement"])
		self.assertIs(
			outbox.operation("Material Document Reversal"), actions.ACTIONS["Material Document Reversal"]
		)
		self.assertEqual(len(outbox.operation_names()), len(outbox.OPERATIONS) + len(actions.ACTIONS))
		with self.assertRaises(KeyError):
			outbox.operation("Nope")

	def test_prepare_checks_parameters(self):
		action = actions.ACTIONS["Confirmation Cancellation"]
		prepared = outbox.prepare(
			action, {"ConfirmationGroup": "77", "ConfirmationCount": 1, "PostingDate": "2026-10-31"}, "k"
		)
		self.assertEqual(
			prepared,
			{"ConfirmationGroup": "77", "ConfirmationCount": "1", "PostingDate": "2026-10-31T00:00:00"},
		)
		with self.assertRaises(ValueError):
			outbox.prepare(action, {"ConfirmationGroup": "77"}, "k")
		with self.assertRaises(ValueError):
			outbox.prepare(action, {"ConfirmationGroup": "77", "ConfirmationCount": "1", "OrderID": "1"}, "k")

	def test_cancel_confirmation_posts_the_function_import(self):
		fake = (
			FakeS4HANA()
			.on("FETCH", "API_PROD_ORDER_CONFIRMATION_2_SRV", csrf("T9"))
			.on(
				"POST",
				"CancelProdnOrdConf",
				ok({"CancelProdnOrdConf": {"ConfirmationGroup": "77", "ConfirmationCount": "2"}}),
			)
		)
		operation, payload = actions.cancel_confirmation("77", "1", posting_date=date(2026, 10, 31))
		self.assertEqual(operation, "Confirmation Cancellation")
		action = outbox.operation(operation)
		result = outbox.send(client(fake), action, outbox.prepare(action, payload, "k"), verify_first=False)
		self.assertEqual((result.status, result.document), ("Posted", "77|2"))
		request = fake.requests[-1]
		self.assertEqual(request["method"], "POST")
		self.assertTrue(request["path"].endswith("/API_PROD_ORDER_CONFIRMATION_2_SRV/CancelProdnOrdConf"))
		self.assertEqual(request["query"]["ConfirmationGroup"], "'77'")
		self.assertEqual(request["query"]["ConfirmationCount"], "'1'")
		self.assertEqual(request["query"]["PostingDate"], "datetime'2026-10-31T00:00'")
		self.assertEqual(request["query"]["sap-client"], "100")
		self.assertEqual(request["headers"]["X-CSRF-Token"], "T9")

	def test_cancel_confirmation_is_not_repeated_once_reversed(self):
		fake = FakeS4HANA().on(
			"GET",
			"ProdnOrdConf2(",
			ok({"ConfirmationGroup": "77", "ConfirmationCount": "1", "IsReversed": True}),
		)
		action = outbox.operation("Confirmation Cancellation")
		result = outbox.send(
			client(fake), action, {"ConfirmationGroup": "77", "ConfirmationCount": "1"}, verify_first=True
		)
		self.assertEqual((result.status, result.document), ("Posted", "77|1"))
		self.assertEqual([r["method"] for r in fake.requests], ["GET"])

	def test_cancel_confirmation_proceeds_when_not_yet_reversed(self):
		fake = (
			FakeS4HANA()
			.on(
				"GET",
				"ProdnOrdConf2(",
				ok({"ConfirmationGroup": "77", "ConfirmationCount": "1", "IsReversed": False}),
			)
			.on("FETCH", "API_PROD_ORDER_CONFIRMATION_2_SRV", csrf())
			.on("POST", "CancelProdnOrdConf", ok({"ConfirmationGroup": "77", "ConfirmationCount": "2"}))
		)
		action = outbox.operation("Confirmation Cancellation")
		result = outbox.send(
			client(fake), action, {"ConfirmationGroup": "77", "ConfirmationCount": "1"}, verify_first=True
		)
		self.assertEqual((result.status, result.document), ("Posted", "77|2"))

	def test_reversal_finds_an_existing_reversal_document(self):
		fake = FakeS4HANA().on(
			"GET",
			"A_MaterialDocumentItem",
			ok({"results": [{"MaterialDocumentYear": "2026", "MaterialDocument": "4900001300"}]}),
		)
		operation, payload = actions.reverse_material_document("2026", "4900001234")
		action = outbox.operation(operation)
		result = outbox.send(client(fake), action, outbox.prepare(action, payload, "k"), verify_first=True)
		self.assertEqual((result.status, result.document), ("Posted", "2026|4900001300"))
		self.assertEqual(
			fake.requests[0]["query"]["$filter"],
			"ReversedMaterialDocumentYear eq '2026' and ReversedMaterialDocument eq '4900001234'",
		)

	def test_reversal_posts_cancel(self):
		fake = (
			FakeS4HANA()
			.on("FETCH", "API_MATERIAL_DOCUMENT_SRV", csrf())
			.on("POST", "/Cancel", ok({"MaterialDocumentYear": "2026", "MaterialDocument": "4900001300"}))
		)
		action = outbox.operation("Material Document Reversal")
		result = outbox.send(
			client(fake),
			action,
			{"MaterialDocumentYear": "2026", "MaterialDocument": "4900001234"},
			verify_first=False,
		)
		self.assertEqual((result.status, result.document), ("Posted", "2026|4900001300"))
		self.assertEqual(fake.requests[-1]["query"]["MaterialDocument"], "'4900001234'")

	def test_function_import_outcomes(self):
		action = outbox.operation("Material Document Reversal")
		params = {"MaterialDocumentYear": "2026", "MaterialDocument": "1"}
		rejected = (
			FakeS4HANA()
			.on("FETCH", "API_MATERIAL_DOCUMENT_SRV", csrf())
			.on("POST", "/Cancel", sap_error(400, "M7/021", "Deficit of stock"))
		)
		self.assertEqual(outbox.send(client(rejected), action, params, False).status, "Failed")
		throttled = (
			FakeS4HANA()
			.on("FETCH", "API_MATERIAL_DOCUMENT_SRV", csrf())
			.on("POST", "/Cancel", Response(429, {}, b""))
		)
		self.assertEqual(outbox.send(client(throttled), action, params, False).status, "Retry")
		dropped = (
			FakeS4HANA()
			.on("FETCH", "API_MATERIAL_DOCUMENT_SRV", csrf())
			.on("POST", "/Cancel", TimeoutError("t"))
		)
		self.assertEqual(outbox.send(client(dropped), action, params, False).status, "Unknown")

	def test_function_import_refreshes_an_expired_csrf_token(self):
		fake = (
			FakeS4HANA()
			.on("FETCH", "API_MATERIAL_DOCUMENT_SRV", csrf("OLD"), once=True)
			.on("FETCH", "API_MATERIAL_DOCUMENT_SRV", csrf("NEW"))
			.on("POST", "/Cancel", Response(403, {"x-csrf-token": "Required"}, b""), once=True)
			.on("POST", "/Cancel", ok({"MaterialDocumentYear": "2026", "MaterialDocument": "2"}))
		)
		action = outbox.operation("Material Document Reversal")
		result = outbox.send(
			client(fake), action, {"MaterialDocumentYear": "2026", "MaterialDocument": "1"}, False
		)
		self.assertEqual(result.status, "Posted")
		posts = [r for r in fake.requests if r["method"] == "POST"]
		self.assertEqual([p["headers"]["X-CSRF-Token"] for p in posts], ["OLD", "NEW"])
