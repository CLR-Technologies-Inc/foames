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

## Setup checklist

The short version; each step is detailed below.

| Step | Where | Done when |
| --- | --- | --- |
| 1. Communication user or OAuth client for FoaMES | S/4HANA | You have a user name and password, or a token URL, client id and secret |
| 2. Communication arrangements or activated services for the OData APIs you use | S/4HANA | `$metadata` of each service answers for that user |
| 3. Fill in **S4HANA Settings**, press **Test Connection** | FoaMES | "Connected to ..." is shown |
| 4. Check entity sets and key fields against `$metadata`; add **Entity Mappings** for Unit of Measure, Operation, Location, Serial Number if you use them, or to override a default | FoaMES | An External Reference of each type you need resolves |
| 5. Tick **Enabled**; set **Default ERP System** to `S4HANA` in FoaMES Settings if S/4HANA is the main ERP | FoaMES | New references resolve against S/4HANA |
| 6. For inbound IDocs: a FoaMES user with the **FoaMES Integration** role and an API key; RFC destination (SM59), XML HTTP port (WE21), partner profile (WE20) | Both | A test IDoc shows up as an S4HANA Inbound IDoc with status Processed |
| 7. Make sure the scheduler is enabled on the site | FoaMES | `bench --site <site> scheduler status` says enabled; queued postings move to Posted |

Postings are sent by the scheduler, so nothing leaves FoaMES until step 7 is in place, and **Pause Outbox** in S4HANA Settings holds them at any time.

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

### Outbox statuses

| Status | Meaning | What to do |
| --- | --- | --- |
| Queued | Waiting for the scheduler, or for an earlier posting of its sequence group | Nothing |
| Sending | A worker is sending it now. A row left in Sending for 15 minutes belongs to a worker that died and is put back as Unknown | Nothing |
| Retry | A transient failure (throttling, 5xx, network, a rejected login); **Next Attempt** says when it is tried again | Nothing, unless S/4HANA stays down or the credentials are wrong |
| Unknown | The last send got no clear answer. The next attempt looks for the idempotency marker in S/4HANA first | Nothing; it resolves itself to Posted or Retry |
| Posted | S/4HANA created the document; **S/4HANA Document** holds its key, and a Goods Movement also gets an External Reference of type Stock Movement | Nothing |
| Failed | S/4HANA rejected it, or 12 attempts were used up; **Last Error** has SAP's message | Fix the cause, then **Requeue**, or **Cancel Posting** |
| Cancelled | Dropped by a System Manager; later postings in its group are sent | Nothing |

Requeue and Cancel Posting are limited to System Managers. Requeue first puts the posting into Unknown, so a posting that failed after a timeout is checked for in S/4HANA before being sent again. The scheduler sends up to 50 postings per run, oldest first, and commits after each one, so a posting S/4HANA accepted is recorded even if a later one in the same run fails.

## Day-to-day operation

- Watch the **S4HANA Outbox Reconciliation** report. With **Include Posted** off it lists everything that still needs attention, with the earlier posting that holds each one. Filter by sequence group to follow one order.
- A posting that is Failed with a business message (period closed, order locked, batch missing) is fixed in S/4HANA or by correcting the payload on the record, then requeued. Do not create a second outbox record for the same business event; the idempotency key would return the first one anyway.
- **Pause Outbox** before planned S/4HANA downtime. Queued postings keep accumulating and are sent in order when it is cleared.
- Reference lookups that fail because S/4HANA is unreachable leave the External Reference Unverified rather than blocking a save. Resolve them later from the form or by saving again.
- Rotate the communication user's password in S/4HANA and in S4HANA Settings together. A 401 or 403 is treated as temporary on both paths: reference lookups leave the reference Unverified to resolve later, and outbox postings go to **Retry** with the usual backoff, so nothing is failed or held as long as the credentials are fixed within the retry window (12 attempts, up to 6 hours apart).
- The Digital Access point above applies to every Posted row: it is a document created in S/4HANA by a third-party system.

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
