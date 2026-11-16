# claude-code-sonnet-5-5: benchmark run of 2026-11-16

<!-- Copyright (c) 2026 CLR Technologies Inc. and contributors -->
<!-- SPDX-License-Identifier: Apache-2.0 -->

- **Run dates (UTC):** started 2026-11-16T05:12:08+00:00, last run finished 2026-11-16T15:00:55+00:00
- **Model:** `claude-sonnet-5-5` (baseline tier, built for agentic coding), Claude Code 2.1.325 (CLI), model claude-sonnet-5-5, called 2026-11-16 through this account's Claude subscription (not the API); the model behind an alias may be updated by Anthropic
- **Harness:** claude-code
- **Where it ran:** Claude Code cloud container (Linux, unshare sandbox), tasks from commit c8bf84e; subscription run, cost $0; list price is Claude Code's API-equivalent estimate; sandbox unshare
- **FoaMES commit:** `c8bf84e10b92`
- Claude Code headless with Claude Sonnet 5.5, on a Claude subscription account (a Claude Code cloud session), not the API: nothing is billed per token. Cost is shown as $0; the list-price column is Claude Code's own API-equivalent estimate (total_cost_usd). No MCP servers are loaded (--strict-mcp-config).

| Runs | Success (95 % CI) | Quality | Correctness | Process | Composite | Mean time | Tokens in / cached / out | Cost | List-price equivalent | ECL reached |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 35 | 94% (81% to 98%) | 0.98 | 0.98 | 0.97 | 0.93 | 101 s | 1,861,997 / 21,855,432 / 487,575 | $0.00 | $14.51 | none |

