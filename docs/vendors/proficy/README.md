# Proficy Smart Factory MES (Velotic)

Proficy Smart Factory MES (Velotic, formerly GE Vernova) is reached through the shared MES and MOM adapter framework: one **MES Connection** per system, its **MES Entity Mappings** and the **MES Outbox**. How the framework works (what is built in and what you enter, the setup checklist, entity mappings, the outbox and day-to-day operation) is in [../../mes-adapters.md](../../mes-adapters.md). This page holds only what is particular to Proficy Smart Factory MES (Velotic, formerly GE Vernova).

| Adapter key | Code | Connection style the profile knows |
| --- | --- | --- |
| `PROFICY` | `foames/foames_adapters/proficy/` (its `profile.py` and `AGENTS.md`) | OAuth 2.0 client credentials at the UAA token URL, or Basic |

## What the profile ships

The profile ships the authentication styles it supports and its notes. Its API is published per installation, so the paths come from your installation.

## Notes

Built on Proficy Plant Applications, a long-standing MES in process and hybrid industries. The Proficy
software business, Kepware included, moved from GE Vernova to Velotic; its documentation lives on the
Proficy documentation portal. Plant Applications publishes REST APIs for its web client and
integrations, with tokens from its UAA service (OAuth 2.0 client credentials). Kepware is a data
source for FoaMES through OPC UA or MQTT, not through this adapter.
