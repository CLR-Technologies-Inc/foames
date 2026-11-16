FoaMES started as an answer to a request for machine monitoring, OEE and plant-floor visibility in ERPNext ([frappe/erpnext#50827](https://github.com/frappe/erpnext/issues/50827)). The obvious design would have been an ERPNext app with Link fields to Work Order, Job Card and Workstation. FoaMES deliberately does not do that.

## The problem with linking

A Link field is a hard dependency. If a Machine linked to an ERPNext Workstation, the Machine DocType could not exist on a site without ERPNext, and every plant on another ERP would need a fork. Plants change ERPs, run two at once during a migration, or run an enterprise MES alongside a lightweight one. A floor system that is welded to one ERP has to be rebuilt each time.

There is a second problem. The shop floor and the ERP disagree about time. A machine reports every few seconds; an ERP is updated when someone books a confirmation. A floor system that writes into ERP records synchronously, inside the same transaction as a machine event, makes the floor as slow and as fragile as the ERP.

## What FoaMES does instead

The core depends on the Frappe framework only. When a FoaMES record needs to point at something in an ERP, it points at an **External Reference**: a triple of ERP system, reference type and external ID. The ERP's **adapter** turns that triple into a real record when asked, and reports whether the ERP can be reached at all.

This has consequences you can rely on:

- **FoaMES runs without an ERP.** Machines, events, downtime, OEE, the Floor View, suggestions, SPC, maintenance, SOPs and process mining all work with **Default ERP System** empty. When an ERP arrives, you set the default and start adding references; nothing else changes.
- **An ERP outage does not stop the floor.** A reference to an unreachable ERP stays *Unverified* and the save goes through. It is resolved later, by hand or by the daily refresh.
- **Missing records are visible.** A reference that resolves as *Missing* shows up in the floor snapshot and raises a suggestion, rather than failing silently.
- **One record, one reference.** The reference key is a hash of the triple, so the same ERP record is referenced once per site.
- **More systems without core changes.** Adapters register through the `foames_erp_adapters` hook, so ERPNext, SAP S/4HANA, Siemens Insights Hub and eleven MES platforms all plug into the same contract, and another app can add its own.

## Reads and writes are different

Adapters resolve references by **reading**. Anything that changes another system goes through an outbox, sent later by the scheduler, with an idempotency key and a check before any resend ([The outbox and safe writes](Explanation-The-outbox-and-safe-writes)). This keeps the floor fast, makes writes auditable, and lets you pause or inspect them at any time.

## The cost

The indirection costs something. You do not get Frappe's link autocomplete to ERP records in FoaMES forms, and an adapter has to be written for each system. The project accepts that cost because the alternative, a fork per ERP, costs far more over the life of a plant.

Even ERPNext, on the same site, is reached through an adapter. FoaMES imports nothing from ERPNext at module load, and CI runs the suite with and without it.
