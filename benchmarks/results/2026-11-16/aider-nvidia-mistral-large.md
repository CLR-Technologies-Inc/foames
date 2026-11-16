# aider-nvidia-mistral-large: benchmark run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T08:45:12+00:00, last run finished 2026-11-16T09:15:17+00:00
- **Model:** `nvidia_nim/mistralai/mistral-large-4-1t-a52b` (oss tier, built for general chat (off-label)), API model id nvidia_nim/mistralai/mistral-large-4-1t-a52b, called 2026-11-16 (picked from the agent's candidates; the provider may update a model behind an unversioned id)
- nvidia_nim/mistralai/mistral-large-4-1t-a52b: HTTP 200
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner, model on the provider's free API tier; sandbox docker, image `sha256:d882ba77ce4c`
- **FoaMES commit:** `711c83b57a8e`
- Aider on NVIDIA Build's free API (NIM, OpenAI-compatible); needs the NVIDIA_API_KEY Actions secret. Model family: general chat (Mistral Large). The job picks the newest listed id that matches the candidates and answers a test call. About 40 requests a minute, shared by every NVIDIA agent, and NVIDIA logs prompts: send only public benchmark scenarios.

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 35 | 0% (0% to 10%) | 0.12 | 0.18 | 0.05 | 0.09 | 50 s | 34,000 / 0 / 2,977 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T08:45 | fail | 0.51 | 0.84 | 0.14 | 11 s | 11,000 / 95 | 0 | broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T08:45 | fail | 0.26 | 0.24 | 0.28 | 10 s | 11,000 / 182 | 0 | broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T08:53 | fail | 0.13 | 0.25 | 0.00 | 444 s | 12,000 / 2,700 | 0 | broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T08:58 | fail | 0.14 | 0.12 | 0.17 | 348 s | 0 / 0 | 0 | broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T08:59 | fail | 0.16 | 0.12 | 0.20 | 8 s | 0 / 0 | 0 | broke an invariant |
| sector-211-oil-gas (rep 1) | - | medium | 2026-11-16T08:59 | fail | 0.10 | 0.15 | 0.04 | 32 s | 0 / 0 | 0 | broke an invariant |
| sector-212-mining (rep 1) | - | medium | 2026-11-16T09:00 | fail | 0.10 | 0.15 | 0.04 | 31 s | 0 / 0 | 0 | broke an invariant |
| sector-2213-wastewater (rep 1) | - | medium | 2026-11-16T09:00 | fail | 0.10 | 0.15 | 0.04 | 32 s | 0 / 0 | 0 | broke an invariant |
| sector-311-food (rep 1) | - | medium | 2026-11-16T09:01 | fail | 0.10 | 0.15 | 0.04 | 32 s | 0 / 0 | 0 | broke an invariant |
| sector-312-beverage (rep 1) | - | medium | 2026-11-16T09:01 | fail | 0.10 | 0.15 | 0.04 | 31 s | 0 / 0 | 0 | broke an invariant |
| sector-313-textile-mills (rep 1) | - | medium | 2026-11-16T09:02 | fail | 0.10 | 0.15 | 0.04 | 32 s | 0 / 0 | 0 | broke an invariant |
| sector-314-carpet (rep 1) | - | medium | 2026-11-16T09:02 | fail | 0.10 | 0.15 | 0.04 | 32 s | 0 / 0 | 0 | broke an invariant |
| sector-315-apparel (rep 1) | - | medium | 2026-11-16T09:03 | fail | 0.10 | 0.15 | 0.04 | 31 s | 0 / 0 | 0 | broke an invariant |
| sector-316-footwear (rep 1) | - | medium | 2026-11-16T09:04 | fail | 0.10 | 0.15 | 0.04 | 32 s | 0 / 0 | 0 | broke an invariant |
| sector-321-wood (rep 1) | - | medium | 2026-11-16T09:04 | fail | 0.10 | 0.15 | 0.04 | 31 s | 0 / 0 | 0 | broke an invariant |
| sector-322-paper (rep 1) | - | medium | 2026-11-16T09:05 | fail | 0.10 | 0.15 | 0.04 | 31 s | 0 / 0 | 0 | broke an invariant |
| sector-323-printing (rep 1) | - | medium | 2026-11-16T09:05 | fail | 0.10 | 0.15 | 0.04 | 31 s | 0 / 0 | 0 | broke an invariant |
| sector-324-refining (rep 1) | - | medium | 2026-11-16T09:06 | fail | 0.10 | 0.15 | 0.04 | 31 s | 0 / 0 | 0 | broke an invariant |
| sector-325-chemicals (rep 1) | - | medium | 2026-11-16T09:06 | fail | 0.10 | 0.15 | 0.04 | 31 s | 0 / 0 | 0 | broke an invariant |
| sector-3254-pharmaceuticals (rep 1) | - | medium | 2026-11-16T09:07 | fail | 0.10 | 0.15 | 0.04 | 32 s | 0 / 0 | 0 | broke an invariant |
| sector-326-plastics (rep 1) | - | medium | 2026-11-16T09:07 | fail | 0.10 | 0.15 | 0.04 | 32 s | 0 / 0 | 0 | broke an invariant |
| sector-3272-glass (rep 1) | - | medium | 2026-11-16T09:08 | fail | 0.10 | 0.15 | 0.04 | 31 s | 0 / 0 | 0 | broke an invariant |
| sector-3273-cement (rep 1) | - | medium | 2026-11-16T09:09 | fail | 0.10 | 0.15 | 0.04 | 32 s | 0 / 0 | 0 | broke an invariant |
| sector-331-aluminum (rep 1) | - | medium | 2026-11-16T09:09 | fail | 0.10 | 0.15 | 0.04 | 31 s | 0 / 0 | 0 | broke an invariant |
| sector-3315-foundry (rep 1) | - | medium | 2026-11-16T09:10 | fail | 0.10 | 0.15 | 0.04 | 30 s | 0 / 0 | 0 | broke an invariant |
| sector-332-forging (rep 1) | - | medium | 2026-11-16T09:10 | fail | 0.13 | 0.15 | 0.11 | 32 s | 0 / 0 | 0 | broke an invariant |
| sector-332-machine-shop (rep 1) | - | medium | 2026-11-16T09:11 | fail | 0.10 | 0.15 | 0.04 | 31 s | 0 / 0 | 0 | broke an invariant |
| sector-333-machinery (rep 1) | - | medium | 2026-11-16T09:11 | fail | 0.10 | 0.15 | 0.04 | 32 s | 0 / 0 | 0 | broke an invariant |
| sector-3344-semiconductors (rep 1) | - | medium | 2026-11-16T09:12 | fail | 0.10 | 0.15 | 0.04 | 32 s | 0 / 0 | 0 | broke an invariant |
| sector-335-electrical-equipment (rep 1) | - | medium | 2026-11-16T09:12 | fail | 0.10 | 0.15 | 0.04 | 32 s | 0 / 0 | 0 | broke an invariant |
| sector-3361-motor-vehicles (rep 1) | - | medium | 2026-11-16T09:13 | fail | 0.10 | 0.15 | 0.04 | 30 s | 0 / 0 | 0 | broke an invariant |
| sector-3364-aerospace (rep 1) | - | medium | 2026-11-16T09:14 | fail | 0.10 | 0.15 | 0.04 | 31 s | 0 / 0 | 0 | broke an invariant |
| sector-337-furniture (rep 1) | - | medium | 2026-11-16T09:14 | fail | 0.10 | 0.15 | 0.04 | 33 s | 0 / 0 | 0 | broke an invariant |
| sector-3391-medical-devices (rep 1) | - | medium | 2026-11-16T09:15 | fail | 0.10 | 0.15 | 0.04 | 31 s | 0 / 0 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T09:15 | fail | 0.13 | 0.25 | 0.00 | 8 s | 0 / 0 | 0 | broke an invariant |
