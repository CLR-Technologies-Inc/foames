# aider-ollama-llama3.1-8b: benchmark run of 2026-11-16

<!-- Copyright 2026 CLR Technologies Inc. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T04:47:42+00:00, last run finished 2026-11-16T08:13:11+00:00
- **Model:** `ollama_chat/llama3.1:8b` (oss tier, built for general chat (off-label)), Ollama llama3.1:8b digest 46e0c10c039e, pulled 2026-11-16
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner (4 vCPU, 15 GB, CPU only); sandbox docker, image `sha256:24ada277b946`, Ollama ollama version is 0.40.16
- **FoaMES commit:** `a5e355aa7bce`
- Aider with llama3.1:8b (Meta, Llama 3.1 Community License) served by Ollama on the same machine. Built for general chat, so it is off-label for agentic coding. Quality over speed: the timeout is thirteen times the task budget. Cost is electricity and time, recorded as $0.

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.25 | 0.28 | 0.22 | 0.19 | 8148 s | 167,000 / 0 / 14,081 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T06:58 | fail | 0.51 | 0.84 | 0.14 | 7800 s | 19,100 / 2,932 | None | timed out, broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T07:14 | fail | 0.03 | 0.00 | 0.06 | 7212 s | 36,400 / 2,598 | 0 | purity violation, broke an invariant, regression tests 0% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T07:53 | fail | 0.19 | 0.22 | 0.15 | 9435 s | 49,300 / 6,400 | 0 | broke an invariant, regression tests 87% |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T08:13 | fail | 0.28 | 0.12 | 0.47 | 11700 s | 54,000 / 1,698 | None | timed out, broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T05:05 | fail | 0.36 | 0.25 | 0.49 | 1042 s | 8,200 / 453 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T08:11 | fail | 0.13 | 0.25 | 0.00 | 11700 s | 0 / 0 | None | timed out, broke an invariant |
