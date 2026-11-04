# Adapters for other MES and MOM systems

FoaMES is often not the only manufacturing system in a plant. An enterprise MES or MOM suite holds
the orders, materials, batches and equipment, or a frontline platform runs the operator apps, while
FoaMES reads the machines, computes OEE and raises suggestions. These adapters let FoaMES refer to the
records those systems own, and queue writes to them that are never performed twice. They are
registered through the same `foames_erp_adapters` hook as the ERPNext, S/4HANA and Insights Hub
adapters, so an External Reference can point at any of them.

| Folder | Key | System | Connection style the profile knows |
| --- | --- | --- | --- |
| `plex/` | `PLEX` | Rockwell Plex Smart Manufacturing Platform | API key header `X-Plex-Connect-Api-Key`, customer id (PCN) header, gateway `connect.plex.com` |
| `factorytalk_productioncentre/` | `FTPC` | Rockwell FactoryTalk ProductionCentre and PharmaSuite | Basic, bearer token or OAuth 2.0 against the site's web services |
| `sap_dmc/` | `SAP_DMC` | SAP Digital Manufacturing | OAuth 2.0 client credentials (XSUAA), plant as a query parameter; material, order, resource, work center and SFC reads ship as defaults |
| `delmia_apriso/` | `APRISO` | Dassault Systèmes DELMIA Apriso | Basic, bearer token or OAuth 2.0 against the site's published Apriso services |
| `aveva_mes/` | `AVEVA_MES` | AVEVA Manufacturing Execution System (formerly Wonderware MES) | Basic, bearer token or OAuth 2.0 (AVEVA Connect) against the MES web API |
| `critical_manufacturing/` | `CMF_MES` | Critical Manufacturing MES | Bearer token from its security service, or Basic |
| `tulip/` | `TULIP` | Tulip | Basic with an API bot's key and secret, instance URL `<instance>.tulip.co`, Tables API |
| `aegis_factorylogix/` | `FACTORYLOGIX` | Aegis FactoryLogix | Basic, bearer token or OAuth 2.0 against the xTend API |
| `koerber_pasx/` | `PASX` | Körber Werum PAS-X MES | Basic or bearer token against the site's PAS-X interfaces; read-first under GxP |
| `proficy/` | `PROFICY` | Proficy Smart Factory MES (Velotic, formerly GE Vernova) | OAuth 2.0 client credentials at the UAA token URL, or Basic |

Each folder holds a **profile**: the key and label, where the vendor's public API documentation
lives, how the system authenticates, what the base URL looks like, the entity lookups documented well
enough to ship as defaults, and the operations the outbox offers. The machinery they share is in
`foames/foames_adapters/mes/`, and the site records are **MES Connection**, **MES Entity Mapping**
and **MES Outbox**.

## What is built in, and what you enter

The profiles were written from the vendors' public documentation and product descriptions, but they
could not be checked against the live API references while this version was built, so they follow one
rule: **a profile ships a path only when the vendor publishes it as a stable public API, and otherwise
says where to find it.** In this version that means:

- **SAP Digital Manufacturing** ships the material, order, resource, work center and SFC reads from
  the SAP Digital Manufacturing package on the SAP Business Accelerator Hub. Check them against the
  package's OpenAPI descriptions for your release before relying on them; a mapping row overrides any
  of them.
- **Plex** ships the authentication style and headers of the Plex Connect gateway but no resource
  paths: the Developer Portal groups them by area, and you copy the one you need.
- **Tulip** ships the authentication style and instance URL pattern; everything else is a Tulip Table
  the site designed, so every type is mapped to its table.
- **The rest** ship the authentication styles they support and their notes. Their APIs are either
  published per installation (Apriso, FactoryTalk ProductionCentre, Critical Manufacturing, PAS-X,
  FactoryLogix, Proficy) or behind a customer login (AVEVA), so the paths come from your installation.

Nothing is guessed on your behalf. An unmapped reference type is refused when an External Reference
is created, which is better than resolving against a path that does not exist.

## Setup checklist

| Step | Where | Done when |
| --- | --- | --- |
| 1. Credentials for FoaMES in the style the profile names: an API key, a bot, a technical user, or an OAuth client | The MES | You have the key, token, user name or client id and secret |
| 2. Create an **MES Connection** for the adapter (one per system), fill in the Base URL, the Site if the profile uses one, the authentication, any extra headers | FoaMES | **Test Connection** says "Connected to ..." (set a **Test Path** to a small read first) |
| 3. Add **Entity Mappings** for the reference types you need, from the vendor's API reference or your installation's service documentation | FoaMES | An External Reference of each type resolves |
| 4. Tick **Enabled** | FoaMES | New references of that system resolve |
| 5. Make sure the scheduler is enabled on the site | FoaMES | `bench --site <site> scheduler status` says enabled; queued postings move to Posted |

Writes are sent by the scheduler, so nothing leaves FoaMES until step 5 is in place, and **Pause
Outbox** on the connection holds them at any time.

