# aider-ollama-meditron-7b: benchmark run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T07:55:08+00:00, last run finished 2026-11-16T08:21:59+00:00
- **Model:** `ollama_chat/meditron:7b` (oss tier, built for domain: medicine (off-label)), Ollama meditron:7b digest ad11a6250f54, pulled 2026-11-16
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner (4 vCPU, 15 GB, CPU only); sandbox docker, image `sha256:2cc683c7bc57`, Ollama ollama version is 0.40.16
- **FoaMES commit:** `a5e355aa7bce`
- Aider with meditron:7b (EPFL, Llama 2 Community License) served by Ollama on the same machine. Built for domain: medicine, so it is off-label for agentic coding. Quality over speed: the timeout is thirteen times the task budget. Cost is electricity and time, recorded as $0.
- Workflow run: https://github.com/CLR-Technologies-Inc/foames/actions/runs/43805918094

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.22 | 0.30 | 0.13 | 0.17 | 67 s | 6,437 / 0 / 42 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T08:03 | fail | 0.51 | 0.84 | 0.14 | 50 s | 868 / 7 | 0 | broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T08:00 | fail | 0.26 | 0.24 | 0.28 | 111 s | 1,200 / 7 | 0 | broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T08:09 | fail | 0.13 | 0.25 | 0.00 | 64 s | 1,100 / 7 | 0 | broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T07:56 | fail | 0.14 | 0.12 | 0.17 | 81 s | 1,100 / 7 | 0 | broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T08:21 | fail | 0.16 | 0.12 | 0.20 | 56 s | 969 / 7 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T07:58 | fail | 0.13 | 0.25 | 0.00 | 41 s | 1,200 / 7 | 0 | broke an invariant |
