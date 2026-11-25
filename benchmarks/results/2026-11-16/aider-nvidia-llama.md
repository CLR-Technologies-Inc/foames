# aider-nvidia-llama: benchmark run of 2026-11-16

<!-- Copyright 2026 CLR Technologies Inc. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T08:41:36+00:00, last run finished 2026-11-16T09:59:10+00:00
- **Model:** `nvidia_nim/meta/llama-3.2-90b-vision-instruct` (oss tier, built for general chat (off-label)), API model id nvidia_nim/meta/llama-3.2-90b-vision-instruct, called 2026-11-16 (picked from the agent's candidates; the provider may update a model behind an unversioned id)
- nvidia_nim/meta/llama-4-maverick*: not listed
- nvidia_nim/meta/llama-3.3-70b-instruct: not listed
- nvidia_nim/meta/llama-3.2-90b-vision-instruct: HTTP 200
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner, model on the provider's free API tier; sandbox docker, image `sha256:c33240fa4883`
- **FoaMES commit:** `711c83b57a8e`
- Aider on NVIDIA Build's free API (NIM, OpenAI-compatible); needs the NVIDIA_API_KEY Actions secret. Model family: general chat (Meta Llama). The job picks the newest listed id that matches the candidates and answers a test call. About 40 requests a minute, shared by every NVIDIA agent, and NVIDIA logs prompts: send only public benchmark scenarios.

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 35 | 0% (0% to 10%) | 0.12 | 0.18 | 0.05 | 0.09 | 130 s | 63,000 / 0 / 6,971 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T08:57 | fail | 0.51 | 0.84 | 0.14 | 963 s | 37,000 / 2,447 | 0 | broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T09:04 | fail | 0.26 | 0.24 | 0.28 | 381 s | 26,000 / 4,524 | 0 | broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T09:05 | fail | 0.13 | 0.25 | 0.00 | 75 s | 0 / 0 | 0 | broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T09:06 | fail | 0.14 | 0.12 | 0.17 | 75 s | 0 / 0 | 0 | broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T09:07 | fail | 0.16 | 0.12 | 0.20 | 75 s | 0 / 0 | 0 | broke an invariant |
| sector-211-oil-gas (rep 1) | - | medium | 2026-11-16T09:09 | fail | 0.10 | 0.15 | 0.04 | 100 s | 0 / 0 | 0 | broke an invariant |
| sector-212-mining (rep 1) | - | medium | 2026-11-16T09:11 | fail | 0.10 | 0.15 | 0.04 | 100 s | 0 / 0 | 0 | broke an invariant |
| sector-2213-wastewater (rep 1) | - | medium | 2026-11-16T09:13 | fail | 0.10 | 0.15 | 0.04 | 102 s | 0 / 0 | 0 | broke an invariant |
| sector-311-food (rep 1) | - | medium | 2026-11-16T09:14 | fail | 0.10 | 0.15 | 0.04 | 100 s | 0 / 0 | 0 | broke an invariant |
| sector-312-beverage (rep 1) | - | medium | 2026-11-16T09:16 | fail | 0.10 | 0.15 | 0.04 | 101 s | 0 / 0 | 0 | broke an invariant |
| sector-313-textile-mills (rep 1) | - | medium | 2026-11-16T09:18 | fail | 0.10 | 0.15 | 0.04 | 101 s | 0 / 0 | 0 | broke an invariant |
| sector-314-carpet (rep 1) | - | medium | 2026-11-16T09:20 | fail | 0.10 | 0.15 | 0.04 | 102 s | 0 / 0 | 0 | broke an invariant |
| sector-315-apparel (rep 1) | - | medium | 2026-11-16T09:21 | fail | 0.10 | 0.15 | 0.04 | 102 s | 0 / 0 | 0 | broke an invariant |
| sector-316-footwear (rep 1) | - | medium | 2026-11-16T09:23 | fail | 0.10 | 0.15 | 0.04 | 101 s | 0 / 0 | 0 | broke an invariant |
| sector-321-wood (rep 1) | - | medium | 2026-11-16T09:25 | fail | 0.10 | 0.15 | 0.04 | 101 s | 0 / 0 | 0 | broke an invariant |
| sector-322-paper (rep 1) | - | medium | 2026-11-16T09:26 | fail | 0.10 | 0.15 | 0.04 | 100 s | 0 / 0 | 0 | broke an invariant |
| sector-323-printing (rep 1) | - | medium | 2026-11-16T09:28 | fail | 0.10 | 0.15 | 0.04 | 100 s | 0 / 0 | 0 | broke an invariant |
| sector-324-refining (rep 1) | - | medium | 2026-11-16T09:30 | fail | 0.10 | 0.15 | 0.04 | 100 s | 0 / 0 | 0 | broke an invariant |
| sector-325-chemicals (rep 1) | - | medium | 2026-11-16T09:32 | fail | 0.10 | 0.15 | 0.04 | 101 s | 0 / 0 | 0 | broke an invariant |
| sector-3254-pharmaceuticals (rep 1) | - | medium | 2026-11-16T09:33 | fail | 0.10 | 0.15 | 0.04 | 101 s | 0 / 0 | 0 | broke an invariant |
| sector-326-plastics (rep 1) | - | medium | 2026-11-16T09:35 | fail | 0.10 | 0.15 | 0.04 | 101 s | 0 / 0 | 0 | broke an invariant |
| sector-3272-glass (rep 1) | - | medium | 2026-11-16T09:37 | fail | 0.10 | 0.15 | 0.04 | 100 s | 0 / 0 | 0 | broke an invariant |
| sector-3273-cement (rep 1) | - | medium | 2026-11-16T09:38 | fail | 0.10 | 0.15 | 0.04 | 100 s | 0 / 0 | 0 | broke an invariant |
| sector-331-aluminum (rep 1) | - | medium | 2026-11-16T09:40 | fail | 0.10 | 0.15 | 0.04 | 100 s | 0 / 0 | 0 | broke an invariant |
| sector-3315-foundry (rep 1) | - | medium | 2026-11-16T09:42 | fail | 0.10 | 0.15 | 0.04 | 100 s | 0 / 0 | 0 | broke an invariant |
| sector-332-forging (rep 1) | - | medium | 2026-11-16T09:44 | fail | 0.13 | 0.15 | 0.11 | 101 s | 0 / 0 | 0 | broke an invariant |
| sector-332-machine-shop (rep 1) | - | medium | 2026-11-16T09:45 | fail | 0.10 | 0.15 | 0.04 | 102 s | 0 / 0 | 0 | broke an invariant |
| sector-333-machinery (rep 1) | - | medium | 2026-11-16T09:47 | fail | 0.10 | 0.15 | 0.04 | 102 s | 0 / 0 | 0 | broke an invariant |
| sector-3344-semiconductors (rep 1) | - | medium | 2026-11-16T09:49 | fail | 0.10 | 0.15 | 0.04 | 100 s | 0 / 0 | 0 | broke an invariant |
| sector-335-electrical-equipment (rep 1) | - | medium | 2026-11-16T09:51 | fail | 0.10 | 0.15 | 0.04 | 100 s | 0 / 0 | 0 | broke an invariant |
| sector-3361-motor-vehicles (rep 1) | - | medium | 2026-11-16T09:52 | fail | 0.10 | 0.15 | 0.04 | 100 s | 0 / 0 | 0 | broke an invariant |
| sector-3364-aerospace (rep 1) | - | medium | 2026-11-16T09:54 | fail | 0.10 | 0.15 | 0.04 | 101 s | 0 / 0 | 0 | broke an invariant |
| sector-337-furniture (rep 1) | - | medium | 2026-11-16T09:56 | fail | 0.10 | 0.15 | 0.04 | 101 s | 0 / 0 | 0 | broke an invariant |
| sector-3391-medical-devices (rep 1) | - | medium | 2026-11-16T09:57 | fail | 0.10 | 0.15 | 0.04 | 101 s | 0 / 0 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T09:59 | fail | 0.13 | 0.25 | 0.00 | 76 s | 0 / 0 | 0 | broke an invariant |
