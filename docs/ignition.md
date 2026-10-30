# Ignition SCADA: connecting an Ignition gateway to FoaMES

Ignition (Inductive Automation) already talks to the PLCs. FoaMES does not replace that; it takes the machine data Ignition has and turns it into Machine Events, downtime, counts and OEE. There are three ways to connect, and a plant can use more than one. All three end in the same Machine Event records, so nothing downstream cares which path was used.

| Path | Ignition side | FoaMES side | Choose it when |
| --- | --- | --- | --- |
| Sparkplug B over MQTT | MQTT Transmission module (Cirrus Link) publishes tags to a broker, often Ignition's own MQTT Distributor | `bench --site <site> execute foames.foames_mes.gateway.sparkplug.run` | You have the Cirrus Link modules. Event-driven, reports by exception, carries data types and timestamps, and tells FoaMES when a node goes offline. The preferred path. |
| OPC UA | Ignition's built-in OPC UA server exposes every tag (enabled under Config, OPC UA, Server Settings) | `bench --site <site> execute foames.foames_mes.gateway.opcua.run` with the nodes mapped in Machine Data Settings | No MQTT modules. Polled, so set the poll interval to the slowest change you need to see. |
| Signed webhook | A gateway tag-change script or a scheduled script POSTs JSON with `system.net.httpClient()` | `POST /api/method/foames.foames_mes.api.ingest_machine_events` | You want Ignition's scripting to decide what counts as an event, or to batch events. |

The MQTT broker, user and TLS setting in Machine Data Settings serve both the plain MQTT gateway and the Sparkplug gateway.

## Sparkplug B

Ignition's MQTT Transmission module publishes on `spBv1.0/<group>/<message type>/<edge node>/<device>` with protobuf payloads. FoaMES decodes them itself (the Sparkplug B schema is public and small), learns metric aliases from NBIRTH and DBIRTH, and turns each metric into an event. No Sparkplug library is needed; only `paho-mqtt`.

1. In Machine Data Settings, fill in the MQTT broker and tick **Sparkplug B Enabled**. Set **Group ID** to limit the gateway to one Sparkplug group.
2. In MQTT Transmission, create a Transmitter whose tag folder holds one subfolder per machine. The subfolder name becomes the Sparkplug device id and is matched against the Machine's **Source ID** (or its code).
3. Name the tags inside each machine folder by the convention below, or map them explicitly.
4. Run the gateway as a supervised process.

### The naming convention

With the convention, a machine folder needs no configuration in FoaMES. The last segment of a metric name decides the event:

| Tag name (last segment) | Event |
| --- | --- |
| `state` | State. Strings are mapped through the usual aliases (run, fault, changeover, ...). For numeric states add a map row with a state map. |
| `good`, `scrap`, `count`, `total`, `parts`, `reject`, `bad`, `ng` | Count, with that counter name. Send the running total, not the increment. |
| `count/<name>` | Count with counter `<name>`. |
| `alarm` | Alarm. A numeric value is the code; anything else is text. |
| `message` | Message with the value as text. |
| any other numeric tag | Measurement named by the full metric path. |

Example tag folder on the edge node `Edge1`, published as device `press-1`:

```
press-1/
  state        (String)  "Running"
  good         (Int64)   120341
  scrap        (Int64)   871
  temperature  (Double)  72.5
```

### Explicit mapping

For tags that cannot be renamed, add rows to **Node and Metric Map** with source **Sparkplug B** and the path `<group>/<edge node>/<device>/<metric name>` (the group, or the device, may be left out). The row's machine, event type, counter or measurement name and state map then apply, exactly as for OPC UA nodes.

### What else the gateway does

- NBIRTH and DBIRTH values are recorded like data, so the first counts after a reconnect set the baseline. Counter deltas are computed by FoaMES, so a rebirth never invents production.
- NDEATH and DDEATH set the machines they cover to Unknown, which opens the usual staleness handling. A device under a dead edge node is covered when FoaMES has seen its birth.
- Each metric's own timestamp is used when Ignition sends one, otherwise the payload's.
- Host `STATE` messages and command messages (NCMD, DCMD) are ignored. FoaMES never writes tags.

## OPC UA

Enable Ignition's OPC UA server and give it a user. Ignition exposes tags as string node ids in namespace 2, for example `ns=2;s=[default]Line1/Press1/GoodCount` for a tag in the default tag provider. Add one row per tag under **Node and Metric Map** with source **OPC UA**, then run the OPC UA gateway. The endpoint is `opc.tcp://<gateway host>:62541/discovery` by default.

## Webhook from a gateway script

A gateway tag-change script can post events as soon as a tag changes. The script below signs the request the way FoaMES expects (HMAC-SHA256 of `<timestamp>.<body>` with the webhook secret from Machine Data Settings). Ignition scripts run in Jython, so the standard `hmac` and `hashlib` modules are available.

```python
# Gateway event script: Tag Change, on the tags you want to report.
import hashlib, hmac, time
import system

FOAMES = "https://foames.example.com/api/method/foames.foames_mes.api.ingest_machine_events"
SECRET = "the webhook secret"


def post_events(events):
	body = system.util.jsonEncode({"events": events})
	ts = str(int(time.time()))
	signature = hmac.new(SECRET, ts + "." + body, hashlib.sha256).hexdigest()
	client = system.net.httpClient()
	client.post(
		FOAMES,
		data=body,
		headers={
			"Content-Type": "application/json",
			"X-FoaMES-Timestamp": ts,
			"X-FoaMES-Signature": signature,
		},
	)


# event.tagPath, newValue and previousValue are provided by Ignition
machine = str(event.tagPath).split("/")[-2]  # the machine folder
tag = str(event.tagPath).split("/")[-1]
value = newValue.value
if tag == "state":
	post_events([{"machine": machine, "type": "State", "state": value}])
elif tag in ("good", "scrap"):
	post_events([{"machine": machine, "type": "Count", "counter": tag, "value": value}])
```

The event shape is the same as for any other source; see [machine-data.md](machine-data.md).

## What FoaMES does not do with Ignition

- It does not write tags or send commands. Control stays in Ignition.
- It does not read Ignition's tag history. OEE is computed from the events FoaMES received; for history before the connection was made, replay it through the webhook with the original timestamps.
- It does not need the WebDev module or Ignition's Perspective or Vision; the Floor View is a Frappe page. An Ignition screen can embed Frappe pages or call the floor snapshot API if a plant wants one screen.
