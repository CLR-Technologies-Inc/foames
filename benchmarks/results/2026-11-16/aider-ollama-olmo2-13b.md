# aider-ollama-olmo2-13b: benchmark run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T05:33:26+00:00, last run finished 2026-11-16T07:02:42+00:00
- **Model:** `ollama_chat/olmo2:13b` (oss tier, built for general chat (fully open data) (off-label)), Ollama olmo2:13b digest 6c279ebc980f, pulled 2026-11-16
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner (4 vCPU, 15 GB, CPU only); sandbox docker, image `sha256:0a2303cbea9e`, Ollama ollama version is 0.40.16
- **FoaMES commit:** `a5e355aa7bce`
- Aider with olmo2:13b (Allen Institute for AI, Apache-2.0) served by Ollama on the same machine. Built for general chat (fully open data), so it is off-label for agentic coding. Quality over speed: the timeout is thirteen times the task budget. Cost is electricity and time, recorded as $0.

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.23 | 0.30 | 0.14 | 0.17 | 522 s | 7,784 / 0 / 5,949 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T06:41 | fail | 0.55 | 0.84 | 0.22 | 884 s | 1,222 / 1,379 | 0 | broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T05:46 | fail | 0.26 | 0.24 | 0.28 | 795 s | 3,048 / 1,587 | 0 | broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T07:02 | fail | 0.13 | 0.25 | 0.00 | 407 s | 892 / 718 | 0 | broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T06:20 | fail | 0.14 | 0.12 | 0.17 | 250 s | 894 / 842 | 0 | broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T06:14 | fail | 0.16 | 0.12 | 0.20 | 301 s | 777 / 606 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T06:49 | fail | 0.13 | 0.25 | 0.00 | 494 s | 951 / 817 | 0 | broke an invariant |
