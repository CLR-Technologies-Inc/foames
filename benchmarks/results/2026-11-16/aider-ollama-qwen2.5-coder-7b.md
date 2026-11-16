# aider-ollama-qwen2.5-coder-7b: benchmark run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T03:13:59+00:00, last run finished 2026-11-16T06:29:14+00:00
- **Model:** `ollama_chat/qwen2.5-coder:7b` (oss tier, built for coding), Ollama qwen2.5-coder:7b digest dae161e27b0e, pulled 2026-11-16
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner (4 vCPU, 15 GB, CPU only); sandbox docker, image `sha256:08fc17ca1cf5`, Ollama ollama version is 0.40.16
- **FoaMES commit:** `a1c95f786e96`
- Aider with qwen2.5-coder:7b (Alibaba Qwen, Apache-2.0) served by Ollama on the same machine. Quality over speed: the timeout is ten times the task budget. Cost is electricity and time, recorded as $0.

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.22 | 0.30 | 0.13 | 0.17 | 4846 s | 118,200 / 0 / 12,424 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T03:50 | fail | 0.51 | 0.84 | 0.14 | 2179 s | 17,900 / 1,235 | 0 | broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T03:51 | fail | 0.26 | 0.24 | 0.28 | 2221 s | 25,400 / 1,634 | 0 | broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T03:50 | fail | 0.13 | 0.25 | 0.00 | 2187 s | 22,200 / 2,317 | 0 | broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T06:29 | fail | 0.14 | 0.12 | 0.17 | 11700 s | 0 / 0 | None | timed out, broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T03:44 | fail | 0.16 | 0.12 | 0.20 | 1756 s | 17,700 / 802 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T05:45 | fail | 0.13 | 0.25 | 0.00 | 9031 s | 35,000 / 6,436 | 0 | broke an invariant |
