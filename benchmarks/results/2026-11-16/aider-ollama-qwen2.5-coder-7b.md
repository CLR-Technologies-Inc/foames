# aider-ollama-qwen2.5-coder-7b: benchmark run of 2026-11-16

<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T01:08:31+00:00, last run finished 2026-11-16T02:40:23+00:00
- **Model:** `ollama_chat/qwen2.5-coder:7b` (oss tier), Ollama qwen2.5-coder:7b digest dae161e27b0e, pulled 2026-11-16
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner (4 vCPU, 15 GB, CPU only); sandbox docker, image `sha256:3f269f31c435`, Ollama ollama version is 0.40.16
- **FoaMES commit:** `db2f835e6792`
- Aider with qwen2.5-coder:7b (Alibaba Qwen, Apache-2.0) served by Ollama on the same machine. Quality over speed: the timeout is ten times the task budget. Cost is electricity and time, recorded as $0.
- Workflow run: https://github.com/CLR-Technologies-Inc/foames/actions/runs/43784200629

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.22 | 0.30 | 0.13 | 0.17 | 3204 s | 32,600 / 0 / 3,735 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T01:21 | fail | 0.51 | 0.84 | 0.14 | 768 s | 17,100 / 1,035 | 0 | broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T01:24 | fail | 0.26 | 0.24 | 0.28 | 969 s | 7,800 / 1,200 | 0 | broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T02:40 | fail | 0.13 | 0.25 | 0.00 | 5470 s | 0 / 0 | 0 | broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T02:40 | fail | 0.14 | 0.12 | 0.17 | 5470 s | 0 / 0 | 0 | broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T01:27 | fail | 0.16 | 0.12 | 0.20 | 1075 s | 7,700 / 1,500 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T02:40 | fail | 0.13 | 0.25 | 0.00 | 5471 s | 0 / 0 | 0 | broke an invariant |
