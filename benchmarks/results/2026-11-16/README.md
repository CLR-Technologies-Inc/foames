# FoaMES agent benchmark results: run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

**Run of 2026-11-16.** Runs started 2026-11-16T01:26:37+00:00 and the last finished 2026-11-16T08:41:34+00:00 (UTC), on FoaMES commit `11c643fbf2`, `2cbb32a971`, `a1c95f786e`, `ac71285e48`. Report built 2026-11-16T12:59:28+00:00. Workflow run: https://github.com/CLR-Technologies-Inc/foames/actions/runs/43796612771.

Every agent is aider driving one model on the benchmark's pure tasks, in the benchmark's sandbox. Local models ran on Ollama; hosted models, where present, on their providers' free API tiers. Each model's page gives its exact version (digest or API model id), where it ran and when. Ranking is by tasks cleared at the reference bar, then quality (correctness and process, without cost), as in [docs/methodology.md](../../docs/methodology.md). One repetition cannot separate close agents: read the intervals.

**Reference bar: 80% of the reference solution's quality on each task**, and every invariant kept. "Clears" counts the tasks where every repetition reached it. Move the bar with the slider in [comparison.html](comparison.html) (open it in a browser), or rebuild with `--reference`.

| Agent | Model | Built for | Tier | Ran on | Runs | Clears bar | Success (95 % CI) | Quality | Composite | Mean time | Tokens in / out | Cost | List-price equivalent | ECL reached |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| [aider-gemini-flash](aider-gemini-flash.md) | `gemini/gemini-3.8-flash` | - | baseline | GitHub-hosted runner, model on the provider's free API tier | 5 | 4 / 6 | 80% (38% to 96%) | 0.87 | 0.77 | 857 s | 127,900 / 252,200 | $0.00 | $1.04 | ECL 2 |
| [aider-openrouter-free](aider-openrouter-free.md) | `openrouter/thinkingmachines/inkling-2-small:free` | - | oss | GitHub-hosted runner, model on the provider's free API tier | 6 | 3 / 6 | 50% (19% to 81%) | 0.67 | 0.62 | 178 s | 352,900 / 182,210 | $0.00 | $0.29 | none |
| [aider-ollama-gpt-oss-20b](aider-ollama-gpt-oss-20b.md) | `ollama_chat/gpt-oss:20b` | reasoning (off-label) | oss | GitHub-hosted runner (4 vCPU, 15 GB, CPU only) | 6 | 1 / 6 | 17% (3% to 56%) | 0.48 | 0.38 | 4404 s | 81,700 / 27,055 | $0.00 | n/a | none |
| [aider-ollama-qwen2.5-coder-14b](aider-ollama-qwen2.5-coder-14b.md) | `ollama_chat/qwen2.5-coder:14b` | coding | oss | GitHub-hosted runner (4 vCPU, 15 GB, CPU only) | 6 | 0 / 6 | 0% (0% to 39%) | 0.30 | 0.22 | 7532 s | 33,800 / 4,934 | $0.00 | n/a | none |
| [aider-ollama-qwen3-8b](aider-ollama-qwen3-8b.md) | `ollama_chat/qwen3:8b` | general chat (off-label) | oss | GitHub-hosted runner (4 vCPU, 15 GB, CPU only) | 6 | 0 / 6 | 0% (0% to 39%) | 0.25 | 0.19 | 7395 s | 90,500 / 21,587 | $0.00 | n/a | none |
| [aider-ollama-granite3.3-8b](aider-ollama-granite3.3-8b.md) | `ollama_chat/granite3.3:8b` | general chat (off-label) | oss | GitHub-hosted runner (4 vCPU, 15 GB, CPU only) | 6 | 0 / 6 | 0% (0% to 39%) | 0.22 | 0.17 | 5337 s | 56,500 / 6,030 | $0.00 | n/a | none |
| [aider-ollama-qwen2.5-coder-7b](aider-ollama-qwen2.5-coder-7b.md) | `ollama_chat/qwen2.5-coder:7b` | coding | oss | GitHub-hosted runner (4 vCPU, 15 GB, CPU only) | 6 | 0 / 6 | 0% (0% to 39%) | 0.22 | 0.17 | 4846 s | 118,200 / 12,424 | $0.00 | n/a | none |
| [aider-ollama-qwen3-14b](aider-ollama-qwen3-14b.md) | `ollama_chat/qwen3:14b` | general chat (off-label) | oss | GitHub-hosted runner (4 vCPU, 15 GB, CPU only) | 6 | 0 / 6 | 0% (0% to 39%) | 0.22 | 0.17 | 11455 s | 30,500 / 6,100 | $0.00 | n/a | none |
| [reference](reference.md) | `-` | - | calibration | runner | 6 | 6 / 6 | 100% (61% to 100%) | 0.97 | 0.98 | 0 s | 0 / 0 | n/a | n/a | n/a |
| [noop](noop.md) | `-` | - | calibration | runner | 6 | 0 / 6 | 0% (0% to 39%) | 0.22 | 0.17 | 0 s | 0 / 0 | n/a | n/a | n/a |

