# aider-ollama-phi4-mini-3.8b: benchmark run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T05:31:21+00:00, last run finished 2026-11-16T12:21:28+00:00
- **Model:** `ollama_chat/phi4-mini:3.8b` (oss tier, built for tiny (off-label)), Ollama phi4-mini:3.8b digest 78fad5d182a7, pulled 2026-11-16
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner (4 vCPU, 15 GB, CPU only); sandbox docker, image `sha256:215285cb2546`, Ollama ollama version is 0.40.16
- **FoaMES commit:** `a5e355aa7bce`
- Aider with phi4-mini:3.8b (Microsoft, MIT) served by Ollama on the same machine. Built for tiny, so it is off-label for agentic coding. Quality over speed: the timeout is thirteen times the task budget. Cost is electricity and time, recorded as $0.

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.25 | 0.30 | 0.18 | 0.19 | 11063 s | 40,200 / 0 / 7,100 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T07:43 | fail | 0.51 | 0.84 | 0.14 | 7800 s | 0 / 0 | None | timed out, broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T10:56 | fail | 0.26 | 0.24 | 0.28 | 19500 s | 0 / 0 | None | timed out, broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T07:32 | fail | 0.23 | 0.25 | 0.21 | 954 s | 9,200 / 1,400 | 0 | broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T10:28 | fail | 0.14 | 0.12 | 0.17 | 11700 s | 0 / 0 | None | timed out, broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T12:21 | fail | 0.16 | 0.12 | 0.20 | 19500 s | 0 / 0 | None | timed out, broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T09:30 | fail | 0.19 | 0.25 | 0.11 | 6922 s | 31,000 / 5,700 | 0 | broke an invariant |
