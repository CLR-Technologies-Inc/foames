**Goal:** have an agent watch the material at your machines, warn before a line runs dry, and point at material close to or past its time limit. Decisions about difficult material go to the right experts.

**You need:** an agent connected over MCP as a user with the FoaMES Operator, Quality or Engineer role (see [Connect an agent CLI or harness](How-to-Connect-an-agent-CLI-or-harness)). Background: [Material processing complexity](Explanation-Material-processing-complexity) and [Equipment complexity levels](Explanation-Equipment-complexity-levels).

> **Two modes.** Lineside inventory, material queues, dry-line alerts and MPC are in review in [pull request #72](https://github.com/CLR-Technologies-Inc/foames/pull/72) (see [Upcoming features](Upcoming-features)). On a site that has them, the agent runs in **full mode**. On one that does not, it runs in **reduced mode**: it reports downtime recorded for missing material and says that it can see nothing more. It checks which mode applies itself, from the tools the site offers.

## 1. Give the agent the skill

The materials agent is a skill file: [docs/agents/materials-agent/SKILL.md](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/agents/materials-agent/SKILL.md). Load it the way your harness loads skills. For example, copy the folder into your own project's skills folder for Claude Code, or paste the file in as the agent's instructions. It reports only, by default. Say "suggest mode is on" to let it post Agent Suggestions. Those are its only writes. With read-only mode on, they may wait for sign-off first.

The ERP stays the inventory system of record. The agent never calls for, moves or consumes material. It tells people what to call for in the ERP and by when.

## 2. Ask it for work

- "Which lines will run dry this shift?" The agent lists bins worst first (**Dry**, **Will Run Dry**, **Running Dry**, **Reorder**) with stock on hand, use per hour, hours to dry and the quantity to call for.
- "What in the queues is close to its Q-time or floor life?" For each queue, it reads the dispatch list in the queue's own order. It reports entries in **Q-time Warning** with the time left, and sends anything **Q-time Exceeded** or **Expired** to Quality to decide. It never puts those in a start order.
- "Can press-2 run the next four hours?" It calls `foames_get_material_readiness(machine, hours)` before suggesting a start.

## 3. Who reviews

The material's MPC and the machine's ECL both set oversight, and the stricter one wins:

| Rating | Review by |
| --- | --- |
| MPC 1 to 3 and ECL 1 to 3 | The operator, engineer or Quality |
| MPC 4 or ECL 4 | One expert (**Human Expert Recommended**). The agent gives options, not a decision |
| MPC 5 or ECL 5 | A team of experts (**Expert Team Required**). The agent lists options only. MPC 5 material cannot start until an expert review is recorded |

## Check it worked

- The report opens with the mode (full or reduced) and the read-only state.
- Suggestions from the agent carry `agent = foames-materials-agent`. FoaMES's own material check posts as `foames-material`, and the agent does not repeat what that check already raised.
- Every finding about MPC 4 or 5 material, or ECL 4 or 5 equipment, names its level and its reviewer.
