# aider-nvidia-laguna: benchmark run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T08:40:57+00:00, last run finished 2026-11-16T14:06:49+00:00
- **Model:** `nvidia_nim/poolside/laguna-xs-2.1` (oss tier, built for coding)
- **Harness:** aider
- **Where it ran:** GitHub-hosted runner; sandbox docker
- **FoaMES commit:** `711c83b57a8e`
- Aider on NVIDIA Build's free API (NIM, OpenAI-compatible); needs the NVIDIA_API_KEY Actions secret. Model family: coding (Poolside Laguna). The job picks the newest listed id that matches the candidates and answers a test call. About 40 requests a minute, shared by every NVIDIA agent, and NVIDIA logs prompts: send only public benchmark scenarios.

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 12 | 0% (0% to 24%) | 0.16 | 0.22 | 0.09 | 0.12 | 1627 s | 1,103,000 / 0 / 14,551 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T09:10 | fail | 0.51 | 0.84 | 0.14 | 1800 s | 11,000 / 797 | None | timed out, broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T09:11 | fail | 0.26 | 0.24 | 0.28 | 13 s | 30,000 / 210 | 0 | broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T09:26 | fail | 0.13 | 0.25 | 0.00 | 933 s | 26,000 / 283 | 0 | broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T09:37 | fail | 0.14 | 0.12 | 0.17 | 631 s | 35,000 / 46 | 0 | broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T10:18 | fail | 0.16 | 0.12 | 0.20 | 2441 s | 11,000 / 87 | 0 | broke an invariant |
| sector-211-oil-gas (rep 1) | - | medium | 2026-11-16T10:43 | fail | 0.13 | 0.15 | 0.11 | 1543 s | 200,000 / 13,000 | 0 | broke an invariant |
| sector-212-mining (rep 1) | - | medium | 2026-11-16T10:44 | fail | 0.10 | 0.15 | 0.04 | 62 s | 229,000 / 63 | 0 | broke an invariant |
| sector-2213-wastewater (rep 1) | - | medium | 2026-11-16T10:45 | fail | 0.10 | 0.15 | 0.04 | 38 s | 331,000 / 0 | 0 | broke an invariant |
| sector-311-food (rep 1) | - | medium | 2026-11-16T11:45 | fail | 0.10 | 0.15 | 0.04 | 3600 s | 0 / 0 | None | timed out, broke an invariant |
| sector-312-beverage (rep 1) | - | medium | 2026-11-16T12:45 | fail | 0.10 | 0.15 | 0.04 | 3600 s | 0 / 0 | None | timed out, broke an invariant |
| sector-313-textile-mills (rep 1) | - | medium | 2026-11-16T13:45 | fail | 0.10 | 0.15 | 0.04 | 3600 s | 0 / 0 | None | timed out, broke an invariant |
| sector-314-carpet (rep 1) | - | medium | 2026-11-16T14:06 | fail | 0.10 | 0.15 | 0.04 | 1259 s | 230,000 / 65 | 0 | broke an invariant |
