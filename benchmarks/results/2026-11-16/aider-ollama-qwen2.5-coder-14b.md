# aider-ollama-qwen2.5-coder-14b: benchmark run of 2026-11-16

<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T01:09:18+00:00, last run finished 2026-11-16T02:42:31+00:00
- **Model:** `ollama_chat/qwen2.5-coder:14b` (oss tier), Ollama qwen2.5-coder:14b digest 9ec8897f747e, pulled 2026-11-16
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner (4 vCPU, 15 GB, CPU only); sandbox docker, image `sha256:06e24fcb3e49`, Ollama ollama version is 0.40.16
- **FoaMES commit:** `db2f835e6792`
- Aider with qwen2.5-coder:14b (Alibaba Qwen, Apache-2.0) served by Ollama on the same machine. Quality over speed: the timeout is ten times the task budget. Cost is electricity and time, recorded as $0.
- Workflow run: https://github.com/CLR-Technologies-Inc/foames/actions/runs/43784200629

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.22 | 0.30 | 0.13 | 0.17 | 5473 s | 0 / 0 / 0 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T02:42 | fail | 0.51 | 0.84 | 0.14 | 5471 s | 0 / 0 | 0 | broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T02:40 | fail | 0.26 | 0.24 | 0.28 | 5473 s | 0 / 0 | 0 | broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T02:40 | fail | 0.13 | 0.25 | 0.00 | 5470 s | 0 / 0 | 0 | broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T02:41 | fail | 0.14 | 0.12 | 0.17 | 5483 s | 0 / 0 | 0 | broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T02:40 | fail | 0.16 | 0.12 | 0.20 | 5471 s | 0 / 0 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T02:41 | fail | 0.13 | 0.25 | 0.00 | 5472 s | 0 / 0 | 0 | broke an invariant |