## Entity mappings

A mapping row says how one reference type is found:

| Field | Meaning | Example (Plex part) | Example (SAP DMC order) |
| --- | --- | --- | --- |
| Path | Relative to the Base URL; may carry `{site}`, and for a Path lookup `{<key field>}` | `mdm/v1/parts` | `order/v1/orders` |
| Lookup | **Path** `GET <path>/<id>`; **Query** `GET <path>?<key>=<value>`; **OData** `$filter=<key> eq '<value>'`; **JSON Filter** `?filter={"<key>":"<value>"}` | Query | Query |
| Key Fields | Comma-separated, in External ID order; values joined by `\|` | `number` | `order` |
| Label Field | Dotted path to the text shown | `name` | `material.description` |
| Extra Query | Fixed parameters, `name=value&name=value`; values may carry `{site}` | | `plant={site}` |

A collection answer is unwrapped whatever its envelope (a plain list, OData `value` or `d.results`,
`_embedded`, `content`, `items`, `results`, `data`, `records`), and a filtered GET that answers with
the one record is taken as is. The first record is used, so the key should identify one record.

## The outbox

Every write is an **MES Outbox** record, sent by the scheduler. Code queues one with:

```python
from foames.foames_adapters.doctype.mes_outbox.mes_outbox import enqueue

enqueue(
	"TULIP",
	"REST Request",
	{
		"method": "POST",
		"path": "api/v3/tables/<table id>/records",
		"body": {"order": "1000123", "good": 120, "scrap": 3},
		"reference_field": "foamesRef",
		"lookup_path": "api/v3/tables/<table id>/records",
		"lookup_query": "foamesRef",
	},
	idempotency_key="<the business event, for example machine and window end>",
	sequence_group="<optional group sent in order>",
)
```

Every profile has the **REST Request** operation: the payload names the method (POST, PUT, PATCH or
DELETE), the path and the body. How the posting is kept from being performed twice depends on what
the system offers, and the payload says which:

| Kind | When | What happens after an unclear answer (timeout, dropped connection, 5xx) |
| --- | --- | --- |
| **Upsert** | A PUT, or `"idempotent": true`: the system keys the record on something in the body, so sending again overwrites | The posting goes to **Retry** and is sent again |
| **Client Reference** | `reference_field`, `lookup_path` and optionally `lookup_query` are given: the body carries a field the system keeps and can be searched by | FoaMES writes a 23-character marker into that field; the next attempt searches for it first and records the existing record instead of posting again |
| **Manual** | Neither | The posting stops in **Unknown** with **Needs Check** set and no next attempt. A person looks in the system, then **Mark Posted** (with the record's id), **Requeue** (sends it again) or **Cancel Posting** |

The rest follows the S/4HANA outbox. Queuing the same idempotency key twice returns the first record.
Throttling, server errors on reads, network failures and a rejected login are retried with exponential
backoff (1, 2, 4 ... minutes, up to 6 hours) for 12 attempts. A validation error or business rejection
marks the posting **Failed** with the system's message; fix the cause, then **Requeue**, or **Cancel
Posting**. Postings of one connection that share a sequence group are sent strictly in order, and a
failed or checked-pending one holds the rest of its group. **Pause Outbox** on the connection stops
sending without stopping queuing. The **ERP Outbox Health** report shows each connection as its own
adapter.

A vendor folder can add named operations to its profile when the vendor publishes a write API with a
stable path and a client reference: an `Operation` in `profile.py` with its method, path, required
fields, idempotency kind, reference field and lookup, plus a test in `mes/test_outbox_rules.py`
against the scripted fake. Keep the invariant: a posting is checked for before it is resent after an
unclear answer, or it is not resent at all.

## System notes

The same notes are shown on each MES Connection.

### Rockwell Plex Smart Manufacturing Platform

Plex is Rockwell Automation's cloud-native SaaS platform for mid-to-large discrete manufacturers, and
the one system in this family that is also the plant's ERP. Its public REST APIs are on the Plex
Developer Portal (developers.plex.com), reached through the Plex Connect gateway with an API key in
`X-Plex-Connect-Api-Key` and the customer (PCN) in `X-Plex-Connect-Customer-Id`, which the profile
fills from the connection's Site. The portal groups the APIs by area (master data such as parts and
units, production, scheduling and jobs, inventory, quality, engineering); open the area you need and
copy the resource path and its query parameter into a mapping with the Query lookup. Older
integrations use Plex Data Sources (a stored-procedure style call with Basic authentication), reachable
with the REST Request operation.

### Rockwell FactoryTalk ProductionCentre and PharmaSuite

