# aider-ollama-qwen3-8b: benchmark run of 2026-11-16

<!-- Copyright 2026 CLR Technologies Inc. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T03:14:11+00:00, last run finished 2026-11-16T06:29:40+00:00
- **Model:** `ollama_chat/qwen3:8b` (oss tier, built for general chat (off-label)), Ollama qwen3:8b digest 500a1f067a9f, pulled 2026-11-16
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner (4 vCPU, 15 GB, CPU only); sandbox docker, image `sha256:0aedc61115ef`, Ollama ollama version is 0.40.16
- **FoaMES commit:** `a1c95f786e96`
- Aider with qwen3:8b (Alibaba Qwen, Apache-2.0) served by Ollama on the same machine. Quality over speed: the timeout is ten times the task budget. Cost is electricity and time, recorded as $0.

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.25 | 0.30 | 0.19 | 0.19 | 7395 s | 90,500 / 0 / 21,587 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T05:21 | fail | 0.51 | 0.84 | 0.14 | 7598 s | 19,000 / 5,500 | 0 | broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T03:23 | fail | 0.38 | 0.24 | 0.54 | 533 s | 8,400 / 848 | 0 | broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T06:29 | fail | 0.13 | 0.25 | 0.00 | 11700 s | 0 / 0 | None | timed out, broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T06:29 | fail | 0.14 | 0.12 | 0.17 | 11700 s | 0 / 0 | None | timed out, broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T04:51 | fail | 0.16 | 0.12 | 0.20 | 5848 s | 31,100 / 5,039 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T05:10 | fail | 0.19 | 0.25 | 0.11 | 6994 s | 32,000 / 10,200 | 0 | broke an invariant |
