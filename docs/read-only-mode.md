# Read-only mode (RO mode)

Read-only mode lets a plant connect FoaMES to its ERP, other MES and MOM systems, SCADA and historians **reading only**, and approve each write path when it is ready. While a connector is read-only, nothing it would write leaves FoaMES on its own: each write waits as a **Pending Write** until an authorised person signs it off with an electronic signature, or it is refused. Every step (requested, held, signed, rejected, released, executed, refused, and every change to the mode itself) is recorded in the append-only, hash-chained **Write Audit Log**, against the work order, Job Card, process run and machine the write belongs to.

It is on by default: a new site starts with site-wide read-only mode on, and every connector the site has not approved yet starts read-only.

> **Credit.** Shipping connectors read-only first, with any write going through an operator sign-off logged against the work order so that regulated plants can approve the connector rollout, was suggested by **Ramakrishna Gampa**. Thank you.

## What it covers

| Write | Where the gate sits | While read-only |
| --- | --- | --- |
| Postings to an ERP or another MES through an adapter outbox (ERPNext, S/4HANA, Insights Hub, every MES Connection including Tulip) | The outbox's `claim`, just before it sends, and the moment a posting is queued | Held for sign-off, or cancelled and logged if the connector blocks |
| Writes an agent makes through the MCP server (`foames_set_current_job`, and any writing tool another app adds) | `foames_mcp.api.execute_tool` | The agent gets the Pending Write's name instead of a result; nothing is written until it is signed |
| Agent Suggestions raised through MCP (`foames_post_suggestion`, `foames_run_suggestion_rules`) | The same | Run by default, because a suggestion only asks a person to act; **Hold Agent Suggestions Too** in FoaMES Settings holds them as well |
| Any other write to another system (a SCADA tag or setpoint, a historian write, a write a bridge makes) | `write_gate.request_write`, for actions registered in the `foames_write_actions` hook | Held for sign-off, or refused |

What it does **not** gate, because it is the read side of a read-only connector: machine data coming in (the signed webhook, MQTT, OPC UA, Sparkplug B from Ignition, the Bluesky and historian bridges), which FoaMES records as observations; and changes people make on the desk or in the ERP themselves, which are covered by the ERP's and Frappe's own permissions and version history.

FoaMES already never writes tags, sends commands to SCADA or changes machine state on its own (see the root `AGENTS.md`, invariant 5). Read-only mode makes the remaining write paths, the configured ones, wait for a person too.

## Settings

**FoaMES Settings**, section *Read-only Mode*:

| Field | Default (new site) | Meaning |
| --- | --- | --- |
| Site-wide Read-only Mode | On | Every connector is read-only, whatever its own policy says. The switch for the whole site |
| When Read-only | Queue for sign-off | What happens to a held write: *Queue for sign-off* or *Block* (refuse and log) |
| New Connectors Start Read-only | On | A connector the gate sees for the first time gets a read-only Connector Write Policy |
| Sign-off Role | FoaMES Supervisor | The role a signer needs; a connector's policy can name another (for example FoaMES Quality) |
| Signer Must Differ from Requester | On | The person or API user who asked for a write cannot sign it off |
| Hold Agent Suggestions Too | Off | Also hold the MCP tools that only raise suggestions |

**Connector Write Policy**, one per connector, created automatically the first time a connector writes. Its name is the connector's key: the adapter key (`ERPNext`, `S4HANA`, `INSIGHTS_HUB`), the MES Connection's name (`TULIP`, `PLEX`, ...), `mcp` for the MCP server, or the key an app passes to `request_write`.

| Field | Meaning |
| --- | --- |
| Read-only | Checked: this connector's writes are held or refused |
| When Read-only | *Site default*, *Queue for sign-off* or *Block* |
| Sign-off Role | Overrides the site's sign-off role for this connector |
| Approval Reference | The change control or validation record that approved the connector's mode. Required to turn read-only off |
| Notes | Free text |

A connector is read-write only when site-wide read-only mode is off **and** its own policy is not read-only. Each change to the settings or to a policy is written to the Write Audit Log with who, when and what changed.

**Upgrading an existing site** changes nothing on the day: the upgrade leaves site-wide read-only mode off and gives every connector that has already written (it has rows in an outbox, or it is the MCP server) a read-write policy whose Approval Reference says so. Connectors set up after the upgrade start read-only. Turn site-wide read-only mode on, or check Read-only on a policy, whenever you want writes to wait.

Turning a connector read-write does not release writes it already holds: sign them off or reject them. That keeps the record of every write requested under read-only mode complete.

## Signing a write off

Pending Writes are listed under **Pending Write** (filter *Awaiting Sign-off*). The form shows what will be written (the payload), the connector, who asked and when, and what it is logged against. **Sign Off** asks for:

- the **meaning** of the signature: *Approved* or *Rejected*;
- a **reason**;
- the signer's **password**, re-entered.

On approval an outbox posting is released and goes with the outbox's next run, in its place in its sequence group; an MCP tool call or registered action runs at once, as the user who asked for it, and its result or error is stored on the Pending Write. On rejection an outbox posting is cancelled with the signer's name and reason as its error, which also lets the rest of its sequence group move on.

A signature is refused, and the failed attempt is logged, when the password does not match, the signer lacks the sign-off role, the signer asked for the write themselves (unless the site allows it), there is no reason, the write is no longer waiting, or the payload has changed since it was held. A posting held in an outbox is checked against its outbox row again at signing and again just before it is sent; if either changed, the signature does not apply.

