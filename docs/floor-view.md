# The Floor View, downtime and suggestions

The Floor View is the page operators and supervisors keep open. It shows every enabled machine as a tile, with its state, its counts for the last day and its latest OEE, followed by the open suggestions that need a person's decision. This page covers using it, the downtime workflow around it, and the Agent Suggestion records it lists.

## Opening it

The page is at `/app/floor-view`, and in the desk search as **Floor View**. Any user with read access to Machine can open it: FoaMES Engineer, FoaMES Operator, FoaMES Quality or System Manager. It refreshes itself every 30 seconds and has a **Refresh** button for right now.

## Tiles

One tile per enabled Machine, in code order. The colour is the machine's current state:

| Colour | State | How a machine gets there |
| --- | --- | --- |
| Green | Running | A State event of Running (or an alias such as `run`, `auto`, `producing`) |
| Yellow | Idle | A State event of Idle (`ready`, `waiting`, `starved`, `blocked`) |
| Red | Down | A State event of Down (`fault`, `stopped`), or any Alarm event |
| Blue | Setup | A State event of Setup (`changeover`) |
| Grey | Unknown | No event yet, a State event of Unknown, or no event for longer than **Mark Machine Unknown After** in Machine Data Settings |

Each tile also shows when the machine was last seen, how many minutes since its last count ("No counts today" when there is none in the window), the good and scrap counts over the last day, and "OEE n %" from the machine's most recent OEE Period when one exists. Clicking a tile opens the Machine record.

A grey tile is the one to look at first. Unknown time is loss in OEE, and a machine that was counting and then went quiet usually means a gateway, network or PLC problem rather than a stopped machine.

## Downtime

Downtime is opened and closed automatically from machine state. When a machine goes Down (by State event or Alarm), a **Downtime Record** with source Automatic opens at that timestamp; when the machine reaches any other state, the open record closes and its duration is computed. There is never more than one open record per machine.

