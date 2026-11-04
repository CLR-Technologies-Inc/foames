# SAP Digital Manufacturing

SAP Digital Manufacturing is reached through the shared MES and MOM adapter framework: one **MES Connection** per system, its **MES Entity Mappings** and the **MES Outbox**. How the framework works (what is built in and what you enter, the setup checklist, entity mappings, the outbox and day-to-day operation) is in [../../mes-adapters.md](../../mes-adapters.md). This page holds only what is particular to SAP Digital Manufacturing.

| Adapter key | Code | Connection style the profile knows |
| --- | --- | --- |
| `SAP_DMC` | `foames/foames_adapters/sap_dmc/` (its `profile.py` and `AGENTS.md`) | OAuth 2.0 client credentials (XSUAA), plant as a query parameter; material, order, resource, work center and SFC reads ship as defaults |

## What the profile ships

The profile ships the material, order, resource, work center and SFC reads from the SAP Digital Manufacturing package on the SAP Business Accelerator Hub. Check them against the package's OpenAPI descriptions for your release before relying on them; a mapping row overrides any of them. Example mapping for an order: Path `order/v1/orders`, Lookup Query, Key Fields `order`, Label Field `material.description`, Extra Query `plant={site}`.

## Notes

SAP's cloud MES, usually chosen by plants already on S/4HANA or ECC that want execution, batch
tracking and multi-site transparency inside the SAP landscape. Its public REST APIs are the SAP
Digital Manufacturing package on the SAP Business Accelerator Hub (api.sap.com), one OpenAPI
description per API. A caller needs a service instance of the Digital Manufacturing APIs on SAP BTP:
its client id and secret are exchanged for a bearer token at the subaccount's XSUAA token URL, and
every call carries the plant as a query parameter, filled from the connection's Site. Orders usually
originate in S/4HANA; when both are connected, use the S/4HANA adapter for the order itself and this
one for execution data (SFCs, resources, work centers). SAP's APIs take no client reference, so a
write through REST Request stops for a person after an unclear answer.
