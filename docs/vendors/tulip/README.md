# Tulip

Tulip is reached through the shared MES and MOM adapter framework: one **MES Connection** per system, its **MES Entity Mappings** and the **MES Outbox**. How the framework works (what is built in and what you enter, the setup checklist, entity mappings, the outbox and day-to-day operation) is in [../../mes-adapters.md](../../mes-adapters.md). This page holds only what is particular to Tulip.

| Adapter key | Code | Connection style the profile knows |
| --- | --- | --- |
| `TULIP` | `foames/foames_adapters/tulip/` (its `profile.py` and `AGENTS.md`) | Basic with an API bot's key and secret, instance URL `<instance>.tulip.co`, Tables API |

## What the profile ships

The profile ships the authentication style and instance URL pattern; everything else is a Tulip Table the site designed, so every type is mapped to its table. A write to a table with a client reference, so it is never performed twice, is a REST Request with `path` and `lookup_path` set to `api/v3/tables/<table id>/records` and `reference_field` and `lookup_query` set to a field such as `foamesRef`.

## Notes

A no-code frontline operations platform and composable MES, used in regulated industries with
electronic signatures. Its API is documented on support.tulip.co: a bot (API token) created in the
instance's account settings provides a key and secret sent as Basic authentication. Tulip has no
fixed order or material model: records live in Tulip Tables the site designs, read and written
through the Tables API (`api/v3/tables/<table id>/records`), so every reference type is mapped to the
table that holds it. A record created through the API can carry a field for the FoaMES marker, which
makes a write a Client Reference posting.
