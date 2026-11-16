# aider-ghm-gpt-4.1-mini

<!-- SPDX-License-Identifier: Apache-2.0 -->

- Model: `openai/gpt-4.1-mini` (baseline tier), harness: aider aider 0.86.1
- Aider on GitHub Models (gpt-4.1-mini), free tier through the workflow's GITHUB_TOKEN (permission models: read, passed as OPENAI_API_KEY). Free-tier requests are capped at about 8,000 input tokens, so the repository map is kept small. 
- FoaMES commit: `6025f370625ec85fc3dac415fa4157b20b1bae66`, bench 0.1.0, started 2026-11-16T00:22:03+00:00
- Sandbox: docker, image `sha256:a42b29948979`
- Workflow run: https://github.com/CLR-Technologies-Inc/foames/actions/runs/43779693868

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL tier |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 1 | 0% (0% to 79%) | 0.51 | 0.84 | 0.14 | 0.39 | 71 s | 0 / 0 / 0 | $0.00 | $0.00 | n/a |

| Task | Complexity | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | low | fail | 0.51 | 0.84 | 0.14 | 71 s | 0 / 0 | 0 | regression tests 95% |
