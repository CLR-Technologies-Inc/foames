# Tulip

Tulip is reached through the shared MES and MOM adapter framework: one **MES Connection** per system, its **MES Entity Mappings** and the **MES Outbox**. How the framework works (what is built in and what you enter, the setup checklist, entity mappings, the outbox and day-to-day operation) is in [../../mes-adapters.md](../../mes-adapters.md). This page holds only what is particular to Tulip.

| Adapter key | Code | Connection style the profile knows |
| --- | --- | --- |
| `TULIP` | `foames/foames_adapters/tulip/` (its `profile.py`, `api.py`, `reads.py` and `AGENTS.md`) | Basic with a service account's key and secret, instance URL `<instance>.tulip.co`, the Tables, Machines and Stations APIs; read-only by default |

## What the profile ships

The profile ships the authentication style and instance URL pattern; everything else is a Tulip Table the site designed, so every type is mapped to its table. A write to a table with a client reference, so it is never performed twice, is a REST Request with `path` and `lookup_path` set to `api/v3/tables/<table id>/records` and `reference_field` and `lookup_query` set to a field such as `foamesRef`.

## Reading Tulip

FoaMES reads Tulip through its public API ([Work with APIs](https://support.tulip.co/docs/work-with-apis), the [Table API guide](https://support.tulip.co/docs/table-api-guide) and the apidocs pages it links). Set up the MES Connection named `TULIP` with:

- **Base URL** `https://<instance>.tulip.co`;
- **Authentication** Basic, with the service account's API key as user name and its secret as password (Settings, Tulip API, Create Service Account; the secret is shown once);
- **Site** the workspace id when the instance uses workspaces and the service account is a global one (paths then carry `w/<workspace>/`); leave it empty otherwise.

Give the service account **read scopes only** while the connector is read-only: `tables:read` (and `table-queries:read` if you use table queries), `machines:read`, `stations:read`.

| Read | Tulip endpoint | Method (also an MCP tool) |
| --- | --- | --- |
| Tables and their columns | `GET api/v3[/w/<ws>]/tables` (limit up to 100, offset) | `list_tables` / `foames_tulip_list_tables` |
| Records of a table | `GET api/v3[/w/<ws>]/tables/<table id>/records` with `filters` (a JSON list of `{"field", "functionType", "arg"}`), `filterAggregator`, `fields`, `sortOptions`, `limit` up to 100, `offset` | `list_table_records` / `foames_tulip_list_table_records` |
| Count of matching records | `GET .../tables/<table id>/count` | `count_table_records` / `foames_tulip_count_table_records` |
| One record | `GET .../tables/<table id>/records/<record id>` | `get_table_record` / `foames_tulip_get_table_record` |
| Machines and machine types | `GET api/v3[/w/<ws>]/machines` | `list_machines` / `foames_tulip_list_machines` |
| Stations | `GET api/stations/v1[/w/<ws>]/stations` (search, sort, archived, station group filter) | `list_stations` / `foames_tulip_list_stations` |

The methods are `foames.foames_adapters.tulip.reads.<method>`; they need read permission on MES Connection. Entity mappings on the MES Connection (for example Work Order to the table that holds orders, lookup *Query* or *JSON Filter* on the table's id field) still drive External Reference resolution as for every MES.

The `/w/<workspace>/` form for the machines and stations paths follows the Table API guide; Tulip's apidocs list those endpoints without the prefix. Check your instance's own reference at `https://<instance>.tulip.co/apidocs` if a call answers 404.

## Writing to Tulip, read-only first

The connector starts **read-only** (see [read-only mode](../../read-only-mode.md)): its Connector Write Policy, `TULIP`, is created read-only the first time a write is queued. Writes are MES Outbox postings through the REST Request operation, for example a table record:

```json
{"method": "POST", "path": "api/v3/w/<ws>/tables/<table id>/records",
 "body": {"id": "WO-1001-OP10", "status": "Released"},
 "reference_field": "foamesRef", "lookup_path": "api/v3/w/<ws>/tables/<table id>/records"}
```

or machine attribute values (`POST .../attributes/report` with `{"attributes": [{"machineId", "attributeId", "value"}]}`, scope `attributes:report`; Tulip applies none of them if one fails validation). While read-only, each posting waits as a Pending Write until an authorised person signs it off, and it is logged against its work order in the Write Audit Log. When the plant's change control approves Tulip writes, add the write scopes (`tables:write`, `attributes:report`) to the service account and turn Read-only off on the `TULIP` policy with the change control reference.

Tulip's own GxP features (electronic signature widgets, record history) cover what operators do in Tulip apps; FoaMES's sign-off covers what FoaMES writes to Tulip.

## Notes

A no-code frontline operations platform and composable MES, used in regulated industries with
electronic signatures. Its API is documented on support.tulip.co: a bot (API token) created in the
instance's account settings provides a key and secret sent as Basic authentication. Tulip has no
fixed order or material model: records live in Tulip Tables the site designs, read and written
through the Tables API (`api/v3/tables/<table id>/records`), so every reference type is mapped to the
table that holds it. A record created through the API can carry a field for the FoaMES marker, which
makes a write a Client Reference posting.
