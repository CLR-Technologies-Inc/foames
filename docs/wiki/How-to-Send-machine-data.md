**Goal:** get events from a machine into FoaMES so it has a state, downtime and counts.

**You need:** a Machine record whose **Source ID** matches the name your source will send, and the FoaMES Engineer or System Manager role to edit **Machine Data Settings**.

## Pick a path

| Path | Choose it when | Installs |
| --- | --- | --- |
| Signed webhook | Your gateway or script can POST JSON over HTTPS. The simplest choice, and the only one on hosted benches | Nothing |
| MQTT | Your devices publish JSON to a broker | `paho-mqtt` in the bench |
| Sparkplug B | Your SCADA or edge layer publishes Sparkplug B (for example Ignition with MQTT Transmission) | `paho-mqtt` in the bench |
| OPC UA | Your PLC or SCADA serves OPC UA nodes | `asyncua` in the bench |

All four end in the same Machine Event records, so you can mix them.

## Signed webhook

1. In **Machine Data Settings**, set the **Webhook Secret**.
2. From your gateway, POST to `/api/method/foames.foames_mes.api.ingest_machine_events` with body `{"events": [...]}` and two headers:
   - `X-FoaMES-Timestamp`: the current Unix time in seconds;
   - `X-FoaMES-Signature`: the hex HMAC-SHA256 of `<timestamp>.<body>` with the webhook secret.

A minimal Python sender:

```python
import hashlib, hmac, json, time, urllib.request

SECRET = b"<webhook secret>"
body = json.dumps({"events": [
    {"machine": "press-1", "type": "State", "state": "Running", "id": "press-1-000981"},
    {"machine": "press-1", "type": "Count", "counter": "good", "value": 120341, "id": "press-1-000982"},
]}).encode()
ts = str(int(time.time()))
sig = hmac.new(SECRET, ts.encode() + b"." + body, hashlib.sha256).hexdigest()
req = urllib.request.Request(
    "https://mes.example.com/api/method/foames.foames_mes.api.ingest_machine_events",
    data=body, method="POST",
    headers={"Content-Type": "application/json", "X-FoaMES-Timestamp": ts, "X-FoaMES-Signature": sig},
)
print(urllib.request.urlopen(req).read().decode())
```

Send each counter's **running total**, not the increment, and give every event an `id` so a retry is not stored twice.

## MQTT

1. In **Machine Data Settings**, fill in **Broker Host**, **Port**, **Use TLS**, the user and **Topic Prefix** (default `foames`), and tick **MQTT Enabled**.
2. Publish JSON events to `<prefix>/<machine source id>/<event type>`.
3. Start the gateway: `bench --site <site> execute foames.foames_mes.gateway.mqtt.run`, then keep it running as described in [Run the gateways in production](How-to-Run-the-gateways-in-production).

## Sparkplug B

1. In **Machine Data Settings**, fill in the MQTT broker, tick **Sparkplug B Enabled**, and optionally set the **Group ID**.
2. Name each device after the machine's Source ID, and its metrics `state`, `good`, `scrap`, `alarm`, `message` or anything numeric for a measurement. For tags you cannot rename, add rows to **Node and Metric Map** with source Sparkplug B.
3. Start `bench --site <site> execute foames.foames_mes.gateway.sparkplug.run`.

A node or device death (NDEATH, DDEATH) marks its machines Unknown at once.

## OPC UA

1. In **Machine Data Settings**, tick **OPC UA Enabled**, set **Endpoint URL** and **Poll Interval (s)**, and under **OPC UA Security** choose **SignAndEncrypt**, a policy the server lists, and upload a client certificate and a **private** key file. [docs/machine-data.md](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/machine-data.md#making-a-client-certificate) shows how to make the certificate with OpenSSL.
2. Add one **Node and Metric Map** row per node: the node id, the machine, the event type and the counter or measurement name.
3. Start `bench --site <site> execute foames.foames_mes.gateway.opcua.run` once, trust the FoaMES certificate on the server (it usually lands in a quarantine list), and start it again.

## Check that data arrives

- The **Machine Event** list shows new events, each with its counter delta.
- The machine's tile on the **Floor View** changes colour with its state.
- Rejected events are listed in the webhook response with the reason, usually an unknown Source ID or a bad signature.

See also: [Machine event format](Reference-Machine-event-format), [docs/machine-data.md](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/machine-data.md).
