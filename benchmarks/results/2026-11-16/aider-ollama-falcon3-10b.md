# aider-ollama-falcon3-10b: benchmark run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T05:59:43+00:00, last run finished 2026-11-16T09:48:55+00:00
- **Model:** `ollama_chat/falcon3:10b` (oss tier, built for general chat (off-label)), Ollama falcon3:10b digest 1653ff122acd, pulled 2026-11-16
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner (4 vCPU, 15 GB, CPU only); sandbox docker, image `sha256:64f5a60e9cbf`, Ollama ollama version is 0.40.16
- **FoaMES commit:** `a5e355aa7bce`
- Aider with falcon3:10b (TII, TII Falcon License 2.0 (Apache-based)) served by Ollama on the same machine. Built for general chat, so it is off-label for agentic coding. Quality over speed: the timeout is thirteen times the task budget. Cost is electricity and time, recorded as $0.

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.20 | 0.26 | 0.12 | 0.15 | 5140 s | 182,200 / 0 / 14,699 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T08:45 | fail | 0.51 | 0.84 | 0.14 | 7800 s | 9,500 / 854 | None | timed out, broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T09:48 | fail | 0.02 | 0.00 | 0.04 | 11032 s | 72,900 / 7,759 | 0 | purity violation, broke an invariant, regression tests 0% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T08:12 | fail | 0.20 | 0.25 | 0.15 | 7942 s | 55,000 / 3,594 | 0 | broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T06:05 | fail | 0.14 | 0.12 | 0.17 | 365 s | 1,200 / 624 | 0 | broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T07:39 | fail | 0.16 | 0.12 | 0.20 | 1004 s | 9,600 / 654 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T07:17 | fail | 0.13 | 0.25 | 0.00 | 2698 s | 34,000 / 1,214 | 0 | broke an invariant |
