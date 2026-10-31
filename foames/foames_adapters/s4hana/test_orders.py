# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Tests for the order, routing, BOM and work center reads and the new entity defaults. A scripted
fake answers the OData calls."""

import unittest
from datetime import date, datetime
from decimal import Decimal

from foames.foames_adapters.s4hana import orders
from foames.foames_adapters.s4hana.entities import DEFAULT_ENTITIES
from foames.foames_adapters.s4hana.fake import FakeS4HANA, ok
from foames.foames_adapters.s4hana.odata import Connection, ODataClient


def client(fake):
	return ODataClient(
		Connection(base_url="https://s4.example.com", client="100", username="U", password="P"),
		transport=fake,
	)


ORDER = {
	"ManufacturingOrder": "1000123",
	"ManufacturingOrderCategory": "10",
	"ManufacturingOrderType": "PP01",
	"Material": "FG-1",
	"ProductionPlant": "1010",
	"TotalQuantity": "100.000",
	"MfgOrderConfirmedYieldQty": "40.000",
	"ProductionUnit": "KG",
	"MfgOrderPlannedStartDate": "/Date(1793404800000)/",
	"MfgOrderPlannedStartTime": "PT06H00M00S",
	"MfgOrderPlannedEndDate": "/Date(1793491200000)/",
	"OrderIsReleased": True,
	"OrderIsPartiallyConfirmed": True,
	"to_ProductionOrderStatus": {
		"results": [
			{"StatusCode": "I0002", "StatusShortName": "REL", "StatusName": "Released"},
			{"StatusCode": "E0001", "IsUserStatus": True, "StatusShortName": "QHLD"},
		]
	},
	"to_ProductionOrderOperation": {
		"results": [
			{
				"OrderInternalBillOfOperations": "10000456",
				"OrderIntBillOfOperationsItem": "00000001",
				"ManufacturingOrderSequence": "0",
				"ManufacturingOrderOperation": "0010",
				"MfgOrderOperationText": "Mix",
				"WorkCenter": "MIX01",
				"OpPlannedTotalQuantity": "100.000",
				"OpTotalConfirmedYieldQty": "40.000",
				"OperationUnit": "KG",
				"OperationIsPartiallyConfirmed": True,
			},
			{
				"ManufacturingOrderSequence": "0",
				"ManufacturingOrderOperation": "0020",
				"MfgOrderOperationText": "Cure",
				"WorkCenter": "CURE01",
			},
		]
	},
	"to_ProductionOrderComponent": {
		"results": [
			{
				"Reservation": "0000012345",
				"ReservationItem": "0001",
				"Material": "RM-1",
				"Plant": "1010",
				"StorageLocation": "0001",
				"ManufacturingOrderOperation": "0010",
				"RequiredQuantity": "50.000",
				"WithdrawnQuantity": "20.000",
				"BaseUnit": "KG",
				"MatlCompRequirementDate": "/Date(1793404800000)/",
				"MatlCompIsBackflushed": True,
			}
		]
	},
	"to_ProductionOrderItem": {
		"results": [
			{
				"ManufacturingOrderItem": "0001",
				"Material": "FG-1",
				"MfgOrderItemPlannedTotalQty": "100.000",
				"MfgOrderItemGoodsReceiptQty": "40.000",
				"ProductionUnit": "KG",
			}
		]
	},
}


class TestOrders(unittest.TestCase):
	def test_production_order_is_read_with_its_children(self):
		fake = FakeS4HANA().on("GET", "A_ProductionOrder_2('1000123')", ok(ORDER))
		order = orders.production_order(client(fake), "1000123")
		request = fake.requests[0]
		self.assertEqual(request["query"]["$expand"], orders.ORDER_EXPAND)
		self.assertEqual(order["order"], "1000123")
		self.assertEqual(order["material"], "FG-1")
		self.assertEqual(order["plant"], "1010")
		self.assertEqual(order["quantity"], Decimal("100.000"))
		self.assertEqual(order["confirmed_yield"], Decimal("40.000"))
		self.assertEqual(order["planned_start"], datetime(2026, 10, 31, 6, 0))
		self.assertEqual(order["planned_end"], datetime(2026, 11, 1, 0, 0))
		self.assertTrue(order["released"])
		self.assertTrue(order["partially_confirmed"])
		self.assertEqual([s["short"] for s in order["statuses"]], ["REL", "QHLD"])
		self.assertTrue(order["statuses"][1]["user_status"])
		self.assertEqual([o["operation"] for o in order["operations"]], ["0010", "0020"])
		self.assertEqual(order["operations"][0]["work_center"], "MIX01")
		self.assertEqual(order["operations"][0]["confirmed_yield"], Decimal("40.000"))
		self.assertTrue(order["operations"][0]["is_partially_confirmed"])
		self.assertEqual(order["operations"][0]["internal_id"], "10000456|00000001")
		component = order["components"][0]
		self.assertEqual((component["reservation"], component["reservation_item"]), ("0000012345", "0001"))
		self.assertEqual(component["required_quantity"], Decimal("50.000"))
		self.assertEqual(component["requirement_date"], date(2026, 10, 31))
		self.assertTrue(component["is_backflushed"])
		self.assertEqual(order["items"][0]["received_quantity"], Decimal("40.000"))
		self.assertNotIn("to_ProductionOrderOperation", order["raw"])

	def test_missing_order_is_none(self):
		self.assertIsNone(orders.production_order(client(FakeS4HANA()), "9"))

	def test_process_order_uses_its_own_service(self):
		entity = {**ORDER, "ManufacturingOrderCategory": "40"}
		entity = {k.replace("to_ProductionOrder", "to_ProcessOrder"): v for k, v in entity.items()}
		fake = FakeS4HANA().on("GET", "A_ProcessOrder_2('1000123')", ok(entity))
		order = orders.production_order(client(fake), "1000123", process_order=True)
		self.assertIn("/API_PROCESS_ORDER_2_SRV/", fake.requests[0]["path"])
		self.assertEqual(len(order["operations"]), 2)

	def test_orders_for_material(self):
		fake = FakeS4HANA().on("GET", "A_ProductionOrder_2", ok({"results": [ORDER]}))
		result = orders.orders_for_material(client(fake), "FG-1", "1010", released_only=True)
		self.assertEqual(
			fake.requests[0]["query"]["$filter"],
			"Material eq 'FG-1' and ProductionPlant eq '1010' and OrderIsReleased eq true",
		)
		self.assertEqual(result[0]["order"], "1000123")

	def test_order_confirmations(self):
		fake = FakeS4HANA().on(
			"GET",
			"ProdnOrdConf2",
			ok(
				{
					"results": [
						{
							"ConfirmationGroup": "77",
							"ConfirmationCount": "1",
							"OrderID": "1000123",
							"ConfirmationYieldQuantity": "40.000",
							"IsReversed": True,
						}
					]
				}
			),
		)
		result = orders.order_confirmations(client(fake), "1000123")
		self.assertEqual(fake.requests[0]["query"]["$filter"], "OrderID eq '1000123'")
		self.assertEqual(result[0]["confirmation"], "77|1")
		self.assertTrue(result[0]["reversed"])

	def test_order_goods_movements_and_balance(self):
		items = [
			{
				"MaterialDocumentYear": "2026",
				"MaterialDocument": "1",
				"Material": "RM-1",
				"Batch": "B1",
				"GoodsMovementType": "261",
				"QuantityInEntryUnit": "20.000",
				"EntryUnit": "KG",
				"ManufacturingOrder": "1000123",
			},
			{
				"MaterialDocumentYear": "2026",
				"MaterialDocument": "2",
				"Material": "RM-1",
				"Batch": "B1",
				"GoodsMovementType": "262",
				"QuantityInEntryUnit": "5.000",
				"EntryUnit": "KG",
				"ManufacturingOrder": "1000123",
			},
			{
				"MaterialDocumentYear": "2026",
				"MaterialDocument": "3",
				"Material": "FG-1",
				"Batch": "L7",
				"GoodsMovementType": "101",
				"QuantityInEntryUnit": "40.000",
				"EntryUnit": "KG",
				"ManufacturingOrder": "1000123",
			},
			{
				"MaterialDocumentYear": "2026",
				"MaterialDocument": "4",
				"Material": "FG-1",
				"Batch": "L7",
				"GoodsMovementType": "101",
				"QuantityInEntryUnit": "40.000",
				"EntryUnit": "KG",
				"ManufacturingOrder": "1000123",
				"ReversedMaterialDocumentYear": "2026",
				"ReversedMaterialDocument": "3",
			},
			{
				"MaterialDocumentYear": "2026",
				"MaterialDocument": "5",
				"Material": "FG-1",
				"Batch": "L8",
				"GoodsMovementType": "101",
				"QuantityInEntryUnit": "35.000",
				"EntryUnit": "KG",
				"ManufacturingOrder": "1000123",
				"GoodsMovementIsCancelled": True,
			},
		]
		fake = FakeS4HANA().on("GET", "A_MaterialDocumentItem", ok({"results": items}))
		movements = orders.order_goods_movements(client(fake), "1000123")
		self.assertEqual(fake.requests[0]["query"]["$filter"], "ManufacturingOrder eq '1000123'")
		self.assertEqual(fake.requests[0]["query"]["$expand"], "to_MaterialDocumentHeader")
		self.assertEqual(fake.requests[0]["query"]["$skip"], "0")
		self.assertEqual(len(movements), 5)
		balance = orders.order_balance(client(fake), "1000123")
		self.assertEqual(
			balance["consumptions"],
			[{"material": "RM-1", "batch": "B1", "quantity": Decimal("15.000"), "unit": "KG"}],
		)
		self.assertEqual(
			balance["receipts"],
			[{"material": "FG-1", "batch": "L7", "quantity": Decimal("0.000"), "unit": "KG"}],
		)

	def test_order_goods_movements_follows_pages(self):
		def page(request):
			skip, top = int(request["query"]["$skip"]), int(request["query"]["$top"])
			rows = [
				{
					"MaterialDocumentYear": "2026",
					"MaterialDocument": str(n),
					"Material": "RM-1",
					"GoodsMovementType": "261",
					"QuantityInEntryUnit": "1",
					"EntryUnit": "KG",
				}
				for n in range(skip, min(skip + top, 5))
			]
			return ok({"results": rows})

		fake = FakeS4HANA().on("GET", "A_MaterialDocumentItem", page)
		movements = orders.order_goods_movements(client(fake), "1000123", page_size=2)
		self.assertEqual([m["document"] for m in movements], [f"2026|{n}" for n in range(5)])
		self.assertEqual([r["query"]["$skip"] for r in fake.requests], ["0", "2", "4"])
		balance = orders.order_balance(
			client(FakeS4HANA().on("GET", "A_MaterialDocumentItem", page)), "1000123"
		)
		self.assertEqual(balance["consumptions"][0]["quantity"], Decimal(5))


ROUTING = {
	"ProductionRoutingGroup": "50000123",
	"ProductionRouting": "1",
	"ProductionRoutingInternalVers": "1",
	"BillOfOperationsDesc": "Foam block",
	"Plant": "1010",
	"BillOfOperationsStatus": "4",
	"BillOfOperationsUnit": "KG",
	"MinimumLotSizeQuantity": "1.000",
	"MaximumLotSizeQuantity": "99999999.000",
	"ValidityStartDate": "/Date(1704067200000)/",
	"to_MatlAssgmt": {"results": [{"Product": "FG-1", "Plant": "1010"}]},
	"to_Sequence": {
		"results": [
			{
				"ProductionRoutingSequence": "0",
				"to_Operation": {
					"results": [
						{
							"ProductionRoutingOperation": "0010",
							"OperationText": "Mix",
							"WorkCenter": "MIX01",
							"Plant": "1010",
							"OperationControlProfile": "PP01",
							"OperationReferenceQuantity": "100.000",
							"OperationUnit": "KG",
							"OpStandardWorkQuantity1": "15.000",
							"OpStandardWorkQuantityUnit1": "MIN",
							"OpStandardWorkQuantity2": "1.500",
							"OpStandardWorkQuantityUnit2": "H",
						},
						{
							"ProductionRoutingOperation": "0020",
							"OperationText": "Cure",
							"WorkCenter": "CURE01",
						},
					]
				},
			}
		]
	},
}


class TestMasterData(unittest.TestCase):
	def test_routing(self):
		fake = FakeS4HANA().on("GET", "ProductionRoutingHeader(", ok(ROUTING))
		result = orders.routing(client(fake), "50000123", "1", "1")
		self.assertEqual(
			fake.requests[0]["path"],
			"/sap/opu/odata/sap/API_PRODUCTION_ROUTING/ProductionRoutingHeader(ProductionRoutingGroup='50000123',ProductionRouting='1',ProductionRoutingInternalVers='1')",
		)
		self.assertEqual(fake.requests[0]["query"]["$expand"], "to_Sequence/to_Operation,to_MatlAssgmt")
		self.assertEqual(result["description"], "Foam block")
		self.assertEqual(result["materials"], [{"material": "FG-1", "plant": "1010"}])
		self.assertEqual([o["operation"] for o in result["operations"]], ["0010", "0020"])
		op = result["operations"][0]
		self.assertEqual(op["base_quantity"], Decimal("100.000"))
		self.assertEqual(
			op["activities"],
			[
				{"position": 1, "quantity": Decimal("15.000"), "unit": "MIN", "parameter": ""},
				{"position": 2, "quantity": Decimal("1.500"), "unit": "H", "parameter": ""},
			],
		)
		self.assertEqual(result["valid_from"], date(2024, 1, 1))
		self.assertIsNone(orders.routing(client(FakeS4HANA()), "1", "1", "1"))

	def test_routing_without_version_reads_the_newest(self):
		fake = (
			FakeS4HANA()
			.on("GET", "ProductionRoutingHeader(", ok(ROUTING))
			.on(
				"GET",
				"ProductionRoutingHeader",
				ok(
					{
						"results": [
							{
								"ProductionRoutingGroup": "50000123",
								"ProductionRouting": "1",
								"ProductionRoutingInternalVers": "3",
							}
						]
					}
				),
			)
		)
		result = orders.routing(client(fake), "50000123", "1")
		listing, read = fake.requests
		self.assertEqual(
			listing["query"]["$filter"], "ProductionRoutingGroup eq '50000123' and ProductionRouting eq '1'"
		)
		self.assertEqual(listing["query"]["$orderby"], "ProductionRoutingInternalVers desc")
		self.assertIn("ProductionRoutingInternalVers='3'", read["path"])
		self.assertEqual(result["description"], "Foam block")
		self.assertIsNone(orders.routing(client(FakeS4HANA()), "50000123", "1"))

	def test_routings_for_material(self):
		fake = FakeS4HANA().on(
			"GET",
			"ProductionRoutingMatlAssgmt",
			ok(
				{
					"results": [
						{
							"ProductionRoutingGroup": "50000123",
							"ProductionRouting": "1",
							"Product": "FG-1",
							"Plant": "1010",
						}
					]
				}
			),
		)
		result = orders.routings_for_material(client(fake), "FG-1", "1010")
		self.assertEqual(fake.requests[0]["query"]["$filter"], "Product eq 'FG-1' and Plant eq '1010'")
		self.assertEqual((result[0]["group"], result[0]["counter"]), ("50000123", "1"))

	def test_bill_of_material(self):
		bom = {
			"BillOfMaterial": "00000123",
			"BillOfMaterialCategory": "M",
			"BillOfMaterialVariant": "1",
			"BillOfMaterialVersion": "",
			"Material": "FG-1",
			"Plant": "1010",
			"BOMHeaderQuantityInBaseUnit": "100.000",
			"BOMHeaderBaseUnit": "KG",
			"to_BillOfMaterialItem": {
				"results": [
					{
						"BillOfMaterialItemNumber": "0010",
						"BillOfMaterialComponent": "RM-1",
						"BillOfMaterialItemQuantity": "50.000",
						"BillOfMaterialItemUnit": "KG",
						"IsBackflushed": True,
					}
				]
			},
		}
		fake = FakeS4HANA().on("GET", "MaterialBOM(", ok(bom))
		result = orders.bill_of_material(client(fake), "00000123", "FG-1", "1010")
		self.assertEqual(
			fake.requests[0]["path"],
			"/sap/opu/odata/sap/API_BILL_OF_MATERIAL_SRV;v=0002/MaterialBOM(BillOfMaterial='00000123',"
			"BillOfMaterialCategory='M',BillOfMaterialVariant='1',BillOfMaterialVersion='',"
			"EngineeringChangeDocument='',Material='FG-1',Plant='1010')",
		)
		self.assertEqual(result["base_quantity"], Decimal("100.000"))
		self.assertEqual(result["items"][0]["component"], "RM-1")
		self.assertTrue(result["items"][0]["is_backflushed"])
		listing = FakeS4HANA().on("GET", "MaterialBOM", ok({"results": [bom]}))
		self.assertEqual(orders.boms_for_material(client(listing), "FG-1", "1010")[0]["bom"], "00000123")

	def test_work_centers(self):
		fake = FakeS4HANA().on(
			"GET",
			"A_WorkCenters",
			ok(
				{
					"results": [
						{
							"WorkCenter": "MIX01",
							"WorkCenterInternalID": "10000001",
							"WorkCenterTypeCode": "A",
							"Plant": "1010",
							"WorkCenterDesc": "Mixer 1",
						}
					]
				}
			),
		)
		result = orders.work_centers(client(fake), "1010")
		self.assertEqual(fake.requests[0]["query"]["$filter"], "Plant eq '1010'")
		self.assertEqual(result[0]["description"], "Mixer 1")
		one = FakeS4HANA().on(
			"GET", "A_WorkCenters(", ok({"WorkCenter": "MIX01", "WorkCenterInternalID": "10000001"})
		)
		self.assertEqual(orders.work_center(client(one), "10000001")["work_center"], "MIX01")
		self.assertIn("WorkCenterTypeCode='A'", one.requests[0]["path"])


class TestNewEntityDefaults(unittest.TestCase):
	def test_routing_key_needs_the_version(self):
		spec = DEFAULT_ENTITIES["Routing"]
		self.assertEqual(
			spec.keys_for("50000123|1|2"),
			{
				"ProductionRoutingGroup": "50000123",
				"ProductionRouting": "1",
				"ProductionRoutingInternalVers": "2",
			},
		)
		with self.assertRaises(ValueError):
			spec.keys_for("50000123|1")
		self.assertEqual(spec.label_for({"BillOfOperationsDesc": "Foam block"}), "Foam block")

	def test_bom_key_defaults_category_version_and_change_document(self):
		spec = DEFAULT_ENTITIES["Bill of Materials"]
		self.assertEqual(
			spec.keys_for("00000123|1|FG-1|1010"),
			{
				"BillOfMaterial": "00000123",
				"BillOfMaterialCategory": "M",
				"BillOfMaterialVariant": "1",
				"BillOfMaterialVersion": "",
				"EngineeringChangeDocument": "",
				"Material": "FG-1",
				"Plant": "1010",
			},
		)
		self.assertEqual(
			spec.keys_for("00000123|M|1|2|500000001|FG-1|1010")["EngineeringChangeDocument"], "500000001"
		)
		self.assertEqual(
			spec.external_id_for(
				{
					"BillOfMaterial": "00000123",
					"BillOfMaterialCategory": "M",
					"BillOfMaterialVariant": "1",
					"BillOfMaterialVersion": "",
					"EngineeringChangeDocument": "",
					"Material": "FG-1",
					"Plant": "1010",
				}
			),
			"00000123|1|FG-1|1010",
		)

	def test_work_center_key(self):
		spec = DEFAULT_ENTITIES["Workstation"]
		self.assertEqual(
			spec.keys_for("10000001"), {"WorkCenterInternalID": "10000001", "WorkCenterTypeCode": "A"}
		)
		self.assertEqual(spec.label_for({"WorkCenterInternalID": "10000001", "WorkCenter": "MIX01"}), "MIX01")

	def test_every_default_is_consistent(self):
		for spec in DEFAULT_ENTITIES.values():
			self.assertTrue(spec.service and spec.entity_set and spec.key_fields)
			for name in spec.key_defaults:
				self.assertIn(name, spec.key_fields)
