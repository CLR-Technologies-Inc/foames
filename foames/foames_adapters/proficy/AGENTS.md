# AGENTS.md: Proficy Smart Factory MES (Velotic)

Read this when you work in `foames/foames_adapters/proficy/`. This system is a profile on the shared MES and MOM framework: the framework's rules are in [../mes/AGENTS.md](../mes/AGENTS.md), the rules for every adapter in [../AGENTS.md](../AGENTS.md), and the project-wide rules in the root [AGENTS.md](../../../AGENTS.md). The human guide is [docs/vendors/proficy/](../../../docs/vendors/proficy/README.md).

## What it is

Proficy Smart Factory MES (Proficy Plant Applications) with Kepware, from Velotic (formerly GE Vernova Proficy). Registered under the key `PROFICY` (`adapter.py`, class `ProficyAdapter`, a `ProfileAdapter`); the site configures it with one **MES Connection** for that key. The vendor's public API documentation: https://www.ge.com/digital/documentation/

## What `profile.py` holds

- Authentication styles: OAuth 2.0 Client Credentials, Basic.
- Base URL pattern: `https://plantapps.example.com`.
- OAuth token URL pattern: `https://<host>/uaa/oauth/token`.
- Outbox operations: REST Request.

It ships **no** entity paths, so every reference type is mapped by the site on its MES Connection; the human guide says where the vendor documents them. Do not add a default path unless the vendor publishes it as a stable public API, and cite where.

The profile's `notes` are shown on the MES Connection form and repeated in the human guide; keep the two in step when you change either.

## Rules specific to this system

- Everything in this folder is written from Velotic (formerly GE Vernova Proficy)'s public documentation and product descriptions. Do not add Velotic (formerly GE Vernova Proficy) code, SDKs, API metadata or payloads copied from material behind a customer login.
- Anything this system needs that the framework lacks is added to the framework as a general field and set here (see [../mes/AGENTS.md](../mes/AGENTS.md)), not special-cased in `mes/`.

## Tests

`foames/foames_adapters/mes/test_profiles.py` checks every registered profile (this one is in its `ADAPTERS`) against the framework with `mes/fake.py`; there is no vendor system in the tests.
