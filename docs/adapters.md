# ERP adapters and External References

FoaMES keeps no Link fields to ERP DocTypes. When a FoaMES record needs to point at something in an ERP, it points at an **External Reference**, and the ERP's adapter turns that reference into a real record. This page explains External References, how to run with no ERP, and how to write an adapter for another ERP. It is vendor-neutral: how a particular ERP is connected, configured and posted to is in that vendor's folder under [vendors/](vendors/README.md).

## External Reference

An External Reference is a triple:

| Field | Meaning |
| --- | --- |
| **ERP System** | The key of a registered adapter. `get_available_erp_systems` lists the keys on a site. Defaults to **Default ERP System** in FoaMES Settings. |
| **Reference Type** | One of the kernel's reference types (below). |
| **External ID** | The record's identifier in that ERP, in whatever form the adapter documents (a document name, a key, a composite id). Each vendor guide under [vendors/](vendors/README.md) says what its adapter expects. |

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
- Adapters record the references of the records they receive or create; each vendor guide says which.
- Other apps built on FoaMES link to External Reference in the same way instead of linking to ERP DocTypes directly.

### Creating references from code

```python
from foames.foames_kernel.doctype.external_reference.external_reference import get_reference

# Name of the External Reference for Item "FG-100" in the default ERP, created if it does not exist.
name = get_reference("Item", "FG-100")

# The same for an explicit ERP.
name = get_reference("Work Order", "WO-00012", erp_system="<adapter key>")
```

`get_reference` is safe under concurrency: if two workers create the same reference at once, both get the same record. Only System Managers may create External References through the desk; code that has done its own permission check can pass `ignore_permissions=True`.

For pickers in a UI, `foames.foames_adapters.get_available_erp_systems` returns every registered adapter with its key, label and whether its ERP is reachable from the site.

## Running without an ERP

Leave **Default ERP System** empty. Machines, events, downtime, OEE, the Floor View and suggestions work without any reference. An External Reference cannot be saved without an ERP System, because there is nothing to resolve it against, so simply do not create any. When an ERP arrives later, set the default and start adding references; nothing else changes.

## Writing an adapter for another ERP

An adapter is a Python class that another Frappe app registers through the `foames_erp_adapters` hook. The adapters FoaMES ships are registered the same way and are described under [vendors/](vendors/README.md); `get_available_erp_systems` lists what a site has.

```python
# myapp/adapters/acme_erp.py
import frappe

from foames.foames_adapters.base import ERPAdapter, ResolvedReference


class AcmeERPAdapter(ERPAdapter):
	key = "AcmeERP"  # stored on External Reference.erp_system
	label = "Acme ERP"  # shown to users
	reference_map = {  # kernel reference type -> the ERP's own record type
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

- `key`, `label` and `reference_map` are class attributes. `reference_map` may also be a property when the mapping depends on settings, as an adapter that reads its connection from settings does.
- `is_available()` says whether the ERP can be reached now. The core calls it before every lookup and treats `False` as "leave the reference Unverified", never as an error.
- `fetch(erp_type, reference_type, external_id)` returns a `ResolvedReference` or `None`. Raise `foames.foames_adapters.base.AdapterUnavailable` for a transient failure (timeout, authentication problem) so the save still goes through, and `AdapterError` for a real failure that should be shown to the user.
- `resolve(reference_type, external_id)` is implemented on the base class and is what the core calls. It checks support and availability, then calls `fetch`. Do not override it.
- Adapters are instantiated on every lookup, so keep the constructor cheap and cache connections elsewhere (for example in `frappe.cache` or a module-level client).

Once registered, the adapter appears in `get_available_erp_systems`, its key is accepted in **ERP System** and **Default ERP System**, and External References of its supported types resolve through it. Nothing in the core needs to change.

Keep two rules when you write one:

1. Resolve by reading. Writing to the ERP belongs in explicit, idempotent postings, through an outbox with an idempotency key, a marker in the created document, a check before a resend and strict order within a sequence group (see `foames/foames_adapters/AGENTS.md`), not inside `fetch`.
2. Store credentials in Password fields of a Settings DocType, never in code or site config.
