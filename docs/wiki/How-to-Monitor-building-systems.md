**Goal:** watch the plant's building systems (water, wastewater, electricity, chilled water, HVAC, RTUs, chillers, lighting, server rooms, hazmat storage) from FoaMES, get alarms and suggestions when they leave their limits or go silent, and see utility use per production line.

**You need:** FoaMES Engineer (or Maintenance) on the site, the webhook secret from **Machine Data Settings**, and network access from a small host to the building controllers and meters. The full reference is [docs/building-management.md](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/building-management.md).

## 1. Describe the facility

Open the **FoaMES Building** workspace.

1. In **Facility Zone**, build the tree: the site, its buildings, floors, rooms and areas. Tick **Is Group** on zones that hold others. On a zone that a production line uses, fill **Production Line** with the Line its machines carry.
2. In **Facility Asset**, add one record per piece of equipment or utility system: `CH-01` (Chiller), `RTU-3` (Rooftop Unit), `MAIN-ELEC` (Electricity), `SRV-ROOM` (Server Room), `FLAM-CAB-2` (Hazardous Material Storage). Set **Located In**, and **Serves** when it conditions or supplies another zone. Brick class and Haystack tags fill themselves; change them if you keep your own model.
3. For hazmat storage, link the **Hazard Assessment** that covers what is stored and list the stored materials.

## 2. Add the points

In **Building Point**, one record per value, with the **Point ID** the readings will carry (for example `CH-01.CHWS-TEMP`):

| Point | Point Type | Quantity / Utility | Limits |
| --- | --- | --- | --- |
| Chilled water supply temperature | Sensor | Temperature, degC | High 9 (Medium), High High 12 (Critical), Deadband 0.5 |
| Chiller run status | Status | Run Status | none (it feeds run hours) |
| Server room temperature | Sensor | Temperature, degC | High 27 (High, on-delay 300 s) |
| Hazmat cabinet leak detector | Alarm, Binary | Leak | Alarm State 1 (Critical) |
| Main electricity meter | Meter, Totalizer | Electricity, kWh | none |

Set **Stale After** where 60 minutes of silence is too long (a server room might be 10).

## 3. Send the readings

On a host that can reach the controllers, install the gateway from `bridges/bms` and describe each device and point in a JSON file (examples in `bridges/bms/examples/bms.json`):

```bash
cd bridges/bms && pip install .
export FOAMES_WEBHOOK_SECRET=...
python -m foames_bms_gateway check --config bms.json
python -m foames_bms_gateway read  --config bms.json
python -m foames_bms_gateway poll  --config bms.json --site https://foames.example.com --interval 60
```

BACnet/IP points name the object type and instance; Modbus TCP points name the register reference (for example `40001`) and data type. The gateway only reads. Run it under supervisor or systemd as you would the other gateways ([Run the gateways in production](How-to-Run-the-gateways-in-production)). Any other client can post the same JSON to `foames.foames_bms.api.ingest_point_readings`, signed like machine events.

## 4. Check the result

- Each point shows **Last Value**, **Last Reading At** and **Condition**; each asset shows **Status** Normal.
- Push a value past a limit (or post one by hand as an Engineer): a **Building Alarm** opens, the asset turns to Alarm and an Agent Suggestion from `foames-bms` appears under **Facility Suggestions**.
- **Acknowledge** the alarm; when the value returns inside its limit by the deadband, the alarm closes and its suggestions are Done.
- Open **Utility Consumption** for the month: each meter's use per day, and per good unit where the zone names a line.

## 5. Plan maintenance on building equipment

Create a **Maintenance Plan** with **Facility Asset** instead of Machine: Calendar for a quarterly filter change, **Run Hours** from the asset's run-status point for a chiller's tube cleaning, or **Count** from one of its totalizing meters. The rest works as in [Plan preventive maintenance](How-to-Plan-preventive-maintenance).
