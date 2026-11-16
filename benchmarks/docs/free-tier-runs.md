<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright 2026 CLR Technologies Inc. -->

# Running the benchmark on free models in GitHub Actions

The [Agent benchmark workflow](../../.github/workflows/agent-bench.yml) runs the benchmark without a paid key and without anyone's own machine. Start it from the repository's **Actions** tab (Agent benchmark, Run workflow). Each agent is one job, so each model's rate limit is spent on its own, and the last job combines the runs into `benchmarks/results/<date>/`.

Every agent here is [aider](https://aider.chat) in the benchmark's Docker sandbox, so the comparison is between models, not harnesses. The harness version is pinned by the `aider_version` input and recorded with the results.

## What runs with no key at all

| Agents | Where the model runs | Key |
| --- | --- | --- |
| `aider-ghm-*` | GitHub Models, free tier | The workflow's own `GITHUB_TOKEN` with `models: read`. Nothing to set up. |
| `aider-ollama-*` | Ollama on the runner (4 vCPU, 16 GB, no GPU) | None. Small coder models only; a 30B model does not fit. |

GitHub Models' free tier caps each request at about 8,000 input tokens and a few dozen to a few hundred requests a day per model. A full run is 6 tasks and a handful of requests each, so one repetition a day per model fits.

## Free API tiers you can add

Each needs one Actions secret (Settings, Secrets and variables, Actions, New repository secret). The plan job skips an agent whose secret is missing and says so in the run summary. Keys go into Actions secrets only, never into a file, an issue or a chat.

| Agent | Provider and free tier | Secret name | Sign up |
| --- | --- | --- | --- |
| `aider-gemini-2.5-flash` | Google AI Studio (Gemini API) free tier | `GEMINI_API_KEY` | aistudio.google.com, Get API key |
| `aider-groq-gpt-oss-120b` | Groq free tier (tokens-per-minute limits are tight) | `GROQ_API_KEY` | console.groq.com, API keys |
| `aider-openrouter-qwen3-coder-free` | OpenRouter `:free` models (50 requests a day without credits) | `OPENROUTER_API_KEY` | openrouter.ai, Keys |
| `aider-mistral-devstral` | Mistral La Plateforme, free Experiment plan | `MISTRAL_API_KEY` | console.mistral.ai, API keys |
| `aider-cerebras-gpt-oss-120b` | Cerebras Inference free tier | `CEREBRAS_API_KEY` | cloud.cerebras.ai, API keys |

Model names and free-tier limits change often. If a provider renames a model, change its `model` in [agents.json](../agents.json); the workflow needs no change.

Free tiers may keep or train on prompts. The benchmark's tasks are public and use invented data, so that is acceptable here. Do not point these agents at private code.

## Reading the results

`benchmarks/results/<date>/README.md` ranks the agents by quality and shows tokens, the actual cost ($0 on free tiers) and a list-price equivalent from each agent's `_list_prices`. `comparison.html` in the same folder has a **reference bar** slider: set the bar as a share of the reference solution's own score on each task (or as an absolute score), choose the score (quality, correctness, process, composite) and whether invariants must hold, and the table re-ranks by how many tasks each agent clears. `publish_results.py --reference 0.8 --reference-mode relative` sets the bar written into the README.
