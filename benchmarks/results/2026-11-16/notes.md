<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Notes on the 2026-11-16 runs, added to the README by publish_results.py.

- Gemini's `spc-ewma-chart` is from its third attempt (workflow run 43871563784). The first met the free tier's limit of 20 requests a day (HTTP 429) and the second got HTTP 503 (model overloaded) on every request; both are kept out of the scores, in `runs/run-aider-gemini-flash-all_/dropped-rate-limited.jsonl` and `runs/run-aider-gemini-flash-spc-ewma-chart_/dropped-unavailable.jsonl`.
- The first local-model run (workflow run 43784200629) is not in this report: on 4 CPU cores most requests outlived aider's 600-second timeout and were retried until aider gave up, so its scores measured the timeout. The local models were rerun with a one-hour request timeout.
- OpenRouter's `qwen/qwen3-coder:free` had gone paid-only; the agent ran on the free model with the largest context window that day, `thinkingmachines/inkling-2-small:free`.
- Local models on the 4-vCPU runners mostly ran out of time: each task's limit is thirteen times its budget (up to 3.25 hours), and many runs used all of it while producing a few thousand tokens. Of the 34 local models, only gpt-oss 20b passed a task (1 of 6). On CPU these scores say more about speed than about what the models can do; the GPU notebook runs the larger models without that limit.
