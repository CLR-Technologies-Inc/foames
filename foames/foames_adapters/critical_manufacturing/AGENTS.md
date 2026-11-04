# AGENTS.md: Critical Manufacturing MES

Read this when you work in `foames/foames_adapters/critical_manufacturing/`. This system is a profile on the shared MES and MOM framework: the framework's rules are in [../mes/AGENTS.md](../mes/AGENTS.md), the rules for every adapter in [../AGENTS.md](../AGENTS.md), and the project-wide rules in the root [AGENTS.md](../../../AGENTS.md). The human guide is [docs/vendors/critical_manufacturing/](../../../docs/vendors/critical_manufacturing/README.md).

## What it is

Critical Manufacturing MES, from Critical Manufacturing (an ASMPT company). Registered under the key `CMF_MES` (`adapter.py`, class `CriticalManufacturingAdapter`, a `ProfileAdapter`); the site configures it with one **MES Connection** for that key. The vendor's public API documentation: https://help.criticalmanufacturing.com/

## What `profile.py` holds

- Authentication styles: Bearer Token, Basic.
- Base URL pattern: `https://mes.example.com/api`.
- Outbox operations: REST Request.

It ships **no** entity paths, so every reference type is mapped by the site on its MES Connection; the human guide says where the vendor documents them. Do not add a default path unless the vendor publishes it as a stable public API, and cite where.

The profile's `notes` are shown on the MES Connection form and repeated in the human guide; keep the two in step when you change either.

## Rules specific to this system

- Everything in this folder is written from Critical Manufacturing (an ASMPT company)'s public documentation and product descriptions. Do not add Critical Manufacturing (an ASMPT company) code, SDKs, API metadata or payloads copied from material behind a customer login.
- Anything this system needs that the framework lacks is added to the framework as a general field and set here (see [../mes/AGENTS.md](../mes/AGENTS.md)), not special-cased in `mes/`.

## Tests

`foames/foames_adapters/mes/test_profiles.py` checks every registered profile (this one is in its `ADAPTERS`) against the framework with `mes/fake.py`; there is no vendor system in the tests.
