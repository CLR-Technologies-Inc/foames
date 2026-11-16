# FoaMES topology collectors

Optional collectors that add what FoaMES cannot see by itself to its topology graph
([docs/topology.md](../../docs/topology.md)). Standard library only, Python 3.10 or later.

| Collector | Reads | Reports |
| --- | --- | --- |
| `network` | `tailscale status --json` (or a saved copy) | each node as a Host on the physical layer, joined to the tailnet by a Network link; online hosts OK, offline ones Down with their last-seen time |
| `agents` | a JSON Lines log of agent events | each agent as an Agent and each task as an Agent Task on the data layer; Delegates links for who handed what to whom; Runs On links to hosts; a Write binding from a task to the equipment it acts on |

Both only read what they observe. Ids line up across collectors and the built-in sync: the agent
collector's `host:<name>` is the network collector's host, and a task's `target` can be any
existing asset id such as `machine:P-201`.

## Run

Create a user with the **FoaMES Integration** role and an API key, then:

```sh
pip install ./bridges/topology
export FOAMES_API_KEY=… FOAMES_API_SECRET=…
foames-topology-collect network --provider network-collector --tenant "Plant A" --site-name "Plant A" --url https://foames.example.com
foames-topology-collect agents --provider agent-events --log /var/log/agents/events.jsonl --url https://foames.example.com
```

`--dry-run` (or leaving out `--url`) prints the report instead of sending it. Run each from cron
or a systemd timer, every few minutes. Each report is a full one (`retire_missing`), so hosts that
leave the tailnet and tasks that age out of `--window-hours` (default 24) are retired.

The provider name is yours to choose; the names `foames-mes`, `foames-pid` and `foames-erp` are
reserved for the built-in sync. A provider can only change what it reported itself.

## Agent event log

One JSON object per line. Only `agent` and `task` are required.

```json
{"time": "2026-11-15T10:01:00Z", "agent": "planner", "task": "T-11", "status": "running",
 "title": "Re-plan line 2", "host": "gpu-box", "delegated_by": "orchestrator", "parent_task": "T-10",
 "target": "machine:CNC-01"}
```

`status` maps to running → Running, done or completed → OK, failed or error → Down, waiting,
queued or blocked → Idle. The latest event per task wins, keeping fields only earlier events
carried. `summary`, `model`, `cost` and `tokens` are kept as attributes.

## Tests

```sh
cd bridges/topology && python -m unittest discover -s tests -v
```
