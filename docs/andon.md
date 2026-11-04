# Andon calls

An andon call is someone on the floor asking for help at a machine: a technician for a breakdown, material for a starved station, quality for a suspect part, a supervisor for a decision, or help with a safety problem. FoaMES records each call, shows it on the Floor View until it is closed, measures how quickly it was answered, and raises an Agent Suggestion when a call misses its target.

A call never stops, starts or changes a machine. If the machine is stopped while people wait, that shows up as downtime from the machine's own signal or from a Downtime Record, as usual (see [floor-view.md](floor-view.md)).

## Call types

**Andon Call Type** holds the kinds of help a plant can call for and the targets for each:

| Field | Meaning |
| --- | --- |
| **Code** / **Title** | The name operators pick, such as `Maintenance` |
| **Acknowledge Within (min)** | A call still Open after this long is escalated. 0 turns the check off |
| **Resolve Within (min)** | A call not Resolved or Cancelled after this long is escalated. 0 turns the check off |
| **Escalation Severity** | Severity of the Agent Suggestion raised for this type: Warning, or Critical |
| **Disabled** | No new calls of this type can be raised |

Five types are created on install, and can be edited or disabled:

| Code | Acknowledge within | Resolve within | Severity |
| --- | --- | --- | --- |
| Maintenance | 5 | 60 | Warning |
| Material | 5 | 20 | Warning |
| Quality | 10 | 60 | Warning |
| Supervisor | 5 | 30 | Warning |
| Safety | 2 | 30 | Critical |

## The life of a call

| Status | Set when | Stamped |
| --- | --- | --- |
| Open | the call is raised | Raised At, Raised By |
| Acknowledged | someone is on the way | Acknowledged At, Acknowledged By, Response (min) |
| Resolved | the problem is dealt with; Resolution says what was done | Resolved At, Resolved By, Resolution (min) |
| Cancelled | help is no longer needed | Resolved At, Resolved By, Resolution (min) |

A call can go Open to Acknowledged to Resolved, straight from Open to Resolved, or to Cancelled from either open status. Resolved and Cancelled are final, and an acknowledged call cannot go back to Open. A call resolved without being acknowledged first has its response time measured to the resolution. The times are stamped whether the status is changed on the form, from the Floor View or through the API.

Operators, supervisors, maintenance and quality can raise, acknowledge and close calls. FoaMES Engineers and System Managers can also delete them; supervisors can edit the call types.

## Escalation

Every five minutes the scheduler checks the open calls against their call type's targets. A call that has missed a target becomes an Agent Suggestion in category **Andon**, with the call in the evidence and the call as its reference:

- **unanswered**: still Open after Acknowledge Within;
- **open too long**: not Resolved or Cancelled after Resolve Within.

Each target is escalated once per call. The call remembers it (Acknowledge Target Escalated, Resolve Target Escalated), so dismissing the suggestion does not bring it back. When the call is acknowledged, its open "unanswered" suggestion is marked Done, and when it is resolved or cancelled, both are. The rule itself is pure logic in `foames/foames_mes/andon.py`.

## On the Floor View

Users who can create Andon Calls get a **Call for Help** button on the Floor View. It asks for the machine, the call type and an optional note. Each open call shows on its machine's tile with its type, status and minutes open, and an Open call blinks until it is acknowledged. Clicking the tile opens the machine; the calls are listed under the Andon Call list, filtered on the machine.

The floor snapshot carries the calls too: each machine has `andon` (its open and acknowledged calls) and the snapshot has `andon_calls` (all of them, oldest first). Each call has `name`, `machine`, `call_type`, `status`, `note`, `raised_at`, `raised_by`, `acknowledged_at`, `minutes_open`, the call type's targets and the escalation flags.

## From a PLC, a SCADA screen or an agent

| Method | Verb | Arguments | Returns |
| --- | --- | --- | --- |
| `foames.foames_mes.doctype.andon_call.andon_call.raise_andon` | POST | `machine`, `call_type`, optional `note` | `name`, `status` |
| `foames.foames_mes.doctype.andon_call.andon_call.acknowledge_andon` | POST | `name` | `name`, `status`, `response_minutes` |
| `foames.foames_mes.doctype.andon_call.andon_call.resolve_andon` | POST | `name`, optional `resolution`, `cancel` (1 to cancel) | `name`, `status`, `resolution_minutes` |
| `foames.foames_mes.doctype.andon_call.andon_call.list_open_andon_calls` | GET | optional `machine` | the open calls, oldest first |

They use Frappe's usual authentication (an API key of a user with the FoaMES Operator role is enough), not the machine-data webhook. An andon button wired to a PLC or a SCADA screen calls `raise_andon` through a gateway script; see [ignition.md](vendors/ignition/README.md) for the Ignition gateway-script pattern.

## The Andon Response report

**Andon Response** (FoaMES MES) lists the calls raised in a date range, grouped by call type, machine or line, filtered by machine, line and call type. Per group: calls, still open, resolved, cancelled, median and 90th-percentile response and resolution minutes, and how many calls missed the acknowledge and resolve targets. The chart shows the median response per group. It is linked from the Supervisor and Maintenance workspaces; the call list is on the Operator, Supervisor and Maintenance workspaces.

Andon is a long-standing lean practice. Floorgraph ([prior art](../README.md#prior-art-and-credits)) also has an andon board; FoaMES's implementation is independent.
