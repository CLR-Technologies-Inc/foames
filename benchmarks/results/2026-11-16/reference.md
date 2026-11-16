# reference: benchmark run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T03:12:01+00:00, last run finished 2026-11-16T03:12:09+00:00
- **Model:** `-` (calibration tier, built for -)
- **Harness:** built in
- **Where it ran:** GitHub-hosted runner; sandbox built-in
- **FoaMES commit:** `11c643fbf2e7`
- Applies the task's reference solution. Validates tasks and the grader.
- Workflow run: https://github.com/CLR-Technologies-Inc/foames/actions/runs/43796612771

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 100% (61% to 100%) | 0.97 | 1.00 | 0.95 | 0.98 | 0 s | 0 / 0 / 0 | n/a | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T03:12 | PASS | 0.99 | 1.00 | 0.99 | 0 s | 0 / 0 | 0 |  |
| erp-retry-after (rep 1) | - | high | 2026-11-16T03:12 | PASS | 1.00 | 1.00 | 1.00 | 0 s | 0 / 0 | 0 |  |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T03:12 | PASS | 0.99 | 1.00 | 0.98 | 0 s | 0 / 0 | 0 |  |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T03:12 | PASS | 0.90 | 1.00 | 0.78 | 0 s | 0 / 0 | 0 |  |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T03:12 | PASS | 0.98 | 1.00 | 0.95 | 0 s | 0 / 0 | 0 |  |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T03:12 | PASS | 0.99 | 1.00 | 0.99 | 0 s | 0 / 0 | 0 |  |
