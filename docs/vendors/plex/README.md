# Rockwell Plex Smart Manufacturing Platform

Rockwell Plex Smart Manufacturing Platform is reached through the shared MES and MOM adapter framework: one **MES Connection** per system, its **MES Entity Mappings** and the **MES Outbox**. How the framework works (what is built in and what you enter, the setup checklist, entity mappings, the outbox and day-to-day operation) is in [../../mes-adapters.md](../../mes-adapters.md). This page holds only what is particular to Rockwell Plex Smart Manufacturing Platform.

| Adapter key | Code | Connection style the profile knows |
| --- | --- | --- |
| `PLEX` | `foames/foames_adapters/plex/` (its `profile.py` and `AGENTS.md`) | API key header `X-Plex-Connect-Api-Key`, customer id (PCN) header, gateway `connect.plex.com` |

## What the profile ships

The profile ships the authentication style and headers of the Plex Connect gateway but no resource paths: the Developer Portal groups them by area, and you copy the one you need. Example mapping for a part: Path `mdm/v1/parts`, Lookup Query, Key Fields `number`, Label Field `name`.

## Notes

Plex is Rockwell Automation's cloud-native SaaS platform for mid-to-large discrete manufacturers, and
the one system in this family that is also the plant's ERP. Its public REST APIs are on the Plex
Developer Portal (developers.plex.com), reached through the Plex Connect gateway with an API key in
`X-Plex-Connect-Api-Key` and the customer (PCN) in `X-Plex-Connect-Customer-Id`, which the profile
fills from the connection's Site. The portal groups the APIs by area (master data such as parts and
units, production, scheduling and jobs, inventory, quality, engineering); open the area you need and
copy the resource path and its query parameter into a mapping with the Query lookup. Older
integrations use Plex Data Sources (a stored-procedure style call with Basic authentication), reachable
with the REST Request operation.