## The Write Audit Log

One entry per event, never edited or deleted (the DocType refuses both, and no role may create entries from the desk or the REST API). Each entry records the event, the time, the user and their full name, the connector and action, the Pending Write, the record it concerns (the outbox row or the machine), the **work order, Job Card, process run and machine**, a reason and details. The gate finds the work order and the others in the payload (keys such as `work_order`, `job_card`, `process_run`, `machine` and their usual spellings in each system) or, for an outbox posting, from its sequence group; a caller of `request_write` passes them itself.

Each entry carries the SHA-256 hash of its own content chained to the previous entry's hash. **Verify Chain** on the list (System Manager, FoaMES Quality), or `verify_audit_trail()`, recomputes the whole chain and lists any entry that does not match. A Pending Write's **Verify Seal** recomputes its payload hash and its signature hash.

To read the trail for one order: the Write Audit Log list filtered by Work Order or Job Card, `foames.foames_kernel.write_gate.get_write_audit_trail(work_order=...)`, or the MCP tool `foames_get_write_audit_trail`.

## The approval path for a regulated plant

Read-only mode is built so that a plant under 21 CFR Part 11, EU GMP Annex 11 or a similar regime can bring connectors in one step at a time. It is a set of controls, not a validation: the site validates FoaMES for its intended use as it would any computerised system. A typical path:

1. **Install read-only.** A new site starts with site-wide read-only mode on. Connect the ERP, MES, SCADA and historian connectors; they read from the first day, and anything they would write waits.
2. **Qualify reading.** Run the connectors read-only through installation and operational qualification: machine data, OEE, downtime, references and suggestions, with no write leaving the site. The pending writes that accumulate show exactly what each connector would send.
3. **Sign writes one at a time.** Turn site-wide read-only mode off but keep each connector's policy read-only, so every write is held per connector. Authorised people (the sign-off role, separate from the requester) review each Pending Write and sign it with meaning, reason and password. This is the period in which a write path is proven with real postings, each signed and logged against its order.
4. **Release a connector.** When the plant's change control approves a connector's writes, uncheck Read-only on its policy and enter the change control reference in Approval Reference. The change is logged; the connector's postings then flow without sign-off, still idempotent and sequenced, and still recorded in its outbox.
5. **Keep the switch.** Site-wide read-only mode stays available as a single switch (for an upgrade, an investigation or a validation hold), and Block refuses writes outright where even a queue is not wanted.

How the controls map to Part 11 (a guide for the site's own assessment, not a claim of compliance):

| Requirement | What FoaMES provides |
| --- | --- |
| 11.10(e) audit trail: secure, computer-generated, time-stamped, recording operator entries and actions, not obscuring earlier entries | The Write Audit Log: append-only, refused edits and deletes, hash-chained, with user, time, reason and the record it concerns |
| 11.10(d) limiting access; 11.10(g) authority checks | Frappe users and roles; the sign-off role per site or connector; only signers with that role can approve |
| 11.10(f) operational checks (sequence) | Outbox postings keep their sequence group; a held posting holds back later ones for the same order |
| 11.50 signature manifestation | Signer's printed name, date and time, and meaning (Approved or Rejected) on the Pending Write and in the audit entry |
| 11.70 signature/record linking | The signature hash covers the Pending Write, the SHA-256 hash of its exact payload, signer, meaning, reason and time; a changed payload breaks it |
| 11.100(a) unique to one individual | One Frappe user per person; shared logins should not be given the sign-off role |
| 11.200(a) two distinct identification components | The signer is the logged-in user and re-enters their password for each signature |
| 11.300 controls for identification codes and passwords | Frappe's password policy, expiry and lockout settings (configure them); failed signatures are logged as *Signature Failed* |
| Separation of duties | *Signer Must Differ from Requester*, on by default |

The site still owns procedures (who holds the sign-off role, training, periodic review of the audit trail), the password and session policy in System Settings, backups and record retention, and the validation of its configuration. Where the site uses Tulip, Tulip's own GxP features (electronic signature widgets, record history) apply to what operators do in Tulip apps; FoaMES's sign-off covers what FoaMES writes to Tulip.

## For integrators and agents

- **New write paths go through the gate.** An adapter outbox is listed in the `foames_write_gated_outboxes` hook (outbox DocType to connector key, or `field:<fieldname>` when rows name their connector) and calls `write_gate.outbox_may_send(doc)` in its `claim` before it marks a row Sending. A write that does not go through an outbox is registered in `foames_write_actions` (action key to dotted path) and requested with `write_gate.request_write(connector, action, arguments, context=...)`, which runs it, holds it or refuses it and says which.
- **MCP.** `foames_get_write_mode`, `foames_list_pending_writes` and `foames_get_write_audit_trail` read the mode, the held writes and the trail. A writing tool called while read-only answers `{"status": "Awaiting Sign-off", "pending_write": ...}`; an agent should report that and not call the tool again. No tool signs: a signature needs a person and their password.
- **Pure rules.** The decision, the context extraction, the hashes and the signature checks are in `foames/foames_kernel/write_policy.py`, with no Frappe import, tested in `test_write_policy.py`. The Frappe side is `foames/foames_kernel/write_gate.py`, tested in `test_write_gate.py`.
- **Bridges** (Bluesky, the historian bridge) read their source and post observations to the webhook; they write nothing to the source. A bridge that ever needs to write back registers the write as an action and requests it through the gate.
