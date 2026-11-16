# reference

<!-- SPDX-License-Identifier: Apache-2.0 -->

- Model: `` ( tier), harness:  
- Applies the task's reference solution. Validates tasks and the grader.
- FoaMES commit: `50e033039c70c51c625793c9cc39322803e9100f`, bench 0.1.0, started 2026-11-16T00:42:59+00:00
- Sandbox: built-in, image ``
- Workflow run: https://github.com/CLR-Technologies-Inc/foames/actions/runs/43781545523

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL tier |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 100% (61% to 100%) | 0.97 | 1.00 | 0.95 | 0.98 | 0 s | 0 / 0 / 0 | n/a | n/a | n/a |

| Task | Complexity | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | low | PASS | 0.99 | 1.00 | 0.99 | 0 s | 0 / 0 | 0 |  |
| erp-retry-after (rep 1) | high | PASS | 1.00 | 1.00 | 1.00 | 0 s | 0 / 0 | 0 |  |
| oee-unknown-time (rep 1) | medium | PASS | 0.99 | 1.00 | 0.98 | 0 s | 0 / 0 | 0 |  |
| process-mining-analysis (rep 1) | medium | PASS | 0.90 | 1.00 | 0.78 | 0 s | 0 / 0 | 0 |  |
| process-spec-network-loss (rep 1) | high | PASS | 0.98 | 1.00 | 0.95 | 0 s | 0 / 0 | 0 |  |
| spc-ewma-chart (rep 1) | medium | PASS | 0.99 | 1.00 | 0.99 | 0 s | 0 / 0 | 0 |  |
