# Native gateway: high-rate machine-data ingest in Rust (proposal)

Status: proposal. This document sketches `foames-gateway`, a native Rust edge
gateway that replaces the Python MQTT, Sparkplug B and OPC UA gateways for
sites where ingest volume is the constraint. It is a design for review; no code
is included yet.

## Why

The three Python gateways in `foames/foames_mes/gateway/` each decode protocol
messages in-process and then call `record_event` **once per event**, committing
after every insert:

- `mqtt.py` — one `frappe.db.commit()` per message (`handle_message`).
- `sparkplug.py` — one commit per metric-derived event; a single NDATA message
  with N metrics costs N inserts and N commits.
- `opcua.py` — sequential `read_value` + insert + commit per mapped node per
  poll, all on one asyncio loop.

At plant scale this shows up as: paho-mqtt falling behind on Sparkplug B
bursts, OPC UA poll cycles stretching past their period as node counts grow,
worker memory climbing with queue depth, and the bench process competing with
Frappe for CPU during shift changes. The decode work itself (protobuf varints,
topic parsing, state maps) is trivially parallel and allocation-light — a poor
fit for CPython.

`foames-waft` already proved the shape of the answer for simulated and direct
sensor sources: a small Rust binary that owns transport only and posts signed
batches to `ingest_machine_events`. This proposal extends that pattern to the
three protocol gateways.

## Design principle: transport and decode in Rust, every rule in Core

The gateway produces **raw event dicts** — exactly the shape
`ingest_machine_events` already accepts — and POSTs them in signed batches.
Nothing else changes:

- `normalise_event` in `gateway/mapping.py` still validates every event
  server-side. Rust-side decoding is a *pre-filter*, never a second authority.
- Counter deltas, state ledgers, downtime overlay, OEE, the write gate and all
  permissions stay in Frappe exactly as today (invariants 3–6 are untouched —
  there is no new write path; the gateway only reads through the existing
  signed webhook).
- Stable event ids (`sp:<group>/<node>/<device>:<ts_ms>:<metric>` etc.) are
  preserved, so Core-side dedup makes retries and gateway restarts safe.
- The Python gateways remain, unchanged, for small sites and for OPC UA until
  the Rust port proves out. This is an addition, not a rip-out.

## Architecture

```
 MQTT broker ──┐                                     ┌─▶ ingest_machine_events
               ├─▶ foames-gateway (Rust, tokio) ────┤    (signed batches)
 OPC UA servers┘      decode → raw events → batch     └─▶ Machine Event → state/OEE
```

One binary, three front-ends behind a shared pipeline:

```
protocol front-end ──▶ bounded channel ──▶ decoder ──▶ batcher ──▶ signer ──▶ HTTPS POST
 (rumqttc /           (drops counted,        (port of    (reuse waft   (reuse waft
  opcua crate)         never blocks)        mapping +   batcher)      sign.rs / sender)
                                        sparkplug.py)
```

Components, mapped to what already exists:

| Piece | Source |
| --- | --- |
| Batcher, backoff, drop counting, stable ids | Reuse `native/foames-waft/src/batcher.rs`, `sender.rs` |
| HMAC-SHA256 signing, `X-FoaMES-Timestamp`/`X-FoaMES-Signature` | Reuse `sign.rs` — byte-identical to `foames_mes.signing` |
| Config file shape, `secret_env` pattern, `allow_http` lab escape | Reuse `config.rs` conventions |
| MQTT transport | `rumqttc` (async, supports TLS + username/password) |
| Sparkplug B decode | Port of `sparkplug.py`: the protobuf wire reader (~150 lines), `AliasBook`, reserved-metric rules, convention naming. The module is already Frappe-free, so the port is mechanical |
| Plain MQTT topic mapping | Port of `mapping.py::mqtt_message_to_raw` + `parse_topic` |
| OPC UA polling | `opcua` crate (Rust OPC UA stack) — see risks |
| Node map / state maps / group id | Exported config, see below |

### What the Rust side must *not* do

- Resolve machines. `machine` in a raw event is the **source id**; Core maps it
  via `get_machine_by_source`. The gateway never learns Frappe names.
- Decide event validity. `normalise_event` re-checks type, state aliases,
  timestamps and numbers. Rust emits best-effort raw dicts; rejects are counted
  locally for metrics but the authority is the server's `rejected` list.
- Store secrets in config. Same rule as waft: secrets come from named env vars
  or a local secrets file on the gateway host, never from the site.

### Configuration export

