# AGENTS.md: Tulip

Read this when you work in `foames/foames_adapters/tulip/`. This system is a profile on the shared MES and MOM framework: the framework's rules are in [../mes/AGENTS.md](../mes/AGENTS.md), the rules for every adapter in [../AGENTS.md](../AGENTS.md), and the project-wide rules in the root [AGENTS.md](../../../AGENTS.md). The human guide is [docs/vendors/tulip/](../../../docs/vendors/tulip/README.md).

## What it is

Tulip frontline operations platform (composable MES), from Tulip Interfaces. Registered under the key `TULIP` (`adapter.py`, class `TulipAdapter`, a `ProfileAdapter`); the site configures it with one **MES Connection** for that key. The vendor's public API documentation: https://support.tulip.co/docs/api-overview

## Package map

| Module | Holds | Pure |
| --- | --- | --- |
| `__init__.py` | `ADAPTER_KEY` | yes |
| `adapter.py` | `TulipAdapter`, a `ProfileAdapter` over the profile | no (framework) |
| `profile.py` | The profile: authentication, URL pattern, notes | yes |
| `api.py` | Tulip's read API: table, record, count, machine and station paths, the records query (`filters`, `filterAggregator`, `fields`, `sortOptions`, limit 1..100), the stations query, answer flattening | yes |
| `reads.py` | Whitelisted reads over the site's TULIP MES Connection (`list_tables`, `list_table_records`, `count_table_records`, `get_table_record`, `list_machines`, `list_stations`) and their MCP tools (`mcp_tools`, registered with the `foames_mcp_tools` hook) | no |
| `test_api.py` | Unit tests of `api.py` and the reads against `mes/fake.py` | |

## Read-only by default

The Tulip connector's key in the write gate is `TULIP` (the MES Connection's name). Like every new connector it starts read-only: writes to Tulip are MES Outbox postings (REST Request) and wait for an operator's electronic sign-off until the plant approves them on its Connector Write Policy (see [docs/read-only-mode.md](../../../docs/read-only-mode.md)). The reads in `reads.py` never write and need no sign-off. Do not add a Tulip write that bypasses the MES Outbox; if one cannot be an outbox posting, register it in `foames_write_actions` and request it through `write_gate.request_write`.

## What `profile.py` holds

- Authentication styles: Basic.
- Base URL pattern: `https://<instance>.tulip.co`.
- Outbox operations: REST Request.
- Site: the Tulip workspace id, used as `w/<workspace>/` in the read paths.

It ships **no** entity paths, so every reference type is mapped by the site on its MES Connection; the human guide says where the vendor documents them. Do not add a default path unless the vendor publishes it as a stable public API, and cite where.

The profile's `notes` are shown on the MES Connection form and repeated in the human guide; keep the two in step when you change either.

## Rules specific to this system

- Everything in this folder is written from Tulip Interfaces's public documentation and product descriptions. Do not add Tulip Interfaces code, SDKs, API metadata or payloads copied from material behind a customer login.
- Anything this system needs that the framework lacks is added to the framework as a general field and set here (see [../mes/AGENTS.md](../mes/AGENTS.md)), not special-cased in `mes/`.

## Tests

`foames/foames_adapters/mes/test_profiles.py` checks every registered profile (this one is in its `ADAPTERS`) against the framework with `mes/fake.py`; `test_api.py` checks the read paths and queries. There is no vendor system in the tests.
