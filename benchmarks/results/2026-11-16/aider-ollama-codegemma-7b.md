# aider-ollama-codegemma-7b: benchmark run of 2026-11-16

<!-- Copyright 2026 CLR Technologies Inc. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T04:47:30+00:00, last run finished 2026-11-16T05:18:12+00:00
- **Model:** `ollama_chat/codegemma:7b` (oss tier, built for coding), Ollama codegemma:7b digest 0c96700aaada, pulled 2026-11-16
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner (4 vCPU, 15 GB, CPU only); sandbox docker, image `sha256:26f6de7177f5`, Ollama ollama version is 0.40.16
- **FoaMES commit:** `a5e355aa7bce`
- Aider with codegemma:7b (Google, Gemma Terms of Use) served by Ollama on the same machine. Built for coding. Quality over speed: the timeout is thirteen times the task budget. Cost is electricity and time, recorded as $0.

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.22 | 0.30 | 0.13 | 0.17 | 300 s | 28,660 / 0 / 1,711 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T04:52 | fail | 0.51 | 0.84 | 0.14 | 281 s | 7,500 / 58 | 0 | broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T04:55 | fail | 0.26 | 0.24 | 0.28 | 415 s | 10,700 / 504 | 0 | broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T04:51 | fail | 0.13 | 0.25 | 0.00 | 163 s | 981 / 210 | 0 | broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T04:50 | fail | 0.14 | 0.12 | 0.17 | 159 s | 979 / 336 | 0 | broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T05:18 | fail | 0.16 | 0.12 | 0.20 | 681 s | 7,500 / 428 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T04:49 | fail | 0.13 | 0.25 | 0.00 | 103 s | 1,000 / 175 | 0 | broke an invariant |
