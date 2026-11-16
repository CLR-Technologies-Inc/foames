**Goal:** connect FoaMES to an ERP or system it does not support yet, from your own Frappe app, without changing FoaMES.

**You need:** a Frappe app of your own that lists `foames` in `required_apps`, and the target system's published API.

## 1. Write the adapter class

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
		return bool(frappe.db.get_single_value("Acme ERP Settings", "enabled"))

	def fetch(self, erp_type, reference_type, external_id):
		record = acme_client().get(erp_type, external_id)
		if not record:
			return None
		return ResolvedReference(reference_type=reference_type, external_id=record["id"],
			label=record["description"], data={"type": erp_type})
```

## 2. Register it

```python
# myapp/hooks.py
foames_erp_adapters = ["myapp.adapters.acme_erp.AcmeERPAdapter"]
```

After `bench migrate`, the key appears in `get_available_erp_systems` and in **Default ERP System**, and External References of the mapped types resolve through it.

## 3. Keep the rules

- `is_available()` returning False leaves references Unverified; it is never an error.
- Raise `AdapterUnavailable` for a transient failure (timeout, login problem) so saves still go through, and `AdapterError` for a real failure to show the user.
- Do not override `resolve`; the base class implements it.
- **Resolve by reading.** Writes belong in an outbox with an idempotency key and a check before any resend, never inside `fetch`. See [The outbox and safe writes](Explanation-The-outbox-and-safe-writes).
- Keep credentials in Password fields of a Settings DocType, never in code or site config.
- Talk only to the vendor's published interfaces. Do not add proprietary code, API metadata or SDKs.

If the system is an MES or MOM platform with a REST API, a profile on the shared framework may be less work; see [docs/mes-adapters.md](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/mes-adapters.md). The full contract is in [docs/adapters.md](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/adapters.md) and `foames/foames_adapters/AGENTS.md`.
