# aider-ollama-qwen2.5-coder-1.5b: benchmark run of 2026-11-16

<!-- Copyright 2026 CLR Technologies Inc. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T04:47:38+00:00, last run finished 2026-11-16T10:14:51+00:00
- **Model:** `ollama_chat/qwen2.5-coder:1.5b` (oss tier, built for coding), Ollama qwen2.5-coder:1.5b digest d7372fd82851, pulled 2026-11-16
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner (4 vCPU, 15 GB, CPU only); sandbox docker, image `sha256:0b8ff0ab4234`, Ollama ollama version is 0.40.16
- **FoaMES commit:** `a5e355aa7bce`
- Aider with qwen2.5-coder:1.5b (Alibaba Qwen, Apache-2.0) served by Ollama on the same machine. Built for coding. Quality over speed: the timeout is thirteen times the task budget. Cost is electricity and time, recorded as $0.

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.25 | 0.30 | 0.19 | 0.19 | 4310 s | 211,900 / 0 / 17,637 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T04:56 | fail | 0.57 | 0.84 | 0.26 | 513 s | 33,600 / 92 | 0 | broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T10:14 | fail | 0.26 | 0.24 | 0.28 | 19500 s | 0 / 0 | None | timed out, broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T05:12 | fail | 0.19 | 0.25 | 0.11 | 1472 s | 48,200 / 4,000 | 0 | broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T05:28 | fail | 0.14 | 0.12 | 0.17 | 1202 s | 32,000 / 15 | 0 | broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T05:17 | fail | 0.16 | 0.12 | 0.20 | 192 s | 8,100 / 30 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T05:47 | fail | 0.19 | 0.25 | 0.11 | 2979 s | 90,000 / 13,500 | 0 | broke an invariant |
