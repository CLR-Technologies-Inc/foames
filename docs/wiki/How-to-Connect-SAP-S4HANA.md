**Goal:** connect FoaMES to an SAP S/4HANA system (on-premise or private cloud) to resolve references, post confirmations and goods movements, and receive IDocs.

**You need:** an S/4HANA basis or integration contact who can create a communication user and communication arrangements, System Manager in FoaMES, and the scheduler running.

> **Licensing.** Documents FoaMES creates in S/4HANA, such as material documents, may count against the customer's SAP Digital Access entitlement. Check the SAP contract before you turn postings on.

The adapter uses released OData V2 APIs and IDoc XML over HTTP only. It needs no RFC SDK, and no SAP code is in the repository.

## In S/4HANA

1. Create a communication user, or an OAuth 2.0 client, for FoaMES.
2. Create communication arrangements (or activate the services in `/IWFND/MAINT_SERVICE` on older releases) for the services you use:

   | Service | For |
   | --- | --- |
   | `API_PRODUCT_SRV` | Item references |
   | `API_BATCH_SRV` | Batch references |
   | `API_PRODUCTION_ORDER_2_SRV` | Work Order references |
   | `API_MATERIAL_DOCUMENT_SRV` | Goods movements |
   | `API_PROD_ORDER_CONFIRMATION_2_SRV` | Production order confirmations (SAP_COM_0104) |
   | `API_PROC_ORDER_CONFIRMATION_2_SRV` | Process order confirmations |

3. For inbound IDocs, create an RFC destination of type G (SM59) pointing at `https://<foames-site>/api/method/foames.foames_adapters.s4hana.api.receive_idoc`, using the API key and secret of a FoaMES user with the **FoaMES Integration** role. Add an XML HTTP port (WE21) and the message types you want to the partner profile (WE20).

## In FoaMES

1. Open **S4HANA Settings**. Fill in **Base URL**, **SAP Client**, **Language**, the authentication method and its credentials, and **CA Bundle Path** if S/4HANA uses a private CA.
2. Press **Test Connection** until it says *Connected to ...*.
3. Compare each service's `$metadata` on your release with the defaults, and add **Entity Mappings** for anything that differs or is not shipped (Unit of Measure, Operation, Location, Serial Number). Composite keys go into External ID joined by `|`, for example `MATERIAL|BATCH`.
4. Tick **Enabled**. If S/4HANA is your main ERP, set **Default ERP System** to `S4HANA` in FoaMES Settings.
5. Optional: tick **Roll Up Machine Counts to Confirmations**, set the confirmation unit, and give machines an order operation as **Current Job Reference** (External ID `ORDER|OPERATION`, for example `1000123|0010`).

## Check

- An External Reference of each type you need resolves with a label.
- A test IDoc appears as an **S4HANA Inbound IDoc** with status Processed.
- Queued postings in the **S4HANA Outbox** move to Posted. **Pause Outbox** in S4HANA Settings holds them at any time.

Full detail, including outbox statuses and cancellations, is in [docs/vendors/s4hana](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/vendors/s4hana/README.md), [setup.md](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/vendors/s4hana/setup.md) and [postings.md](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/vendors/s4hana/postings.md).
