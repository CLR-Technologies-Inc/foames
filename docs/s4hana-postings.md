# Posting to and reading from S/4HANA

What the S/4HANA adapter can post and read once it is connected
([s4hana-setup.md](s4hana-setup.md)), and how a screen, an agent or another app calls it. Every
posting goes through the **S4HANA Outbox**, so it is queued immediately, sent by the scheduler, and
never posted twice ([s4hana-adapter.md](s4hana-adapter.md) describes the outbox).

Field names follow SAP's released APIs. Check them against your system's `$metadata`; the
payload builders accept an `extra` dict for fields a release adds or renames.

## Confirmations

A confirmation (`ProdnOrdConf2`) reports work done on one operation of a production order: the
yield, scrap and rework quantities, the activities (setup, machine and labour time in the positions
of the operation's standard value key), when the work ran, who did it, and whether the operation is
finished. Process orders use the same fields on `ProcOrdConf2`.

```python
from foames.foames_adapters.s4hana import confirmations
from foames.foames_adapters.doctype.s4hana_outbox.s4hana_outbox import enqueue

payload = confirmations.confirmation(
	"1000123",
	"0010",
	yield_quantity=95.5,
	unit="KG",
	scrap_quantity=4.5,
	work_center="MIX01",
	plant="1010",
	activities=[confirmations.Activity(2, 1.5, "H")],  # machine time, position 2
	times=confirmations.ExecutionTimes(start=started_at, end=finished_at),
	final=True,
	goods_movements=[  # optional, posted with it
		confirmations.GoodsMovementItem("RM-1", "1010", 50, "KG", "261", batch="B1", storage_location="0001"),
	],
)
enqueue(
	confirmations.PRODUCTION, payload, idempotency_key="<record>:<step>:confirm", sequence_group="1000123"
)
```

- Quantities are sent as decimal strings; dates as `YYYY-MM-DDT00:00:00`; times as `PTxxHxxMxxS`.
- `final=True` sets `IsFinalConfirmation`; `final_confirmation_type` (`X` final, `P` partial,
  empty for automatic) is the alternative on releases that use it.
- `clear_open_reservations=True` closes the remaining component reservations with a final
  confirmation.
- Leave `ConfirmationText` alone: the outbox writes its idempotency marker there, and searches for
  it before resending a confirmation whose first send got no answer.
- `no_goods_movements=True` (`APIConfHasNoGoodsMovements`) stops S/4HANA from backflushing or
  receiving automatically for this confirmation.
- Leave `goods_movements` empty to let S/4HANA backflush components and receive the product
  according to the order's settings. As soon as one `GoodsMovementItem` is given, S/4HANA stops
  determining movements for this confirmation, so the list must then be complete: every
  backflushed component, the goods receipt and any by-product. The order's components (see the
  reads below) give the reservation items and quantities to build it from.

### Cancelling a confirmation

`CancelProdnOrdConf` (`CancelProcOrdConf` for process orders) creates a reversal confirmation and
reverses the goods movements that came with the original.

```python
from foames.foames_adapters.s4hana import actions

operation, payload = actions.cancel_confirmation("77", "1", posting_date=today)
enqueue(operation, payload, idempotency_key="<record>:<step>:cancel", sequence_group="1000123")
```

A function import carries no marker, so after an unclear answer the outbox reads the original
confirmation and treats `IsReversed` as proof that the cancellation went through. In that one
case the posting's document is the original `GROUP|COUNT` (with `IsReversed` in the response)
rather than the reversal confirmation's own number, because the API exposes no link from the
original to its reversal.

## Goods movements

A material document (`A_MaterialDocumentHeader` with items) posts one or more movements of the
same kind; the header's `GoodsMovementCode` says which transaction it stands for (02 receipt for
order, 03 goods issue, 04 transfer posting, 05 other receipt, 06 reversal). The builders pick the
code from the movement types.

```python
from foames.foames_adapters.s4hana import goods_movements as gm

# Product into stock, against the order (101)
gm.goods_receipt_for_order(
	"1000123", "FG-1", "1010", 95.5, "KG", storage_location="0002", batch="L7", is_completely_delivered=True
)
# Components out of stock, against the order (261)
gm.goods_issue_to_order(
	"1000123",
	[
		gm.Item(
			"RM-1", "1010", 50, "KG", "261", batch="B1", reservation="0000012345", reservation_item="0001"
		),
		{"material": "RM-2", "plant": "1010", "quantity": 2, "unit": "L"},
	],
)
# Storage location to storage location (311), quality inspection to unrestricted (321)
gm.transfer_posting(
	"FG-1", "1010", 10, "KG", from_storage_location="0002", to_storage_location="0003", batch="L7"
)
gm.transfer_posting(
	"FG-1", "1010", 10, "KG", movement_type="321", from_storage_location="0002", from_stock_type="2"
)
# Scrap (551)
gm.scrap(
	"FG-1", "1010", 1, "KG", storage_location="0002", batch="L7", cost_center="CC100", reason_code="0002"
)
# Anything else
gm.material_document([gm.Item(..., movement_type="531", order="1000123")])  # by-product receipt
```

Each returns the payload for `enqueue("Goods Movement", payload, idempotency_key=..., sequence_group=...)`.
Every material document carries a posting date; the builders default it to today. Give the
reservation and item of an order component when you have them (they are on the order's
components, see the reads below); without them S/4HANA books the issue as an unplanned
consumption for the order. `reversal=True` on the receipt and issue builders posts the matching
reversal type instead: 102 under code 02, and 262 as a receipt against the reservation (code 05
with `MaterialDocumentPostingType` 1 on reserved items). To undo a whole document, use the
reversal below.

