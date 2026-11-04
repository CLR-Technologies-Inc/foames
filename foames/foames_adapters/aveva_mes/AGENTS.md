# AGENTS.md: AVEVA Manufacturing Execution System

Read this when you work in `foames/foames_adapters/aveva_mes/`. This system is a profile on the shared MES and MOM framework: the framework's rules are in [../mes/AGENTS.md](../mes/AGENTS.md), the rules for every adapter in [../AGENTS.md](../AGENTS.md), and the project-wide rules in the root [AGENTS.md](../../../AGENTS.md). The human guide is [docs/vendors/aveva_mes/](../../../docs/vendors/aveva_mes/README.md).

## What it is

AVEVA Manufacturing Execution System (formerly Wonderware MES), from AVEVA. Registered under the key `AVEVA_MES` (`adapter.py`, class `AvevaMESAdapter`, a `ProfileAdapter`); the site configures it with one **MES Connection** for that key. The vendor's public API documentation: https://docs.aveva.com/

## What `profile.py` holds

- Authentication styles: Basic, Bearer Token, OAuth 2.0 Client Credentials.
- Base URL pattern: `https://mes.example.com`.
- Outbox operations: REST Request.

It ships **no** entity paths, so every reference type is mapped by the site on its MES Connection; the human guide says where the vendor documents them. Do not add a default path unless the vendor publishes it as a stable public API, and cite where.

The profile's `notes` are shown on the MES Connection form and repeated in the human guide; keep the two in step when you change either.

## Rules specific to this system

- Everything in this folder is written from AVEVA's public documentation and product descriptions. Do not add AVEVA code, SDKs, API metadata or payloads copied from material behind a customer login.
- Anything this system needs that the framework lacks is added to the framework as a general field and set here (see [../mes/AGENTS.md](../mes/AGENTS.md)), not special-cased in `mes/`.

## Tests

`foames/foames_adapters/mes/test_profiles.py` checks every registered profile (this one is in its `ADAPTERS`) against the framework with `mes/fake.py`; there is no vendor system in the tests.
