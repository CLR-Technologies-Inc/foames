# noop: benchmark run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T03:12:01+00:00, last run finished 2026-11-16T03:12:10+00:00
- **Model:** `-` (calibration tier)
- **Harness:** built in
- **Where it ran:** GitHub-hosted runner; sandbox built-in
- **FoaMES commit:** `11c643fbf2e7`
- Changes nothing. Every real agent must beat it.
- Workflow run: https://github.com/CLR-Technologies-Inc/foames/actions/runs/43787796363

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.22 | 0.30 | 0.13 | 0.17 | 0 s | 0 / 0 / 0 | n/a | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T03:12 | fail | 0.51 | 0.84 | 0.14 | 0 s | 0 / 0 | 0 | broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T03:12 | fail | 0.26 | 0.24 | 0.28 | 0 s | 0 / 0 | 0 | broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T03:12 | fail | 0.13 | 0.25 | 0.00 | 0 s | 0 / 0 | 0 | broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T03:12 | fail | 0.14 | 0.12 | 0.17 | 0 s | 0 / 0 | 0 | broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T03:12 | fail | 0.16 | 0.12 | 0.20 | 0 s | 0 / 0 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T03:12 | fail | 0.13 | 0.25 | 0.00 | 0 s | 0 / 0 | 0 | broke an invariant |