FactoryTalk ProductionCentre, and PharmaSuite for life sciences, is Rockwell's on-premise enterprise
MES, closely tied to Allen-Bradley and ControlLogix automation through FactoryTalk Linx. FoaMES does
not go through it to reach the controllers: machine data comes in over OPC UA, MQTT or the webhook as
on any other plant. The adapter is for the records ProductionCentre owns. Its web services and
integration framework are configured per site, so the REST endpoints and their fields are entered as
mappings from the installation's own service documentation; Rockwell's Literature Library holds the
product manuals.

### SAP Digital Manufacturing

SAP's cloud MES, usually chosen by plants already on S/4HANA or ECC that want execution, batch
tracking and multi-site transparency inside the SAP landscape. Its public REST APIs are the SAP
Digital Manufacturing package on the SAP Business Accelerator Hub (api.sap.com), one OpenAPI
description per API. A caller needs a service instance of the Digital Manufacturing APIs on SAP BTP:
its client id and secret are exchanged for a bearer token at the subaccount's XSUAA token URL, and
every call carries the plant as a query parameter, filled from the connection's Site. Orders usually
originate in S/4HANA; when both are connected, use the S/4HANA adapter for the order itself and this
one for execution data (SFCs, resources, work centers). SAP's APIs take no client reference, so a
write through REST Request stops for a person after an unclear answer.

### Dassault Systèmes DELMIA Apriso

A global multi-plant MOM suite, strongest in aerospace and automotive, integrated with ENOVIA PLM and
the 3DEXPERIENCE platform. Apriso exposes its business processes as web services through the Business
Integrator and Apriso Services, published per site, so there is no fixed public catalogue of paths.
Take the operations from the installation's service definitions and the Apriso documentation on the
Dassault Systèmes support portal (login needed).

### AVEVA Manufacturing Execution System

Formerly Wonderware MES, widely used in batch, hybrid and process industries on the AVEVA System
Platform. Its functions are reached through the MES web services and the MES Web API documented on
docs.aveva.com (an AVEVA Connect account is needed for parts of it); AVEVA Connect issues OAuth 2.0
tokens. AVEVA's utilization and OEE are computed in AVEVA, FoaMES's in FoaMES; the two are reconciled
through references, not by copying numbers either way.

### Critical Manufacturing MES

An ASMPT subsidiary serving high-tech, complex discrete and semiconductor manufacturing with a highly
configurable data model. Its REST API exposes the system's business objects and services and is
documented in the product's help portal, with a security service that issues the bearer tokens the
API wants. Because the object model is configured per customer, the resources behind materials,
resources, lots and steps differ between installations.

### Tulip

A no-code frontline operations platform and composable MES, used in regulated industries with
electronic signatures. Its API is documented on support.tulip.co: a bot (API token) created in the
instance's account settings provides a key and secret sent as Basic authentication. Tulip has no
fixed order or material model: records live in Tulip Tables the site designs, read and written
through the Tables API (`api/v3/tables/<table id>/records`), so every reference type is mapped to the
table that holds it. A record created through the API can carry a field for the FoaMES marker, which
makes a write a Client Reference posting.

### Aegis FactoryLogix

An MES built for electronics manufacturing: PCB assembly, box build and their traceability. Its
integration surface (the xTend API and web services) is documented for customers on Aegis's portal.
Machine data on an SMT line usually reaches FactoryLogix through its own equipment connectors
(IPC-CFX); FoaMES reads the same machines through its gateways and uses this adapter for the work
orders, assemblies and stations FactoryLogix owns.

### Körber Werum PAS-X MES

The dominant on-premise MES for pharmaceutical and biotech production, run in validated GxP
environments. Its interfaces (PAS-X Connect and the integration services) are documented for customers
and implemented per site under change control. Treat the adapter as read-first: resolve batches,
materials and equipment so FoaMES's machine data can be seen next to the batch record. Any write into
PAS-X touches an electronic batch record and belongs in the site's validation scope.

### Proficy Smart Factory MES (Velotic)

Built on Proficy Plant Applications, a long-standing MES in process and hybrid industries. The Proficy
software business, Kepware included, moved from GE Vernova to Velotic; its documentation lives on the
Proficy documentation portal. Plant Applications publishes REST APIs for its web client and
integrations, with tokens from its UAA service (OAuth 2.0 client credentials). Kepware is a data
source for FoaMES through OPC UA or MQTT, not through this adapter.

## Day-to-day operation

- Watch the **ERP Outbox Health** report; each MES Connection is a row group of its own, and the
  **MES Outbox** list filtered on **Needs Check** shows what waits for a person.
- A Failed posting with a system message is fixed in the system or by correcting the payload, then
  requeued. A posting that needs a check is looked up in the system first.
- **Pause Outbox** on a connection before planned maintenance on that system.
- Reference lookups that fail because a system is unreachable, or because its credentials were
  rejected, leave the External Reference Unverified rather than blocking a save.
- Rotate a key, token or secret in the system and on the connection together; a 401 or 403 is treated
  as temporary on both paths.
- Each vendor licenses API use in its own way (named integrations, call quotas, Digital Access style
  document counting); check the contract before turning on writes.
