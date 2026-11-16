**Goal:** let people on the floor call for help at a machine, and measure how quickly help arrives.

**You need:** FoaMES Supervisor to edit call types; any of FoaMES Operator, Supervisor, Maintenance or Quality to raise and close calls.

## 1. Set the targets

Five **Andon Call Types** are created on install. Adjust them to your plant:

| Type | Acknowledge within (min) | Resolve within (min) | Severity |
| --- | --- | --- | --- |
| Maintenance | 5 | 60 | Warning |
| Material | 5 | 20 | Warning |
| Quality | 10 | 60 | Warning |
| Supervisor | 5 | 30 | Warning |
| Safety | 2 | 30 | Critical |

Set a target to 0 to switch that check off, or tick **Disabled** to retire a type.

## 2. Raise and answer calls

- On the **Floor View**, press **Call for Help**, pick the machine and type, and add a note. The call shows on the machine's tile and blinks until acknowledged.
- The responder sets it **Acknowledged**, then **Resolved** with what was done, or **Cancelled**.
- From a PLC button, a SCADA screen or an agent, call `raise_andon`, `acknowledge_andon` and `resolve_andon` (see [HTTP API](Reference-HTTP-API)) with an Operator's API key.

A call never stops or changes a machine.

## 3. Review response

Every five minutes, a call that misses a target becomes an Agent Suggestion (category Andon), once per call and target. The **Andon Response** report shows median and 90th-percentile response and resolution times, and missed targets, by call type, machine or line.

Details: [docs/andon.md](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/andon.md).