Leave `MaterialDocumentHeaderText` alone: it carries the idempotency marker (the field holds 25
characters, so the marker is `FOAMES-` plus 16 hex digits).

### Reversing a material document

```python
operation, payload = actions.reverse_material_document("2026", "4900001234", posting_date=today)
enqueue(operation, payload, idempotency_key="<record>:reverse-4900001234")
```

S/4HANA answers with the reversal document, which the outbox records as the posting's document
and as a Stock Movement External Reference. After an unclear answer the outbox searches
`A_MaterialDocumentItem` for an item whose `ReversedMaterialDocument` names the original.

## Sequencing postings for one order

Postings that share a `sequence_group` are sent in the order they were queued, and a failed one
holds the rest. Use the order number as the group so that, for example, the goods issue of the
components, the confirmation and the goods receipt of an operation reach S/4HANA in that order,
and a locked order holds everything that follows instead of posting out of order.

## Reads

All reads take the adapter's client and return plain dicts, with the raw entity under `raw`.

```python
from foames.foames_adapters.s4hana import orders
from foames.foames_adapters.doctype.s4hana_settings.s4hana_settings import get_settings

client = get_settings().client()
order = orders.production_order(client, "1000123")  # operations, components, items, statuses
orders.orders_for_material(client, "FG-1", "1010", released_only=True)
orders.order_confirmations(client, "1000123")  # what was confirmed, reversed ones flagged
orders.order_goods_movements(client, "1000123")  # every material document item of the order
orders.order_balance(client, "1000123")  # receipts and consumptions net of reversals
orders.routing(client, "50000123", "1")  # newest version; or pass version="1"
orders.routings_for_material(client, "FG-1", "1010")
orders.bill_of_material(client, "00000123", "FG-1", "1010", variant="1")  # items, quantities, backflush flags
orders.boms_for_material(client, "FG-1", "1010")
orders.work_centers(client, "1010")
```

`production_order(..., process_order=True)` reads `A_ProcessOrder_2` instead. An order's
`operations[*].internal_id` is the key of `A_ProductionOrderOperation_2`, and its
`components[*]` carry the reservation and item needed for goods issues. A routing's internal
version is part of its key; `routing` without a version lists the versions and reads the newest.
A material BOM is keyed by seven fields (number, category, variant, version, change document,
material, plant), so `bill_of_material` takes the material and plant too, and a Bill of Materials
External Reference is `BOM|VARIANT|MATERIAL|PLANT` (category M, no version, no change document) or
all seven values.

## HTTP and agent endpoints

Every function below is whitelisted under `foames.foames_adapters.s4hana.api` and callable as
`/api/method/foames.foames_adapters.s4hana.api.<name>`. Reads need one of the FoaMES roles
(Operator, Engineer, Quality, Integration) or System Manager. Postings need create permission on
S4HANA Outbox; the posting itself is made later by the scheduler with the adapter's credentials.
Every posting takes an `idempotency_key` that names the business event; repeating the call returns
the same outbox record.

| Endpoint | Does |
| --- | --- |
| `get_operations` | Lists the outbox operations and the fields each needs |
| `get_production_order(order, process_order=0)` | The order with operations, components, items and statuses |
| `get_orders_for_material(material, plant, top, released_only)` | Orders of a material |
| `get_order_confirmations(order)` | Confirmations posted for the order |
| `get_order_goods_movements(order)` | Material document items of the order |
| `get_order_balance(order)` | Net receipts and consumptions |
| `get_routing(group, counter, version)` / `get_routings_for_material(material, plant)` | Routings |
| `get_bill_of_material(bom, material, plant, variant, category, version, change_document)` / `get_boms_for_material(material, plant)` | BOMs |
| `get_work_centers(plant)` | Work centers of a plant |
| `confirm_order(order, operation, idempotency_key, yield_quantity, unit, scrap_quantity, ..., activities, start, end, goods_movements_items, final, process_order)` | Queues a confirmation |
| `post_goods_receipt(order, material, plant, quantity, unit, idempotency_key, storage_location, batch, ...)` | Queues a 101 (or 102 with `reversal=1`) |
| `post_goods_issue(order, components, idempotency_key, reversal)` | Queues 261s (or 262s) |
| `post_transfer(material, plant, quantity, unit, idempotency_key, from_storage_location, to_storage_location, ...)` | Queues a transfer posting |
| `post_scrap(material, plant, quantity, unit, idempotency_key, ...)` | Queues a 551 |
| `cancel_confirmation(confirmation_group, confirmation_count, idempotency_key, posting_date, process_order)` | Queues a cancellation |
| `reverse_material_document(year, document, idempotency_key, posting_date)` | Queues a reversal |

JSON arguments (`activities`, `goods_movements_items`, `components`) are lists of objects with the
builder's field names, for example `[{"position": 2, "quantity": 1.5, "unit": "H"}]` or
`[{"material": "RM-1", "plant": "1010", "quantity": 50, "unit": "KG", "batch": "B1"}]`.

Each posting endpoint returns `{"outbox": <name>, "operation": ..., "payload": ...}`. Follow the
posting on the S4HANA Outbox record: `status`, `sap_document` (the confirmation `GROUP|COUNT` or
the material document `YEAR|NUMBER`) and `last_error`.

## What the adapter does not do

- It does not create or change orders, routings or BOMs in S/4HANA; those stay with planning.
- It does not post quality results or inspection lots; S/4HANA's `API_INSPECTIONLOT_SRV` can be
  added the same way the operations here were (a payload builder, an outbox operation, a test).
- It does not keep a local copy of orders. Read on demand, or let S/4HANA push LOIPRO IDocs.
