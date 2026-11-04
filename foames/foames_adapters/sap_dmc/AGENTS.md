# AGENTS.md: SAP Digital Manufacturing

Read this when you work in `foames/foames_adapters/sap_dmc/`. This system is a profile on the shared MES and MOM framework: the framework's rules are in [../mes/AGENTS.md](../mes/AGENTS.md), the rules for every adapter in [../AGENTS.md](../AGENTS.md), and the project-wide rules in the root [AGENTS.md](../../../AGENTS.md). The human guide is [docs/vendors/sap_dmc/](../../../docs/vendors/sap_dmc/README.md).

## What it is

SAP Digital Manufacturing (DMC, formerly Digital Manufacturing Cloud for execution), from SAP. Registered under the key `SAP_DMC` (`adapter.py`, class `SAPDigitalManufacturingAdapter`, a `ProfileAdapter`); the site configures it with one **MES Connection** for that key. The vendor's public API documentation: https://api.sap.com/package/SAPDigitalManufacturingCloud/rest

## What `profile.py` holds

- Authentication styles: OAuth 2.0 Client Credentials.
- Base URL pattern: `https://api.<region>.dmc.cloud.sap`.
- OAuth token URL pattern: `https://<subdomain>.authentication.<region>.hana.ondemand.com/oauth/token`.
- The connection's Site is labelled **Plant**.
- Outbox operations: REST Request.

It ships these entity defaults, because the vendor publishes them as a stable public API; check them against the vendor's reference for the installed release, and remember a mapping row on the MES Connection overrides any of them:

| Reference type | Path | Lookup |
| --- | --- | --- |
| Item | `material/v1/materials` | Query |
| Work Order | `order/v1/orders` | Query |
| Workstation | `resource/v1/resources` | Query |
| Location | `workcenter/v1/workcenters` | Query |
| Job Card | `sfc/v1/sfcdetail` | Query |

The profile's `notes` are shown on the MES Connection form and repeated in the human guide; keep the two in step when you change either.

## Rules specific to this system

- Everything in this folder is written from SAP's public documentation and product descriptions. Do not add SAP code, SDKs, API metadata or payloads copied from material behind a customer login.
- Anything this system needs that the framework lacks is added to the framework as a general field and set here (see [../mes/AGENTS.md](../mes/AGENTS.md)), not special-cased in `mes/`.

## Tests

`foames/foames_adapters/mes/test_profiles.py` checks every registered profile (this one is in its `ADAPTERS`) against the framework with `mes/fake.py`; there is no vendor system in the tests.
