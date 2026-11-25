# aider-nvidia-gpt-oss-120b: benchmark run of 2026-11-16

<!-- Copyright 2026 CLR Technologies Inc. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T08:49:02+00:00, last run finished 2026-11-16T11:20:08+00:00
- **Model:** `nvidia_nim/openai/gpt-oss-20b` (oss tier, built for reasoning (off-label)), API model id nvidia_nim/openai/gpt-oss-20b, called 2026-11-16 (picked from the agent's candidates; the provider may update a model behind an unversioned id)
- nvidia_nim/openai/gpt-oss-120b: not listed
- nvidia_nim/openai/gpt-oss-20b: HTTP timeout TimeoutError: The read operation timed out
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner, model on the provider's free API tier; sandbox docker, image `sha256:9298f86fda73`
- **FoaMES commit:** `711c83b57a8e`
- Aider on NVIDIA Build's free API (NIM, OpenAI-compatible); needs the NVIDIA_API_KEY Actions secret. Model family: reasoning (OpenAI open weights; 120b if listed, else the largest gpt-oss on offer: only 20b on 2026-11-16). The job picks the newest listed id that matches the candidates and answers a test call. About 40 requests a minute, shared by every NVIDIA agent, and NVIDIA logs prompts: send only public benchmark scenarios.

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 35 | 3% (0% to 14%) | 0.16 | 0.21 | 0.11 | 0.12 | 256 s | 308,000 / 0 / 100,972 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T08:58 | fail | 0.27 | 0.24 | 0.30 | 561 s | 52,000 / 11,172 | 0 | broke an invariant, regression tests 96% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T09:06 | fail | 0.69 | 0.82 | 0.54 | 484 s | 32,000 / 14,900 | 0 | broke an invariant, regression tests 96% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T09:40 | PASS | 0.91 | 1.00 | 0.80 | 2027 s | 79,000 / 32,100 | 0 |  |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T09:42 | fail | 0.14 | 0.12 | 0.17 | 101 s | 29,000 / 1,800 | 0 | broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T09:47 | fail | 0.70 | 0.62 | 0.79 | 341 s | 10,000 / 4,200 | 0 | broke an invariant |
| sector-211-oil-gas (rep 1) | - | medium | 2026-11-16T09:54 | fail | 0.10 | 0.15 | 0.04 | 408 s | 0 / 0 | 0 | broke an invariant |
| sector-212-mining (rep 1) | - | medium | 2026-11-16T10:12 | fail | 0.10 | 0.15 | 0.04 | 1076 s | 0 / 0 | 0 | broke an invariant |
| sector-2213-wastewater (rep 1) | - | medium | 2026-11-16T10:14 | fail | 0.10 | 0.15 | 0.04 | 128 s | 0 / 0 | 0 | broke an invariant |
| sector-311-food (rep 1) | - | medium | 2026-11-16T10:16 | fail | 0.10 | 0.15 | 0.04 | 120 s | 0 / 0 | 0 | broke an invariant |
| sector-312-beverage (rep 1) | - | medium | 2026-11-16T10:18 | fail | 0.10 | 0.15 | 0.04 | 82 s | 0 / 0 | 0 | broke an invariant |
| sector-313-textile-mills (rep 1) | - | medium | 2026-11-16T10:19 | fail | 0.10 | 0.15 | 0.04 | 87 s | 0 / 0 | 0 | broke an invariant |
| sector-314-carpet (rep 1) | - | medium | 2026-11-16T10:21 | fail | 0.10 | 0.15 | 0.04 | 92 s | 0 / 0 | 0 | broke an invariant |
| sector-315-apparel (rep 1) | - | medium | 2026-11-16T10:22 | fail | 0.10 | 0.15 | 0.04 | 88 s | 0 / 0 | 0 | broke an invariant |
| sector-316-footwear (rep 1) | - | medium | 2026-11-16T10:24 | fail | 0.10 | 0.15 | 0.04 | 82 s | 0 / 0 | 0 | broke an invariant |
| sector-321-wood (rep 1) | - | medium | 2026-11-16T10:25 | fail | 0.10 | 0.15 | 0.04 | 95 s | 0 / 0 | 0 | broke an invariant |
| sector-322-paper (rep 1) | - | medium | 2026-11-16T10:27 | fail | 0.10 | 0.15 | 0.04 | 77 s | 0 / 0 | 0 | broke an invariant |
| sector-323-printing (rep 1) | - | medium | 2026-11-16T10:28 | fail | 0.10 | 0.15 | 0.04 | 92 s | 0 / 0 | 0 | broke an invariant |
| sector-324-refining (rep 1) | - | medium | 2026-11-16T10:30 | fail | 0.10 | 0.15 | 0.04 | 81 s | 0 / 0 | 0 | broke an invariant |
| sector-325-chemicals (rep 1) | - | medium | 2026-11-16T10:31 | fail | 0.10 | 0.15 | 0.04 | 90 s | 0 / 0 | 0 | broke an invariant |
| sector-3254-pharmaceuticals (rep 1) | - | medium | 2026-11-16T10:33 | fail | 0.10 | 0.15 | 0.04 | 86 s | 0 / 0 | 0 | broke an invariant |
| sector-326-plastics (rep 1) | - | medium | 2026-11-16T10:35 | fail | 0.10 | 0.15 | 0.04 | 125 s | 0 / 0 | 0 | broke an invariant |
| sector-3272-glass (rep 1) | - | medium | 2026-11-16T10:37 | fail | 0.10 | 0.15 | 0.04 | 113 s | 0 / 0 | 0 | broke an invariant |
| sector-3273-cement (rep 1) | - | medium | 2026-11-16T10:38 | fail | 0.10 | 0.15 | 0.04 | 66 s | 0 / 0 | 0 | broke an invariant |
| sector-331-aluminum (rep 1) | - | medium | 2026-11-16T10:40 | fail | 0.10 | 0.15 | 0.04 | 101 s | 0 / 0 | 0 | broke an invariant |
| sector-3315-foundry (rep 1) | - | medium | 2026-11-16T10:42 | fail | 0.10 | 0.15 | 0.04 | 123 s | 0 / 0 | 0 | broke an invariant |
| sector-332-forging (rep 1) | - | medium | 2026-11-16T10:43 | fail | 0.13 | 0.15 | 0.11 | 98 s | 0 / 0 | 0 | broke an invariant |
| sector-332-machine-shop (rep 1) | - | medium | 2026-11-16T10:45 | fail | 0.10 | 0.15 | 0.04 | 93 s | 0 / 0 | 0 | broke an invariant |
| sector-333-machinery (rep 1) | - | medium | 2026-11-16T10:47 | fail | 0.10 | 0.15 | 0.04 | 98 s | 0 / 0 | 0 | broke an invariant |
| sector-3344-semiconductors (rep 1) | - | medium | 2026-11-16T10:48 | fail | 0.10 | 0.15 | 0.04 | 86 s | 0 / 0 | 0 | broke an invariant |
| sector-335-electrical-equipment (rep 1) | - | medium | 2026-11-16T10:50 | fail | 0.10 | 0.15 | 0.04 | 81 s | 0 / 0 | 0 | broke an invariant |
| sector-3361-motor-vehicles (rep 1) | - | medium | 2026-11-16T10:51 | fail | 0.10 | 0.15 | 0.04 | 75 s | 0 / 0 | 0 | broke an invariant |
| sector-3364-aerospace (rep 1) | - | medium | 2026-11-16T10:53 | fail | 0.10 | 0.15 | 0.04 | 96 s | 0 / 0 | 0 | broke an invariant |
| sector-337-furniture (rep 1) | - | medium | 2026-11-16T10:54 | fail | 0.10 | 0.15 | 0.04 | 96 s | 0 / 0 | 0 | broke an invariant |
| sector-3391-medical-devices (rep 1) | - | medium | 2026-11-16T10:56 | fail | 0.10 | 0.15 | 0.04 | 88 s | 0 / 0 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T11:20 | fail | 0.07 | 0.00 | 0.15 | 1436 s | 106,000 / 36,800 | 0 | broke an invariant, regression tests 0% |
