# aider-ollama-granite-code-8b: benchmark run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T04:47:33+00:00, last run finished 2026-11-16T07:12:10+00:00
- **Model:** `ollama_chat/granite-code:8b` (oss tier, built for coding), Ollama granite-code:8b digest 36c3c3b9683b, pulled 2026-11-16
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner (4 vCPU, 15 GB, CPU only); sandbox docker, image `sha256:488337d161dc`, Ollama ollama version is 0.40.16
- **FoaMES commit:** `a5e355aa7bce`
- Aider with granite-code:8b (IBM, Apache-2.0) served by Ollama on the same machine. Built for coding. Quality over speed: the timeout is thirteen times the task budget. Cost is electricity and time, recorded as $0.
- Workflow run: https://github.com/CLR-Technologies-Inc/foames/actions/runs/43805918094

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.22 | 0.30 | 0.13 | 0.17 | 3534 s | 76,500 / 0 / 2,925 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T06:57 | fail | 0.51 | 0.84 | 0.14 | 7800 s | 0 / 0 | None | timed out, broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T05:02 | fail | 0.26 | 0.24 | 0.28 | 793 s | 9,400 / 14 | 0 | broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T05:04 | fail | 0.13 | 0.25 | 0.00 | 939 s | 10,000 / 1,300 | 0 | broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T07:12 | fail | 0.14 | 0.12 | 0.17 | 8655 s | 34,000 / 484 | 0 | broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T04:55 | fail | 0.16 | 0.12 | 0.20 | 484 s | 9,100 / 628 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T05:29 | fail | 0.13 | 0.25 | 0.00 | 2531 s | 14,000 / 499 | 0 | broke an invariant |
