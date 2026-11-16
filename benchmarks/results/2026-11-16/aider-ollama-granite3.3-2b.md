# aider-ollama-granite3.3-2b: benchmark run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T07:54:40+00:00, last run finished 2026-11-16T09:18:00+00:00
- **Model:** `ollama_chat/granite3.3:2b` (oss tier, built for tiny (off-label)), Ollama granite3.3:2b digest 07bd1f170855, pulled 2026-11-16
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner (4 vCPU, 15 GB, CPU only); sandbox docker, image `sha256:023962853113`, Ollama ollama version is 0.40.16
- **FoaMES commit:** `a5e355aa7bce`
- Aider with granite3.3:2b (IBM, Apache-2.0) served by Ollama on the same machine. Built for tiny, so it is off-label for agentic coding. Quality over speed: the timeout is thirteen times the task budget. Cost is electricity and time, recorded as $0.
- Workflow run: https://github.com/CLR-Technologies-Inc/foames/actions/runs/43805918094

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.23 | 0.30 | 0.16 | 0.17 | 1923 s | 140,500 / 0 / 9,148 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T08:43 | fail | 0.51 | 0.84 | 0.14 | 1730 s | 20,000 / 2,542 | 0 | broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T08:40 | fail | 0.26 | 0.24 | 0.28 | 1128 s | 22,400 / 879 | 0 | broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T08:30 | fail | 0.19 | 0.22 | 0.15 | 840 s | 21,000 / 2,800 | 0 | broke an invariant, regression tests 87% |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T09:18 | fail | 0.14 | 0.12 | 0.17 | 3905 s | 34,000 / 594 | 0 | broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T08:27 | fail | 0.16 | 0.12 | 0.20 | 683 s | 9,100 / 1,100 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T08:48 | fail | 0.13 | 0.25 | 0.00 | 3252 s | 34,000 / 1,233 | 0 | broke an invariant |
