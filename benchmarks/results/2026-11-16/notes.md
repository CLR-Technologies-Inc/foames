<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Notes on the 2026-11-16 runs, added to the README by publish_results.py.

- Gemini's `spc-ewma-chart` run is left out: it was the sixth task in the job and met the free tier's limit of 20 requests a day for `gemini-3.8-flash` (HTTP 429). The rerun after the quota reset (workflow run 43830642714) got HTTP 503 from Google (model overloaded) on every request, so it is left out too (`runs/run-aider-gemini-flash-spc-ewma-chart_/dropped-unavailable.jsonl`); it is retried later.
- The first local-model run (workflow run 43784200629) is not in this report: on 4 CPU cores most requests outlived aider's 600-second timeout and were retried until aider gave up, so its scores measured the timeout. The local models were rerun with a one-hour request timeout.
- OpenRouter's `qwen/qwen3-coder:free` had gone paid-only; the agent ran on the free model with the largest context window that day, `thinkingmachines/inkling-2-small:free`.
- Local models on the 4-vCPU runners mostly ran out of time: each task's limit is thirteen times its budget (up to 3.25 hours), and many runs used all of it while producing a few thousand tokens. Only gpt-oss 20b passed a task (1 of 6). On CPU these scores say more about speed than about what the models can do; the GPU notebook runs the larger models without that limit.
