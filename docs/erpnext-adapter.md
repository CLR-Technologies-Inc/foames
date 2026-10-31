# ERP adapters and the ERPNext adapter

FoaMES keeps no Link fields to ERP DocTypes. When a FoaMES record needs to point at something in an ERP, it points at an **External Reference**, and the ERP's adapter turns that reference into a real record. This page explains External References, how the built-in ERPNext adapter works, how to run with no ERP, and how to write an adapter for another ERP. The SAP S/4HANA adapter has its own page: [s4hana-adapter.md](s4hana-adapter.md).

## External Reference

An External Reference is a triple:

| Field | Meaning |
| --- | --- |
| **ERP System** | The key of a registered adapter: `ERPNext`, `S4HANA`, or the key of an adapter another app registers. Defaults to **Default ERP System** in FoaMES Settings. |
| **Reference Type** | One of the kernel's reference types (below). |
| **External ID** | The record's identifier in that ERP. For ERPNext this is the document name, for example the Item code or the Work Order name. |

The kernel reference types are Item, Unit of Measure, Batch, Serial Number, Work Order, Operation, Location, Stock Movement, Job Card, Bill of Materials, Routing and Workstation. An adapter declares which of them it supports; saving a reference of an unsupported type for that ERP is refused.

Each reference also carries:

- **Status**: `Unverified` until it has been looked up, then `Resolved` when the record exists in the ERP or `Missing` when it does not.
- **Label**: the human-readable name the adapter returned (the Item name, the warehouse name, and so on).
- **Last Resolved On**: when the lookup last ran.
- **Reference Key**: a hash of the triple that makes the reference unique. The same ERP record is referenced exactly once per site, and a second attempt to create it is rejected as a duplicate.

### When references are resolved

By default a reference is looked up in its ERP every time it is saved, as long as the adapter reports that its ERP is available. If the ERP is reachable but the record is not there, the status becomes `Missing`. If a remote ERP is down, saving still succeeds and the reference stays `Unverified` to be resolved later.

Two controls change this:

- **Skip Resolving References on Save** in FoaMES Settings turns the automatic lookup off. References are then resolved only through the **Resolve** button on the form, or by code calling the document's `resolve` method.
- Changing the ERP System, Reference Type or External ID of an existing reference clears its resolution, so a corrected reference is never shown as Resolved on the strength of its old value.

References that resolve as `Missing` show up in the floor snapshot and trigger the built-in ERP rule, which raises one Agent Suggestion listing them (see [floor-view.md](floor-view.md)).

### Where references are used

- A **Machine** can carry an **ERP Workstation Reference** and an **ERP Location Reference**. The first must be a Workstation reference and the second a Location reference; the form refuses anything else.
- The S/4HANA adapter records a reference for every order, material or batch IDoc it receives, and for every material document its outbox creates.
- Other apps built on FoaMES link to External Reference in the same way instead of linking to ERP DocTypes directly.

### Creating references from code

```python
from foames.foames_kernel.doctype.external_reference.external_reference import get_reference

# Name of the External Reference for Item "FG-100" in the default ERP, created if it does not exist.
name = get_reference("Item", "FG-100")

# The same for an explicit ERP.
name = get_reference("Work Order", "MFG-WO-2026-00012", erp_system="ERPNext")
```

`get_reference` is safe under concurrency: if two workers create the same reference at once, both get the same record. Only System Managers may create External References through the desk; code that has done its own permission check can pass `ignore_permissions=True`.

For pickers in a UI, `foames.foames_adapters.get_available_erp_systems` returns every registered adapter with its key, label and whether its ERP is reachable from the site.

## The ERPNext adapter

The ERPNext adapter is built in and needs no configuration. It is registered under the key `ERPNext` and reports itself available when the `erpnext` app is installed on the same site. Set **Default ERP System** in FoaMES Settings to `ERPNext` so new references use it without being told.

Resolution is a direct read of ERPNext's tables, so it is fast and needs no credentials. The adapter maps each kernel reference type to an ERPNext DocType and takes the label from one of its fields:

| Reference type | ERPNext DocType | Label |
| --- | --- | --- |
| Item | Item | Item Name |
| Unit of Measure | UOM | UOM Name |
| Batch | Batch | Batch ID |
| Serial Number | Serial No | Serial No |
| Work Order | Work Order | Production Item |
| Operation | Operation | Description |
| Location | Warehouse | Warehouse Name |
| Stock Movement | Stock Entry | Stock Entry Type |
| Job Card | Job Card | Operation |
| Bill of Materials | BOM | Item |
| Routing | Routing | Routing Name |
| Workstation | Workstation | Workstation Name |

