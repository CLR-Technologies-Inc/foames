# aider-ollama-gemma3-12b: benchmark run of 2026-11-16

<!-- Copyright 2026 CLR Technologies Inc. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T04:55:51+00:00, last run finished 2026-11-16T10:25:30+00:00
- **Model:** `ollama_chat/gemma3:12b` (oss tier, built for general chat (off-label)), Ollama gemma3:12b digest b92b218582c5, pulled 2026-11-16
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner (4 vCPU, 15 GB, CPU only); sandbox docker, image `sha256:2612cb9a60a5`, Ollama ollama version is 0.40.16
- **FoaMES commit:** `a5e355aa7bce`
- Aider with gemma3:12b (Google, Gemma Terms of Use) served by Ollama on the same machine. Built for general chat, so it is off-label for agentic coding. Quality over speed: the timeout is thirteen times the task budget. Cost is electricity and time, recorded as $0.

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.18 | 0.20 | 0.15 | 0.14 | 5244 s | 154,900 / 0 / 16,303 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T05:29 | fail | 0.20 | 0.24 | 0.15 | 1746 s | 18,800 / 499 | 0 | broke an invariant, regression tests 96% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T07:00 | fail | 0.04 | 0.00 | 0.07 | 5980 s | 57,200 / 4,304 | 0 | purity violation, broke an invariant, regression tests 0% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T05:29 | fail | 0.42 | 0.49 | 0.34 | 961 s | 10,000 / 2,000 | 0 | broke an invariant, regression tests 87% |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T06:50 | fail | 0.14 | 0.12 | 0.17 | 6900 s | 34,000 / 1,500 | 0 | broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T08:19 | fail | 0.16 | 0.12 | 0.20 | 4179 s | 20,900 / 2,600 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T10:25 | fail | 0.13 | 0.25 | 0.00 | 11700 s | 14,000 / 5,400 | None | timed out, broke an invariant |
