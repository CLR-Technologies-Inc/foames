# aider-ollama-deepcoder-14b: benchmark run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T04:48:10+00:00, last run finished 2026-11-16T10:13:56+00:00
- **Model:** `ollama_chat/deepcoder:14b` (oss tier, built for coding), Ollama deepcoder:14b digest 12bdda054d23, pulled 2026-11-16
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner (4 vCPU, 15 GB, CPU only); sandbox docker, image `sha256:2c5f2c9986fb`, Ollama ollama version is 0.40.16
- **FoaMES commit:** `a5e355aa7bce`
- Aider with deepcoder:14b (Agentica, MIT) served by Ollama on the same machine. Built for coding. Quality over speed: the timeout is thirteen times the task budget. Cost is electricity and time, recorded as $0.
- Workflow run: https://github.com/CLR-Technologies-Inc/foames/actions/runs/43805918094

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.19 | 0.22 | 0.16 | 0.14 | 13650 s | 111,700 / 0 / 19,300 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T07:30 | fail | 0.51 | 0.84 | 0.14 | 7800 s | 8,000 / 1,300 | None | timed out, broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T10:13 | fail | 0.07 | 0.00 | 0.15 | 19500 s | 36,300 / 5,500 | None | timed out, broke an invariant, regression tests 0% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T08:04 | fail | 0.19 | 0.22 | 0.15 | 11700 s | 35,300 / 7,600 | None | timed out, broke an invariant, regression tests 87% |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T08:03 | fail | 0.14 | 0.12 | 0.17 | 11700 s | 0 / 0 | None | timed out, broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T10:13 | fail | 0.16 | 0.12 | 0.20 | 19500 s | 8,100 / 1,600 | None | timed out, broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T08:03 | fail | 0.07 | 0.00 | 0.15 | 11700 s | 24,000 / 3,300 | None | timed out, broke an invariant, regression tests 0% |
