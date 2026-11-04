# Critical Manufacturing MES

Critical Manufacturing MES is reached through the shared MES and MOM adapter framework: one **MES Connection** per system, its **MES Entity Mappings** and the **MES Outbox**. How the framework works (what is built in and what you enter, the setup checklist, entity mappings, the outbox and day-to-day operation) is in [../../mes-adapters.md](../../mes-adapters.md). This page holds only what is particular to Critical Manufacturing MES.

| Adapter key | Code | Connection style the profile knows |
| --- | --- | --- |
| `CMF_MES` | `foames/foames_adapters/critical_manufacturing/` (its `profile.py` and `AGENTS.md`) | Bearer token from its security service, or Basic |

## What the profile ships

The profile ships the authentication styles it supports and its notes. Its API is published per installation, so the paths come from your installation.

## Notes

An ASMPT subsidiary serving high-tech, complex discrete and semiconductor manufacturing with a highly
configurable data model. Its REST API exposes the system's business objects and services and is
documented in the product's help portal, with a security service that issues the bearer tokens the
API wants. Because the object model is configured per customer, the resources behind materials,
resources, lots and steps differ between installations.
