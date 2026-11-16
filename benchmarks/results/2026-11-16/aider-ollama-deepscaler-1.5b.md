# aider-ollama-deepscaler-1.5b: benchmark run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T07:56:08+00:00, last run finished 2026-11-16T13:48:07+00:00
- **Model:** `ollama_chat/deepscaler:1.5b` (oss tier, built for domain: maths reasoning (off-label)), Ollama deepscaler:1.5b digest 0031bcf7459f, pulled 2026-11-16
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner (4 vCPU, 15 GB, CPU only); sandbox docker, image `sha256:06311ad01581`, Ollama ollama version is 0.40.16
- **FoaMES commit:** `a5e355aa7bce`
- Aider with deepscaler:1.5b (Agentica, MIT) served by Ollama on the same machine. Built for domain: maths reasoning, so it is off-label for agentic coding. Quality over speed: the timeout is thirteen times the task budget. Cost is electricity and time, recorded as $0.

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.22 | 0.30 | 0.13 | 0.17 | 5920 s | 79,200 / 0 / 8,042 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T08:29 | fail | 0.51 | 0.84 | 0.14 | 685 s | 19,000 / 1,642 | 0 | broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T13:48 | fail | 0.26 | 0.24 | 0.28 | 19500 s | 0 / 0 | None | timed out, broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T08:31 | fail | 0.13 | 0.25 | 0.00 | 466 s | 9,200 / 1,300 | 0 | broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T08:34 | fail | 0.14 | 0.12 | 0.17 | 2300 s | 32,000 / 2,100 | 0 | broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T08:21 | fail | 0.16 | 0.12 | 0.20 | 866 s | 19,000 / 3,000 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T11:35 | fail | 0.13 | 0.25 | 0.00 | 11700 s | 0 / 0 | None | timed out, broke an invariant |
