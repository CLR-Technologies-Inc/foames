<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- Copyright 2026 CLR Technologies Inc. -->

# Running the benchmark on free models in GitHub Actions

The [Agent benchmark workflow](../../.github/workflows/agent-bench.yml) runs the benchmark without a paid key and without anyone's own machine. Start it from the repository's **Actions** tab (Agent benchmark, Run workflow). Each agent is one job, so each model's rate limit is spent on its own, and the last job combines the runs into `benchmarks/results/<date>/`.

Every agent here is [aider](https://aider.chat) in the benchmark's Docker sandbox, so the comparison is between models, not harnesses. The harness version is pinned by the `aider_version` input and recorded with the results.

## What runs with no key at all

| Agents | Where the model runs | Key |
| --- | --- | --- |
| `aider-ollama-*` | Ollama on the runner (4 vCPU, 16 GB, no GPU) | None. Models up to about 20B: Qwen2.5-Coder 7B and 14B, Qwen3 8B and 14B, IBM Granite 3.3 8B, gpt-oss 20b. One job per model and task, with a timeout of ten times the task budget, because quality matters here, not speed. |
| `aider-ollama-qwen3-coder-30b`, `aider-ollama-devstral-24b` (and gpt-oss 20b on a GPU) | A free notebook GPU: [notebooks/foames-bench-gpu.ipynb](../notebooks/foames-bench-gpu.ipynb) on Kaggle (T4 x2, about 30 GPU hours a week, runs headless) or Colab (one T4) | A free Kaggle account, phone-verified for GPU and internet. Notebooks have no Docker: the run uses the `unshare` sandbox when allowed and is marked `none` otherwise. |

Every local model here is published under Apache-2.0 by a known publisher (Alibaba Qwen, IBM, OpenAI, Mistral AI). Models with research-only or custom licences are left out.

GitHub Models was tried first, because a workflow's own token can call it with no sign-up. On 2026-11-16 every request to `models.github.ai` from a hosted runner, including the catalog and made-up paths, answered `200 OK` with a plain-text body of `OK` and no completion, and the older `models.inference.ai.azure.com` host no longer resolves. It is left out until it answers again.

## Free API tiers you can add

Each needs one Actions secret (Settings, Secrets and variables, Actions, New repository secret). The plan job skips an agent whose secret is missing and says so in the run summary. Keys go into Actions secrets only, never into a file, an issue or a chat.

| Agent | Provider and free tier | Secret name | Sign up |
| --- | --- | --- | --- |
| `aider-gemini-2.5-flash` | Google AI Studio (Gemini API) free tier | `GEMINI_API_KEY` | aistudio.google.com, Get API key |
| `aider-groq-gpt-oss-120b` | Groq free tier (tokens-per-minute limits are tight) | `GROQ_API_KEY` | console.groq.com, API keys |
| `aider-openrouter-qwen3-coder-free` | OpenRouter `:free` models (50 requests a day without credits) | `OPENROUTER_API_KEY` | openrouter.ai, Keys |

Mistral (`aider-mistral-devstral`, `MISTRAL_API_KEY`) and Cerebras (`aider-cerebras-gpt-oss-120b`, `CEREBRAS_API_KEY`) are configured but skipped by default: on 2026-11-16 both asked for a credit card at sign-up, so they are not a no-cost tier here. Devstral still runs, as open weights, through the GPU notebook.

Model names and free-tier limits change often. If a provider renames a model, change its `model` in [agents.json](../agents.json); the workflow needs no change.

Free tiers may keep or train on prompts. The benchmark's tasks are public and use invented data, so that is acceptable here. Do not point these agents at private code.

## Dates and versions

Each report folder is named after the date its runs started (`benchmarks/results/<YYYY-MM-DD>/`). The README gives the start and finish times, the FoaMES commit and when the report was built; each agent's page adds the model's Ollama digest and pull date (or the API model id and call date), the aider version, the sandbox image and where it ran. Hosted model ids such as `gemini-2.5-flash` can change behind the same name, which is why the call date is kept.

## Reading the results

`benchmarks/results/<date>/README.md` ranks the agents by quality and shows tokens, the actual cost ($0 on free tiers) and a list-price equivalent from each agent's `_list_prices`. `comparison.html` in the same folder has a **reference bar** slider: set the bar as a share of the reference solution's own score on each task (or as an absolute score), choose the score (quality, correctness, process, composite) and whether invariants must hold, and the table re-ranks by how many tasks each agent clears. `publish_results.py --reference 0.8 --reference-mode relative` sets the bar written into the README.