The External ID is the ERPNext document name in every case (`FG-100`, `MFG-WO-2026-00012`, `Stores - ACME`, `BOM-FG-100-001`).

What the ERPNext adapter does not do: it does not write to ERPNext, and it does not import anything from the ERPNext code base. FoaMES installs and passes its tests on a plain Frappe site, and CI runs the suite both with and without ERPNext to keep it that way. Postings into ERPNext (stock entries, job card time logs) are the job of an app that builds on FoaMES, using ERPNext's own APIs.

### Typical setup with ERPNext

1. Install ERPNext and FoaMES on the same site.
2. In FoaMES Settings, set Default ERP System to `ERPNext`.
3. For each Machine, create an External Reference of type Workstation whose External ID is the ERPNext Workstation name, and select it in the Machine's ERP Workstation Reference. Do the same with a Location reference for the warehouse the machine feeds, if you track that.
4. Save; each reference resolves at once and shows the ERPNext label.

If ERPNext is installed later, existing references stay `Unverified` until they are saved again or resolved from the form.

## Running without an ERP

Leave **Default ERP System** empty. Machines, events, downtime, OEE, the Floor View and suggestions work without any reference. An External Reference cannot be saved without an ERP System, because there is nothing to resolve it against, so simply do not create any. When an ERP arrives later, set the default and start adding references; nothing else changes.

## Writing an adapter for another ERP

An adapter is a Python class that another Frappe app registers through the `foames_erp_adapters` hook. FoaMES ships two: `foames.foames_adapters.erpnext.ERPNextAdapter` and `foames.foames_adapters.s4hana.adapter.S4HANAAdapter`.

```python
# myapp/adapters/acme_erp.py
import frappe

from foames.foames_adapters.base import ERPAdapter, ResolvedReference


class AcmeERPAdapter(ERPAdapter):
	key = "AcmeERP"          # stored on External Reference.erp_system
	label = "Acme ERP"       # shown to users
	reference_map = {        # kernel reference type -> the ERP's own record type
		"Item": "material",
		"Work Order": "production_order",
		"Location": "storage_location",
	}

	def is_available(self) -> bool:
		# True when the ERP can be reached from this site: a setting is filled in, a connection works.
		return bool(frappe.db.get_single_value("Acme ERP Settings", "enabled"))

	def fetch(self, erp_type: str, reference_type: str, external_id: str) -> ResolvedReference | None:
		# erp_type is reference_map[reference_type]. Return None when the record does not exist.
		record = acme_client().get(erp_type, external_id)
		if not record:
			return None
		return ResolvedReference(
			reference_type=reference_type,
			external_id=record["id"],
			label=record["description"],
			data={"type": erp_type},
		)
```

```python
# myapp/hooks.py
foames_erp_adapters = ["myapp.adapters.acme_erp.AcmeERPAdapter"]
```

The contract, from `foames/foames_adapters/base.py`:

- `key`, `label` and `reference_map` are class attributes. `reference_map` may also be a property when the mapping depends on settings, as the S/4HANA adapter does.
- `is_available()` says whether the ERP can be reached now. The core calls it before every lookup and treats `False` as "leave the reference Unverified", never as an error.
- `fetch(erp_type, reference_type, external_id)` returns a `ResolvedReference` or `None`. Raise `foames.foames_adapters.base.AdapterUnavailable` for a transient failure (timeout, authentication problem) so the save still goes through, and `AdapterError` for a real failure that should be shown to the user.
- `resolve(reference_type, external_id)` is implemented on the base class and is what the core calls. It checks support and availability, then calls `fetch`. Do not override it.
- Adapters are instantiated on every lookup, so keep the constructor cheap and cache connections elsewhere (for example in `frappe.cache` or a module-level client).

Once registered, the adapter appears in `get_available_erp_systems`, its key is accepted in **ERP System** and **Default ERP System**, and External References of its supported types resolve through it. Nothing in the core needs to change.

Keep two rules when you write one:

1. Resolve by reading. Writing to the ERP belongs in explicit, idempotent postings, as the S/4HANA outbox does, not inside `fetch`.
2. Store credentials in Password fields of a Settings DocType, never in code or site config.
