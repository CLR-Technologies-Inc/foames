# aider-gemini-flash: benchmark run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T01:46:36+00:00, last run finished 2026-11-16T02:58:12+00:00
- **Model:** `gemini/gemini-3.8-flash` (baseline tier, built for -), API model id gemini/gemini-3.8-flash, called 2026-11-16 (picked from the agent's candidates; the provider may update a model behind an unversioned id)
- gemini/gemini-3.8-flash: HTTP 200
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner, model on the provider's free API tier; sandbox docker, image `sha256:5493dea23e6b`
- **FoaMES commit:** `2cbb32a9719c`
- Aider on a free API tier; needs the GEMINI_API_KEY Actions secret. Google AI Studio free tier. The job picks the first candidate model the key can list (Google retired gemini-2.5-flash for new users in 2026-11). Free tiers can use prompts for training: send only public benchmark scenarios.
- Workflow run: https://github.com/CLR-Technologies-Inc/foames/actions/runs/43796612771

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 5 | 80% (38% to 96%) | 0.87 | 0.85 | 0.89 | 0.77 | 857 s | 127,900 / 0 / 252,200 | $0.00 | $1.04 | ECL 2 |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T02:04 | PASS | 1.00 | 1.00 | 1.00 | 1096 s | 19,300 / 31,100 | 0 |  |
| erp-retry-after (rep 1) | - | high | 2026-11-16T02:20 | PASS | 1.00 | 1.00 | 1.00 | 932 s | 31,500 / 65,100 | 0 |  |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T02:26 | PASS | 0.91 | 1.00 | 0.80 | 343 s | 9,700 / 47,000 | 0 |  |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T02:32 | PASS | 0.91 | 1.00 | 0.80 | 372 s | 33,000 / 63,000 | 0 |  |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T02:58 | fail | 0.53 | 0.25 | 0.85 | 1543 s | 34,400 / 46,000 | 0 | broke an invariant |
