# Authorization and record scope

FoaMES uses Frappe's roles and User Permissions for every read and write, and adds a few rules of its own where an aggregate read, a Dynamic Link or a policy change would otherwise say or allow more than the reader's grant. This page states the access matrix, what each read surface returns, and which authorities are kept apart.

Report a suspected access-control weakness privately, as [SECURITY.md](../SECURITY.md) describes, not in a public issue.

## Restricting a person or an agent to an area

Give the user (an agent is a user with an API key) **User Permissions on Machine** for the machines of their site, line or area. Frappe then filters every DocType that links to Machine. FoaMES extends that to:

- **Agent Suggestion**, which names its machine through a Dynamic Link (`reference_doctype`, `reference_name`). A restricted reader lists and opens only the suggestions about their machines, or about no machine (`foames.foames_kernel.access`, registered as `has_permission` and `permission_query_conditions`).
- **Aggregates**: the floor snapshot, the qualification status and the reports are built from several DocTypes. Read on behalf of a user, they hold only that user's machines, and only the sections of DocTypes the user may read.

A User Permission limited to other DocTypes ("Applicable For") does not restrict suggestions.

## Read surfaces

| Surface | Scope |
| --- | --- |
| `get_floor_snapshot` (Floor View, the API, the MCP tool `foames_get_floor_snapshot`) | The reader's machines. Counts need read on Machine Event, OEE on OEE Period, downtime on Downtime Record, the ERP job on External Reference (without it, the snapshot says only that a job is set). Suggestions, Andon Calls, Work Instruction Runs, recognitions and every section an extension adds are scrubbed of other machines (`record_scope.scrub`). `snapshot["scope"]` names the reader and their machines. |
| `list_active_runs` (Work Instruction Runs) | The runs the reader may read, through `frappe.get_list`, before any step detail is loaded; a named machine outside their area is refused like a missing one. |
| The MCP read tools (`foames.foames_mcp.reads`) | `frappe.get_list` for every list. A single record is read through `access.require_read`, which raises the same error for a record that does not exist and one the reader may not read, so an error never confirms that a record outside the reader's area exists. |
| `get_qualification_status`, the Qualification Status report | Only protocols and executions the reader may read, and no row for a machine outside their area. |
| `get_material_status`, `get_material_readiness`, `get_dispatch_list` | The reader's bins and queues; a named machine or queue outside their area is refused like a missing one. Readiness keeps the machine's verdict: a short bin the reader cannot see still makes `ok` false. |
| Downtime Pareto, MTBF and MTTR, OEE Trend, Suggestion Status reports | `frappe.get_list`: the reader's role and User Permissions apply to the rows and so to every total. |
| `run_suggestion_rules` | The rules see the whole floor, as the scheduler's do; the caller gets back only the suggestions they may read. |

**Nothing is cached across readers.** The snapshot and the status are built on every call. A new cache must be keyed by user, or hold only data every reader may see.

**System reads.** The scheduler's rules, the write gate, the outboxes and the event processing read with `frappe.get_all` (no permission filter) on purpose: they act for the site, not for a person, and what they produce (a suggestion, a Pending Write, an audit row) is itself filtered when someone reads it. Do not pass their results to a user unfiltered; call `floor_snapshot(for_user=True)` or filter with `foames.foames_kernel.record_scope`.

## Access matrix

| Role | Reads | Writes and authority |
| --- | --- | --- |
| FoaMES Operator | Floor, machines, suggestions, Pending Writes, validation status, within User Permissions | Operational records (Andon Calls, work instruction runs); requests writes, which wait at the gate |
| FoaMES Engineer | As Operator, plus configuration, Connector Write Policies, the Write Audit Log | Configuration records; may **tighten** a Connector Write Policy |
| FoaMES Supervisor | As Engineer | Signs Pending Writes (the default sign-off role); may not sign their own request |
| FoaMES Quality | As Engineer, validation records | Approves validation executions; may tighten a policy |
| FoaMES Integration | Connector and audit reads | The identity a connector or bridge runs as; its writes wait at the gate |
| FoaMES Policy Administrator | Connector Write Policies | The only FoaMES role that may **weaken** a policy: turn read-only off, move "when read-only" to a less strict choice, change the sign-off role, create a policy that writes or that overrides the site's action or sign-off role, or delete a read-only one |
| System Manager | Everything | FoaMES Settings (the site's read-only switch); may weaken policies |
| Agent (an API user) | What its roles and User Permissions allow | Its writes go through the MCP gate; a model's benchmark or capability claim never adds a permission |

Three authorities stay apart: **policy administration** (FoaMES Policy Administrator, System Manager), **sign-off** (the policy's sign-off role, never the requester) and **execution** (the gate, after sign-off). Give the Policy Administrator role to people who neither request nor sign the writes it governs.

The gate itself still creates a connector's first policy exactly as FoaMES Settings say, whoever triggers it; tightening and the approval reference rule from [read-only mode](read-only-mode.md) are unchanged.

## Testing

`foames/foames_kernel/test_authorization.py` builds two mutually isolated areas with one reader each and checks every surface above in both directions, plus the policy authority rules. The pure rules are tested in `test_record_scope.py`. A new read surface needs a positive and a negative cross-area case there.
