# aider-ollama-mistral-nemo-12b: benchmark run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T04:47:49+00:00, last run finished 2026-11-16T08:18:36+00:00
- **Model:** `ollama_chat/mistral-nemo:12b` (oss tier, built for general chat (off-label)), Ollama mistral-nemo:12b digest e7e06d107c6c, pulled 2026-11-16
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner (4 vCPU, 15 GB, CPU only); sandbox docker, image `sha256:9522a146f4d6`, Ollama ollama version is 0.40.16
- **FoaMES commit:** `a5e355aa7bce`
- Aider with mistral-nemo:12b (Mistral AI and NVIDIA, Apache-2.0) served by Ollama on the same machine. Built for general chat, so it is off-label for agentic coding. Quality over speed: the timeout is thirteen times the task budget. Cost is electricity and time, recorded as $0.

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.23 | 0.26 | 0.19 | 0.17 | 6407 s | 173,400 / 0 / 8,159 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T06:29 | fail | 0.51 | 0.84 | 0.14 | 4073 s | 19,300 / 844 | 0 | broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T06:53 | fail | 0.29 | 0.24 | 0.35 | 7427 s | 46,700 / 2,712 | 0 | broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T05:45 | fail | 0.13 | 0.25 | 0.00 | 2076 s | 9,700 / 500 | 0 | broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T08:18 | fail | 0.21 | 0.12 | 0.32 | 11700 s | 34,000 / 393 | None | timed out, broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T06:19 | fail | 0.17 | 0.12 | 0.23 | 5485 s | 30,400 / 1,876 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T07:24 | fail | 0.05 | 0.00 | 0.11 | 7681 s | 33,300 / 1,834 | 0 | broke an invariant, regression tests 0% |
