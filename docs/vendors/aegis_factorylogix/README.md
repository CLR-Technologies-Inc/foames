# Aegis FactoryLogix

Aegis FactoryLogix is reached through the shared MES and MOM adapter framework: one **MES Connection** per system, its **MES Entity Mappings** and the **MES Outbox**. How the framework works (what is built in and what you enter, the setup checklist, entity mappings, the outbox and day-to-day operation) is in [../../mes-adapters.md](../../mes-adapters.md). This page holds only what is particular to Aegis FactoryLogix.

| Adapter key | Code | Connection style the profile knows |
| --- | --- | --- |
| `FACTORYLOGIX` | `foames/foames_adapters/aegis_factorylogix/` (its `profile.py` and `AGENTS.md`) | Basic, bearer token or OAuth 2.0 against the xTend API |

## What the profile ships

The profile ships the authentication styles it supports and its notes. Its API is published per installation, so the paths come from your installation.

## Notes

An MES built for electronics manufacturing: PCB assembly, box build and their traceability. Its
integration surface (the xTend API and web services) is documented for customers on Aegis's portal.
Machine data on an SMT line usually reaches FactoryLogix through its own equipment connectors
(IPC-CFX); FoaMES reads the same machines through its gateways and uses this adapter for the work
orders, assemblies and stations FactoryLogix owns.
