# aider-nvidia-laguna: benchmark run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T08:40:57+00:00, last run finished 2026-11-16T20:04:29+00:00
- **Model:** `nvidia_nim/poolside/laguna-xs-2.1` (oss tier, built for coding), API model id nvidia_nim/poolside/laguna-xs-2.1, called 2026-11-16 (picked from the agent's candidates; the provider may update a model behind an unversioned id)
- nvidia_nim/poolside/laguna-xs-2.1: HTTP 200
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner, model on the provider's free API tier; sandbox docker, image `sha256:8c67795b97e9`
- **FoaMES commit:** `1a844a1fd738`, `46a75d6abb2f`, `711c83b57a8e`, `d3d465fd3689`
- Aider on NVIDIA Build's free API (NIM, OpenAI-compatible); needs the NVIDIA_API_KEY Actions secret. Model family: coding (Poolside Laguna). The job picks the newest listed id that matches the candidates and answers a test call. About 40 requests a minute, shared by every NVIDIA agent, and NVIDIA logs prompts: send only public benchmark scenarios.

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 28 | 0% (0% to 12%) | 0.16 | 0.21 | 0.10 | 0.12 | 2045 s | 2,657,000 / 0 / 47,658 | $0.00 | n/a | none |

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
| sector-315-apparel (rep 1) | - | medium | 2026-11-16T15:09 | fail | 0.11 | 0.15 | 0.06 | 1732 s | 211,000 / 4,000 | 0 | broke an invariant |
| sector-326-plastics (rep 1) | - | medium | 2026-11-16T14:58 | fail | 0.13 | 0.15 | 0.11 | 1037 s | 220,000 / 3,700 | 0 | broke an invariant |
| sector-3272-glass (rep 1) | - | medium | 2026-11-16T15:04 | fail | 0.10 | 0.15 | 0.04 | 349 s | 225,000 / 65 | 0 | broke an invariant |
| sector-3273-cement (rep 1) | - | medium | 2026-11-16T16:04 | fail | 0.10 | 0.15 | 0.04 | 3600 s | 0 / 0 | None | timed out, broke an invariant |
| sector-331-aluminum (rep 1) | - | medium | 2026-11-16T17:04 | fail | 0.10 | 0.15 | 0.04 | 3600 s | 0 / 0 | None | timed out, broke an invariant |
| sector-3315-foundry (rep 1) | - | medium | 2026-11-16T18:04 | fail | 0.10 | 0.15 | 0.04 | 3600 s | 0 / 0 | None | timed out, broke an invariant |
| sector-332-forging (rep 1) | - | medium | 2026-11-16T19:04 | fail | 0.13 | 0.15 | 0.11 | 3600 s | 0 / 0 | None | timed out, broke an invariant |
| sector-332-machine-shop (rep 1) | - | medium | 2026-11-16T20:04 | fail | 0.10 | 0.15 | 0.04 | 3600 s | 0 / 0 | None | timed out, broke an invariant |
| sector-333-machinery (rep 1) | - | medium | 2026-11-16T15:25 | fail | 0.18 | 0.15 | 0.21 | 2613 s | 217,000 / 4,900 | 0 | broke an invariant |
| sector-3344-semiconductors (rep 1) | - | medium | 2026-11-16T15:31 | fail | 0.10 | 0.15 | 0.04 | 348 s | 215,000 / 66 | 0 | broke an invariant |
| sector-335-electrical-equipment (rep 1) | - | medium | 2026-11-16T15:37 | fail | 0.10 | 0.15 | 0.04 | 374 s | 211,000 / 76 | 0 | broke an invariant |
| sector-3361-motor-vehicles (rep 1) | - | medium | 2026-11-16T16:37 | fail | 0.10 | 0.15 | 0.04 | 3600 s | 0 / 0 | None | timed out, broke an invariant |
| sector-3364-aerospace (rep 1) | - | medium | 2026-11-16T17:37 | fail | 0.10 | 0.15 | 0.04 | 3600 s | 0 / 0 | None | timed out, broke an invariant |
| sector-337-furniture (rep 1) | - | medium | 2026-11-16T17:39 | fail | 0.13 | 0.15 | 0.11 | 143 s | 211,000 / 2,900 | 0 | broke an invariant |
| sector-3391-medical-devices (rep 1) | - | medium | 2026-11-16T18:39 | fail | 0.10 | 0.15 | 0.04 | 3600 s | 0 / 0 | None | timed out, broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T15:48 | fail | 0.79 | 0.87 | 0.70 | 2349 s | 44,000 / 17,400 | 0 | broke an invariant, regression tests 90% |