The Python gateways read `Machine Data Settings` live (node maps, state maps,
broker endpoint, credentials). A gateway outside the bench needs that config
without a Frappe session. Proposal: a whitelisted export command —

```
bench --site <site> execute foames.foames_mes.gateway.export_config.write --kwargs '{"path": "/etc/foames-gateway.json"}'
```

— that renders the enabled gateways' settings to a JSON file the operator
copies to the gateway host (or fetches over the site's authenticated file API).
Secrets are written as `*_env` names, not values, matching waft's
`secret_env` convention; the operator sets the real values in the gateway
host's environment. Config carries a `settings_version`/hash so the gateway
can warn when the site config has drifted.

### Source attribution (small Core change, optional)

Events posted by a signed guest caller are recorded with `source="Webhook"`.
The Python gateways record `"MQTT"` or `"OPC UA"`, and floor views and reports
use that field. To keep attribution honest, propose a narrow addition to
`ingest_machine_events`: when the request is signature-authorised, honour an
optional `"source"` field restricted to a whitelist (`MQTT`, `OPC UA`,
`Sparkplug B`, `WAFT`) — unsigned/manual calls keep `"Manual"`/`"Webhook"`.
~15 lines in `api.py` plus a test. Without it the system still works; events
just show as Webhook.

## Phasing

1. **Phase 1 — MQTT + Sparkplug B.** Highest message volume, simplest decode,
   no new crypto. Covers Ignition/Cirrus Link and generic MQTT publishers.
   This is where the throughput win is largest.
2. **Phase 2 — OPC UA.** Polling is inherently sequential per server but the
   `opcua` crate supports async sessions and the security policies
   (`Basic256Sha256`, `Aes128_Sha256_RsaOaep`, `Aes256_Sha256_RsaPss`) map to
   RustCrypto crates. Certificate handling ports from `opcua_trust.py`
   (chain-to-bundle validation, validity, application URI). Gated on a spike
   proving the crate covers the policies sites actually use; sites needing
   uncovered policies keep the Python gateway.
3. **Phase 3 — bench harness parity.** Extend the waft `bench` command to
   replay captured Sparkplug/OPC UA traffic and publish the same metrics
   (throughput, p50/p95/p99, RSS, drops) against the Python gateways.

## Expected performance

Honest expectations, consistent with the waft benchmarks pending baseline:

- **Protocol decode**: 10–100× — protobuf decode and topic mapping are the hot
  loop; Rust does this with no GIL and no per-message allocation churn.
- **Ingest path end-to-end**: bounded by the server. `record_event` still does
  one DocType insert per event inside `ingest_machine_events`, so database
  insert cost dominates once batches arrive. The gateway removes the *client-
  side* serialization (per-message commits in the Python gateways) and the
  HTTP round-trips (batched POSTs), which is where the Python gateways actually
  lose time — not in Frappe's insert itself.
- **If server-side insert becomes the wall**, the follow-up is a Core change:
  a bulk-insert path for `Machine Event` inside `record_events` (one commit per
  batch, executemany-style inserts). That is a separate PR and benefits every
  ingest path, not just this one.
- **Operational**: single static binary, ~tens of MB RSS vs. a bench process +
  paho/asyncua inside the Frappe worker pool, and the gateway can run on the
  plant floor network segment next to the broker.

## Risks and open questions

- **OPC UA crate maturity.** The Rust `opcua` ecosystem is younger than
  asyncua. Phase 2 is explicitly gated on a spike; the Python gateway remains
  the fallback for exotic security policies.
- **Behavioural parity.** `sparkplug.py`'s alias book, reserved-metric list,
  death-message fan-out (`NDEATH` → Unknown for every known device) and
  convention rules must be ported exactly; the existing
  `test_gateways.py` cases become the parity spec — each should have a Rust
  unit-test twin feeding identical bytes.
- **Config drift.** A rendered config file can go stale when someone edits
  Machine Data Settings. Mitigation: `settings_version` check plus a documented
  re-export step; alternatively a read-only pull endpoint later.
- **Ordering.** Sparkplug `seq`/`bdSeq` ordering is informational today; the
  gateway preserves per-topic ordering through the bounded channel but makes
  no ordering guarantees across devices — same as the Python gateway.
- **Scope guard.** This must not grow into "Rust backend for FoaMES." It owns
  protocol front-ends and transport only; if a change would need business
  rules, it belongs in Core.

## Non-goals

- No direct database access from the gateway.
- No ERP writes, no machine commands (NCMD/DCMD stay ignored, as today).
- No replacement of the Desk UI, reports, or any non-ingest path.
- No removal of the Python gateways in this proposal.
