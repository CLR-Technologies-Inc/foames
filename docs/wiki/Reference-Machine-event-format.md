Every path into FoaMES (webhook, MQTT, Sparkplug B, OPC UA, the historian and Bluesky bridges) produces events of this shape.

```json
{"machine": "press-1", "type": "Count", "counter": "good", "value": 1234, "timestamp": "2026-10-30T02:00:00Z", "id": "press-1-000981"}
```

## Common fields

| Field | Required | Meaning |
| --- | --- | --- |
| `machine` | yes | The Machine's **Source ID** |
| `type` | yes | `State`, `Count`, `Measurement`, `Alarm` or `Message` |
| `timestamp` (or `ts`) | no | ISO 8601 or Unix seconds. A naive ISO time is read in the site's time zone; `Z` or an offset is converted. Missing means now |
| `id` | no | The source's own event id. A repeated id is rejected as a duplicate, so retries are safe |

## Types

| `type` | Fields | Effect |
| --- | --- | --- |
| `State` | `state` | Sets the machine state. Down opens a Downtime Record; the next other state closes it |
| `Count` | `counter`, `value` (the running total) | The delta from the previous reading is stored and feeds OEE. A first reading, a reset or an out-of-order reading counts zero |
| `Measurement` | `name`, `value` | Stored for SPC and analysis |
| `Alarm` | `code` or `value`, `text` | Stored, and marks the machine Down |
| `Message` | `text` | Stored; refreshes the machine's last-seen time |

## States and aliases

| State | Accepted aliases (examples) | Floor View colour |
| --- | --- | --- |
| Running | run, auto, producing | Green |
| Idle | ready, waiting, starved, blocked | Yellow |
| Down | fault, stopped (and any Alarm) | Red |
| Setup | changeover | Blue |
| Unknown | (sent by Sparkplug on node or device death, or by the staleness check) | Grey |

## Counter names

| Names | Counted as |
| --- | --- |
| `good`, `count`, `total`, `parts` | Good |
| `scrap`, `reject`, `bad`, `ng` | Scrap |
| `energy`, `kwh`, `power`, `electricity`, `water`, `gas`, `feed`, `steam`, `air`, `fuel` (also with a unit suffix such as `energy_kwh`) | Consumed input: feeds specific consumption and the consumption-with-no-output rule, never OEE |
| anything else | Stored, not in OEE |

Good and scrap are added to make the total, so send counters that do not overlap. FoaMES does not subtract counters for you. Set the Machine's **Counter Rollover** for a counter that wraps.

## Webhook signing

| Item | Value |
| --- | --- |
| URL | `POST /api/method/foames.foames_mes.api.ingest_machine_events` |
| Body | `{"events": [ ... ]}` or one event |
| `X-FoaMES-Timestamp` | Unix seconds |
| `X-FoaMES-Signature` | Hex HMAC-SHA256 of `<timestamp>.<body>` with **Webhook Secret** from Machine Data Settings |
| Tolerance | **Signature Tolerance (s)**, 300 by default |

A logged-in user with FoaMES Operator, Engineer or System Manager may post unsigned. The response lists the accepted Machine Event names and the reason for each rejection.

## MQTT topics

`<topic prefix>/<machine source id>/<event type>`, with the prefix from Machine Data Settings (default `foames`). Sparkplug B uses `spBv1.0/<group>/#`; see [Connect Ignition](How-to-Connect-Ignition) for its naming convention.
