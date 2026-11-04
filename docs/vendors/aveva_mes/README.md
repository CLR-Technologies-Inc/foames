# AVEVA Manufacturing Execution System

AVEVA Manufacturing Execution System (formerly Wonderware MES) is reached through the shared MES and MOM adapter framework: one **MES Connection** per system, its **MES Entity Mappings** and the **MES Outbox**. How the framework works (what is built in and what you enter, the setup checklist, entity mappings, the outbox and day-to-day operation) is in [../../mes-adapters.md](../../mes-adapters.md). This page holds only what is particular to AVEVA Manufacturing Execution System (formerly Wonderware MES).

| Adapter key | Code | Connection style the profile knows |
| --- | --- | --- |
| `AVEVA_MES` | `foames/foames_adapters/aveva_mes/` (its `profile.py` and `AGENTS.md`) | Basic, bearer token or OAuth 2.0 (AVEVA Connect) against the MES web API |

## What the profile ships

The profile ships the authentication styles it supports and its notes. The API is documented behind a customer login, so the paths come from your installation.

## Notes

Formerly Wonderware MES, widely used in batch, hybrid and process industries on the AVEVA System
Platform. Its functions are reached through the MES web services and the MES Web API documented on
docs.aveva.com (an AVEVA Connect account is needed for parts of it); AVEVA Connect issues OAuth 2.0
tokens. AVEVA's utilization and OEE are computed in AVEVA, FoaMES's in FoaMES; the two are reconciled
through references, not by copying numbers either way.