| Task | ECL | Complexity | Finished (UTC) | Success | Quality | Correctness | Process | Time | Tokens in / out | Exit | Notes |
| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| counter-reset (rep 1) | 2 | low | 2026-11-16T14:53 | PASS | 1.00 | 1.00 | 1.00 | 38 s | 40,510 / 4,454 | 0 |  |
| erp-retry-after (rep 1) | - | high | 2026-11-16T14:54 | PASS | 0.98 | 1.00 | 0.96 | 50 s | 49,707 / 6,964 | 0 |  |
| oee-unknown-time (rep 1) | 2 | medium | 2026-11-16T14:55 | PASS | 1.00 | 1.00 | 1.00 | 29 s | 32,536 / 4,003 | 0 |  |
| process-mining-analysis (rep 1) | 3 | medium | 2026-11-16T14:55 | PASS | 1.00 | 1.00 | 1.00 | 41 s | 34,279 / 4,952 | 0 |  |
| process-spec-network-loss (rep 1) | 3 | high | 2026-11-16T15:00 | fail | 0.98 | 1.00 | 0.95 | 265 s | 93,200 / 34,415 | 0 | broke an invariant |
| sector-211-oil-gas (rep 1) | - | medium | 2026-11-16T05:14 | PASS | 0.98 | 1.00 | 0.96 | 117 s | 50,454 / 15,681 | 0 |  |
| sector-212-mining (rep 1) | - | medium | 2026-11-16T05:15 | PASS | 0.97 | 1.00 | 0.94 | 101 s | 54,914 / 14,032 | 0 |  |
| sector-2213-wastewater (rep 1) | - | medium | 2026-11-16T05:17 | PASS | 0.97 | 1.00 | 0.94 | 72 s | 49,882 / 10,211 | 0 |  |
| sector-311-food (rep 1) | - | medium | 2026-11-16T05:19 | PASS | 0.97 | 1.00 | 0.94 | 136 s | 62,244 / 18,079 | 0 |  |
| sector-312-beverage (rep 1) | - | medium | 2026-11-16T06:01 | PASS | 0.98 | 1.00 | 0.96 | 114 s | 63,942 / 16,701 | 0 |  |
| sector-313-textile-mills (rep 1) | - | medium | 2026-11-16T06:01 | PASS | 1.00 | 1.00 | 1.00 | 102 s | 59,705 / 14,016 | 0 |  |
| sector-314-carpet (rep 1) | - | medium | 2026-11-16T06:20 | PASS | 0.97 | 1.00 | 0.94 | 91 s | 36,630 / 12,681 | 0 |  |
| sector-315-apparel (rep 1) | - | medium | 2026-11-16T06:20 | PASS | 1.00 | 1.00 | 1.00 | 110 s | 45,111 / 14,693 | 0 |  |
| sector-316-footwear (rep 1) | - | medium | 2026-11-16T06:21 | PASS | 0.99 | 1.00 | 0.98 | 88 s | 49,933 / 12,586 | 0 |  |
| sector-321-wood (rep 1) | - | medium | 2026-11-16T06:21 | PASS | 0.97 | 1.00 | 0.94 | 89 s | 47,955 / 12,366 | 0 |  |
| sector-322-paper (rep 1) | - | medium | 2026-11-16T06:23 | PASS | 0.98 | 1.00 | 0.96 | 111 s | 58,783 / 15,995 | 0 |  |
| sector-323-printing (rep 1) | - | medium | 2026-11-16T06:23 | PASS | 1.00 | 1.00 | 1.00 | 74 s | 47,610 / 10,372 | 0 |  |
| sector-324-refining (rep 1) | - | medium | 2026-11-16T06:25 | PASS | 0.95 | 1.00 | 0.90 | 107 s | 52,437 / 14,644 | 0 |  |
| sector-325-chemicals (rep 1) | - | medium | 2026-11-16T06:24 | PASS | 0.96 | 0.94 | 0.98 | 104 s | 53,358 / 14,707 | 0 |  |
| sector-3254-pharmaceuticals (rep 1) | - | medium | 2026-11-16T06:26 | PASS | 1.00 | 1.00 | 1.00 | 89 s | 50,533 / 12,867 | 0 |  |
| sector-326-plastics (rep 1) | - | medium | 2026-11-16T05:13 | PASS | 0.95 | 1.00 | 0.90 | 107 s | 42,895 / 14,820 | 0 |  |
| sector-3272-glass (rep 1) | - | medium | 2026-11-16T05:15 | PASS | 0.99 | 1.00 | 0.98 | 113 s | 52,209 / 15,365 | 0 |  |
| sector-3273-cement (rep 1) | - | medium | 2026-11-16T05:17 | PASS | 1.00 | 1.00 | 1.00 | 94 s | 49,178 / 13,290 | 0 |  |
| sector-331-aluminum (rep 1) | - | medium | 2026-11-16T05:19 | PASS | 0.99 | 1.00 | 0.98 | 105 s | 53,271 / 14,828 | 0 |  |
| sector-3315-foundry (rep 1) | - | medium | 2026-11-16T06:27 | PASS | 1.00 | 1.00 | 1.00 | 128 s | 59,514 / 18,035 | 0 |  |
| sector-332-forging (rep 1) | - | medium | 2026-11-16T07:55 | PASS | 0.98 | 1.00 | 0.96 | 115 s | 64,083 / 15,986 | 0 |  |
| sector-332-machine-shop (rep 1) | - | medium | 2026-11-16T07:57 | PASS | 0.97 | 1.00 | 0.94 | 103 s | 63,857 / 14,404 | 0 |  |
| sector-333-machinery (rep 1) | - | medium | 2026-11-16T07:59 | PASS | 1.00 | 1.00 | 1.00 | 133 s | 66,647 / 18,435 | 0 |  |
| sector-3344-semiconductors (rep 1) | - | medium | 2026-11-16T08:01 | PASS | 0.99 | 1.00 | 0.98 | 131 s | 68,469 / 18,404 | 0 |  |
| sector-335-electrical-equipment (rep 1) | - | medium | 2026-11-16T08:03 | PASS | 1.00 | 1.00 | 1.00 | 114 s | 56,709 / 16,323 | 0 |  |
| sector-3361-motor-vehicles (rep 1) | - | medium | 2026-11-16T08:05 | PASS | 0.96 | 0.94 | 0.98 | 112 s | 56,892 / 15,462 | 0 |  |
| sector-3364-aerospace (rep 1) | - | medium | 2026-11-16T08:07 | PASS | 0.98 | 1.00 | 0.96 | 89 s | 51,060 / 12,983 | 0 |  |
| sector-337-furniture (rep 1) | - | medium | 2026-11-16T08:08 | PASS | 0.98 | 1.00 | 0.96 | 101 s | 51,557 / 14,457 | 0 |  |
| sector-3391-medical-devices (rep 1) | - | medium | 2026-11-16T08:10 | PASS | 0.98 | 1.00 | 0.96 | 121 s | 57,997 / 16,110 | 0 |  |
| spc-ewma-chart (rep 1) | 2 | medium | 2026-11-16T15:00 | fail | 0.72 | 0.57 | 0.90 | 32 s | 33,936 / 4,254 | 0 | broke an invariant |
