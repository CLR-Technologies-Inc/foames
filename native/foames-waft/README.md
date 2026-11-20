# foames-waft

**WAFT: Lightweight Affordable Frequent Transmission** — a minimal native Rust transport that streams machine events from simulations, sensors and constrained edge devices into foaMES Core through the existing **signed machine-event webhook**. No Python, Frappe or ERPNext needed on the device; no second ingestion path is introduced.

WAFT owns transport only: sampling, batching, HMAC signing, bounded buffering, backoff and stable event ids. All MES business rules — state interpretation, counter deltas, permissions, audit — stay in Core.

## Build

```bash
cd native/foames-waft
cargo build --release          # binary: target/release/foames-waft
cargo test                     # unit tests, no network or Frappe needed
```

Minimum supported target: any platform `rustc` 1.75+ reaches; the release profile uses LTO, one codegen unit, `panic=abort` and stripping for a small binary. A C header (`include/foames_waft.h`) and `cdylib`/`staticlib` crate types are provided for native consumers; today the stable FFI surface is `foames_waft_protocol_version()`.

## Run

```bash
export FOAMES_WEBHOOK_SECRET=...        # the secret Machine Data Settings holds; never on the command line
foames-waft run --config examples/waft.json
foames-waft run --config waft.json --once
foames-waft bench --config waft.json --duration 30
```

`run` samples the built-in simulation machine (`sample_rate_hz` Count events/sec for counter `good`, plus periodic State events) and POSTs batches to the endpoint. `bench` reports throughput, p50/p95/p99 send latency, sent/failed/dropped counts — the harness for the performance budgets in [BENCHMARKS.md](BENCHMARKS.md).

## Configuration (`waft.json`)

| Field | Meaning |
| --- | --- |
| `endpoint` | Full webhook URL (`…/api/method/foames.foames_mes.api.ingest_machine_events`); `https://` required unless `allow_http` for isolated labs |
| `machine` | The machine's **Source ID** in foaMES |
| `secret_env` | Name of the env var holding the webhook secret — the value is read at send time, never stored |
| `batch_size` / `max_buffer` | Events per POST / buffer cap (overflow drops incoming, counted) |
| `flush_interval_ms` / `timeout_ms` | Flush cadence / per-request timeout |
| `sample_rate_hz` | Simulation rate; 0 disables the built-in sim |

## Wire contract (protocol v1)

Each POST body is `{"events": [...]}`; each event is `{"machine", "type", "timestamp", "id", ...}` with `type` one of `State`, `Count`, `Measurement`, `Alarm`, `Message` — exactly the shape `ingest_machine_events` accepts. Headers: `X-FoaMES-Timestamp` (Unix seconds) and `X-FoaMES-Signature` (hex HMAC-SHA256 of `<timestamp>.<body>`), identical to `foames.foames_mes.signing`. Event `id`s are stable and unique, so Core-side dedup makes retries safe.

## Behaviour under stress

- **Disconnect:** batches retry with exponential backoff (200 ms → 2 s cap); the bounded buffer holds up to `max_buffer` events, then drops *incoming* events and counts them (`dropped` is reported by `bench`/logs).
- **4xx (bad signature/payload):** never retried — fix config, not the network.
- **5xx/timeout:** retried up to 4 attempts, then the batch is requeued in order at the front of the next flush.
- **Backpressure:** producers are never blocked; `Batcher::push` returns immediately.

## Security

Secrets come only from the named environment variable at send time — never compiled in, logged, or written to config. TLS is required by default (`rustls`); `allow_http` exists for isolated lab benches only. WAFT performs no MES authorization: it is a dumb pipe; Core enforces everything.

## Benchmarks

See [BENCHMARKS.md](BENCHMARKS.md) for the harness and how budgets are set from measured baselines (throughput, p50/p95/p99 latency, RSS, CPU, binary size) on a documented small-device profile.

## Docs

- [Machine data formats and signed ingestion](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/machine-data.md)
- [FoaMES architecture](https://github.com/CLR-Technologies-Inc/foames/blob/main/README.md)
- Issue #112
