# aider-ollama-mistral-7b: benchmark run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T04:47:52+00:00, last run finished 2026-11-16T08:06:10+00:00
- **Model:** `ollama_chat/mistral:7b` (oss tier, built for general chat (off-label)), Ollama mistral:7b digest 6577803aa9a0, pulled 2026-11-16
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner (4 vCPU, 15 GB, CPU only); sandbox docker, image `sha256:24cb7c9ea9c5`, Ollama ollama version is 0.40.16
- **FoaMES commit:** `a5e355aa7bce`
- Aider with mistral:7b (Mistral AI, Apache-2.0) served by Ollama on the same machine. Built for general chat, so it is off-label for agentic coding. Quality over speed: the timeout is thirteen times the task budget. Cost is electricity and time, recorded as $0.
- Workflow run: https://github.com/CLR-Technologies-Inc/foames/actions/runs/43805918094

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.17 | 0.16 | 0.18 | 0.12 | 6186 s | 167,000 / 0 / 14,812 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T06:57 | fail | 0.18 | 0.24 | 0.11 | 7800 s | 59,800 / 3,194 | None | timed out, broke an invariant, regression tests 96% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T08:06 | fail | 0.26 | 0.24 | 0.28 | 10849 s | 31,000 / 3,500 | 0 | broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T05:10 | fail | 0.19 | 0.22 | 0.15 | 1349 s | 11,000 / 819 | 0 | broke an invariant, regression tests 87% |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T05:10 | fail | 0.14 | 0.12 | 0.17 | 461 s | 1,300 / 1,900 | 0 | broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T07:12 | fail | 0.16 | 0.12 | 0.20 | 7176 s | 9,900 / 3,100 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T07:26 | fail | 0.07 | 0.00 | 0.15 | 9483 s | 54,000 / 2,299 | 0 | broke an invariant, regression tests 0% |
