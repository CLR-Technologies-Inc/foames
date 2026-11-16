**FoaMES** (Free Open-source Agentic MES) is a manufacturing execution system built as a [Frappe](https://frappe.io/framework) app. It reads your machines, keeps an honest record of what they did, computes OEE, shows the floor live, and raises findings for people to act on. It runs with ERPNext on the same site, with SAP S/4HANA or another system through an adapter, or with no ERP at all.

This wiki is for people who are new to FoaMES. It is organised the [Diátaxis](https://diataxis.fr/) way, so pick the kind of page that matches what you need right now:

| You want to... | Read | Start with |
| --- | --- | --- |
| **Learn** FoaMES by doing, step by step | [Tutorials](Tutorials) | [Install FoaMES on a development site](Tutorial-1-Install-FoaMES) |
| **Get a specific job done** on a site you already run | [How-to guides](How-to-guides) | [Connect ERPNext](How-to-Connect-ERPNext) |
| **Look something up**: a DocType, a setting, an API method, an MCP tool | [Reference](Reference) | [DocTypes](Reference-DocTypes) |
| **Understand** why FoaMES works the way it does | [Explanation](Explanation) | [The ERP-agnostic core and adapters](Explanation-ERP-agnostic-core-and-adapters) |

## What FoaMES does today

Everything below is on the `main` branch and is described in this wiki.

- **Machine data** from a signed webhook, MQTT, OPC UA (with Sign and SignAndEncrypt) or Sparkplug B, plus read-only bridges for process historians and lab instruments.
- **Machine states and downtime**, opened and closed automatically from the machine's own signal, with reasons that operators assign.
- **OEE** per day or per shift from a minute-by-minute time ledger, where silence is counted as loss and never as run time.
- **The Floor View**, a live page of machine tiles and open suggestions.
- **Agent Suggestions** from built-in rules, from SPC run rules, from maintenance plans and from external AI agents. FoaMES never acts on a suggestion by itself.
- **Andon calls** with response targets and escalation.
- **Statistical process control** (I-MR and X-bar R charts with Nelson and Western Electric rules) on machine measurements.
- **Preventive maintenance** plans by calendar, run hours or counts, with work orders and a due list.
- **Building management**: utilities and building services (water, wastewater, electricity, chilled water, HVAC, RTUs, chillers, lighting, server rooms, hazmat storage) read over BACnet/IP or Modbus TCP, with alarm limits, communication-loss alarms, utility consumption per good unit and maintenance on building equipment. Read-only.
- **Standard operating procedures** as controlled documents, with sign-off, effective dates and a training matrix.
- **Process mining**: event logs, discovery, conformance, XES and OCEL 2.0 export.
- **An MCP server**, so Claude, Cursor or any MCP client can read the floor and raise suggestions under a normal user's permissions.
- **Adapters** for ERPNext, SAP S/4HANA, Siemens Insights Hub and eleven MES and frontline platforms (including Tulip), all alpha.
- **An agent benchmark** that scores any coding agent (Claude Code, Codex, Gemini CLI, OpenCode, Aider or your own harness) on FoaMES tasks, in a sandbox, against the manufacturing invariants, with time, tokens and cost.
- **Role workspaces, dashboards and reports** for operators, supervisors, maintenance, quality and integration staff.

Features that are still being reviewed are listed on [[Upcoming features|Upcoming-features]]. They are not on `main` yet and may change.

## Starting with agents

If you are here to test AI agents, there are two paths, and neither needs a real plant:

- **Agents that use FoaMES** (read the floor, analyse OEE, raise suggestions): [Tutorial 3](Tutorial-3-Your-first-agent-over-MCP), then [Connect an agent CLI or harness](How-to-Connect-an-agent-CLI-or-harness) and [Seed a dev site for agent tests](How-to-Seed-a-dev-site-for-agent-tests).
- **Agents that develop FoaMES** (fix bugs, add features, write specifications): [Tutorial 4](Tutorial-4-Your-first-agent-benchmark-run), which needs no site, then [Run the agent benchmark](How-to-Run-the-agent-benchmark).

## Where things live

- Code and the canonical documentation: [CLR-Technologies-Inc/foames](https://github.com/CLR-Technologies-Inc/foames) and its [`docs/`](https://github.com/CLR-Technologies-Inc/foames/tree/main/docs) folder. This wiki gives new users a guided path; the `docs/` pages go deeper, and when the two disagree the code and `docs/` on `main` are right.
- Questions, bugs and ideas: [Issues](https://github.com/CLR-Technologies-Inc/foames/issues).
- Contributing: [[How to contribute|How-to-Contribute]].

FoaMES is licensed under the [Apache License 2.0](https://github.com/CLR-Technologies-Inc/foames/blob/main/LICENSE). All integrations are **alpha**: they are built against each vendor's published interfaces and tested against stand-ins, so treat each as unproven until you have run it against your own system.
