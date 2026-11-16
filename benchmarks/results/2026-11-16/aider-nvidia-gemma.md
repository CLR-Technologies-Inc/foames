# aider-nvidia-gemma: benchmark run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T08:46:39+00:00, last run finished 2026-11-16T15:37:42+00:00
- **Model:** `nvidia_nim/google/gemma-4-31b-it` (oss tier, built for general chat (off-label)), API model id nvidia_nim/google/gemma-4-31b-it, called 2026-11-16 (picked from the agent's candidates; the provider may update a model behind an unversioned id)
- nvidia_nim/google/gemma-4-31b-it: HTTP timeout TimeoutError: The read operation timed out
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner, model on the provider's free API tier; sandbox docker, image `sha256:1fea8f92849d`
- **FoaMES commit:** `1a844a1fd738`, `711c83b57a8e`, `90d9f6049e71`, `d3d465fd3689`
- Aider on NVIDIA Build's free API (NIM, OpenAI-compatible); needs the NVIDIA_API_KEY Actions secret. Model family: general chat (Google Gemma). The job picks the newest listed id that matches the candidates and answers a test call. About 40 requests a minute, shared by every NVIDIA agent, and NVIDIA logs prompts: send only public benchmark scenarios.

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 28 | 4% (1% to 18%) | 0.20 | 0.26 | 0.15 | 0.16 | 940 s | 116,000 / 0 / 20,749 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T09:16 | PASS | 1.00 | 1.00 | 1.00 | 1800 s | 26,000 / 3,576 | None | timed out |
| erp-retry-after (rep 1) | - | high | 2026-11-16T09:55 | fail | 0.26 | 0.24 | 0.28 | 2350 s | 12,000 / 773 | 0 | broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T10:40 | fail | 0.84 | 0.93 | 0.74 | 2700 s | 13,000 / 4,000 | None | timed out, broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T11:03 | fail | 0.41 | 0.36 | 0.47 | 1338 s | 36,000 / 2,400 | 0 | broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T11:39 | fail | 0.90 | 1.00 | 0.79 | 2160 s | 12,000 / 2,400 | 0 | broke an invariant |
| sector-211-oil-gas (rep 1) | - | medium | 2026-11-16T12:39 | fail | 0.10 | 0.15 | 0.04 | 3600 s | 0 / 0 | None | timed out, broke an invariant |
| sector-212-mining (rep 1) | - | medium | 2026-11-16T12:48 | fail | 0.10 | 0.15 | 0.04 | 533 s | 0 / 0 | 0 | broke an invariant |
| sector-2213-wastewater (rep 1) | - | medium | 2026-11-16T12:58 | fail | 0.10 | 0.15 | 0.04 | 592 s | 0 / 0 | 0 | broke an invariant |
| sector-311-food (rep 1) | - | medium | 2026-11-16T13:12 | fail | 0.10 | 0.15 | 0.04 | 867 s | 0 / 0 | 0 | broke an invariant |
| sector-312-beverage (rep 1) | - | medium | 2026-11-16T13:20 | fail | 0.10 | 0.15 | 0.04 | 451 s | 0 / 0 | 0 | broke an invariant |
| sector-313-textile-mills (rep 1) | - | medium | 2026-11-16T13:24 | fail | 0.10 | 0.15 | 0.04 | 272 s | 0 / 0 | 0 | broke an invariant |
| sector-314-carpet (rep 1) | - | medium | 2026-11-16T13:28 | fail | 0.10 | 0.15 | 0.04 | 211 s | 0 / 0 | 0 | broke an invariant |
| sector-315-apparel (rep 1) | - | medium | 2026-11-16T13:38 | fail | 0.10 | 0.15 | 0.04 | 603 s | 0 / 0 | 0 | broke an invariant |
| sector-326-plastics (rep 1) | - | medium | 2026-11-16T14:57 | fail | 0.10 | 0.15 | 0.04 | 802 s | 0 / 0 | 0 | broke an invariant |
| sector-3272-glass (rep 1) | - | medium | 2026-11-16T15:05 | fail | 0.10 | 0.15 | 0.04 | 479 s | 0 / 0 | 0 | broke an invariant |
| sector-3273-cement (rep 1) | - | medium | 2026-11-16T15:10 | fail | 0.10 | 0.15 | 0.04 | 279 s | 0 / 0 | 0 | broke an invariant |
| sector-331-aluminum (rep 1) | - | medium | 2026-11-16T15:14 | fail | 0.10 | 0.15 | 0.04 | 276 s | 0 / 0 | 0 | broke an invariant |
| sector-3315-foundry (rep 1) | - | medium | 2026-11-16T15:24 | fail | 0.10 | 0.15 | 0.04 | 596 s | 0 / 0 | 0 | broke an invariant |
| sector-332-forging (rep 1) | - | medium | 2026-11-16T15:34 | fail | 0.13 | 0.15 | 0.11 | 566 s | 0 / 0 | 0 | broke an invariant |
| sector-332-machine-shop (rep 1) | - | medium | 2026-11-16T15:37 | fail | 0.10 | 0.15 | 0.04 | 217 s | 0 / 0 | 0 | broke an invariant |
| sector-333-machinery (rep 1) | - | medium | 2026-11-16T14:48 | fail | 0.10 | 0.15 | 0.04 | 266 s | 0 / 0 | 0 | broke an invariant |
| sector-3344-semiconductors (rep 1) | - | medium | 2026-11-16T14:52 | fail | 0.10 | 0.15 | 0.04 | 261 s | 0 / 0 | 0 | broke an invariant |
| sector-335-electrical-equipment (rep 1) | - | medium | 2026-11-16T14:55 | fail | 0.10 | 0.15 | 0.04 | 174 s | 0 / 0 | 0 | broke an invariant |
| sector-3361-motor-vehicles (rep 1) | - | medium | 2026-11-16T15:04 | fail | 0.10 | 0.15 | 0.04 | 492 s | 0 / 0 | 0 | broke an invariant |
| sector-3364-aerospace (rep 1) | - | medium | 2026-11-16T15:09 | fail | 0.10 | 0.15 | 0.04 | 302 s | 0 / 0 | 0 | broke an invariant |
| sector-337-furniture (rep 1) | - | medium | 2026-11-16T15:13 | fail | 0.10 | 0.15 | 0.04 | 285 s | 0 / 0 | 0 | broke an invariant |
| sector-3391-medical-devices (rep 1) | - | medium | 2026-11-16T15:33 | fail | 0.10 | 0.15 | 0.04 | 1149 s | 0 / 0 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T15:28 | fail | 0.13 | 0.25 | 0.00 | 2700 s | 17,000 / 7,600 | None | timed out, broke an invariant |
