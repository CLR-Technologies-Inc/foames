# FoaMES agent benchmark results: run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

**Run of 2026-11-16.** Runs started 2026-11-16T01:26:37+00:00 and the last finished 2026-11-16T03:12:10+00:00 (UTC), on FoaMES commit `11c643fbf2`, `2cbb32a971`, `ac71285e48`. Report built 2026-11-16T03:13:14+00:00. Workflow run: https://github.com/CLR-Technologies-Inc/foames/actions/runs/43787796363.

Every agent is aider driving one model on the benchmark's pure tasks, in the benchmark's sandbox. Local models ran on Ollama; hosted models, where present, on their providers' free API tiers. Each model's page gives its exact version (digest or API model id), where it ran and when. Ranking is by tasks cleared at the reference bar, then quality (correctness and process, without cost), as in [docs/methodology.md](../../docs/methodology.md). One repetition cannot separate close agents: read the intervals.

**Reference bar: 80% of the reference solution's quality on each task**, and every invariant kept. "Clears" counts the tasks where every repetition reached it. Move the bar with the slider in [comparison.html](comparison.html) (open it in a browser), or rebuild with `--reference`.

| Agent | Model | Tier | Ran on | Runs | Clears bar | Success (95 % CI) | Quality | Composite | Mean time | Tokens in / out | Cost | List-price equivalent | ECL reached |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| [aider-gemini-flash](aider-gemini-flash.md) | `gemini/gemini-3.8-flash` | baseline | GitHub-hosted runner, model on the provider's free API tier | 5 | 4 / 6 | 80% (38% to 96%) | 0.87 | 0.77 | 857 s | 127,900 / 252,200 | $0.00 | $1.04 | ECL 2 |
| [aider-openrouter-free](aider-openrouter-free.md) | `openrouter/thinkingmachines/inkling-2-small:free` | oss | GitHub-hosted runner, model on the provider's free API tier | 6 | 3 / 6 | 50% (19% to 81%) | 0.67 | 0.62 | 178 s | 352,900 / 182,210 | $0.00 | $0.29 | none |
| [reference](reference.md) | `-` | calibration | runner | 6 | 6 / 6 | 100% (61% to 100%) | 0.97 | 0.98 | 0 s | 0 / 0 | n/a | n/a | n/a |
| [noop](noop.md) | `-` | calibration | runner | 6 | 0 / 6 | 0% (0% to 39%) | 0.22 | 0.17 | 0 s | 0 / 0 | n/a | n/a | n/a |

## Quality by task

| Agent | counter-reset (ECL 2) | erp-retry-after (ECL -) | oee-unknown-time (ECL 2) | process-mining-analysis (ECL 3) | process-spec-network-loss (ECL 3) | spc-ewma-chart (ECL 2) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| aider-gemini-flash | 1.00 PASS | 1.00 PASS | 0.91 PASS | 0.91 PASS | 0.53 fail |  |
| aider-openrouter-free | 1.00 PASS | 0.38 fail | 1.00 PASS | 1.00 PASS | 0.53 fail | 0.13 fail |
| reference | 0.99 PASS | 1.00 PASS | 0.99 PASS | 0.90 PASS | 0.98 PASS | 0.99 PASS |
| noop | 0.51 fail | 0.26 fail | 0.13 fail | 0.14 fail | 0.16 fail | 0.13 fail |

## Which TRL x complexity cells each agent qualifies for

| TRL band | Complexity | Qualified agents (cheapest first) |
| --- | --- | --- |
| 1-3 | low | aider-gemini-flash, aider-openrouter-free |
| 1-3 | medium | aider-openrouter-free, aider-gemini-flash |
| 1-3 | high | none yet |
| 4-6 | low | aider-openrouter-free, aider-gemini-flash |
| 4-6 | medium | none yet |
| 4-6 | high | none yet |
| 7-9 | low | aider-openrouter-free, aider-gemini-flash |
| 7-9 | medium | none yet |
| 7-9 | high | none yet |

## Notes

- **ECL reached** is the highest Equipment Complexity Level at which the agent passed every task it ran at that level and below, and whose minimum model tier its tier meets (data/recommendations.json). No task above ECL 3 exists yet, so ECL 4 and 5 cannot be reached; at those levels the matrix calls for a human expert anyway.
- Cost is what the runs cost: $0 on free API tiers and for local models (electricity and runner time are not counted). The list-price equivalent prices the same tokens at the provider's paid list price (from agents.json, or else the estimate aider printed during the run).
- Aider prints token counts rounded to the nearest hundred above 1,000, so token totals are approximate. Local models report no cost, so their token counts may also read zero.
- Not run: `aider-groq-free`: Groq's free tier allowed at most 8,000 tokens a minute on every chat model it listed (2026-11-16), less than one aider request (about 12,700 tokens).
- Not run: `aider-mistral-devstral`: the provider asked for a credit card at sign-up (2026-11-16), so it is not a no-cost tier for this benchmark.
- Not run: `aider-cerebras-gpt-oss-120b`: the provider asked for a credit card at sign-up (2026-11-16), so it is not a no-cost tier for this benchmark.
- Local models on GitHub-hosted runners ran on CPU (4 vCPU, 16 GB). Speed is not scored against them here beyond the efficiency term in the composite; read quality.
- Gemini's `spc-ewma-chart` run is left out: it was the sixth task in the job and met the free tier's limit of 20 requests a day for `gemini-3.8-flash` (HTTP 429), so it scored what a no-op scores. The row is kept in `runs/run-aider-gemini-flash-all_/dropped-rate-limited.jsonl`; the task is rerun once the daily quota resets.
- The first local-model run (workflow run 43784200629) is not in this report: on 4 CPU cores most requests outlived aider's 600-second timeout and were retried until aider gave up, so its scores measured the timeout. The local models were rerun with a one-hour request timeout.
- OpenRouter's `qwen/qwen3-coder:free` had gone paid-only; the agent ran on the free model with the largest context window that day, `thinkingmachines/inkling-2-small:free`.
