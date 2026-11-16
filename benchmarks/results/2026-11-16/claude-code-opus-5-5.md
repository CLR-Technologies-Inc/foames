# claude-code-opus-5-5: benchmark run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T05:12:08+00:00, last run finished 2026-11-16T13:45:28+00:00
- **Model:** `claude-opus-5-5` (frontier tier, built for agentic coding), Claude Code 2.1.325 (CLI), model claude-opus-5-5, called 2026-11-16 through this account's Claude subscription (not the API); the model behind an alias may be updated by Anthropic
- **Harness:** claude-code
- **Where it ran:** Claude Code cloud container (Linux, unshare sandbox), tasks from commit c8bf84e; subscription run, cost $0; list price is Claude Code's API-equivalent estimate; sandbox unshare
- **FoaMES commit:** `c8bf84e10b92`
- Claude Code headless with Claude Opus 5.5, on a Claude subscription account (a Claude Code cloud session), not the API: nothing is billed per token. Cost is shown as $0; the list-price column is Claude Code's own API-equivalent estimate (total_cost_usd). No MCP servers are loaded (--strict-mcp-config).

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 29 | 100% (88% to 100%) | 0.99 | 1.00 | 0.98 | 0.86 | 246 s | 1,998,166 / 37,805,152 / 710,329 | $0.00 | $37.75 | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| sector-211-oil-gas (rep 1) | - | medium | 2026-11-16T05:15 | PASS | 0.98 | 1.00 | 0.96 | 204 s | 53,761 / 19,833 | 0 |  |
| sector-212-mining (rep 1) | - | medium | 2026-11-16T05:19 | PASS | 0.98 | 1.00 | 0.96 | 221 s | 68,127 / 20,959 | 0 |  |
| sector-2213-wastewater (rep 1) | - | medium | 2026-11-16T06:22 | PASS | 1.00 | 1.00 | 1.00 | 251 s | 61,347 / 24,814 | 0 |  |
| sector-311-food (rep 1) | - | medium | 2026-11-16T06:22 | PASS | 0.98 | 1.00 | 0.96 | 228 s | 54,602 / 22,241 | 0 |  |
| sector-312-beverage (rep 1) | - | medium | 2026-11-16T06:26 | PASS | 1.00 | 1.00 | 1.00 | 240 s | 66,721 / 22,825 | 0 |  |
| sector-313-textile-mills (rep 1) | - | medium | 2026-11-16T06:26 | PASS | 1.00 | 1.00 | 1.00 | 249 s | 68,026 / 23,911 | 0 |  |
| sector-314-carpet (rep 1) | - | medium | 2026-11-16T07:58 | PASS | 0.98 | 1.00 | 0.96 | 270 s | 84,681 / 27,684 | 0 |  |
| sector-315-apparel (rep 1) | - | medium | 2026-11-16T08:02 | PASS | 1.00 | 1.00 | 1.00 | 244 s | 78,141 / 25,110 | 0 |  |
| sector-316-footwear (rep 1) | - | medium | 2026-11-16T08:05 | PASS | 1.00 | 1.00 | 1.00 | 184 s | 63,881 / 19,712 | 0 |  |
| sector-321-wood (rep 1) | - | medium | 2026-11-16T08:09 | PASS | 0.98 | 1.00 | 0.96 | 249 s | 72,847 / 24,813 | 0 |  |
| sector-322-paper (rep 1) | - | medium | 2026-11-16T08:14 | PASS | 1.00 | 1.00 | 1.00 | 282 s | 72,986 / 29,478 | 0 |  |
| sector-323-printing (rep 1) | - | medium | 2026-11-16T08:17 | PASS | 0.97 | 1.00 | 0.94 | 225 s | 65,049 / 22,557 | 0 |  |
| sector-324-refining (rep 1) | - | medium | 2026-11-16T08:21 | PASS | 0.98 | 1.00 | 0.96 | 222 s | 64,144 / 22,430 | 0 |  |
| sector-325-chemicals (rep 1) | - | medium | 2026-11-16T08:26 | PASS | 0.97 | 0.94 | 1.00 | 287 s | 73,347 / 28,014 | 0 |  |
| sector-3254-pharmaceuticals (rep 1) | - | medium | 2026-11-16T08:30 | PASS | 0.95 | 1.00 | 0.90 | 224 s | 62,445 / 22,234 | 0 |  |
| sector-326-plastics (rep 1) | - | medium | 2026-11-16T05:16 | PASS | 1.00 | 1.00 | 1.00 | 249 s | 59,549 / 24,490 | 0 |  |
| sector-3272-glass (rep 1) | - | medium | 2026-11-16T08:34 | PASS | 0.98 | 1.00 | 0.96 | 272 s | 80,062 / 27,391 | 0 |  |
| sector-3273-cement (rep 1) | - | medium | 2026-11-16T08:39 | PASS | 1.00 | 1.00 | 1.00 | 251 s | 73,856 / 25,741 | 0 |  |
| sector-331-aluminum (rep 1) | - | medium | 2026-11-16T13:04 | PASS | 0.98 | 1.00 | 0.96 | 343 s | 79,483 / 32,591 | 0 |  |
| sector-3315-foundry (rep 1) | - | medium | 2026-11-16T13:09 | PASS | 0.98 | 1.00 | 0.96 | 283 s | 69,320 / 26,406 | 0 |  |
| sector-332-forging (rep 1) | - | medium | 2026-11-16T13:13 | PASS | 1.00 | 1.00 | 1.00 | 245 s | 70,918 / 25,159 | 0 |  |
| sector-332-machine-shop (rep 1) | - | medium | 2026-11-16T13:16 | PASS | 0.98 | 1.00 | 0.96 | 217 s | 67,653 / 22,542 | 0 |  |
| sector-333-machinery (rep 1) | - | medium | 2026-11-16T13:20 | PASS | 0.98 | 1.00 | 0.96 | 241 s | 65,271 / 23,808 | 0 |  |
| sector-3344-semiconductors (rep 1) | - | medium | 2026-11-16T13:26 | PASS | 0.98 | 1.00 | 0.96 | 303 s | 78,384 / 28,940 | 0 |  |
| sector-335-electrical-equipment (rep 1) | - | medium | 2026-11-16T13:30 | PASS | 0.98 | 1.00 | 0.96 | 251 s | 74,076 / 25,377 | 0 |  |
| sector-3361-motor-vehicles (rep 1) | - | medium | 2026-11-16T13:34 | PASS | 1.00 | 1.00 | 1.00 | 241 s | 66,685 / 24,721 | 0 |  |
| sector-3364-aerospace (rep 1) | - | medium | 2026-11-16T13:38 | PASS | 0.98 | 1.00 | 0.96 | 256 s | 71,263 / 24,688 | 0 |  |
| sector-337-furniture (rep 1) | - | medium | 2026-11-16T13:42 | PASS | 1.00 | 1.00 | 1.00 | 204 s | 66,612 / 20,687 | 0 |  |
| sector-3391-medical-devices (rep 1) | - | medium | 2026-11-16T13:45 | PASS | 1.00 | 1.00 | 1.00 | 202 s | 64,929 / 21,173 | 0 |  |
