# claude-code-fable-5-2: benchmark run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T05:12:08+00:00, last run finished 2026-11-16T15:08:42+00:00
- **Model:** `claude-fable-5-2` (frontier tier, built for agentic coding), Claude Code 2.1.325 (CLI), model claude-fable-5-2, called 2026-11-16 through this account's Claude subscription (not the API); the model behind an alias may be updated by Anthropic
- **Harness:** claude-code
- **Where it ran:** Claude Code cloud container (Linux, unshare sandbox), tasks from commit c8bf84e; subscription run, cost $0; list price is Claude Code's API-equivalent estimate; sandbox unshare
- **FoaMES commit:** `c8bf84e10b92`
- Claude Code headless with Claude Fable 5.2, on a Claude subscription account (a Claude Code cloud session), not the API: nothing is billed per token. Cost is shown as $0; the list-price column is Claude Code's own API-equivalent estimate (total_cost_usd). No MCP servers are loaded (--strict-mcp-config).

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 35 | 97% (86% to 100%) | 0.98 | 0.99 | 0.97 | 0.83 | 203 s | 2,294,220 / 23,344,186 / 729,957 | $0.00 | $70.57 | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T14:54 | PASS | 1.00 | 1.00 | 1.00 | 56 s | 46,295 / 5,017 | 0 |  |
| erp-retry-after (rep 1) | - | high | 2026-11-16T14:56 | PASS | 0.85 | 1.00 | 0.69 | 148 s | 85,302 / 15,978 | 0 |  |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T14:57 | PASS | 1.00 | 1.00 | 1.00 | 62 s | 33,236 / 6,569 | 0 |  |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T14:58 | PASS | 1.00 | 1.00 | 1.00 | 66 s | 41,170 / 7,075 | 0 |  |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T15:06 | PASS | 1.00 | 1.00 | 1.00 | 483 s | 131,962 / 47,584 | 0 |  |
| sector-211-oil-gas (rep 1) | - | medium | 2026-11-16T05:15 | PASS | 1.00 | 1.00 | 1.00 | 206 s | 60,087 / 21,817 | 0 |  |
| sector-212-mining (rep 1) | - | medium | 2026-11-16T05:18 | PASS | 0.98 | 1.00 | 0.96 | 170 s | 66,630 / 19,469 | 0 |  |
| sector-2213-wastewater (rep 1) | - | medium | 2026-11-16T06:02 | PASS | 1.00 | 1.00 | 1.00 | 172 s | 68,757 / 19,017 | 0 |  |
| sector-311-food (rep 1) | - | medium | 2026-11-16T06:24 | PASS | 1.00 | 1.00 | 1.00 | 362 s | 60,892 / 26,145 | 0 |  |
| sector-312-beverage (rep 1) | - | medium | 2026-11-16T06:21 | PASS | 1.00 | 1.00 | 1.00 | 208 s | 55,752 / 22,904 | 0 |  |
| sector-313-textile-mills (rep 1) | - | medium | 2026-11-16T06:27 | PASS | 0.98 | 1.00 | 0.96 | 186 s | 63,299 / 20,376 | 0 |  |
| sector-314-carpet (rep 1) | - | medium | 2026-11-16T06:24 | PASS | 0.98 | 1.00 | 0.96 | 178 s | 59,347 / 19,293 | 0 |  |
| sector-315-apparel (rep 1) | - | medium | 2026-11-16T07:56 | PASS | 0.98 | 1.00 | 0.96 | 196 s | 70,071 / 20,373 | 0 |  |
| sector-316-footwear (rep 1) | - | medium | 2026-11-16T06:28 | PASS | 1.00 | 1.00 | 1.00 | 191 s | 63,568 / 21,175 | 0 |  |
| sector-321-wood (rep 1) | - | medium | 2026-11-16T08:00 | PASS | 0.98 | 1.00 | 0.96 | 193 s | 72,516 / 20,182 | 0 |  |
| sector-322-paper (rep 1) | - | medium | 2026-11-16T08:03 | PASS | 1.00 | 1.00 | 1.00 | 224 s | 81,381 / 24,232 | 0 |  |
| sector-323-printing (rep 1) | - | medium | 2026-11-16T08:07 | PASS | 1.00 | 1.00 | 1.00 | 195 s | 66,387 / 20,784 | 0 |  |
| sector-324-refining (rep 1) | - | medium | 2026-11-16T08:10 | PASS | 0.98 | 1.00 | 0.96 | 187 s | 60,527 / 20,498 | 0 |  |
| sector-325-chemicals (rep 1) | - | medium | 2026-11-16T08:14 | PASS | 0.94 | 0.94 | 0.94 | 247 s | 72,899 / 27,417 | 0 |  |
| sector-3254-pharmaceuticals (rep 1) | - | medium | 2026-11-16T08:17 | PASS | 0.98 | 1.00 | 0.96 | 196 s | 65,675 / 21,415 | 0 |  |
| sector-326-plastics (rep 1) | - | medium | 2026-11-16T05:15 | PASS | 1.00 | 1.00 | 1.00 | 208 s | 63,305 / 22,743 | 0 |  |
| sector-3272-glass (rep 1) | - | medium | 2026-11-16T05:18 | PASS | 0.98 | 1.00 | 0.96 | 170 s | 64,547 / 18,864 | 0 |  |
| sector-3273-cement (rep 1) | - | medium | 2026-11-16T08:21 | PASS | 0.98 | 1.00 | 0.96 | 201 s | 72,084 / 22,443 | 0 |  |
| sector-331-aluminum (rep 1) | - | medium | 2026-11-16T08:24 | PASS | 1.00 | 1.00 | 1.00 | 207 s | 66,826 / 23,261 | 0 |  |
| sector-3315-foundry (rep 1) | - | medium | 2026-11-16T08:28 | PASS | 0.98 | 1.00 | 0.96 | 216 s | 68,189 / 23,879 | 0 |  |
| sector-332-forging (rep 1) | - | medium | 2026-11-16T08:31 | PASS | 1.00 | 1.00 | 1.00 | 216 s | 73,025 / 23,795 | 0 |  |
| sector-332-machine-shop (rep 1) | - | medium | 2026-11-16T08:34 | PASS | 0.98 | 1.00 | 0.96 | 177 s | 62,748 / 20,064 | 0 |  |
| sector-333-machinery (rep 1) | - | medium | 2026-11-16T08:38 | PASS | 1.00 | 1.00 | 1.00 | 206 s | 69,153 / 22,564 | 0 |  |
| sector-3344-semiconductors (rep 1) | - | medium | 2026-11-16T13:02 | PASS | 0.98 | 1.00 | 0.96 | 209 s | 53,203 / 22,738 | 0 |  |
| sector-335-electrical-equipment (rep 1) | - | medium | 2026-11-16T13:05 | PASS | 0.98 | 1.00 | 0.96 | 178 s | 59,695 / 20,086 | 0 |  |
| sector-3361-motor-vehicles (rep 1) | - | medium | 2026-11-16T13:08 | PASS | 1.00 | 1.00 | 1.00 | 211 s | 67,837 / 23,208 | 0 |  |
| sector-3364-aerospace (rep 1) | - | medium | 2026-11-16T13:14 | PASS | 0.98 | 1.00 | 0.96 | 339 s | 69,513 / 23,649 | 0 |  |
| sector-337-furniture (rep 1) | - | medium | 2026-11-16T13:17 | PASS | 0.98 | 1.00 | 0.96 | 195 s | 62,251 / 21,464 | 0 |  |
| sector-3391-medical-devices (rep 1) | - | medium | 2026-11-16T13:23 | PASS | 0.98 | 1.00 | 0.96 | 325 s | 67,703 / 22,796 | 0 |  |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T15:08 | fail | 0.71 | 0.57 | 0.86 | 106 s | 48,388 / 11,083 | 0 | broke an invariant |
