# foames-waft benchmarks

The acceptance bar for WAFT is measured, not asserted. This file defines the harness; fill in the baseline table after the first runs on the documented profiles.

## What to measure

| Metric | How |
| --- | --- |
| Throughput | `foames-waft bench --duration 60` → events/sec accepted |
| Latency | same → p50/p95/p99 per-batch POST time (ms) |
| Reliability | `sent`, `failed`, `dropped` counters in the bench line |
| Resident memory | `/usr/bin/time -v foames-waft run …` → `Maximum resident set size` |
| CPU | `top`/`pidstat` over a 60 s run → mean %CPU |
| Binary size | `ls -l target/release/foames-waft` (and `.so`/`.a` for the lib targets) |

## Profiles

1. **Dev workstation** — the machine running this repo's CI-equivalent setup.
2. **Small device** — the smallest realistic target: e.g. a Raspberry Pi Zero 2 W (512 MB, ARMv8, Linux) or an equivalent single-core container with a 256 MB cgroup limit. Document kernel, glibc/musl choice and power mode.

## Budgets (to be set from baseline)

Establish targets *after* the first measured run, then hold them: e.g. "≥ 90% of offered rate sustained for 10 min", "p99 batch latency < 2 s on the small-device profile", "RSS < 32 MB idle", "binary < 8 MB stripped". Record the date and commit of each baseline here.

## Baseline

| Date | Commit | Profile | Events/s | p50/p95/p99 ms | RSS | CPU% | Binary |
| --- | --- | --- | --- | --- | --- | --- | --- |
| _pending first run_ | | | | | | | |