What an operator adds is the **Reason**. Open the record (from the Downtime Record list, filtered on status Open, or from the Machine's connections) and pick a Downtime Reason. Until a reason is assigned the downtime counts as unplanned loss in OEE; once a reason flagged **Counts As Planned Downtime** is assigned, that time is excluded from the availability base instead. Notes are free text.

A Downtime Record can also be created by hand with source Manual, for a stoppage the machine did not report. Give it a start, an end and a reason. An end before the start is refused. A manual record documents the stoppage and counts in the downtime-by-reason figures, but it does not change the OEE time ledger, which is built from state events only: if the machine's last event was Running, those minutes are still run time in OEE. To have them counted as downtime, post a `Down` state event at the start and the real state at the end (a FoaMES Operator may post events unsigned), and then assign the reason on the record that opens.

The Floor View does not list downtime itself. The floor snapshot carries downtime per machine with the top reason over the window, and the suggestion rule below turns a dominant reason into a suggestion. For the full picture use the Downtime Record list with the standard filters and group-by.

## Suggestions

Below the tiles, the page lists every **Agent Suggestion** with status Open, each with a coloured border for its severity (red Critical, yellow Warning, grey Info), its category and who raised it. Clicking one opens the record.

A suggestion is a finding with evidence, for a person to act on. FoaMES never acts on a suggestion itself: it does not change machine states, close downtime, post to an ERP or touch anything in SCADA. The record has:

| Field | Meaning |
| --- | --- |
| Title, Suggestion | What was found and what to do about it |
| Category | Yield, Downtime, Quality, Release, Machine Data, ERP or Other |
| Severity | Info, Warning or Critical |
| Agent | `foames-rules` for the built-in rules, otherwise the name of the external agent that posted it |
| Reference | The record it is about, usually a Machine |
| Evidence | The numbers the suggestion rests on, as JSON, so the reader can check them |
| Rule Key | Identifies the finding. While a suggestion with this key is Open, the same finding is not raised again; if it was resolved and the finding recurs, the old record is reopened with the new evidence rather than duplicated |

### Working a suggestion

Set the **Status**:

- **Accepted**: someone will act on it. Write what will be done in **Resolution**.
- **Done**: the action is complete.
- **Dismissed**: not a real problem, or not worth acting on. Say why in Resolution so the next person does not reopen the question.

Moving a suggestion out of Open stamps **Resolved By** and **Resolved On**. Setting it back to Open clears them. FoaMES Engineer and FoaMES Operator can create and edit suggestions; FoaMES Quality can edit them.

### The built-in rules

The scheduler runs the rules every hour over the last day. The **Run suggestion rules** button on the Floor View runs them now and reports how many new suggestions were created; it needs create permission on Agent Suggestion, so it works for FoaMES Engineer, FoaMES Operator and System Manager, and a FoaMES Quality user gets a permission error from it. The rules are in `foames/foames_mes/suggestions.py` and are plain functions over the floor snapshot:

| Rule | Fires when | Category, severity |
| --- | --- | --- |
| Silent after counting | A machine counted in the window, has not counted for 30 minutes or more, and is now Unknown | Machine Data, Warning |
| Running without counting | A machine counted in the window, reports Running, and has not counted for 30 minutes or more | Downtime, Warning |
| Dominant downtime reason | One reason is half or more of a machine's downtime with a reason assigned over the window (downtime without a reason is not in the denominator) | Downtime, Info |
| Missing ERP references | Any External Reference has resolved as Missing | ERP, Warning (one suggestion listing them) |

Both count-based rules need at least one count in the window; a machine that has never counted, for example a new machine with a broken counter signal, is not caught by them and shows on the Floor View as "No counts today" instead. They use the machine's last-seen time in their rule key, so a machine that goes quiet again after a fix raises a fresh suggestion. The downtime rule keys on machine and reason (its window label is always the same), so there is at most one open suggestion per machine and reason; once that suggestion is accepted, dismissed or done, the next hourly run reopens it if the reason is still dominant over the last day. Record what was decided in Resolution so a reopened suggestion carries its history.

Other apps register further rules through the `foames_suggestion_rules` hook, and external agents post their own suggestions through the API. Both are described in [agents/floor-agent.md](agents/floor-agent.md).

## The floor snapshot

Everything the page shows comes from one call, `foames.foames_mes.api.get_floor_snapshot(days=1)`, which returns a single JSON document:

```json
{
  "as_of": "2026-10-30 14:02:11",
  "machines": [
    {"name": "press-1", "title": "Press 1", "status": "Running", "last_seen": "2026-10-30 14:01:58",
     "machine_type": "Press", "ideal_cycle_seconds": 2.0, "minutes_since_count": 0.4,
     "counts": {"good": 9000, "scrap": 300},
     "oee_today": {"oee": 69.0, "availability": 79.3, "performance": 89.9, "quality": 96.8}}
  ],
  "downtime_by_machine": [
    {"machine": "press-1", "period": "last 1 day(s)", "total_minutes": 65,
     "top_reason": "Planned maintenance", "top_minutes": 45}
  ],
  "external_references": [],
  "open_suggestions": [
    {"name": "SUG-2026-00007", "title": "Jam is 60% of downtime on press-2", "category": "Downtime",
     "severity": "Info", "agent": "foames-rules", "reference_doctype": "Machine", "reference_name": "press-2"}
  ]
}
```

`external_references` lists only references with status Missing, and only when the caller may read External Reference. Other apps add sections to the snapshot through the `foames_floor_snapshot_extensions` hook. The same call is what an external agent or an Ignition screen uses to read the floor, so the page and the agents always see the same numbers.

## Roles at a glance

| Task | Role |
| --- | --- |
| Watch the Floor View | FoaMES Operator, Engineer, Quality |
| Assign a downtime reason, add a manual Downtime Record | FoaMES Operator, Engineer, Quality |
| Create Downtime Reasons and Machines, change Machine Data Settings | FoaMES Engineer |
| Accept, dismiss or complete a suggestion | FoaMES Operator, Engineer, Quality |
| Post machine events by hand or from a test script | FoaMES Operator, Engineer |
| Create OEE Periods by hand | FoaMES Engineer |
