**Goal:** fill a development site with a realistic shift of machine data, so an agent connected over MCP has something to analyse: states, stoppages, counts and measurements.

**You need:** a dev site ([Tutorial 1](Tutorial-1-Install-FoaMES)), an API key of a user with **FoaMES Engineer** (to create machines), and Python 3. Never run this against a production site.

## 1. Save the seeding script

Save as `seed_foames.py`. It creates three machines and two downtime reasons, then posts eight hours of events for yesterday through the public API.

```python
"""Seed a FoaMES dev site with one shift of invented machine data."""
import datetime as dt, json, os, random, urllib.request

SITE = os.environ.get("FOAMES_URL", "http://foames.localhost:8000")
AUTH = {"Authorization": f"token {os.environ['FOAMES_API_KEY']}:{os.environ['FOAMES_API_SECRET']}",
        "Content-Type": "application/json"}

def api(path, payload=None, method="POST"):
    req = urllib.request.Request(SITE + path, data=json.dumps(payload).encode() if payload else None,
                                 headers=AUTH, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 409:  # already exists
            return None
        raise

for code, planned in (("Jam", 0), ("Planned changeover", 1)):
    api("/api/resource/Downtime Reason", {"code": code, "title": code, "counts_as_planned": planned})

machines = {"press-1": 1.5, "press-2": 2.0, "oven-1": 6.0}
for code, cycle in machines.items():
    api("/api/resource/Machine", {"code": code, "title": code.title(), "line": "Line 1",
                                   "ideal_cycle_seconds": cycle})

random.seed(7)
start = dt.datetime.combine(dt.date.today() - dt.timedelta(days=1), dt.time(6, 0))
for code, cycle in machines.items():
    t, good, scrap, events = start, 10_000, 100, []
    ts = lambda x: x.strftime("%Y-%m-%d %H:%M:%S")
    events += [{"machine": code, "type": "State", "state": "Running", "timestamp": ts(t)},
               {"machine": code, "type": "Count", "counter": "good", "value": good, "timestamp": ts(t)},
               {"machine": code, "type": "Count", "counter": "scrap", "value": scrap, "timestamp": ts(t)}]
    while t < start + dt.timedelta(hours=8):
        t += dt.timedelta(minutes=10)
        if random.random() < 0.08:  # a stoppage
            events.append({"machine": code, "type": "State", "state": "Down", "timestamp": ts(t)})
            t += dt.timedelta(minutes=random.choice((5, 15, 30)))
            events.append({"machine": code, "type": "State", "state": "Running", "timestamp": ts(t)})
            continue
        good += int(600 / cycle * random.uniform(0.75, 0.95))
        scrap += random.randint(0, 6)
        events += [{"machine": code, "type": "Count", "counter": "good", "value": good, "timestamp": ts(t)},
                   {"machine": code, "type": "Count", "counter": "scrap", "value": scrap, "timestamp": ts(t)},
                   {"machine": code, "type": "Measurement", "name": "temperature",
                    "value": round(random.gauss(72, 0.8), 2), "timestamp": ts(t)}]
    events.append({"machine": code, "type": "State", "state": "Idle", "timestamp": ts(t)})
    api("/api/method/foames.foames_mes.api.ingest_machine_events", {"events": events})
    print(code, "posted", len(events), "events")
print("Done. Open /app/floor-view, or ask your agent about yesterday's shift.")
```

## 2. Run it

```bash
export FOAMES_URL=http://foames.localhost:8000
export FOAMES_API_KEY=<engineer api key>
export FOAMES_API_SECRET=<engineer api secret>
python3 seed_foames.py
```

## 3. Check

- The **Downtime Record** list has automatic stoppages with no reason yet.
- `get_oee` or the agent's `foames_get_oee` gives each machine an OEE for yesterday 06:00 to 14:00.
- **Run suggestion rules** on the Floor View may raise findings on the seeded data.

## Agent test prompts that use this data

- "Which machine lost the most time yesterday between 06:00 and 14:00, and why?"
- "Compare the OEE of the three machines for that shift and explain the biggest gap."
- "Post a suggestion for the unclassified downtime, with the minutes as evidence."

Then check the agent's numbers against the desk, and decide on its suggestions yourself. Adjust the script freely: it is invented data and uses only the public API.
