# aider-ghm-gpt-4o-mini

<!-- SPDX-License-Identifier: Apache-2.0 -->

- Model: `openai/gpt-4o-mini` (baseline tier), harness: aider aider 0.86.1
- Aider on GitHub Models (gpt-4o-mini), free tier through the workflow's GITHUB_TOKEN (permission models: read, passed as OPENAI_API_KEY). Free-tier requests are capped at about 8,000 input tokens, so the repository map is kept small. 
- FoaMES commit: `50e033039c70c51c625793c9cc39322803e9100f`, bench 0.1.0, started 2026-11-16T00:40:21+00:00
- Sandbox: docker, image `sha256:2c8c8baeb5a8`
- Workflow run: https://github.com/CLR-Technologies-Inc/foames/actions/runs/43781545523

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL tier |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 0% (0% to 79%) | 0.51 | 0.84 | 0.14 | 0.39 | 70 s | 0 / 0 / 0 | $0.00 | $0.00 | n/a |

| Task | Complexity | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | low | fail | 0.51 | 0.84 | 0.14 | 70 s | 0 / 0 | 0 | regression tests 95% |
