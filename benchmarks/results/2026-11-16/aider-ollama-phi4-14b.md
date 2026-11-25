# aider-ollama-phi4-14b: benchmark run of 2026-11-16

<!-- Copyright 2026 CLR Technologies Inc. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T05:21:28+00:00, last run finished 2026-11-16T11:39:55+00:00
- **Model:** `ollama_chat/phi4:14b` (oss tier, built for general chat (off-label)), Ollama phi4:14b digest ac896e5b8b34, pulled 2026-11-16
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner (4 vCPU, 15 GB, CPU only); sandbox docker, image `sha256:142b29b34596`, Ollama ollama version is 0.40.16
- **FoaMES commit:** `a5e355aa7bce`
- Aider with phi4:14b (Microsoft, MIT) served by Ollama on the same machine. Built for general chat, so it is off-label for agentic coding. Quality over speed: the timeout is thirteen times the task budget. Cost is electricity and time, recorded as $0.

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.22 | 0.30 | 0.13 | 0.17 | 5757 s | 58,996 / 0 / 7,194 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T08:27 | fail | 0.51 | 0.84 | 0.14 | 7508 s | 19,100 / 2,287 | 0 | broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T11:39 | fail | 0.26 | 0.24 | 0.28 | 19500 s | 8,500 / 679 | None | timed out, broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T07:53 | fail | 0.13 | 0.25 | 0.00 | 2702 s | 9,300 / 962 | 0 | broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T05:27 | fail | 0.14 | 0.12 | 0.17 | 337 s | 896 / 1,100 | 0 | broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T07:17 | fail | 0.16 | 0.12 | 0.20 | 1958 s | 8,200 / 1,200 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T07:56 | fail | 0.13 | 0.25 | 0.00 | 2536 s | 13,000 / 966 | 0 | broke an invariant |
