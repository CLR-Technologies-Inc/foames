# Machine data: how events reach FoaMES

FoaMES takes machine events four ways. All four end in the same place: a Machine Event record that is processed into machine state, downtime and counter deltas.

| Path | How | Needs |
| --- | --- | --- |
| Signed webhook | `POST /api/method/foames.foames_mes.api.ingest_machine_events` with `{"events": [...]}`; headers `X-FoaMES-Timestamp` (Unix seconds) and `X-FoaMES-Signature` (hex HMAC-SHA256 of `<timestamp>.<body>` with the secret in Machine Data Settings) | Nothing installed; any PLC gateway or IoT bridge that can POST JSON |
| MQTT | `bench --site <site> execute foames.foames_mes.gateway.mqtt.run`; subscribes to `<prefix>/<machine source id>/<event type>` | `pip install paho-mqtt`, a broker |
| OPC UA | `bench --site <site> execute foames.foames_mes.gateway.opcua.run`; polls the nodes mapped in Machine Data Settings | `pip install asyncua` |
| Sparkplug B | `bench --site <site> execute foames.foames_mes.gateway.sparkplug.run`; subscribes to `spBv1.0/<group>/#` on the same broker and decodes the protobuf payloads itself | `pip install paho-mqtt`, a broker; this is how Ignition publishes, see [ignition.md](ignition.md) |

A logged-in user with the FoaMES Operator role may also post events unsigned, which is how a manual entry or a test harness works.

## Event shape

```json
{"machine": "press-1", "type": "Count", "counter": "good", "value": 1234, "timestamp": "2026-10-30T02:00:00Z", "id": "press-1-000981"}
```

| `type` | Fields | Effect |
| --- | --- | --- |
| `State` | `state`: Running, Idle, Down, Setup, Unknown (aliases such as run, fault, changeover are accepted) | Sets the machine state. Down opens a Downtime Record; the next other state closes it |
| `Count` | `counter` (good, scrap, or any name), `value` = the machine's running total | The delta from the previous reading of that counter is stored on the event and feeds OEE. A first reading, a reset, or a reading that arrives after a later one counts zero: FoaMES never invents production. Set the machine's Counter Rollover to handle wrap-around |
| `Measurement` | `name`, `value` | Stored for SPC and OEE work |
| `Alarm` | `code` or `value`, `text` | Stored and marks the machine Down |
| `Message` | `text` | Stored; refreshes the machine's last-seen time |

`id` is optional and deduplicates retries. `timestamp` is ISO 8601 or Unix seconds; missing means now.

## Extending the processing

After an event is processed, every dotted path registered under the `foames_machine_event_handlers` hook is called with the Machine Event document and its Machine. Another app uses this to attach counts and done messages to its own execution records:

```python
# hooks.py of the other app
foames_machine_event_handlers = ["myapp.floor.on_machine_event"]
```

A Machine also carries a **Current Job Reference**, an External Reference of type Job Card for whatever ERP is connected, and **Current Job Since**. Set it on the form or with `foames.foames_mes.api.set_current_job(machine, reference, at=None)` (pass no reference to end the job). Whenever it changes, every dotted path under the `foames_machine_job_changed` hook is called with the Machine, the previous reference and the time of the change. The ERPNext adapter uses this to roll the counts of the job that ended up to its Job Card; see [erpnext-adapter.md](erpnext-adapter.md#rolling-machine-counts-up-to-job-cards).

A machine that stops reporting is marked Unknown after the configured minutes by a scheduled task, so a silent line never looks like a running one.
