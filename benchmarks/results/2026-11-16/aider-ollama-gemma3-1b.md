# aider-ollama-gemma3-1b: benchmark run of 2026-11-16

<!-- Copyright 2026 CLR Technologies Inc. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T06:19:15+00:00, last run finished 2026-11-16T08:42:54+00:00
- **Model:** `ollama_chat/gemma3:1b` (oss tier, built for tiny (off-label)), Ollama gemma3:1b digest 97558784bdc9, pulled 2026-11-16
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner (4 vCPU, 15 GB, CPU only); sandbox docker, image `sha256:1164e7b8e223`, Ollama ollama version is 0.40.16
- **FoaMES commit:** `a5e355aa7bce`
- Aider with gemma3:1b (Google, Gemma Terms of Use) served by Ollama on the same machine. Built for tiny, so it is off-label for agentic coding. Quality over speed: the timeout is thirteen times the task budget. Cost is electricity and time, recorded as $0.

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.25 | 0.30 | 0.18 | 0.18 | 596 s | 114,900 / 0 / 27,080 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T06:20 | fail | 0.57 | 0.84 | 0.26 | 64 s | 8,800 / 470 | 0 | broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T06:46 | fail | 0.31 | 0.24 | 0.39 | 239 s | 9,200 / 1,400 | 0 | broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T08:13 | fail | 0.13 | 0.25 | 0.00 | 186 s | 10,000 / 729 | 0 | broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T08:01 | fail | 0.14 | 0.12 | 0.17 | 564 s | 32,000 / 533 | 0 | broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T08:42 | fail | 0.20 | 0.12 | 0.28 | 1802 s | 40,900 / 13,948 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T08:17 | fail | 0.13 | 0.25 | 0.00 | 722 s | 14,000 / 10,000 | 0 | broke an invariant |
