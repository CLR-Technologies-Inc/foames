# Siemens Insights Hub adapter (Opcenter Intelligence)

The Insights Hub adapter connects FoaMES to a Siemens Insights Hub tenant, the platform Siemens'
Opcenter Intelligence runs on. Opcenter Intelligence reads the plant's equipment from the platform's
asset model and its production from the platform's time series and events, so that is where FoaMES
puts what the machines report. Like S/4HANA, Insights Hub runs on its own servers, so the adapter
works over HTTPS through the region gateway:

| Direction | What | How |
| --- | --- | --- |
| FoaMES reads Insights Hub | Resolve External References: Workstation and Location as assets, plus the Opcenter Intelligence resources you map (materials, orders, operations, batches) | The platform REST APIs behind the gateway |
| Machines report to Insights Hub | Each machine's good and scrap counts, running minutes and job, as one time series record per window on the machine's asset | The roll-up below, through the **Insights Hub Outbox** |
| Machines report to Insights Hub | Each machine state change, as an event on the asset | `foames_machine_state_changed`, through the **Insights Hub Outbox** |

The adapter uses the released REST APIs only, with the Python standard library. No Siemens SDK, code
or API metadata is included in this repository.

## What the adapter knows, and what you tell it

The platform APIs every tenant has are built in, with their paths and field names:

| Service | Used for |
| --- | --- |
| `assetmanagement/v3` | Workstation and Location references (`assets/{assetId}`); the connection test |
| `iottimeseries/v3` | Time series writes (`PUT timeseries/{entityId}/{propertySetName}`) |
| `eventmanagement/v3` | Events (`POST events`, searched by asset, type and time to verify a retry) |
| `technicaltokenmanager/v3` | Tokens for a registered application |

Opcenter Intelligence's own resources (materials, orders, operations, batches, routings, and so on)
are not built in: their paths, key fields and label fields differ by product version and are taken
from the Opcenter Intelligence API reference in the Insights Hub developer documentation
(`developer.siemens.com/insights-hub`, APIs, Advanced, Opcenter Intelligence API). You enter each one
you need as an **Entity Mapping** in Insights Hub Settings; nothing is guessed on your behalf. A
mapping has:

| Field | Meaning | Example |
| --- | --- | --- |
| Reference Type | The kernel type it resolves | Work Order |
| Service | The API behind the gateway, with its version, as the reference shows it in the path after `/api/` | `opcenterintelligence/v1` |
| Resource | The collection inside it | `orders` |
| Lookup | **Path** for a record addressed by its id (`GET <resource>/<id>`); **Filter** for one addressed by another field or by several (`GET <resource>?filter={"<key>":"<value>"}`) | Filter |
| Key Fields | Comma-separated, in the order used in the External ID; values are joined by `\|` | `orderNumber` |
| Label Field | Dotted path to the text shown for the record | `material.description` |

A row for Workstation or Location overrides the asset default, for a site that models equipment in
Opcenter Intelligence rather than as assets.

## Setup checklist

| Step | Where | Done when |
| --- | --- | --- |
| 1. Credentials for FoaMES: an application registered in the Developer Cockpit (Technical Token Manager), or service credentials from the tenant's Settings app | Insights Hub | You have a client id and secret, and for an application its name, version and host tenant |
| 2. The application or the service credentials may read assets and write time series and events; for Opcenter Intelligence resources, the scopes the API reference names | Insights Hub | A token request answers 200 |
| 3. An aspect type with the variables below, assigned to the asset type of the machines | Insights Hub | The aspect shows on each machine's asset |
| 4. Fill in **Insights Hub Settings**, press **Test Connection** | FoaMES | "Connected to ..." is shown |
| 5. Add **Entity Mappings** for the Opcenter Intelligence resources you reference | FoaMES | An External Reference of each type resolves |
| 6. Give each Machine a **Workstation Reference** on the Insights Hub adapter whose External ID is the asset id | FoaMES | The reference resolves to the asset's name |
| 7. Tick **Enabled**; set **Default ERP System** to `INSIGHTS_HUB` in FoaMES Settings only if Insights Hub is where new references should point by default | FoaMES | New references resolve against Insights Hub |
| 8. Make sure the scheduler is enabled on the site | FoaMES | `bench --site <site> scheduler status` says enabled; queued postings move to Posted |
| 9. Tick **Send Machine Production as Time Series** and, if wanted, **Send State Changes as Events** | FoaMES | A running machine's counts show up as queued Time Series Writes |

