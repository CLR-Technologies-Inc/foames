# aider-ollama-granite3.3-8b: benchmark run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T03:14:05+00:00, last run finished 2026-11-16T06:29:43+00:00
- **Model:** `ollama_chat/granite3.3:8b` (oss tier, built for general chat (off-label)), Ollama granite3.3:8b digest fd429f23b909, pulled 2026-11-16
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner (4 vCPU, 15 GB, CPU only); sandbox docker, image `sha256:235dcdb6be71`, Ollama ollama version is 0.40.16
- **FoaMES commit:** `a1c95f786e96`
- Aider with granite3.3:8b (IBM, Apache-2.0) served by Ollama on the same machine. Quality over speed: the timeout is ten times the task budget. Cost is electricity and time, recorded as $0.

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.22 | 0.30 | 0.13 | 0.17 | 5337 s | 56,500 / 0 / 6,030 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T05:24 | fail | 0.51 | 0.84 | 0.14 | 7800 s | 0 / 0 | None | timed out, broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T04:36 | fail | 0.26 | 0.24 | 0.28 | 4870 s | 23,400 / 1,696 | 0 | broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T04:05 | fail | 0.13 | 0.25 | 0.00 | 3051 s | 10,000 / 2,400 | 0 | broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T06:29 | fail | 0.14 | 0.12 | 0.17 | 11700 s | 0 / 0 | None | timed out, broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T03:37 | fail | 0.16 | 0.12 | 0.20 | 1358 s | 9,100 / 1,100 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T04:08 | fail | 0.13 | 0.25 | 0.00 | 3244 s | 14,000 / 834 | 0 | broke an invariant |
