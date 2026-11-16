# aider-ollama-qwen3-1.7b: benchmark run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T05:24:52+00:00, last run finished 2026-11-16T08:39:20+00:00
- **Model:** `ollama_chat/qwen3:1.7b` (oss tier, built for tiny (off-label)), Ollama qwen3:1.7b digest 8f68893c685c, pulled 2026-11-16
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner (4 vCPU, 15 GB, CPU only); sandbox docker, image `sha256:125e02b03f34`, Ollama ollama version is 0.40.16
- **FoaMES commit:** `a5e355aa7bce`
- Aider with qwen3:1.7b (Alibaba Qwen, Apache-2.0) served by Ollama on the same machine. Built for tiny, so it is off-label for agentic coding. Quality over speed: the timeout is thirteen times the task budget. Cost is electricity and time, recorded as $0.

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.22 | 0.30 | 0.13 | 0.17 | 2295 s | 101,900 / 0 / 12,500 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T07:50 | fail | 0.51 | 0.84 | 0.14 | 1161 s | 19,000 / 2,800 | 0 | broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T07:22 | fail | 0.26 | 0.24 | 0.28 | 546 s | 20,400 / 2,500 | 0 | broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T07:20 | fail | 0.13 | 0.25 | 0.00 | 536 s | 9,300 / 1,200 | 0 | broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T08:39 | fail | 0.14 | 0.12 | 0.17 | 6546 s | 32,000 / 2,500 | 0 | broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T06:00 | fail | 0.16 | 0.12 | 0.20 | 560 s | 8,200 / 1,700 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T06:38 | fail | 0.13 | 0.25 | 0.00 | 4420 s | 13,000 / 1,800 | 0 | broke an invariant |