Writes are sent by the scheduler, so nothing leaves FoaMES until step 8 is in place, and **Pause
Outbox** holds them at any time.

## Setup in Insights Hub

1. **Credentials.** Either register an application in the Developer Cockpit and create application
   credentials for it (the adapter then uses the Technical Token Manager with the application's name,
   version and host tenant), or issue service credentials in the tenant's Settings app (the adapter
   then uses OAuth 2.0 client credentials against the tenant's token endpoint,
   `https://<tenant>.piam.<region>/oauth/token`). Application credentials are the way a tenant lets a
   third-party application act for it; service credentials are simpler for a single-tenant
   integration.
2. **Aspect.** Create an aspect type (the default name is `FoaMESProduction`) with these variables
   and assign it to the asset type of the machines. Rename any variable in Insights Hub Settings if
   the aspect uses other names.

   | Variable | Type | Holds |
   | --- | --- | --- |
   | `goodCount` | DOUBLE | The good counters' deltas in the window (`good`, `count`, `total`, `parts`) |
   | `scrapCount` | DOUBLE | The scrap counters' deltas (`scrap`, `reject`, ...) |
   | `runMinutes` | DOUBLE | Minutes the machine was Running in the window |
   | `windowMinutes` | DOUBLE | Length of the window, so a reader can tell a short window from a slow machine |
   | `job` | STRING | The External ID of the machine's current job (an order, or `ORDER\|OPERATION`) |
   | `state` | STRING | The machine's state at the window's end |

3. **Events.** Nothing to create: the adapter uses the platform's standard event type
   (`MindSphereStandardEvent`), with the state in `description` and `code`, the machine's seriousness
   in `severity` (Down is an error, Unknown a warning, the rest information) and `FoaMES` as `source`.
   Enter a custom type in **Event Type ID** if you have one; it must carry the standard type's fields.

## Setup in FoaMES

Open **Insights Hub Settings**:

- **Gateway URL** of the region (`https://gateway.eu1.mindsphere.io` for the European region, the
  equivalent for yours) and the **Tenant** name.
