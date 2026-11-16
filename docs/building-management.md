# Building management

FoaMES watches the building systems that support production without being on its process route: water and wastewater, electricity and gas, chilled and heating hot water, steam, compressed air, HVAC with its air handlers, rooftop units, chillers, cooling towers and boilers, lighting, server rooms, hazardous material storage and similar. In industry terms this is the building management system (BMS) or building automation system (BAS) side of a plant. The controllers keep running those systems. FoaMES reads them, raises alarms and suggestions when they leave their limits or stop reporting, charges their consumption to the areas and production lines they serve, and plans their preventive maintenance. It never writes to them.

Everything here lives in the **FoaMES BMS** module (`foames/foames_bms`), with the pure rules in `bms.py`. Readings come from the read-only BACnet/IP and Modbus TCP gateway in [`bridges/bms`](../bridges/bms/README.md), or from any client that can post signed JSON.

## The register

| Record | What it is |
| --- | --- |
| **Facility Zone** | A site, building, floor, room, area, utility yard or outdoor area, as a tree. A zone can name the **Production Line** it serves (the Line on its Machines), so utility use there is also shown per good unit made. |
| **Facility Asset** | One piece of equipment or one utility system: a chiller, RTU, air handler, boiler, a main electrical meter, a lighting panel, a server room, a hazmat store. It sits in one zone (**Located In**) and can serve another (**Serves**: a rooftop unit on the roof conditioning a production hall). Its **Status** (Unknown, Normal, Alarm, Stale, Out of Service) and **Active Alarms** follow its points. |
| **Building Point** | One value a controller or meter reports: a Sensor, Setpoint, Status, Command, Alarm or Meter point, the BACnet object, Modbus register or historian tag behind it. Its **Point ID** is the id readings carry. It holds the alarm limits and the present value. |
| **Building Point Reading** | One stored reading: timestamp, value and quality (Good, Uncertain, Bad). Readings are unique per point and sample, so a replayed reading is stored once. |
| **Building Alarm** | A point past one of its limits, or no longer reporting, from raise to acknowledgement and return to normal. |

Assets and points carry a **Brick class** and **Project Haystack tags**, filled from the system, point type, quantity and utility when left empty (a chiller is `Chiller` and `equip chiller`; a temperature sensor is `Temperature_Sensor` and `point sensor temp`). They are free text, so a site that already keeps a Brick or Haystack model can use its own. Only the published vocabulary is used: Brick is BSD-3-Clause, Haystack AFL-3.0, and ASHRAE 223P builds on the same terms.

**Out of Service** on an asset keeps recording its readings and alarms but stops them from raising suggestions, and dismisses the open ones, for the duration of a shutdown or a contractor's works.

## Readings in

POST JSON to `/api/method/foames.foames_bms.api.ingest_point_readings`, signed exactly like the machine-event webhook: the hex HMAC-SHA256 of `<timestamp>.<body>` with the webhook secret from **Machine Data Settings**, in `X-FoaMES-Signature`, and the Unix timestamp in `X-FoaMES-Timestamp` (see [machine-data.md](machine-data.md) and `foames/foames_mes/signing.py`). A logged-in user with FoaMES Operator, Engineer or System Manager can post unsigned.

```json
{"readings": [
  {"point": "AHU-1.SAT", "value": 13.2, "timestamp": "2026-11-16T08:00:00Z", "quality": "Good", "id": "AHU-1.SAT@2026-11-16T08:00:00Z"},
  {"point": "AHU-1.FAN-STATUS", "value": "active", "timestamp": 1763280000}
]}
```

`value` is a number, a boolean or a binary word (`on`/`off`, `active`/`inactive`, `open`/`closed`, `alarm`/`normal`, `running`/`stopped`). `timestamp` is ISO 8601 or Unix seconds; a naive ISO time is taken as site time, and a missing one as now. `quality` defaults to Good. `id` is optional; without it the key is derived from the point and the timestamp. The answer lists what was accepted and why the rest was rejected (an unknown or disabled point, a value that is not a number, a duplicate).

A reading older than the point's present value is stored for history and consumption but does not move the alarm state. A **Bad** reading is stored and marks the point's quality, and is never compared with the limits.

### The BMS gateway

`bridges/bms` is a standalone package, standard library only, that runs beside the building network:

```bash
cd bridges/bms && pip install .
export FOAMES_WEBHOOK_SECRET=...
python -m foames_bms_gateway check --config bms.json     # what it would read
python -m foames_bms_gateway read  --config bms.json     # read once, print JSON Lines
python -m foames_bms_gateway poll  --config bms.json --site https://foames.example.com --interval 60
```

The configuration lists devices and the points on them; `point` is the Building Point id:

