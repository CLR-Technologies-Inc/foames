# Rockwell FactoryTalk ProductionCentre and PharmaSuite

Rockwell FactoryTalk ProductionCentre and PharmaSuite is reached through the shared MES and MOM adapter framework: one **MES Connection** per system, its **MES Entity Mappings** and the **MES Outbox**. How the framework works (what is built in and what you enter, the setup checklist, entity mappings, the outbox and day-to-day operation) is in [../../mes-adapters.md](../../mes-adapters.md). This page holds only what is particular to Rockwell FactoryTalk ProductionCentre and PharmaSuite.

| Adapter key | Code | Connection style the profile knows |
| --- | --- | --- |
| `FTPC` | `foames/foames_adapters/factorytalk_productioncentre/` (its `profile.py` and `AGENTS.md`) | Basic, bearer token or OAuth 2.0 against the site's web services |

## What the profile ships

The profile ships the authentication styles it supports and its notes. Its API is published per installation, so the paths come from your installation.

## Notes

FactoryTalk ProductionCentre, and PharmaSuite for life sciences, is Rockwell's on-premise enterprise
MES, closely tied to Allen-Bradley and ControlLogix automation through FactoryTalk Linx. FoaMES does
not go through it to reach the controllers: machine data comes in over OPC UA, MQTT or the webhook as
on any other plant. The adapter is for the records ProductionCentre owns. Its web services and
integration framework are configured per site, so the REST endpoints and their fields are entered as
mappings from the installation's own service documentation; Rockwell's Literature Library holds the
product manuals.
