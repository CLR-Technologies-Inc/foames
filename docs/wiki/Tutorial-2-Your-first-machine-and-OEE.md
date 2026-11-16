In this tutorial you will create a machine, send it two hours of events by hand, watch it on the Floor View, give a stoppage a reason, and work out its OEE. Along the way you will see the three things that make FoaMES numbers trustworthy: counters become deltas, downtime opens and closes from the machine's own signal, and planned stops leave the availability base only when someone says they were planned.

**You need:** the site from [Tutorial 1](Tutorial-1-Install-FoaMES), running, and `curl`.

## 1. Create an API key for yourself

The tutorial posts events with your own user's API key, so no webhook signature is needed.

1. Open your **User** record, go to **Settings**, then **API Access**, and press **Generate Keys**.
2. Copy the secret now; it is shown once. In a terminal:

```bash
export SITE=http://foames.localhost:8000
export AUTH="Authorization: token <api key>:<api secret>"
```

## 2. Create two downtime reasons

Open **Downtime Reason** and create:

| Reason | Category | Counts As Planned Downtime |
| --- | --- | --- |
| Jam | Unplanned | off |
| Planned changeover | Changeover | **on** |

## 3. Create a machine

Open **Machine**, choose **New**, and fill in:

| Field | Value |
| --- | --- |
| Code | `press-1` |
| Title | Press 1 |
| Ideal Cycle Time (s) | `1.5` |

Leave everything else as it is and save. **Source ID** fills itself with the code; that is the name the events will use.

## 4. Send two hours of events

This is a morning on Press 1, from 06:00 to 08:00 on 5 January 2026. The machine runs, stops for 15 minutes at 07:00, runs again, and goes idle at 08:00. Its counters report **running totals**, as real machines do.

```bash
curl -X POST "$SITE/api/method/foames.foames_mes.api.ingest_machine_events" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"events": [
    {"machine": "press-1", "type": "State", "state": "Running", "timestamp": "2026-01-05 06:00:00"},
    {"machine": "press-1", "type": "Count", "counter": "good",  "value": 10000, "timestamp": "2026-01-05 06:00:00"},
    {"machine": "press-1", "type": "Count", "counter": "scrap", "value": 200,   "timestamp": "2026-01-05 06:00:00"},
    {"machine": "press-1", "type": "Count", "counter": "good",  "value": 12000, "timestamp": "2026-01-05 07:00:00"},
    {"machine": "press-1", "type": "Count", "counter": "scrap", "value": 250,   "timestamp": "2026-01-05 07:00:00"},
    {"machine": "press-1", "type": "State", "state": "Down",    "timestamp": "2026-01-05 07:00:00"},
    {"machine": "press-1", "type": "State", "state": "Running", "timestamp": "2026-01-05 07:15:00"},
    {"machine": "press-1", "type": "Count", "counter": "good",  "value": 13500, "timestamp": "2026-01-05 07:59:00"},
    {"machine": "press-1", "type": "State", "state": "Idle",    "timestamp": "2026-01-05 08:00:00"}
  ]}'
```

The response lists the Machine Events it accepted. Open the **Machine Event** list and look at the Count events: the first reading of each counter has a delta of 0, because it only sets the baseline. After that, good rose by 2,000 and then 1,500, and scrap by 50. FoaMES never takes the raw total of 10,000 as production.

## 5. Look at the Floor View

Open **Floor View**. Press 1 has a tile. Its colour is the last state it reported; because the events are from January, the staleness check will soon mark it grey (Unknown), which is what FoaMES does with any machine that has gone quiet. That is expected here.

## 6. Find the stoppage

Open the **Downtime Record** list. There is one record for press-1, source **Automatic**, from 07:00 to 07:15, 15 minutes, with no reason. FoaMES opened it when the machine went Down and closed it when it reported Running again. Nobody typed it in.

## 7. Work out the OEE

Ask FoaMES for OEE over the two hours, without saving anything:

```bash
curl -G "$SITE/api/method/foames.foames_mes.doctype.oee_period.oee_period.get_oee" -H "$AUTH" \
  --data-urlencode "machine=press-1" \
  --data-urlencode "from_time=2026-01-05 06:00:00" \
  --data-urlencode "to_time=2026-01-05 08:00:00"
```

Check the answer by hand:

| Factor | Working | Result |
| --- | --- | --- |
| Run minutes | 06:00 to 07:00 plus 07:15 to 08:00 | 105 |
| Availability | 105 / 120 planned minutes | 87.5 % |
| Performance | (1.5 s × 3,550 units / 60) / 105 run minutes | 84.5 % |
| Quality | 3,500 good / 3,550 total | 98.6 % |
| OEE | 0.875 × 0.845 × 0.986 | **72.9 %** |

## 8. Tell FoaMES the stop was planned

Suppose the 15 minutes were a planned changeover. Open the Downtime Record, set **Reason** to **Planned changeover**, and save. Run the `get_oee` call again.

Availability is now 105 / (120 − 15) = **100 %**, and OEE rises to about **83.3 %**. The planned stop has left the availability base. It did so only because a person gave it a planned reason: an unexplained stop is always counted as loss.

## 9. Save it as an OEE Period (optional)

Open **OEE Period**, choose **New**, pick press-1, set From Time to 2026-01-05 06:00:00, To Time to 2026-01-05 08:00:00 and Planned Minutes to 120, and save. The period fills in its time ledger, counts, factors and **Signal Coverage**. On a real site the scheduler creates one of these per machine per day, or per shift, by itself.

## What you learned

- Machines send running totals; FoaMES turns them into deltas and never invents production from a first reading, a reset or a late reading.
- Downtime is opened and closed by the machine's own signal. People add the reason.
- OEE is computed from a minute-by-minute ledger. Only reasons marked as planned leave the base.

Next: let an AI agent read this floor in [Tutorial 3: Your first agent over MCP](Tutorial-3-Your-first-agent-over-MCP). To understand the ledger in depth, read [How OEE is counted](Explanation-How-OEE-is-counted).