```json
{
  "devices": {
    "ahu-controller": {"protocol": "bacnet", "host": "10.0.5.20"},
    "chiller-plant": {"protocol": "bacnet", "host": "10.0.5.30", "dnet": 2001, "dadr": "0a"},
    "main-meter": {"protocol": "modbus", "host": "10.0.6.10", "unit": 1}
  },
  "points": [
    {"point": "AHU-1.SAT", "device": "ahu-controller", "object": "analog-input", "instance": 3, "status_flags": true},
    {"point": "MAIN.KWH", "device": "main-meter", "reference": 40001, "data_type": "float32"},
    {"point": "MAIN.KW", "device": "main-meter", "table": "holding", "address": 2, "data_type": "float32", "scale": 0.001}
  ]
}
```

- **BACnet/IP** uses the ReadProperty service only (ASHRAE 135, Annex J for BACnet/IP). A point names its object type (`analog-input`, `binary-value`, `multi-state-input` and so on, or the number), instance, and optionally `property` (default `present-value`) and array `index`. With `status_flags`, the gateway also reads the object's status flags and sends a fault as Bad quality and overridden or out of service as Uncertain. A device behind a BACnet router on another network takes `dnet` and `dadr` (its MAC address in hex).
- **Modbus TCP** uses function codes 1 to 4 only. A point names a conventional `reference` (00001, 10001, 30001 or 40001 style, five or six digits) or a `table` (coil, discrete, input, holding) and a zero-based `address`, then `data_type` (uint16, int16, uint32, int32, float32, float64), `word_order` (big, the Modbus convention, or little), `byte_swap`, `scale` and `offset`.

The gateway never writes. It has no WriteProperty, no priority-array command or relinquish, and no Modbus write function code; a test checks the package for them. A point it cannot read is logged and skipped, so FoaMES raises a communication-loss alarm for it once it has been silent for the point's stale time. Both clients are written from the public protocol standards; no vendor code or SDK is used.

Values a SCADA platform or historian already collects can be posted to the same webhook by any client: give the Building Point that source's tag as its id.

## Alarms

Each point has a table of **limits**: High High, High, Low, Low Low and Alarm State, each with a **Priority** (Critical, High, Medium, Low) and an **On Delay** in seconds. This is the usual analog alarm practice, in the spirit of ISA-18.2 / IEC 62682 alarm management:

- The most severe limit a value is past applies: past High High is High High, not High.
- A value at a limit is not past it. Once a condition is active, it clears only when the value comes back inside the limit by the point's **Deadband**, so a value hovering at the limit does not chatter.
- With an on-delay, the condition must still hold on a reading at least that much later before the alarm is raised. A reading back inside the limit resets the delay.
- Alarm State alarms when a binary or multistate point reads the given state (1 for an active binary point). A binary Alarm point with no limits gets Alarm State 1 at Medium.
- A point that has not reported for its **Stale After** minutes (60 by default) gets a communication-loss alarm (condition Stale) at its **Stale Priority**. A point that never reported is Unknown, not stale. The check runs every five minutes.

A point has at most one open alarm. A new condition raises one (Active). A more severe condition, or losing or regaining communication, moves it, makes it Active again and asks people again; a less severe one moves it and keeps the acknowledgement. Back inside every limit, an **Acknowledged** alarm closes; an alarm nobody acknowledged yet becomes **Returned** and closes when someone does. People acknowledge with the **Acknowledge** button on the alarm (or `foames.foames_bms.doctype.building_alarm.building_alarm.acknowledge`). The alarm keeps the value at raise, the limit, the worst value while active and the last value.

### Suggestions

Agents suggest; people act. Each raised or escalated alarm becomes an Agent Suggestion from agent `foames-bms`, category **Facility**, severity from the priority (Critical and High are Critical, Medium is Warning, Low is Info). Acknowledging the alarm marks its suggestions Accepted, and closing it marks them Done. The hourly check adds:

| Finding | Severity |
| --- | --- |
| A Critical or High alarm still Active and unacknowledged after 30 minutes | Critical |
| Hazardous material storage with no active Hazard Assessment linked | Warning (Safety) |
| Hazardous material storage with no enabled Building Point watching it | Info (Safety) |

### Hazardous material storage

An asset whose system is **Hazardous Material Storage** links the [Hazard Assessment](ehs.md) that covers what is stored there and lists the stored materials and their hazard classes. Its alarms (a leak or gas detector, failed ventilation, a temperature out of range) are **Safety** suggestions, Critical at Critical or High priority, and point people at the hazard assessment before anyone goes in.

## Utility consumption

A **Meter** point names its **Utility** (Electricity, Natural Gas, Water, Wastewater, Chilled Water, Heating Hot Water, Steam, Compressed Air) and its **Meter Mode**:

