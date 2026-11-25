# aider-ollama-gpt-oss-20b: benchmark run of 2026-11-16

<!-- Copyright 2026 CLR Technologies Inc. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T03:14:41+00:00, last run finished 2026-11-16T06:29:44+00:00
- **Model:** `ollama_chat/gpt-oss:20b` (oss tier, built for reasoning (off-label)), Ollama gpt-oss:20b digest f38aa0c53da5, pulled 2026-11-16
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner (4 vCPU, 15 GB, CPU only); sandbox docker, image `sha256:1907f14a81a2`, Ollama ollama version is 0.40.16
- **FoaMES commit:** `a1c95f786e96`
- Aider with gpt-oss:20b (OpenAI, Apache-2.0) served by Ollama on the same machine. Quality over speed: the timeout is ten times the task budget. Cost is electricity and time, recorded as $0.

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 17% (3% to 56%) | 0.48 | 0.46 | 0.52 | 0.38 | 4404 s | 81,700 / 0 / 27,055 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T04:04 | PASS | 0.91 | 1.00 | 0.80 | 2879 s | 16,900 / 3,755 | 0 |  |
| erp-retry-after (rep 1) | - | high | 2026-11-16T03:34 | fail | 0.26 | 0.24 | 0.28 | 1136 s | 8,400 / 3,300 | 0 | broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T04:59 | fail | 0.78 | 0.86 | 0.68 | 6247 s | 9,300 / 6,300 | 0 | broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T04:07 | fail | 0.36 | 0.12 | 0.63 | 3088 s | 26,000 / 2,300 | 0 | broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T03:38 | fail | 0.47 | 0.25 | 0.72 | 1377 s | 8,100 / 4,600 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T06:29 | fail | 0.13 | 0.25 | 0.00 | 11700 s | 13,000 / 6,800 | None | timed out, broke an invariant |
