# aider-nvidia-deepseek: benchmark run of 2026-11-16

<!-- Copyright 2026 CLR Technologies Inc. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T08:47:40+00:00, last run finished 2026-11-16T15:28:57+00:00
- **Model:** `nvidia_nim/deepseek-ai/deepseek-v4.1-flash` (oss tier, built for coding and general), API model id nvidia_nim/deepseek-ai/deepseek-v4.1-flash, called 2026-11-16 (picked from the agent's candidates; the provider may update a model behind an unversioned id)
- nvidia_nim/deepseek-ai/deepseek-v4.1-flash: HTTP timeout TimeoutError: The read operation timed out
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner, model on the provider's free API tier; sandbox docker, image `sha256:edfb3f0a1e69`
- **FoaMES commit:** `711c83b57a8e`, `90d9f6049e71`
- Aider on NVIDIA Build's free API (NIM, OpenAI-compatible); needs the NVIDIA_API_KEY Actions secret. Model family: coding and general (DeepSeek). The job picks the newest listed id that matches the candidates and answers a test call. About 40 requests a minute, shared by every NVIDIA agent, and NVIDIA logs prompts: send only public benchmark scenarios.

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 9 | 0% (0% to 30%) | 0.18 | 0.26 | 0.10 | 0.14 | 2497 s | 23,000 / 0 / 378 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T09:17 | fail | 0.51 | 0.84 | 0.14 | 1800 s | 0 / 0 | None | timed out, broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T09:37 | fail | 0.26 | 0.24 | 0.28 | 1175 s | 12,000 / 170 | 0 | broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T10:22 | fail | 0.13 | 0.25 | 0.00 | 2700 s | 0 / 0 | None | timed out, broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T11:07 | fail | 0.14 | 0.12 | 0.17 | 2700 s | 0 / 0 | None | timed out, broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T11:17 | fail | 0.16 | 0.12 | 0.20 | 599 s | 11,000 / 208 | 0 | broke an invariant |
| sector-211-oil-gas (rep 1) | - | medium | 2026-11-16T12:17 | fail | 0.10 | 0.15 | 0.04 | 3600 s | 0 / 0 | None | timed out, broke an invariant |
| sector-212-mining (rep 1) | - | medium | 2026-11-16T13:17 | fail | 0.10 | 0.15 | 0.04 | 3600 s | 0 / 0 | None | timed out, broke an invariant |
| sector-2213-wastewater (rep 1) | - | medium | 2026-11-16T14:17 | fail | 0.10 | 0.15 | 0.04 | 3600 s | 0 / 0 | None | timed out, broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T15:28 | fail | 0.13 | 0.25 | 0.00 | 2700 s | 0 / 0 | None | timed out, broke an invariant |
