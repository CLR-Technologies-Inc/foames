# aider-ollama-yi-coder-9b: benchmark run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T04:47:46+00:00, last run finished 2026-11-16T08:02:50+00:00
- **Model:** `ollama_chat/yi-coder:9b` (oss tier, built for coding), Ollama yi-coder:9b digest 39c63e7675d7, pulled 2026-11-16
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner (4 vCPU, 15 GB, CPU only); sandbox docker, image `sha256:3a0b187505da`, Ollama ollama version is 0.40.16
- **FoaMES commit:** `a5e355aa7bce`
- Aider with yi-coder:9b (01.AI, Apache-2.0) served by Ollama on the same machine. Built for coding. Quality over speed: the timeout is thirteen times the task budget. Cost is electricity and time, recorded as $0.
- Workflow run: https://github.com/CLR-Technologies-Inc/foames/actions/runs/43805918094

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.25 | 0.30 | 0.19 | 0.19 | 4421 s | 88,500 / 0 / 4,659 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T06:06 | fail | 0.57 | 0.84 | 0.26 | 4711 s | 22,700 / 2,300 | 0 | broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T05:13 | fail | 0.31 | 0.24 | 0.39 | 1509 s | 10,000 / 927 | 0 | broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T05:17 | fail | 0.19 | 0.25 | 0.11 | 1743 s | 11,000 / 924 | 0 | broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T06:11 | fail | 0.14 | 0.12 | 0.17 | 5041 s | 35,000 / 14 | 0 | broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T05:18 | fail | 0.16 | 0.12 | 0.20 | 1822 s | 9,800 / 494 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T08:02 | fail | 0.13 | 0.25 | 0.00 | 11700 s | 0 / 0 | None | timed out, broke an invariant |
