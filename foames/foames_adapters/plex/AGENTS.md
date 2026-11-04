# AGENTS.md: Rockwell Plex Smart Manufacturing Platform

Read this when you work in `foames/foames_adapters/plex/`. This system is a profile on the shared MES and MOM framework: the framework's rules are in [../mes/AGENTS.md](../mes/AGENTS.md), the rules for every adapter in [../AGENTS.md](../AGENTS.md), and the project-wide rules in the root [AGENTS.md](../../../AGENTS.md). The human guide is [docs/vendors/plex/](../../../docs/vendors/plex/README.md).

## What it is

Plex Smart Manufacturing Platform (cloud MES and ERP), from Rockwell Automation. Registered under the key `PLEX` (`adapter.py`, class `PlexAdapter`, a `ProfileAdapter`); the site configures it with one **MES Connection** for that key. The vendor's public API documentation: https://developers.plex.com/

## What `profile.py` holds

- Authentication styles: API Key Header, Basic.
- API key header: `X-Plex-Connect-Api-Key`.
- Fixed headers: `X-Plex-Connect-Customer-Id: {site}` (`{site}` is the connection's Site).
- Base URL pattern: `https://connect.plex.com`.
- The connection's Site is labelled **Plex Customer ID (PCN)**.
- Outbox operations: REST Request.

It ships **no** entity paths, so every reference type is mapped by the site on its MES Connection; the human guide says where the vendor documents them. Do not add a default path unless the vendor publishes it as a stable public API, and cite where.

The profile's `notes` are shown on the MES Connection form and repeated in the human guide; keep the two in step when you change either.

## Rules specific to this system

- Everything in this folder is written from Rockwell Automation's public documentation and product descriptions. Do not add Rockwell Automation code, SDKs, API metadata or payloads copied from material behind a customer login.
- Anything this system needs that the framework lacks is added to the framework as a general field and set here (see [../mes/AGENTS.md](../mes/AGENTS.md)), not special-cased in `mes/`.

## Tests

`foames/foames_adapters/mes/test_profiles.py` checks every registered profile (this one is in its `ADAPTERS`) against the framework with `mes/fake.py`; there is no vendor system in the tests.
