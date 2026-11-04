# Dassault Systèmes DELMIA Apriso

Dassault Systèmes DELMIA Apriso is reached through the shared MES and MOM adapter framework: one **MES Connection** per system, its **MES Entity Mappings** and the **MES Outbox**. How the framework works (what is built in and what you enter, the setup checklist, entity mappings, the outbox and day-to-day operation) is in [../../mes-adapters.md](../../mes-adapters.md). This page holds only what is particular to Dassault Systèmes DELMIA Apriso.

| Adapter key | Code | Connection style the profile knows |
| --- | --- | --- |
| `APRISO` | `foames/foames_adapters/delmia_apriso/` (its `profile.py` and `AGENTS.md`) | Basic, bearer token or OAuth 2.0 against the site's published Apriso services |

## What the profile ships

The profile ships the authentication styles it supports and its notes. Its API is published per installation, so the paths come from your installation.

## Notes

A global multi-plant MOM suite, strongest in aerospace and automotive, integrated with ENOVIA PLM and
the 3DEXPERIENCE platform. Apriso exposes its business processes as web services through the Business
Integrator and Apriso Services, published per site, so there is no fixed public catalogue of paths.
Take the operations from the installation's service definitions and the Apriso documentation on the
Dassault Systèmes support portal (login needed).
