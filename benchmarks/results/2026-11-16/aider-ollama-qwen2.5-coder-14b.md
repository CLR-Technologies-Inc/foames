# aider-ollama-qwen2.5-coder-14b: benchmark run of 2026-11-16

<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T00:57:04+00:00, last run finished 2026-11-16T01:00:16+00:00
- **Model:** `ollama_chat/qwen2.5-coder:14b` (oss tier), Ollama qwen2.5-coder:14b digest 9ec8897f747e, pulled 2026-11-16
- **Harness:** aider aider 0.86.1
- **Where it ran:** GitHub-hosted runner (4 vCPU, 15 GB, CPU only); sandbox docker, image `sha256:f03ad87bb979`, Ollama ollama version is 0.40.16
- **FoaMES commit:** `ca5a0fa693c7`
- Aider with qwen2.5-coder:14b (Alibaba Qwen, Apache-2.0) served by Ollama on the same machine. Quality over speed: the timeout is ten times the task budget. Cost is electricity and time, recorded as $0.
- Workflow run: https://github.com/CLR-Technologies-Inc/foames/actions/runs/43783050523

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 0% (0% to 79%) | 0.14 | 0.12 | 0.17 | 0.11 | 190 s | 0 / 0 / 0 | $0.00 | n/a | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T01:00 | fail | 0.14 | 0.12 | 0.17 | 190 s | 0 / 0 | 0 | broke an invariant |
