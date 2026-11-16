# aider-nvidia-nemotron: benchmark run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T08:35:04+00:00, last run finished 2026-11-16T08:59:33+00:00
- **Model:** `nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b` (oss tier, built for reasoning (off-label)), API model id nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b, called 2026-11-16 (picked from the agent's candidates; the provider may update a model behind an unversioned id)
- nvidia_nim/nvidia/nemotron-3-ultra-550b-a55b: HTTP 200
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner, model on the provider's free API tier; sandbox docker, image `sha256:17dc0cdbb1bc`
- **FoaMES commit:** `b568443e65e3`
- Aider on NVIDIA Build's free API (NIM, OpenAI-compatible); needs the NVIDIA_API_KEY Actions secret. Model family: reasoning (NVIDIA Nemotron). The job picks the newest listed id that matches the candidates and answers a test call. About 40 requests a minute, shared by every NVIDIA agent, and NVIDIA logs prompts: send only public benchmark scenarios.

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.24 | 0.30 | 0.16 | 0.18 | 243 s | 136,900 / 0 / 24,239 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T08:42 | fail | 0.51 | 0.84 | 0.14 | 468 s | 27,400 / 8,375 | 0 | broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T08:43 | fail | 0.26 | 0.24 | 0.28 | 11 s | 8,800 / 225 | 0 | broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T08:44 | fail | 0.13 | 0.25 | 0.00 | 64 s | 9,700 / 3,200 | 0 | broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T08:44 | fail | 0.21 | 0.12 | 0.32 | 43 s | 34,000 / 1,500 | 0 | broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T08:45 | fail | 0.16 | 0.12 | 0.20 | 36 s | 18,000 / 1,481 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T08:59 | fail | 0.13 | 0.25 | 0.00 | 838 s | 39,000 / 9,458 | 0 | broke an invariant |
