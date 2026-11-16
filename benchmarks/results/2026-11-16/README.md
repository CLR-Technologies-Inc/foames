# FoaMES agent benchmark results: run of 2026-11-16

<!-- SPDX-License-Identifier: Apache-2.0 -->

**Run of 2026-11-16.** Runs started 2026-11-16T00:57:04+00:00 and the last finished 2026-11-16T01:05:57+00:00 (UTC), on FoaMES commit `ca5a0fa693`. Report built 2026-11-16T01:05:57+00:00. Workflow run: https://github.com/CLR-Technologies-Inc/foames/actions/runs/43783050523.

Every agent is aider driving one model on the benchmark's pure tasks, in the benchmark's sandbox. Local models ran on Ollama; hosted models, where present, on their providers' free API tiers. Each model's page gives its exact version (digest or API model id), where it ran and when. Ranking is by tasks cleared at the reference bar, then quality (correctness and process, without cost), as in [docs/methodology.md](../../docs/methodology.md). One repetition cannot separate close agents: read the intervals.

**Reference bar: 80% of the reference solution's quality on each task**, and every invariant kept. "Clears" counts the tasks where every repetition reached it. Move the bar with the slider in [comparison.html](comparison.html) (open it in a browser), or rebuild with `--reference`.

| Agent | Model | Tier | Ran on | Runs | Clears bar | Success (95 % CI) | Quality | Composite | Mean time | Tokens in / out | Cost | List-price equivalent | ECL reached |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| [aider-ollama-qwen2.5-coder-14b](aider-ollama-qwen2.5-coder-14b.md) | `ollama_chat/qwen2.5-coder:14b` | oss | GitHub-hosted runner (4 vCPU, 15 GB, CPU only) | 1 | 0 / 6 | 0% (0% to 79%) | 0.14 | 0.11 | 190 s | 0 / 0 | $0.00 | n/a | none |
| [reference](reference.md) | `-` | calibration | runner | 6 | 6 / 6 | 100% (61% to 100%) | 0.97 | 0.98 | 0 s | 0 / 0 | n/a | n/a | n/a |
| [noop](noop.md) | `-` | calibration | runner | 6 | 0 / 6 | 0% (0% to 39%) | 0.22 | 0.17 | 0 s | 0 / 0 | n/a | n/a | n/a |

## Quality by task

| Agent | counter-reset (ECL 2) | erp-retry-after (ECL -) | oee-unknown-time (ECL 2) | process-mining-analysis (ECL 3) | process-spec-network-loss (ECL 3) | spc-ewma-chart (ECL 2) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| aider-ollama-qwen2.5-coder-14b |  |  |  | 0.14 fail |  |  |
| reference | 0.99 PASS | 1.00 PASS | 0.99 PASS | 0.90 PASS | 0.98 PASS | 0.99 PASS |
| noop | 0.51 fail | 0.26 fail | 0.13 fail | 0.14 fail | 0.16 fail | 0.13 fail |

## Which TRL x complexity cells each agent qualifies for

No agent qualified for any cell yet: a cell needs every repetition of its qualifying tasks to succeed with mean quality at or above the cell's minimum (data/recommendations.json).

## Notes

- **ECL reached** is the highest Equipment Complexity Level at which the agent passed every task it ran at that level and below, and whose minimum model tier its tier meets (data/recommendations.json). No task above ECL 3 exists yet, so ECL 4 and 5 cannot be reached; at those levels the matrix calls for a human expert anyway.
- Cost is what the runs cost: $0 on free API tiers and for local models (electricity and runner time are not counted). The list-price equivalent prices the same tokens at the provider's paid list price.
- Aider prints token counts rounded to the nearest hundred above 1,000, so token totals are approximate. Local models report no cost, so their token counts may also read zero.
- Local models on GitHub-hosted runners ran on CPU (4 vCPU, 16 GB). Speed is not scored against them here beyond the efficiency term in the composite; read quality.