- **Method**: Technical Token Manager (application credentials) or Service Credentials. For the
  token manager, fill in **Application Name**, **Application Version**, and **Host Tenant** and **User
  Tenant** when they differ from the tenant; **Credentials Header Scheme** is the word before the
  base64 credentials in `X-SPACE-AUTH-KEY` (Basic, as the platform SDKs send it; switch to Bearer only
  if your tenant's documentation says so). For service credentials, the **Token URL**. Both URLs
  must be `https://`.
- **Client ID** and **Client Secret**. The secret is a Password field, read with `get_password`.
- **CA Bundle Path** if the gateway is reached through a proxy with a private CA.
- **Entity Mappings**, as above.
- **Test Connection** fetches a token and reads one asset, which checks the gateway, the tenant and
  the credentials.
- Tick **Enabled**.

Then point each Machine at its asset: an External Reference with ERP System `INSIGHTS_HUB`, type
Workstation and the asset id as External ID, set as the machine's **Workstation Reference**. A
Location reference works the same way for a line or area asset.

## The outbox

Every write to Insights Hub is queued as an **Insights Hub Outbox** record and sent by the scheduler.
Code queues a write with:

```python
from foames.foames_adapters.doctype.insights_hub_outbox.insights_hub_outbox import enqueue

enqueue(
	"Time Series Write",
	{
		"entityId": "<asset id>",
		"propertySetName": "FoaMESProduction",
		"data": [{"_time": "2026-11-04T10:10:00.000Z", "goodCount": 120, "scrapCount": 3}],
	},
	idempotency_key="<the business event, for example machine and window end>",
)
```

Two operations exist:

- **Time Series Write** puts records on an aspect of an asset. The platform keys a record on its
  `_time` and overwrites a record written again, so the write is idempotent by nature: a send that
  ends without a clear answer goes to **Retry** and is simply sent again.
- **Event** creates an event on an asset. An event has no natural key, so the adapter writes a
  23-character marker derived from the idempotency key into the event's `correlationId`. When a send
  ends without a clear answer (timeout, dropped connection, server error), the record goes to
  **Unknown**, and the next attempt searches the asset's events of that type within a minute of the
  event's timestamp, every page of them, for the marker before posting, so an event is never created
  twice. Do not set `correlationId` in the payload; it is overwritten.

The rest is the same as the S/4HANA outbox. Queuing the same key twice returns the first record.
Throttling, server errors, network failures and a rejected login are retried with exponential backoff
(1, 2, 4 ... minutes, up to 6 hours) for 12 attempts. A validation error from the platform (a missing
aspect, a variable the aspect does not have, an asset that does not exist) marks the posting
**Failed** with the platform's message and `logref`; fix the cause, then **Requeue** it, or
**Cancel Posting** to drop it. Postings that share a sequence group are sent strictly in the order
they were queued; state events of one asset share one. **Pause Outbox** stops sending without
stopping queuing. The statuses are those of the [S/4HANA outbox](../s4hana/README.md#outbox-statuses),
with **Insights Hub Record** holding the event's id or the asset, aspect and time of the time series
record.

## Rolling machine data up to Insights Hub

With **Send Machine Production as Time Series** ticked, every ten minutes and at the moment a
machine's job changes, the adapter takes the window since the last record of that machine, sums the
good and scrap counter deltas in it, finds the stretches the machine was Running, and queues one
record at the window's end on the machine's asset. The job is the External ID of the machine's
**Current Job Reference**, whichever adapter it points at: an Insights Hub job is written as it is,
an S/4HANA or ERPNext order as `<adapter>:<id>`, so a plant that runs its orders in another ERP still
gets its production correlated to them in Opcenter Intelligence. A window with no counts and no run
time queues nothing: Opcenter Intelligence takes the absence of a record as nothing produced, and
Unknown time is never written as run time. Counter rules are the core's: a first reading, a reset or
an out-of-order reading adds nothing.

Where the previous window ended is read back from the outbox (the newest record's `_time`), so
nothing about Insights Hub is stored on the Machine, and a machine is rolled up by one worker at a
time. A scheduled window ends two minutes behind the clock, so an event whose transaction is still
committing when the window is cut lands in the next window instead of behind the checkpoint. A machine rolled up for the first time starts with the last ten minutes, so connecting a plant
with months of history does not flood the tenant. Timestamps are converted from the site's timezone
to UTC on the way out.

With **Send State Changes as Events** ticked, each state change of a machine that points at an asset
queues an event on the asset. Events of one asset share a sequence group, so they arrive in order.

An Agent Suggestion is raised for a machine whose write Insights Hub rejected (usually the aspect or
a variable missing on the asset, or a wrong asset id); fix the cause, then requeue the posting, or
cancel it. Cancelling a time series window drops that window's production for good: the next window
starts where the cancelled one ended.

## Day-to-day operation

- Watch the **ERP Outbox Health** report; the Insights Hub adapter is one of its columns.
- A Failed posting with a platform message is fixed on the tenant (create the aspect, add the
  variable, fix the asset id on the machine's Workstation reference) or by correcting the payload,
  then requeued.
- **Pause Outbox** before planned maintenance on the tenant. Queued postings keep accumulating and
  are sent in order when it is cleared.
- Reference lookups that fail because the gateway is unreachable, or because the credentials were
  rejected, leave the External Reference Unverified rather than blocking a save. Resolve them later
  from the form or by saving again.
- Rotate the client secret on the tenant and in Insights Hub Settings together. A 401 or 403 is
  treated as temporary on both paths, so nothing is failed or held as long as the credentials are
  fixed within the retry window.
- The platform meters API calls and time series storage per tenant; one record per machine every ten
  minutes is small, but check the tenant's quotas with Siemens before connecting a large plant.

## Writing more to Opcenter Intelligence

The two outbox operations cover what Opcenter Intelligence reads from the platform. To post to an
Opcenter Intelligence resource directly (for example to create an order or close a batch), add an
operation to `foames/foames_adapters/insights_hub/outbox.py` with its path from the API reference,
a way to make it idempotent (a client reference the resource keeps and can be searched by, as the
event's `correlationId` is), and a test in `test_outbox_rules.py` against the scripted fake. Keep
the invariant: a posting is checked for before it is resent after an unclear answer.
