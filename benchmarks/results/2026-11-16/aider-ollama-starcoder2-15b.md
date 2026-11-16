# aider-ollama-starcoder2-15b: benchmark run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T04:47:54+00:00, last run finished 2026-11-16T10:14:26+00:00
- **Model:** `ollama_chat/starcoder2:15b` (oss tier, built for coding (base model, not tuned for chat)), Ollama starcoder2:15b digest 21ae152d49e0, pulled 2026-11-16
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner (4 vCPU, 15 GB, CPU only); sandbox docker, image `sha256:18e05477851a`, Ollama ollama version is 0.40.16
- **FoaMES commit:** `a5e355aa7bce`
- Aider with starcoder2:15b (BigCode, BigCode OpenRAIL-M) served by Ollama on the same machine. Built for coding (base model, not tuned for chat). Quality over speed: the timeout is thirteen times the task budget. Cost is electricity and time, recorded as $0.

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.22 | 0.30 | 0.13 | 0.17 | 11841 s | 693 / 0 / 2,100 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T07:04 | fail | 0.51 | 0.84 | 0.14 | 7800 s | 0 / 0 | None | timed out, broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T10:12 | fail | 0.26 | 0.24 | 0.28 | 19500 s | 0 / 0 | None | timed out, broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T08:03 | fail | 0.13 | 0.25 | 0.00 | 11700 s | 0 / 0 | None | timed out, broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T05:07 | fail | 0.14 | 0.12 | 0.17 | 843 s | 693 / 2,100 | 0 | broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T10:14 | fail | 0.16 | 0.12 | 0.20 | 19500 s | 0 / 0 | None | timed out, broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T08:07 | fail | 0.13 | 0.25 | 0.00 | 11700 s | 0 / 0 | None | timed out, broke an invariant |
