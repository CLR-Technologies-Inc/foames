# aider-openrouter-free: benchmark run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T01:26:37+00:00, last run finished 2026-11-16T01:44:28+00:00
- **Model:** `openrouter/thinkingmachines/inkling-2-small:free` (oss tier, built for -), API model id openrouter/thinkingmachines/inkling-2-small:free, called 2026-11-16 (picked from the agent's candidates; the provider may update a model behind an unversioned id)
- openrouter/qwen/qwen3-coder:free: not listed as free
- openrouter/openai/gpt-oss-120b:free: not listed as free
- openrouter/moonshotai/kimi-k2:free: not listed as free
- openrouter/deepseek/deepseek-chat-v3.1:free: not listed as free
- openrouter/z-ai/glm-4.5-air:free: not listed as free
- openrouter/meta-llama/llama-3.3-70b-instruct:free: not listed as free
- openrouter/thinkingmachines/inkling-2-small:free: largest-context free model (1048576 tokens)
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner, model on the provider's free API tier; sandbox docker, image `sha256:6166f83c4e86`
- **FoaMES commit:** `ac71285e4838`
- Aider on a free API tier; needs the OPENROUTER_API_KEY Actions secret. OpenRouter free model; 50 requests a day without credits. The job picks the first candidate still listed with a :free id (qwen3-coder:free went paid-only in 2026-11), else the free model with the largest context. Free tiers can use prompts for training: send only public benchmark scenarios.
- Workflow run: https://github.com/CLR-Technologies-Inc/foames/actions/runs/43796612771

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 50% (19% to 81%) | 0.67 | 0.62 | 0.73 | 0.62 | 178 s | 352,900 / 0 / 182,210 | $0.00 | $0.29 | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T01:28 | PASS | 1.00 | 1.00 | 1.00 | 129 s | 24,900 / 20,600 | 0 |  |
| erp-retry-after (rep 1) | - | high | 2026-11-16T01:32 | fail | 0.38 | 0.24 | 0.54 | 246 s | 64,000 / 40,400 | 0 | broke an invariant, regression tests 96% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T01:34 | PASS | 1.00 | 1.00 | 1.00 | 90 s | 10,000 / 15,000 | 0 |  |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T01:38 | PASS | 1.00 | 1.00 | 1.00 | 216 s | 28,000 / 45,000 | 0 |  |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T01:42 | fail | 0.53 | 0.25 | 0.85 | 264 s | 95,000 / 40,566 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T01:44 | fail | 0.13 | 0.25 | 0.00 | 120 s | 131,000 / 20,644 | 0 | broke an invariant |
