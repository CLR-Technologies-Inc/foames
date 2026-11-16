# aider-groq-gpt-oss-120b: benchmark run of 2026-11-16

<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T01:07:54+00:00, last run finished 2026-11-16T01:15:13+00:00
- **Model:** `groq/openai/gpt-oss-120b` (oss tier), API model id groq/openai/gpt-oss-120b, called 2026-11-16 (the provider may update a model behind an unversioned id)
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner, model on the provider's free API tier; sandbox docker, image `sha256:a8765fbd3153`
- **FoaMES commit:** `db2f835e6792`
- Aider on a free API tier; needs the GROQ_API_KEY Actions secret. Groq free tier; tokens-per-minute limits are tight, so expect retries. Free tiers can use prompts for training: send only public benchmark scenarios.
- Workflow run: https://github.com/CLR-Technologies-Inc/foames/actions/runs/43784200629

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 6 | 0% (0% to 39%) | 0.22 | 0.30 | 0.13 | 0.17 | 72 s | 0 / 0 / 0 | $0.00 | $0.00 | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T01:09 | fail | 0.51 | 0.84 | 0.14 | 72 s | 0 / 0 | 0 | broke an invariant, regression tests 95% |
| erp-retry-after (rep 1) | - | high | 2026-11-16T01:10 | fail | 0.26 | 0.24 | 0.28 | 72 s | 0 / 0 | 0 | broke an invariant, regression tests 97% |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T01:11 | fail | 0.13 | 0.25 | 0.00 | 72 s | 0 / 0 | 0 | broke an invariant |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T01:12 | fail | 0.14 | 0.12 | 0.17 | 72 s | 0 / 0 | 0 | broke an invariant |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T01:14 | fail | 0.16 | 0.12 | 0.20 | 72 s | 0 / 0 | 0 | broke an invariant |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T01:15 | fail | 0.13 | 0.25 | 0.00 | 71 s | 0 / 0 | 0 | broke an invariant |
