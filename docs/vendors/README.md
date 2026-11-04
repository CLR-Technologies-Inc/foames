# Vendor guides

Everything specific to one vendor's product lives here, one folder per vendor. The pages in the parent folder describe FoaMES itself and stay vendor-neutral; these pages say how FoaMES connects to a particular ERP, SCADA or other system. Each folder starts with a `README.md` that is the vendor's landing page and links to the rest.

| Vendor | Kind | Start here | What it covers |
| --- | --- | --- | --- |
| SAP S/4HANA | ERP | [s4hana/](s4hana/README.md) | OData resolution, the posting outbox, inbound IDocs, day-to-day operation; [setup.md](s4hana/setup.md) for users, communication arrangements and OAuth; [postings.md](s4hana/postings.md) for confirmations, goods movements and cancellations |
| ERPNext | ERP | [erpnext/](erpnext/README.md) | External References, the ERPNext adapter and its outbox, running without an ERP, and writing an adapter for another ERP |
| Ignition | SCADA | [ignition/](ignition/README.md) | Connecting an Ignition gateway through Sparkplug B, OPC UA or a gateway script |

## Adding a vendor

1. Create `docs/vendors/<vendor>/` with a `README.md` as the landing page. Split setup, operation and reference into further pages in the same folder once the landing page grows past what one reader wants to scroll.
2. Keep vendor-neutral material (the event shape, counter rules, the adapter contract) in the parent `docs/` folder and link to it with a relative path such as `../../machine-data.md`.
3. Add a row to the table above and to the vendor section of [../README.md](../README.md).
