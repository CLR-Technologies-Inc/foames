# AGENTS.md: Körber Werum PAS-X MES

Read this when you work in `foames/foames_adapters/koerber_pasx/`. This system is a profile on the shared MES and MOM framework: the framework's rules are in [../mes/AGENTS.md](../mes/AGENTS.md), the rules for every adapter in [../AGENTS.md](../AGENTS.md), and the project-wide rules in the root [AGENTS.md](../../../AGENTS.md). The human guide is [docs/vendors/koerber_pasx/](../../../docs/vendors/koerber_pasx/README.md).

## What it is

Werum PAS-X MES for pharma and biotech, from Körber (Werum IT Solutions). Registered under the key `PASX` (`adapter.py`, class `KoerberPASXAdapter`, a `ProfileAdapter`); the site configures it with one **MES Connection** for that key. The vendor's public API documentation: https://www.koerber-pharma.com/en/solutions/software

## What `profile.py` holds

- Authentication styles: Basic, Bearer Token.
- Base URL pattern: `https://pasx.example.com`.
- Outbox operations: REST Request.

It ships **no** entity paths, so every reference type is mapped by the site on its MES Connection; the human guide says where the vendor documents them. Do not add a default path unless the vendor publishes it as a stable public API, and cite where.

The profile's `notes` are shown on the MES Connection form and repeated in the human guide; keep the two in step when you change either.

## Rules specific to this system

- Everything in this folder is written from Körber (Werum IT Solutions)'s public documentation and product descriptions. Do not add Körber (Werum IT Solutions) code, SDKs, API metadata or payloads copied from material behind a customer login.
- Anything this system needs that the framework lacks is added to the framework as a general field and set here (see [../mes/AGENTS.md](../mes/AGENTS.md)), not special-cased in `mes/`.

## Tests

`foames/foames_adapters/mes/test_profiles.py` checks every registered profile (this one is in its `ADAPTERS`) against the framework with `mes/fake.py`; there is no vendor system in the tests.
