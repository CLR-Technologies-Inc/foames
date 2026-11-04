# Vendor guides

Everything specific to one vendor's product lives here, one folder per vendor. The pages in the parent folder describe FoaMES itself and stay vendor-neutral (External References and writing an adapter are in [../adapters.md](../adapters.md)); these pages say how FoaMES connects to a particular ERP, SCADA or other system. The matching guidance for coding agents sits next to each adapter's code, in `foames/foames_adapters/<vendor>/AGENTS.md`. Each folder starts with a `README.md` that is the vendor's landing page and links to the rest.

| Vendor | Kind | Start here | What it covers |
| --- | --- | --- | --- |
| SAP S/4HANA | ERP | [s4hana/](s4hana/README.md) | OData resolution, the posting outbox, inbound IDocs, day-to-day operation; [setup.md](s4hana/setup.md) for users, communication arrangements and OAuth; [postings.md](s4hana/postings.md) for confirmations, goods movements and cancellations |
| ERPNext | ERP | [erpnext/](erpnext/README.md) | Setup, reads, the ERPNext Outbox, roll-ups to Job Cards, following Job Cards, Workstation status and downtime, Quality Inspections |
| Siemens Insights Hub (Opcenter Intelligence) | Industrial data platform | [insights_hub/](insights_hub/README.md) | Assets as references, machine production as time series, state changes as events, the outbox, setup on both sides |
| Rockwell Plex Smart Manufacturing Platform | MES / MOM, on the [shared REST framework](../mes-adapters.md) | [plex/](plex/README.md) | Key, connection style, what the profile ships, system notes |
| Rockwell FactoryTalk ProductionCentre and PharmaSuite | MES / MOM, on the [shared REST framework](../mes-adapters.md) | [factorytalk_productioncentre/](factorytalk_productioncentre/README.md) | Key, connection style, what the profile ships, system notes |
| SAP Digital Manufacturing | MES / MOM, on the [shared REST framework](../mes-adapters.md) | [sap_dmc/](sap_dmc/README.md) | Key, connection style, what the profile ships, system notes |
| Dassault Systèmes DELMIA Apriso | MES / MOM, on the [shared REST framework](../mes-adapters.md) | [delmia_apriso/](delmia_apriso/README.md) | Key, connection style, what the profile ships, system notes |
| AVEVA Manufacturing Execution System | MES / MOM, on the [shared REST framework](../mes-adapters.md) | [aveva_mes/](aveva_mes/README.md) | Key, connection style, what the profile ships, system notes |
| Critical Manufacturing MES | MES / MOM, on the [shared REST framework](../mes-adapters.md) | [critical_manufacturing/](critical_manufacturing/README.md) | Key, connection style, what the profile ships, system notes |
| Tulip | MES / MOM, on the [shared REST framework](../mes-adapters.md) | [tulip/](tulip/README.md) | Key, connection style, what the profile ships, system notes |
| Aegis FactoryLogix | MES / MOM, on the [shared REST framework](../mes-adapters.md) | [aegis_factorylogix/](aegis_factorylogix/README.md) | Key, connection style, what the profile ships, system notes |
| Körber Werum PAS-X MES | MES / MOM, on the [shared REST framework](../mes-adapters.md) | [koerber_pasx/](koerber_pasx/README.md) | Key, connection style, what the profile ships, system notes |
| Proficy Smart Factory MES (Velotic) | MES / MOM, on the [shared REST framework](../mes-adapters.md) | [proficy/](proficy/README.md) | Key, connection style, what the profile ships, system notes |
| Ignition | SCADA | [ignition/](ignition/README.md) | Connecting an Ignition gateway through Sparkplug B, OPC UA or a gateway script |

A vendor's folder here has the same name as its package under `foames/foames_adapters/`, so the guide and the code are found the same way. A vendor with no adapter package (a SCADA product that connects through a gateway) has a folder here only.

## Adding a vendor

1. Create `docs/vendors/<vendor>/`, named like the adapter's package, with a `README.md` as the landing page. Split setup, operation and reference into further pages in the same folder once the landing page grows past what one reader wants to scroll.
2. Keep vendor-neutral material (the event shape, counter rules, the adapter contract, a framework several vendors share) in the parent `docs/` folder and link to it with a relative path such as `../../machine-data.md`. Put the agent-facing rules in the adapter's own `AGENTS.md`.
3. Add a row to the table above. Nothing else in `docs/`, `README.md` or the root `AGENTS.md` needs to change.
