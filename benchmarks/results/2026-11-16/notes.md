<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

Notes on the 2026-11-16 runs, added to the README by publish_results.py.

- Gemini's `spc-ewma-chart` run is left out: it was the sixth task in the job and met the free tier's limit of 20 requests a day for `gemini-3.8-flash` (HTTP 429), so it scored what a no-op scores. The row is kept in `runs/run-aider-gemini-flash-all_/dropped-rate-limited.jsonl`; the task is rerun once the daily quota resets.
- The first local-model run (workflow run 43784200629) is not in this report: on 4 CPU cores most requests outlived aider's 600-second timeout and were retried until aider gave up, so its scores measured the timeout. The local models were rerun with a one-hour request timeout.
- OpenRouter's `qwen/qwen3-coder:free` had gone paid-only; the agent ran on the free model with the largest context window that day, `thinkingmachines/inkling-2-small:free`.
