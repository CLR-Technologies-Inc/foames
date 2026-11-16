# FoaMES agent benchmark results

<!-- SPDX-License-Identifier: Apache-2.0 -->

Runs started 2026-11-16T00:21:48+00:00 (UTC) on FoaMES commit(s) `6025f37062`. Workflow run: https://github.com/CLR-Technologies-Inc/foames/actions/runs/43779693868.

Every agent ran the six pure tasks in the benchmark's Docker sandbox on a GitHub-hosted runner (4 vCPU, 16 GB, no GPU). Hosted models were called on GitHub Models' free tier; local models were served by Ollama on the runner's CPU. Ranking is by quality (correctness and process, without cost), as in [docs/methodology.md](../../docs/methodology.md). One repetition cannot separate close agents; read the intervals.

| Agent | Model | Tier | Runs | Success (95 % CI) | Quality | Composite | Mean time | Tokens in / out | Cost | List-price equivalent | ECL tier |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| [reference](reference.md) | `` |  | 6 | 100% (61% to 100%) | 0.97 | 0.98 | 0 s | 0 / 0 | n/a | n/a | n/a |
| [aider-ghm-gpt-4.1](aider-ghm-gpt-4.1.md) | `openai/gpt-4.1` | baseline | 1 | 0% (0% to 79%) | 0.51 | 0.39 | 70 s | 0 / 0 | $0.00 | $0.00 | n/a |
| [aider-ghm-gpt-4.1-mini](aider-ghm-gpt-4.1-mini.md) | `openai/gpt-4.1-mini` | baseline | 1 | 0% (0% to 79%) | 0.51 | 0.39 | 71 s | 0 / 0 | $0.00 | $0.00 | n/a |
| [aider-ghm-gpt-4o-mini](aider-ghm-gpt-4o-mini.md) | `openai/gpt-4o-mini` | baseline | 1 | 0% (0% to 79%) | 0.51 | 0.39 | 72 s | 0 / 0 | $0.00 | $0.00 | n/a |
| [noop](noop.md) | `` |  | 6 | 0% (0% to 39%) | 0.22 | 0.17 | 0 s | 0 / 0 | n/a | n/a | n/a |

## Quality by task

| Agent | counter-reset | erp-retry-after | oee-unknown-time | process-mining-analysis | process-spec-network-loss | spc-ewma-chart |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| reference | 0.99 PASS | 1.00 PASS | 0.99 PASS | 0.90 PASS | 0.98 PASS | 0.99 PASS |
| aider-ghm-gpt-4.1 | 0.51 fail |  |  |  |  |  |
| aider-ghm-gpt-4.1-mini | 0.51 fail |  |  |  |  |  |
| aider-ghm-gpt-4o-mini | 0.51 fail |  |  |  |  |  |
| noop | 0.51 fail | 0.26 fail | 0.13 fail | 0.14 fail | 0.16 fail | 0.13 fail |

## Which TRL x complexity cells each agent qualifies for

No agent qualified for any cell: a cell needs every repetition of its qualifying tasks to succeed with mean quality at or above the cell's minimum (data/recommendations.json).

## Notes

- No ECL (engineering confidence level) tier is on main yet; this column fills in once the ECL tasks land.
- Cost is what the runs cost: $0 on GitHub Models' free tier and for local models (electricity and runner time are not counted). The list-price equivalent prices the same tokens at the provider's paid list price (agents.json `_list_prices`).
- Aider prints token counts rounded to the nearest hundred above 1,000, so token totals are approximate.
- GitHub Models' free tier caps each request at about 8,000 input tokens. Aider's repository map was kept at 512 tokens for those agents, and a model that asks to read a large file such as AGENTS.md can hit the cap. That is a limit of the free tier, not of the model.
- Local models ran on CPU only. The recommended open-weight models in the matrix (Qwen3-Coder 30B, gpt-oss 20b and up) need more memory or a GPU than a hosted runner has; the small coder models here are a floor for the open-weight tier, not its ceiling.
- Versions: aider 0.86.1.
