**Goal:** see which paths work really takes, where it waits, where it is reworked, and whether the floor follows the process you defined.

**You need:** FoaMES Supervisor or Engineer.

## 1. Choose the events

Machine states and downtime are built in. To mine any other DocType on the site (an ERP Work Order, a Job Card, a Quality Inspection), create an **Event Log Source**:

1. Name the DocType as text. If it is not installed, the source is skipped, so a site without that ERP still works.
2. Map the **case** (what a trace follows, such as the work order), the **activity**, the **timestamp**, an optional **end timestamp**, the **resource**, any filters and object fields.
3. Press **Preview events** to check the mapping.

## 2. Extract a log

Create a **Process Event Log**, set the window and the sources, and press **Extract**.

## 3. Analyse it

- **Analyse > Discover** shows the directly-follows graph, the variants with their share and median duration, throughput, service and waiting times, bottlenecks and rework, and a Graphviz DOT rendering.
- **Analyse > Check against another log** replays this log on the graph of a reference log, such as a known-good week, and reports fitness and each deviation.
- **Export** attaches the log as **XES** or **OCEL 2.0** for ProM, PM4Py, Celonis, Disco or any other tool.

The **Process Throughput** report shows cases completed per day or week and cycle times.

Agents can do the same through the `foames_mining_*` MCP tools; see [MCP tools](Reference-MCP-tools). Details: [docs/process-mining.md](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/process-mining.md).
