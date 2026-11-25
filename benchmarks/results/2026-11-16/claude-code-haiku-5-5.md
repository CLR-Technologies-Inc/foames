# claude-code-haiku-5-5: benchmark run of 2026-11-16

<!-- Copyright 2026 CLR Technologies Inc. -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T05:12:08+00:00, last run finished 2026-11-16T15:08:22+00:00
- **Model:** `claude-haiku-5-5` (baseline tier, built for agentic coding), Claude Code 2.1.325 (CLI), model claude-haiku-5-5, called 2026-11-16 through this account's Claude subscription (not the API); the model behind an alias may be updated by Anthropic
- **Harness:** claude-code
- **Where it ran:** Claude Code cloud container (Linux, unshare sandbox), tasks from commit c8bf84e; subscription run, cost $0; list price is Claude Code's API-equivalent estimate; sandbox unshare
- **FoaMES commit:** `c8bf84e10b92`
- Claude Code headless with Claude Haiku 5.5, on a Claude subscription account (a Claude Code cloud session), not the API: nothing is billed per token. Cost is shown as $0; the list-price column is Claude Code's own API-equivalent estimate (total_cost_usd). No MCP servers are loaded (--strict-mcp-config).

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 35 | 94% (81% to 98%) | 0.99 | 1.00 | 0.97 | 0.92 | 328 s | 4,156,915 / 94,099,568 / 2,353,432 | $0.00 | $10.72 | ECL 2 |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T14:54 | PASS | 1.00 | 1.00 | 1.00 | 98 s | 56,740 / 17,528 | 0 |  |
| erp-retry-after (rep 1) | - | high | 2026-11-16T14:56 | PASS | 0.87 | 1.00 | 0.72 | 126 s | 91,257 / 26,896 | 0 |  |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T14:58 | PASS | 1.00 | 1.00 | 1.00 | 72 s | 48,427 / 14,607 | 0 |  |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T15:00 | PASS | 1.00 | 1.00 | 1.00 | 140 s | 72,631 / 29,738 | 0 |  |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T15:06 | fail | 0.98 | 1.00 | 0.95 | 372 s | 155,925 / 74,009 | 0 | broke an invariant |
| sector-211-oil-gas (rep 1) | - | medium | 2026-11-16T06:23 | PASS | 0.96 | 1.00 | 0.92 | 274 s | 93,180 / 57,453 | 0 |  |
| sector-212-mining (rep 1) | - | medium | 2026-11-16T06:25 | PASS | 0.98 | 1.00 | 0.96 | 413 s | 131,329 / 91,171 | 0 |  |
| sector-2213-wastewater (rep 1) | - | medium | 2026-11-16T06:28 | PASS | 1.00 | 1.00 | 1.00 | 301 s | 111,010 / 62,905 | 0 |  |
| sector-311-food (rep 1) | - | medium | 2026-11-16T07:59 | PASS | 0.98 | 1.00 | 0.96 | 354 s | 134,614 / 75,714 | 0 |  |
| sector-312-beverage (rep 1) | - | medium | 2026-11-16T08:05 | PASS | 1.00 | 1.00 | 1.00 | 381 s | 148,130 / 82,512 | 0 |  |
| sector-313-textile-mills (rep 1) | - | medium | 2026-11-16T08:11 | PASS | 1.00 | 1.00 | 1.00 | 316 s | 115,560 / 66,876 | 0 |  |
| sector-314-carpet (rep 1) | - | medium | 2026-11-16T08:15 | PASS | 0.98 | 1.00 | 0.96 | 274 s | 107,680 / 58,970 | 0 |  |
| sector-315-apparel (rep 1) | - | medium | 2026-11-16T08:22 | PASS | 1.00 | 1.00 | 1.00 | 389 s | 144,291 / 85,861 | 0 |  |
| sector-316-footwear (rep 1) | - | medium | 2026-11-16T08:28 | PASS | 0.95 | 1.00 | 0.90 | 352 s | 126,973 / 75,496 | 0 |  |
| sector-321-wood (rep 1) | - | medium | 2026-11-16T08:35 | PASS | 0.98 | 1.00 | 0.96 | 428 s | 156,608 / 91,027 | 0 |  |
| sector-322-paper (rep 1) | - | medium | 2026-11-16T13:07 | PASS | 0.97 | 1.00 | 0.94 | 501 s | 143,210 / 94,933 | 0 |  |
| sector-323-printing (rep 1) | - | medium | 2026-11-16T13:14 | PASS | 1.00 | 1.00 | 1.00 | 418 s | 127,961 / 77,666 | 0 |  |
| sector-324-refining (rep 1) | - | medium | 2026-11-16T13:19 | PASS | 0.98 | 1.00 | 0.96 | 351 s | 112,472 / 64,838 | 0 |  |
| sector-325-chemicals (rep 1) | - | medium | 2026-11-16T13:25 | PASS | 0.97 | 0.94 | 1.00 | 348 s | 116,267 / 70,565 | 0 |  |
| sector-3254-pharmaceuticals (rep 1) | - | medium | 2026-11-16T13:31 | PASS | 0.99 | 1.00 | 0.98 | 311 s | 115,290 / 65,949 | 0 |  |
| sector-326-plastics (rep 1) | - | medium | 2026-11-16T05:17 | PASS | 1.00 | 1.00 | 1.00 | 343 s | 117,089 / 71,451 | 0 |  |
| sector-3272-glass (rep 1) | - | medium | 2026-11-16T13:36 | PASS | 1.00 | 1.00 | 1.00 | 323 s | 119,200 / 67,295 | 0 |  |
| sector-3273-cement (rep 1) | - | medium | 2026-11-16T13:42 | PASS | 0.97 | 1.00 | 0.94 | 335 s | 109,466 / 66,651 | 0 |  |
| sector-331-aluminum (rep 1) | - | medium | 2026-11-16T13:47 | PASS | 1.00 | 1.00 | 1.00 | 313 s | 116,998 / 66,357 | 0 |  |
| sector-3315-foundry (rep 1) | - | medium | 2026-11-16T13:52 | PASS | 1.00 | 1.00 | 1.00 | 335 s | 119,532 / 69,010 | 0 |  |
| sector-332-forging (rep 1) | - | medium | 2026-11-16T13:58 | PASS | 1.00 | 1.00 | 1.00 | 335 s | 124,094 / 67,764 | 0 |  |
| sector-332-machine-shop (rep 1) | - | medium | 2026-11-16T14:08 | PASS | 1.00 | 1.00 | 1.00 | 586 s | 153,757 / 93,736 | 0 |  |
| sector-333-machinery (rep 1) | - | medium | 2026-11-16T14:13 | PASS | 1.00 | 1.00 | 1.00 | 316 s | 118,948 / 65,584 | 0 |  |
| sector-3344-semiconductors (rep 1) | - | medium | 2026-11-16T14:21 | PASS | 1.00 | 1.00 | 1.00 | 470 s | 155,761 / 96,174 | 0 |  |
| sector-335-electrical-equipment (rep 1) | - | medium | 2026-11-16T14:28 | PASS | 0.98 | 1.00 | 0.96 | 391 s | 133,491 / 83,626 | 0 |  |
| sector-3361-motor-vehicles (rep 1) | - | medium | 2026-11-16T14:34 | PASS | 0.97 | 1.00 | 0.94 | 376 s | 133,137 / 80,809 | 0 |  |
| sector-3364-aerospace (rep 1) | - | medium | 2026-11-16T14:39 | PASS | 1.00 | 1.00 | 1.00 | 309 s | 125,112 / 66,286 | 0 |  |
| sector-337-furniture (rep 1) | - | medium | 2026-11-16T14:45 | fail | 0.96 | 1.00 | 0.92 | 350 s | 128,997 / 72,778 | 0 | broke an invariant |
| sector-3391-medical-devices (rep 1) | - | medium | 2026-11-16T14:51 | PASS | 1.00 | 1.00 | 1.00 | 388 s | 136,396 / 82,477 | 0 |  |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T15:08 | PASS | 1.00 | 1.00 | 1.00 | 93 s | 55,382 / 18,720 | 0 |  |
