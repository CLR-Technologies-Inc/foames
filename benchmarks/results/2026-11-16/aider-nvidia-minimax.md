# aider-nvidia-minimax: benchmark run of 2026-11-16

<!-- Copyright 2026 CLR Technologies Inc. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T08:45:57+00:00, last run finished 2026-11-16T15:25:52+00:00
- **Model:** `nvidia_nim/minimaxai/minimax-m3.1-flash` (oss tier, built for agentic coding), API model id nvidia_nim/minimaxai/minimax-m3.1-flash, called 2026-11-16 (picked from the agent's candidates; the provider may update a model behind an unversioned id)
- nvidia_nim/minimaxai/minimax-m3.1-flash: HTTP 200
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner, model on the provider's free API tier; sandbox docker, image `sha256:88601bf5f75a`
- **FoaMES commit:** `684820cb9cec`, `90d9f6049e71`
- Aider on NVIDIA Build's free API (NIM, OpenAI-compatible); needs the NVIDIA_API_KEY Actions secret. Model family: agentic coding (MiniMax). The job picks the newest listed id that matches the candidates and answers a test call. About 40 requests a minute, shared by every NVIDIA agent, and NVIDIA logs prompts: send only public benchmark scenarios.

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 15 | 0% (0% to 20%) | 0.15 | 0.21 | 0.07 | 0.11 | 1563 s | 1,091,000 / 0 / 10,862 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T08:47 | fail | 0.51 | 0.84 | 0.14 | 100 s | 11,000 / 1,600 | 0 | broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T08:48 | fail | 0.26 | 0.24 | 0.28 | 45 s | 11,000 / 673 | 0 | broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T09:33 | fail | 0.13 | 0.25 | 0.00 | 2700 s | 0 / 0 | None | timed out, broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T09:39 | fail | 0.14 | 0.12 | 0.17 | 336 s | 29,000 / 671 | 0 | broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T09:39 | fail | 0.16 | 0.12 | 0.20 | 15 s | 11,000 / 124 | 0 | broke an invariant |
| sector-211-oil-gas (rep 1) | - | medium | 2026-11-16T10:39 | fail | 0.10 | 0.15 | 0.04 | 3600 s | 0 / 0 | None | timed out, broke an invariant |
| sector-212-mining (rep 1) | - | medium | 2026-11-16T11:26 | fail | 0.10 | 0.15 | 0.04 | 2832 s | 178,000 / 414 | 0 | broke an invariant |
| sector-2213-wastewater (rep 1) | - | medium | 2026-11-16T12:26 | fail | 0.10 | 0.15 | 0.04 | 3600 s | 0 / 0 | None | timed out, broke an invariant |
| sector-311-food (rep 1) | - | medium | 2026-11-16T12:33 | fail | 0.10 | 0.15 | 0.04 | 424 s | 178,000 / 1,600 | 0 | broke an invariant |
| sector-312-beverage (rep 1) | - | medium | 2026-11-16T12:50 | fail | 0.10 | 0.15 | 0.04 | 984 s | 166,000 / 687 | 0 | broke an invariant |
| sector-313-textile-mills (rep 1) | - | medium | 2026-11-16T12:51 | fail | 0.10 | 0.15 | 0.04 | 58 s | 169,000 / 555 | 0 | broke an invariant |
| sector-314-carpet (rep 1) | - | medium | 2026-11-16T13:10 | fail | 0.10 | 0.15 | 0.04 | 1129 s | 172,000 / 4,100 | 0 | broke an invariant |
| sector-315-apparel (rep 1) | - | medium | 2026-11-16T13:32 | fail | 0.10 | 0.15 | 0.04 | 1317 s | 166,000 / 438 | 0 | broke an invariant |
| sector-316-footwear (rep 1) | - | medium | 2026-11-16T14:32 | fail | 0.10 | 0.15 | 0.04 | 3600 s | 0 / 0 | None | timed out, broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T15:25 | fail | 0.13 | 0.25 | 0.00 | 2700 s | 0 / 0 | None | timed out, broke an invariant |
