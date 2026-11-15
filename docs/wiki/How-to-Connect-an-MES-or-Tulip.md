**Goal:** let FoaMES refer to records that another MES, MOM or frontline platform owns, and queue writes to it that are never performed twice.

**Systems with a profile today (all alpha):** Tulip, Rockwell Plex, Rockwell FactoryTalk ProductionCentre and PharmaSuite, SAP Digital Manufacturing, DELMIA Apriso, AVEVA MES, Critical Manufacturing MES, Aegis FactoryLogix, Körber Werum PAS-X and Proficy Smart Factory. Siemens Insights Hub has its own adapter; see [docs/vendors/insights_hub](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/vendors/insights_hub/README.md).

**You need:** credentials for FoaMES in the style the profile names (an API key, a bot, a technical user or an OAuth client), the vendor's API reference for your installation, and System Manager.

A profile ships only paths the vendor publishes as a stable public API. Anything else you enter yourself, and FoaMES refuses an unmapped reference type rather than guess.

## Steps

1. **Create credentials in the other system.** For Tulip, create an API bot in the instance's account settings; it gives a key and secret used as Basic authentication.
2. **Create an MES Connection** and pick its **Adapter** (for Tulip, `TULIP`). Fill in **Base URL** (for Tulip, `https://<instance>.tulip.co`), **Site / Plant / Tenant** if the profile uses one, and the authentication. Set a **Test Path** to a small read and press **Test Connection** until it says *Connected to ...*.
3. **Add Entity Mappings** for the reference types you need. Each row has a **Path**, a **Lookup** style (Path, Query, OData or JSON Filter), **Key Fields** and a **Label Field**. Tulip has no fixed order or material model: map each type to the Tulip Table that holds it, at `api/v3/tables/<table id>/records`.
4. **Tick Enabled.**
5. **Make sure the scheduler is enabled**, because writes are sent by it.

## Writing safely

Every write is an **MES Outbox** posting. To make a write safe to retry, give the target a field FoaMES can search, such as `foamesRef` in a Tulip Table; FoaMES writes a marker into it and checks for it before any resend. A write with no such field and no upsert stops in **Unknown** with **Needs Check** after an unclear answer, for a person to look and then **Mark Posted**, **Requeue** or **Cancel Posting**.

Use **Pause Outbox** on the connection before planned maintenance on the other system, and check each vendor's API licensing before you turn writes on.

## Check

- An External Reference of each mapped type resolves with a label.
- The **ERP Outbox Health** report shows each MES Connection as its own adapter.

The framework is described in [docs/mes-adapters.md](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/mes-adapters.md); each system's page is under [docs/vendors/](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/vendors/README.md).
