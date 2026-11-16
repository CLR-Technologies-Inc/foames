# aider-ollama-deepseek-r1-14b: benchmark run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T05:27:43+00:00, last run finished 2026-11-16T10:52:46+00:00
- **Model:** `ollama_chat/deepseek-r1:14b` (oss tier, built for reasoning (off-label)), Ollama deepseek-r1:14b digest c333b7232bdb, pulled 2026-11-16
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner (4 vCPU, 15 GB, CPU only); sandbox docker, image `sha256:092760446bc0`, Ollama ollama version is 0.40.16
- **FoaMES commit:** `a5e355aa7bce`
- Aider with deepseek-r1:14b (DeepSeek (Qwen distil), MIT) served by Ollama on the same machine. Built for reasoning, so it is off-label for agentic coding. Quality over speed: the timeout is thirteen times the task budget. Cost is electricity and time, recorded as $0.

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.39 | 0.40 | 0.38 | 0.29 | 7826 s | 112,600 / 0 / 12,877 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T09:22 | fail | 0.58 | 0.84 | 0.29 | 7800 s | 37,800 / 3,739 | None | timed out, broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T10:52 | fail | 0.26 | 0.24 | 0.28 | 19500 s | 10,000 / 1,300 | None | timed out, broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T10:03 | fail | 0.39 | 0.39 | 0.40 | 10178 s | 24,000 / 2,338 | 0 | broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T07:19 | fail | 0.14 | 0.12 | 0.17 | 189 s | 0 / 0 | 0 | broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T06:26 | fail | 0.40 | 0.25 | 0.56 | 3355 s | 9,800 / 1,100 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T08:49 | fail | 0.56 | 0.57 | 0.55 | 5935 s | 31,000 / 4,400 | 0 | broke an invariant |
