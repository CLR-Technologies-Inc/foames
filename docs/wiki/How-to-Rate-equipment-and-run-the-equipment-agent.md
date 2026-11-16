**Goal:** give each machine an Equipment Complexity Level (ECL), then let an agent advise on the machines its model tier is good enough for, with the right person reviewing what it says.

**You need:** FoaMES Engineer or System Manager to rate machines; an agent connected over MCP as a user with the FoaMES Operator or FoaMES Engineer role (see [Connect an agent CLI or harness](How-to-Connect-an-agent-CLI-or-harness)). Background: [Equipment complexity levels](Explanation-Equipment-complexity-levels).

## 1. Rate your machines

Open a **Machine** and expand **Equipment Complexity**.

| Field | What to enter |
| --- | --- |
| Equipment Complexity Level (ECL) | 1 to 5. Leave it empty until someone has rated the machine; an agent will not advise on an unrated machine |
| ECL Equipment Class | The class id from the public [Equipment Complexity Levels list](https://github.com/CLR-Technologies-Inc/equipment-complexity-levels), for example `cnc-machining-centre`, when you took the level from it |
| ECL Rationale | Why this level, for this machine as configured here |

The public list covers catalogue (SKU-bound) equipment and rates typical machines of each class. Its first entries are drafts marked `ai-initial`, so check them. Rate the machine you actually have: a CNC machine with one fixed cycle may be ECL 2, and a press with adaptive force control may be ECL 3. Custom equipment is not in the list; rate it from the level table. A line takes the ECL of its most complex rated machine.

ECL is complexity, not criticality. Keep criticality in your maintenance ranking.

## 2. See the coverage

Run `foames_list_equipment_complexity` from any MCP client, or filter the Machine list by ECL. It returns the count per level, the machines not rated yet and each line's ECL.

## 3. Give the agent the skill

The equipment agent is a skill file: [docs/agents/equipment-agent/SKILL.md](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/agents/equipment-agent/SKILL.md). Load it the way your harness loads skills. For example, copy the folder into your own project's skills folder for Claude Code, or paste the file in as the agent's instructions. Then tell the agent two things:

- **Its model tier**: `oss` (open weights), `baseline` (low-cost hosted) or `frontier`. Pick it from your [benchmark runs](How-to-Run-the-agent-benchmark), not from the model's own claim.
- **The mode.** It reports only, by default. Say "suggest mode is on" to let it post Agent Suggestions. Those are its only writes. With read-only mode on, they may wait for sign-off first.

## 4. Ask it for work

Examples:

- "Audit ECL coverage and propose ratings for the unrated machines from the public list." The agent matches each machine's type and title to a class and proposes the level, the class id and its rationale, marked Draft where the list entry is unreviewed. People set the fields.
- "Look at press-2's downtime this week and suggest what to do." The agent first calls `foames_get_equipment_profile(machine, tier)`. It advises only if its tier meets the machine's minimum.

What you get back depends on the level:

| ECL | The agent | Review by |
| --- | --- | --- |
| 1 to 3 | Suggests one action, with its numbers | The operator or engineer |
| 4 | Gives two or three options, without choosing one | One expert in that equipment (**Human Expert Recommended**) |
| 5 | Lists options and open questions, and decides nothing | A team of experts (**Expert Team Required**) |

## Check it worked

- `foames_get_equipment_profile` for a rated machine shows its `ecl`, `min_tier` and `human_oversight`. With `tier` given, it also returns an `eligibility` verdict.
- Suggestions from the agent carry `agent = foames-equipment-agent`. Rating proposals use `rule_key = ecl-rating:<machine>`, so a proposal is never raised twice while it is open.
- The agent's report lists the machines it skipped and why.
