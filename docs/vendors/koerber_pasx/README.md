# Körber Werum PAS-X MES

Körber Werum PAS-X MES is reached through the shared MES and MOM adapter framework: one **MES Connection** per system, its **MES Entity Mappings** and the **MES Outbox**. How the framework works (what is built in and what you enter, the setup checklist, entity mappings, the outbox and day-to-day operation) is in [../../mes-adapters.md](../../mes-adapters.md). This page holds only what is particular to Körber Werum PAS-X MES.

| Adapter key | Code | Connection style the profile knows |
| --- | --- | --- |
| `PASX` | `foames/foames_adapters/koerber_pasx/` (its `profile.py` and `AGENTS.md`) | Basic or bearer token against the site's PAS-X interfaces; read-first under GxP |

## What the profile ships

The profile ships the authentication styles it supports and its notes. Its API is published per installation, so the paths come from your installation.

## Notes

The dominant on-premise MES for pharmaceutical and biotech production, run in validated GxP
environments. Its interfaces (PAS-X Connect and the integration services) are documented for customers
and implemented per site under change control. Treat the adapter as read-first: resolve batches,
materials and equipment so FoaMES's machine data can be seen next to the batch record. Any write into
PAS-X touches an electronic batch record and belongs in the site's validation scope.