## Quality by task

| Agent | counter-reset (ECL 2) | erp-retry-after (ECL -) | oee-unknown-time (ECL 2) | process-mining-analysis (ECL 3) | process-spec-network-loss (ECL 3) | spc-ewma-chart (ECL 2) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| aider-gemini-flash | 1.00 PASS | 1.00 PASS | 0.91 PASS | 0.91 PASS | 0.53 fail |  |
| aider-openrouter-free | 1.00 PASS | 0.38 fail | 1.00 PASS | 1.00 PASS | 0.53 fail | 0.13 fail |
| aider-ollama-gpt-oss-20b | 0.91 PASS | 0.26 fail | 0.78 fail | 0.36 fail | 0.47 fail | 0.13 fail |
| aider-ollama-qwen2.5-coder-14b | 0.51 fail | 0.26 fail | 0.53 fail | 0.14 fail | 0.20 fail | 0.13 fail |
| aider-ollama-qwen3-8b | 0.51 fail | 0.38 fail | 0.13 fail | 0.14 fail | 0.16 fail | 0.19 fail |
| aider-ollama-granite3.3-8b | 0.51 fail | 0.26 fail | 0.13 fail | 0.14 fail | 0.16 fail | 0.13 fail |
| aider-ollama-qwen2.5-coder-7b | 0.51 fail | 0.26 fail | 0.13 fail | 0.14 fail | 0.16 fail | 0.13 fail |
| aider-ollama-qwen3-14b | 0.51 fail | 0.26 fail | 0.13 fail | 0.14 fail | 0.16 fail | 0.13 fail |
| reference | 0.99 PASS | 1.00 PASS | 0.99 PASS | 0.90 PASS | 0.98 PASS | 0.99 PASS |
| noop | 0.51 fail | 0.26 fail | 0.13 fail | 0.14 fail | 0.16 fail | 0.13 fail |

## Which TRL x complexity cells each agent qualifies for

| TRL band | Complexity | Qualified agents (cheapest first) |
| --- | --- | --- |
| 1-3 | low | aider-gemini-flash, aider-openrouter-free, aider-ollama-gpt-oss-20b |
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
- Not run: `aider-nvidia-kimi`: NVIDIA Build listed no Kimi model for this key on 2026-11-16.
- Not run: `aider-nvidia-qwen3-coder`: NVIDIA Build listed no Qwen3-Coder model for this key on 2026-11-16.
- Local models on GitHub-hosted runners ran on CPU (4 vCPU, 16 GB). Speed is not scored against them here beyond the efficiency term in the composite; read quality.
- "Built for" is what the model's makers tuned it for. Models marked off-label (general chat, reasoning, tiny or domain models) are not meant for agentic coding; they are here to show how far each kind gets on FoaMES work.
- Gemini's `spc-ewma-chart` run is left out: it was the sixth task in the job and met the free tier's limit of 20 requests a day for `gemini-3.8-flash` (HTTP 429). The rerun after the quota reset (workflow run 43830642714) got HTTP 503 from Google (model overloaded) on every request, so it is left out too (`runs/run-aider-gemini-flash-spc-ewma-chart_/dropped-unavailable.jsonl`); it is retried later.
- The first local-model run (workflow run 43784200629) is not in this report: on 4 CPU cores most requests outlived aider's 600-second timeout and were retried until aider gave up, so its scores measured the timeout. The local models were rerun with a one-hour request timeout.
- OpenRouter's `qwen/qwen3-coder:free` had gone paid-only; the agent ran on the free model with the largest context window that day, `thinkingmachines/inkling-2-small:free`.
- Local models on the 4-vCPU runners mostly ran out of time: each task's limit is thirteen times its budget (up to 3.25 hours), and many runs used all of it while producing a few thousand tokens. Only gpt-oss 20b passed a task (1 of 6). On CPU these scores say more about speed than about what the models can do; the GPU notebook runs the larger models without that limit.
