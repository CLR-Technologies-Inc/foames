# aider-ollama-llama3.2-3b: benchmark run of 2026-11-16

<!-- Copyright 2026 CLR Technologies Inc. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T06:14:14+00:00, last run finished 2026-11-16T08:49:51+00:00
- **Model:** `ollama_chat/llama3.2:3b` (oss tier, built for tiny (off-label)), Ollama llama3.2:3b digest a80c4f17acd5, pulled 2026-11-16
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner (4 vCPU, 15 GB, CPU only); sandbox docker, image `sha256:9efbb593cac5`, Ollama ollama version is 0.40.16
- **FoaMES commit:** `a5e355aa7bce`
- Aider with llama3.2:3b (Meta, Llama 3.2 Community License) served by Ollama on the same machine. Built for tiny, so it is off-label for agentic coding. Quality over speed: the timeout is thirteen times the task budget. Cost is electricity and time, recorded as $0.

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.22 | 0.26 | 0.17 | 0.16 | 2616 s | 275,800 / 0 / 11,699 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T07:21 | fail | 0.57 | 0.84 | 0.26 | 1243 s | 36,400 / 579 | 0 | broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T08:49 | fail | 0.20 | 0.24 | 0.15 | 3606 s | 56,500 / 1,608 | 0 | broke an invariant, regression tests 96% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T08:35 | fail | 0.19 | 0.22 | 0.15 | 4237 s | 44,300 / 4,811 | 0 | broke an invariant, regression tests 87% |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T07:00 | fail | 0.12 | 0.12 | 0.11 | 2798 s | 55,000 / 1,486 | 0 | broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T07:53 | fail | 0.17 | 0.12 | 0.23 | 1667 s | 40,200 / 1,574 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T07:55 | fail | 0.07 | 0.00 | 0.15 | 2144 s | 43,400 / 1,641 | 0 | broke an invariant, regression tests 0% |
