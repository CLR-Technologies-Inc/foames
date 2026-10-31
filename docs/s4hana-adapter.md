# SAP S/4HANA adapter

The S/4HANA adapter connects FoaMES to an SAP S/4HANA system (on-premise or private cloud). S/4HANA
runs on its own server, so the adapter works over HTTP:

| Direction | What | How |
| --- | --- | --- |
| FoaMES reads S/4HANA | Resolve External References (Item, Batch, Work Order, Stock Movement, plus any type you map) | Released OData V2 APIs |
| FoaMES writes S/4HANA | Production or process order confirmations, goods movements | OData create calls through the **S4HANA Outbox** |
| S/4HANA pushes to FoaMES | Order (LOIPRO), material (MATMAS) and batch (BATMAS) downloads, or any other IDoc | IDoc XML over an HTTP port |

The adapter does not use RFC, the SAP NetWeaver RFC SDK or PyRFC, and no SAP code or API metadata is
included in this repository.

## Licensing note for S/4HANA customers

Under SAP's Digital Access (document-based) licensing, some documents created in S/4HANA by a
third-party system are counted, and material documents and quality inspection lots are among the
document types SAP lists. Postings that FoaMES makes through this adapter may therefore count
against the customer's Digital Access entitlement. This is a matter of the customer's SAP contract;
check it before turning on postings.

## Setup in S/4HANA

1. Create a communication user, or an OAuth 2.0 client, for FoaMES.
2. Create communication arrangements (or, on older on-premise releases, activate the OData services in
   `/IWFND/MAINT_SERVICE`) for the services you use:

   | Service | Used for |
   | --- | --- |
   | `API_PRODUCT_SRV` | Item references |
   | `API_BATCH_SRV` | Batch references |
   | `API_PRODUCTION_ORDER_2_SRV` | Work Order references |
   | `API_MATERIAL_DOCUMENT_SRV` | Goods movements and Stock Movement references |
   | `API_PROD_ORDER_CONFIRMATION_2_SRV` | Production order confirmations (communication scenario SAP_COM_0104) |
   | `API_PROC_ORDER_CONFIRMATION_2_SRV` | Process order confirmations |

   Entity sets and field names differ between releases. Check each service's `$metadata` on your
   system against the defaults in `foames/foames_adapters/s4hana/entities.py` and
   `foames/foames_adapters/s4hana/outbox.py`, and override entity sets in **S4HANA Settings**.
3. For IDocs, create an RFC destination of type G (SM59) pointing at
   `https://<foames-site>/api/method/foames.foames_adapters.s4hana.api.receive_idoc`, with the API
   key and secret of a FoaMES user that has the **FoaMES Integration** role as user and password.
   Create an XML HTTP port (WE21) on that destination, and add the message types you want to the
   partner profile (WE20).

## Setup in FoaMES

Open **S4HANA Settings**:

- **Base URL**, **SAP Client** and **Language** of the S/4HANA system.
- **Method**: Basic (communication user) or OAuth 2.0 Client Credentials.
- **CA Bundle Path** if S/4HANA uses a certificate from a private CA.
- **Entity Mappings**: map Unit of Measure, Operation, Location or Serial Number to the entity that
  holds them on your release, or override a default. Composite keys are written into an External
  Reference's External ID as the key values joined by `|`, in the order of the key fields. For
  example, a batch is `MATERIAL|BATCH`, or `MATERIAL|PLANT|BATCH` when batches are unique per plant.
- **Test Connection** fetches a CSRF token, which checks the URL, client and credentials.
- Tick **Enabled**. Set **Default ERP System** in FoaMES Settings to `S4HANA` if new references
  should point at S/4HANA by default.

## The outbox

Every posting to S/4HANA is queued as an **S4HANA Outbox** record and sent by the scheduler. Code
queues a posting with:

```python
from foames.foames_adapters.doctype.s4hana_outbox.s4hana_outbox import enqueue

enqueue(
	"Production Order Confirmation",
	{
		"OrderID": "1000123",
		"OrderOperation": "0010",
		"ConfirmationYieldQuantity": "100",
		"ConfirmationUnit": "KG",
	},
	idempotency_key="<the business event, for example segment and process>",
	sequence_group="1000123",
)
```

- **Idempotency.** Queuing the same key twice returns the first record. The adapter also writes a
  23-character marker derived from the key into the document's text field (confirmation text or
  material document header text). When a send ends without a clear answer (timeout, dropped
  connection, server error), the record goes to **Unknown**, and the next attempt searches S/4HANA
  for the marker before posting, so a confirmation is never posted twice. Do not overwrite that text
  field in the payload.
- **Retries.** Throttling, server errors and network failures are retried with exponential backoff
  (1, 2, 4 ... minutes, up to 6 hours) for 12 attempts.
- **Rejections.** A business rejection from S/4HANA (closed posting period, locked order, missing
  batch) marks the posting **Failed** with SAP's message. Fix the cause, then **Requeue** it, or
  **Cancel Posting** to drop it.
- **Sequencing.** Postings that share a sequence group (for example one order) are sent strictly in
  the order they were queued. A failed posting holds the rest of its group until it is requeued and
  posted, or cancelled.
- **Reconciliation.** The **S4HANA Outbox Reconciliation** report lists postings that still need
  attention and which earlier posting holds each one.
- **Pause Outbox** in S4HANA Settings stops sending without stopping queuing.

## Inbound IDocs

Each IDoc is stored once per sender and IDoc number as an **S4HANA Inbound IDoc**, so a resend is
recognized and not processed twice. For LOIPRO, MATMAS and BATMAS the adapter records an External
Reference for the order, material or batch. Other apps can process IDocs further by message type
through the `foames_s4hana_idoc_handlers` hook:

```python
foames_s4hana_idoc_handlers = {
	"LOIPRO": ["myapp.s4hana.on_order_download"],
}
```

Each handler is called with the inbound record, the parsed IDoc and its summary.

## Certification

SAP certification is not required for the adapter to work. A customer may ask for SAP Integration and
Certification Center (ICC) certification during procurement; it applies to a specific adapter
version.

## Further reading

- [s4hana-setup.md](s4hana-setup.md): users, communication arrangements, OAuth, service checks.
- [s4hana-postings.md](s4hana-postings.md): confirmations, goods movements, cancellations and
  reversals, order, routing and BOM reads, and the HTTP endpoints for screens and agents.