- **Totalizer**: a running total (kWh, m³). Consumption is the sum of the increases between readings, by the same rules as machine counters: a drop counts nothing unless the meter's **Rollover Value** is known, in which case it is counted as a wrap. Nothing is invented.
- **Rate**: an instantaneous rate (kW, m³/h, L/min) with its time base (**Rate Per** hour, minute or second), integrated with the trapezoid rule. Readings further apart than the point's **Max Gap** (60 minutes by default) count nothing between them.

The **Utility Consumption** report (and `foames.foames_bms.api.get_utility_consumption`) shows consumption per day, week or month and meter, charged to the zone the meter's asset serves (or sits in), filtered by utility, zone (with every zone inside it) or asset. Where that zone names a production line, the report adds the good units made on that line in the same period (the good-counter deltas of its machines) and the consumption per good unit, the energy performance indicator of ISO 50001. Bad-quality readings are left out.

A machine's own metered inputs (energy, water, air counters on its Machine Events) stay on the machine; Building Points are for what the building supplies.

## Preventive maintenance

A Maintenance Plan can be for a **Facility Asset** instead of a machine (exactly one of the two). Its meter is read from the asset's points, by the same rules as a machine's:

- **Calendar**: days since the last service.
- **Run Hours**: hours the asset's run-status point (a Status point with quantity Run Status) read on. Each reading holds until the next, for at most the point's Max Gap, so an asset that stops reporting stops wearing on paper.
- **Count**: the increase of one of its totalizing meters since the last service (the plan's **Counter** names the meter point; empty takes the asset's first totalizer).

Work orders, the hourly check and its suggestions work as in [maintenance.md](maintenance.md). A facility work order records no machine downtime, and the ERPNext adapter does not post an Asset Repair for it.

## Where it shows

- **FoaMES Building** workspace (Maintenance, Supervisor, Engineer, Safety): active alarms, assets in alarm or stale, the asset list, the zone tree, Utility Consumption and the open facility suggestions.
- **Floor snapshot**: a `facility` section with, per system, the assets in alarm, stale or out of service and the open alarms by priority, plus the 50 latest open alarms. The Floor View, the rules and agents see facility problems next to the machines they may affect.
- **Topology graph**: zones and assets as Physical-layer assets (zones as Site or Area, assets as Equipment in their zone) and points as Data-layer signals bound to their asset with the present value, reported by the `foames-bms` collector on the topology sync. See [topology.md](topology.md).
- **MCP tools** for agents, all read-only: `foames_bms_list_assets`, `foames_bms_get_asset`, `foames_bms_list_alarms`, `foames_bms_point_history`, `foames_bms_utility_consumption` and `foames_bms_summary`. Acknowledging an alarm is for people.

## API

| Method | Verb | Permission | Purpose |
| --- | --- | --- | --- |
| `foames.foames_bms.api.ingest_point_readings` | POST | HMAC signature, or Operator, Engineer or System Manager | Record readings |
| `foames.foames_bms.api.list_facility_assets` | GET | read on Facility Asset | Assets by `system`, `zone`, `status` |
| `foames.foames_bms.api.get_facility_asset` | GET | read on Facility Asset | One asset with its points and open alarms |
| `foames.foames_bms.api.list_building_alarms` | GET | read on Building Alarm | Open alarms, or by `status`, `priority`, `system`, `zone`, `facility_asset` |
| `foames.foames_bms.api.get_point_history` | GET | read on Building Point and Building Point Reading | One point's readings in `since`..`until` (default the last 24 hours) |
| `foames.foames_bms.api.get_utility_consumption` | GET | read on Building Point Reading | The Utility Consumption rows |
| `foames.foames_bms.api.get_facility_summary` | GET | read on Facility Asset | Per system counts and open alarms by priority |
| `foames.foames_bms.doctype.building_alarm.building_alarm.acknowledge` | POST | write on Building Alarm | Acknowledge an alarm (`alarm`, `note`) |

## Scheduled jobs

| When | Job | What it does |
| --- | --- | --- |
| Every 5 minutes | `foames.foames_bms.tasks.check_stale_points` | Raises a communication-loss alarm for each point silent past its stale time |
| Hourly | `foames.foames_bms.tasks.check_bms` | Unacknowledged Critical and High alarms, hazmat storage without an assessment or points |

## Roles

Engineers keep the register. Maintenance and Supervisors create and edit assets and points; Safety, Operators, Quality and Integration read them. Maintenance, Supervisor, Safety and Operator users can acknowledge alarms. Readings are created by the webhook, Engineers and Integration users.

## Read-only by design

FoaMES does not write to a building controller: no setpoint, no command, no override, no schedule change. The gateway can only send read requests. If a site ever needs FoaMES to write a building point, that write would be a registered `foames_write_actions` entry requested through the read-only write gate (`foames_kernel/write_gate.py`), held for an authorised person's sign-off like every other write to another system. See [read-only-mode.md](read-only-mode.md).
