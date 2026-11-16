# aider-nvidia-glm: benchmark run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T08:39:25+00:00, last run finished 2026-11-16T13:54:34+00:00
- **Model:** `nvidia_nim/z-ai/glm-5.3-flash` (oss tier, built for agentic coding), API model id nvidia_nim/z-ai/glm-5.3-flash, called 2026-11-16 (picked from the agent's candidates; the provider may update a model behind an unversioned id)
- nvidia_nim/z-ai/glm-5.3-flash: HTTP 200
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner, model on the provider's free API tier; sandbox docker, image `sha256:39abefad8f8f`
- **FoaMES commit:** `b568443e65e3`
- Aider on NVIDIA Build's free API (NIM, OpenAI-compatible); needs the NVIDIA_API_KEY Actions secret. Model family: agentic coding (Zhipu GLM). The job picks the newest listed id that matches the candidates and answers a test call. About 40 requests a minute, shared by every NVIDIA agent, and NVIDIA logs prompts: send only public benchmark scenarios.

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.22 | 0.30 | 0.13 | 0.17 | 3150 s | 24,400 / 0 / 8,267 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T09:09 | fail | 0.51 | 0.84 | 0.14 | 1800 s | 8,000 / 867 | None | timed out, broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T10:24 | fail | 0.26 | 0.24 | 0.28 | 4500 s | 8,300 / 1,700 | None | timed out, broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T11:09 | fail | 0.13 | 0.25 | 0.00 | 2700 s | 0 / 0 | None | timed out, broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T11:54 | fail | 0.14 | 0.12 | 0.17 | 2700 s | 0 / 0 | None | timed out, broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T13:09 | fail | 0.16 | 0.12 | 0.20 | 4500 s | 8,100 / 5,700 | None | timed out, broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T13:54 | fail | 0.13 | 0.25 | 0.00 | 2700 s | 0 / 0 | None | timed out, broke an invariant |
