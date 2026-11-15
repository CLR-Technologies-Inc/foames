# Process historians: reading tag history into FoaMES

Most plants already keep years of tag history in a process historian. The live gateways (Sparkplug B, OPC UA, MQTT, the webhook) only see what happens after they connect, and only the tags someone published. The **historian bridge** closes that gap: it reads tag history, read-only, and posts it to FoaMES as ordinary machine events with the historian's own timestamps, so OEE, downtime, SPC control charts, the Floor View, suggestions and process mining work on it with no further code.

| Historian | How the bridge reads it | Source type |
| --- | --- | --- |
| AVEVA PI (OSIsoft PI) | PI Web API: PI Points and AF attributes, recorded values and server-side summaries | `pi` |
| InfluxDB 1.x, 2.x (1.x compatibility API) and 3 | The InfluxQL `/query` endpoint | `influxdb` |
| Ignition Tag Historian | Its SQL tables, directly, with a read-only database login | `ignition-sql` |
| Ignition Tag Historian | A WebDev endpoint on the gateway that runs `system.tag.queryTagHistory` | `ignition-webdev` |
| TimescaleDB | A hypertable of one row per tag and time, aggregated on the server with `time_bucket` | `timescaledb` |
| Any other SQL historian (PostgreSQL, MySQL, SQL Server, SQLite, ...) | A table of one row per tag and time, through the database's Python driver | `sql` |

The bridge lives in [`bridges/historian/`](../../../bridges/historian/) of this repository. It is a separate Python package that runs next to the historian, not on the bench, and needs only the standard library (plus a database driver for the SQL sources). Nothing is installed into the FoaMES app.

It is **read-only by construction**: the REST sources only send GET requests, the SQL sources only build SELECT statements, and the bridge has no code path that writes a tag, a point or a row. Give it a historian account that can only read.

## How it works

1. A JSON **configuration file** names one historian (the source) and lists the tags to read (the tag map). Each entry says which FoaMES Machine the tag belongs to and what it becomes.
2. `sync` reads each tag from where it last stopped up to a little before now, maps the samples to events, sorts them oldest first and posts them in signed batches to `ingest_machine_events`.
3. A **checkpoint file** remembers, per tag map entry, the end of the last window FoaMES accepted. A restart carries on from there; a failed post leaves it where it was.
4. Every event carries an `id` built from the source name, the tag map entry and the sample time, so replaying a window or retrying a post never stores a value twice. FoaMES answers "duplicate event id" for a repeat, which the bridge counts as already stored.

## The tag map

```json
{
	"source": {"type": "pi", "name": "pi-main", "url": "https://pi.example.com/piwebapi", "auth": "basic", "username": "svc-foames-read"},
	"tags": [
		{"tag": "\\\\PISRV01\\Press1.Temperature", "machine": "press-1", "name": "temperature"},
		{"tag": "\\\\PISRV01\\Press1.Temperature", "machine": "press-1", "name": "temperature.mean_1m", "interval": "1m", "aggregate": "mean"},
		{"tag": "\\\\PISRV01\\Press1.GoodCount", "machine": "press-1", "type": "Count", "counter": "good"},
		{"tag": "\\\\PISRV01\\Press1.Status", "machine": "press-1", "type": "State", "states": {"Running": "Running", "Stopped": "Down"}}
	]
}
```

| Key | Meaning |
| --- | --- |
| `tag` | The tag as the historian names it (see each source below). Required. |
| `machine` | The FoaMES Machine's **Source ID**. Required. |
| `type` | `Measurement` (default), `Count`, `State` or `Message`; the event shapes are in [machine-data.md](../../machine-data.md). |
| `name` | The measurement name for a Measurement. Defaults to the last segment of the tag, plus `.<aggregate>` when aggregated. |
| `counter` | The counter name for a Count (`good`, `scrap`, `energy_kwh`, ...). Required for a Count. |
| `states` | For a State: historian value -> FoaMES state (Running, Idle, Down, Setup, Unknown, or an alias FoaMES accepts). `1`, `1.0` and `"1"` are the same key. Without a map, text values are passed through and numbers are skipped. |
| `interval`, `aggregate` | Post one value per bucket (`30s`, `1m`, `1h`, ...) instead of every recorded value. Aggregates: `mean` (default), `min`, `max`, `first`, `last`, `count`, `sum`. Measurements only. |
| `scale`, `offset` | `value * scale + offset` before posting, for a unit change (Wh to kWh is `"scale": 0.001`). The raw value stays in the provenance. |
| `uncertain` | `false` to drop uncertain-quality values as well as bad ones. |

The same tag may appear in several entries, for example once raw and once as a one-minute mean; each entry has its own checkpoint and its own event ids.

### What becomes what, and what never does

- **Counts are never invented or summed here.** A Count carries the historian's running total; FoaMES computes the delta against the previous reading as it does for every other source (a first reading, a reset or an out-of-order reading counts zero). Do not map an "increment per shift" tag as a Count; map the totaliser. A Count cannot be aggregated.
- **States come only from recorded values.** A numeric state needs a `states` map, and a value missing from it is skipped and reported, not guessed. The bridge never infers a state from a gap in the history: a gap stays Unknown, which FoaMES charges as loss.
- **Bad quality is never sent.** Bad samples, PI system digital states (Shutdown, I/O Timeout, No Data, ...) and Ignition rows with a bad `dataintegrity` are skipped. Uncertain samples are sent with `"quality": "uncertain"` in the provenance unless the entry sets `"uncertain": false`.
- **Every event keeps where it came from**: the source name and kind, the tag, the quality, the units when the historian gives them, the aggregate and interval, and any vendor detail (PI digital state code or substituted flag, Ignition `dataintegrity`). FoaMES stores it in the Machine Event's payload.

## Setting it up

1. **Make the Machines** in FoaMES and set their **Source ID**.
2. **Set the webhook secret** in Machine Data Settings and give it to the bridge in `FOAMES_WEBHOOK_SECRET`.
3. **Give the bridge a read-only historian account.** Its password goes in `FOAMES_HISTORIAN_PASSWORD`, or a token in `FOAMES_HISTORIAN_TOKEN` (change the variable names per source with `password_env` / `token_env`). A password or token in the configuration file is refused.
4. **Install** where the historian is reachable: `pip install ./bridges/historian`, with `[postgres]`, `[mysql]` or `[mssql]` for a SQL source. Examples for every source are in [`bridges/historian/examples/`](../../../bridges/historian/examples/).
5. **Check the tag map.** `check` reads the last hour of every entry and reports how many events each would give and why any were skipped. `read` prints one tag's samples.
6. **Try a dry run**, then sync for real, then run it supervised with `--follow`.

```bash
export FOAMES_HISTORIAN_PASSWORD=...     # or FOAMES_HISTORIAN_TOKEN
export FOAMES_WEBHOOK_SECRET=...         # from Machine Data Settings
python -m foames_historian check --config historian.json
python -m foames_historian read  --config historian.json --tag "\\\\PISRV01\\Press1.Temperature" --start now-2h
python -m foames_historian sync  --config historian.json --checkpoint state.json --dry-run
python -m foames_historian sync  --config historian.json --checkpoint state.json --site https://foames.example.com --follow 60
```

### Sync options

| Option | Default | Meaning |
| --- | --- | --- |
| `--checkpoint FILE` | none | Where to remember how far each entry was posted. Without it every run starts from `--initial`. |
| `--lag` | `2m` | Stay this far behind now, so values the historian is still receiving through store-and-forward are read on a later pass instead of missed. Raise it for sites with long buffering. |
| `--initial` | `1h` | How far back an entry with no checkpoint starts. |
| `--max-window` | `1d` | The longest window read per entry per pass. After a long outage the bridge catches up in steps of this size, each checkpointed, without pausing between them. |
| `--follow SECONDS` | off | Keep running, pausing this long between passes once caught up. |
| `--start`, `--end` | off | Replay a fixed window (a **backfill**). The checkpoint is neither read nor moved, and the event ids keep a replay from storing anything twice. |
| `--dry-run` | off | Print the events as JSON and post nothing. |

Two things to know when backfilling counts: FoaMES counts a counter reading that arrives after a later reading as zero, so backfill a machine's counters **before** the live gateway starts sending them, or accept that the backfilled window adds no production. Measurements, states and messages can be backfilled at any time.

## AVEVA PI (PI Web API)

`"type": "pi"`, `"url"` the PI Web API root (`https://<server>/piwebapi`), `"auth"` `basic` (a PI Web API account in Basic authentication mode) or `bearer` (an OpenID Connect token). Kerberos is not built in; put the bridge behind a host with a keytab and a proxy, or use Basic over TLS.

- **Tags**: a PI Point path `\\<data server>\<tag>`, an AF attribute path `\\<AF server>\<database>\<element>|<attribute>`, or `webid:<WebId>`. Remember to double the backslashes in JSON.
- **Raw values** come from `streams/{webId}/recorded` (the archived, compressed values), paged with `maxCount` (default 10000, set `max_count` to match the server's limit).
- **Aggregates** use `streams/{webId}/summary`: `mean` is PI's time-weighted Average (set `"calculation_basis": "EventWeighted"` for a plain mean of the values), `min`, `max` likewise, `count` and `sum` are event-weighted. `first` and `last` are computed by the bridge from recorded values.
- Digital states arrive as their state name, which suits a State entry with a `states` map keyed by name.

## InfluxDB

`"type": "influxdb"`, `"url"`, `"database"` (and optional `"retention_policy"`). Authentication: `"auth": "token"` for InfluxDB 2 and 3 (`Authorization: Token ...`), `"basic"` for 1.x users, or `"none"`. On InfluxDB 2, map the bucket to a database name with a DBRP mapping first (`influx v1 dbrp create`).

- **Tags**: `<measurement>/<field>`, with optional tag filters written like a URL query: `machine_data/temperature?line=L1&machine=press-1`. Every name is quoted as an InfluxQL identifier and every filter value as a string literal, so a tag map cannot inject a query.
- **Aggregates** run on the server: `GROUP BY time(<interval>) fill(none)` with `MEAN`, `MIN`, `MAX`, `FIRST`, `LAST`, `COUNT` or `SUM`. Empty buckets produce nothing.

## Ignition Tag Historian

Two ways; both take tags as Ignition writes them, `[default]Line1/Press1/Temperature` (the provider in brackets is optional; without it every provider's tag with that path is read).

### From the historian database (`ignition-sql`)

The bridge reads the tables Inductive Automation documents for the SQL historian: `sqlth_drv`, `sqlth_scinfo`, `sqlth_te`, `sqlth_partitions` and the data partitions they list (`sqlt_data_<driver>_<year>_<month>` by default). It finds every id the tag has had (a tag that was deleted and re-created, or moved between history providers, has several), reads each partition that overlaps the window, picks the value column by the tag's data type, and maps `dataintegrity` to quality (192 and above good, 64 to 127 uncertain, anything else bad).

```json
{"type": "ignition-sql", "name": "ignition-hist", "driver": "psycopg",
 "connect": {"host": "historian-db", "dbname": "ignition", "user": "foames_read"},
 "gateway": "plant-gateway"}
```

`driver` is the Python DB-API module for the historian's database (`psycopg` for PostgreSQL, `pymysql` for MySQL and MariaDB, `pyodbc` for SQL Server); `connect` holds its connection arguments except the password. `gateway` limits the read to one gateway's driver rows when several gateways share the database. Partition names read from `sqlth_partitions` are checked before they are put into a query.

This is the fastest path for years of history and needs no change on the gateway. It reads the stored values only: Ignition's interpolation, its pre-processed partitions and values still waiting in store-and-forward are not seen. Aggregates are computed by the bridge (arithmetic, not time-weighted).

### Through the gateway (`ignition-webdev`)

When the database is not reachable from where the bridge runs, add a WebDev Python resource on the gateway (for example `foames/history`, with `doGet`) and point `"url"` at it: `https://<gateway>:8043/system/webdev/<project>/foames/history`. Protect the resource with a role that can only read history, and use `"auth": "basic"`.

```python
# WebDev resource foames/history, doGet. Read-only: it only queries tag history.
def doGet(request, session):
	params = request["params"]
	start = system.date.fromMillis(long(params["start"]))
	end = system.date.fromMillis(long(params["end"]))
	options = {"paths": [params["path"]], "startDate": start, "endDate": end, "returnFormat": "Tall"}
	if params.get("intervalMs"):
		options["intervalSeconds"] = max(1, int(params["intervalMs"]) // 1000)
		options["aggregationMode"] = params.get("aggregate", "SimpleAverage")
	else:
		options["returnSize"] = -1        # the values as stored
		options["noInterpolation"] = True
	data = system.tag.queryTagHistory(**options)
	rows = []
	for r in range(data.getRowCount()):
		quality = data.getValueAt(r, "quality")
		try:
			code = 192 if quality.isGood() else (64 if quality.isUncertain() else 0)
		except AttributeError:
			code = int(quality)
		stamp = data.getValueAt(r, "timestamp")
		rows.append({"t": stamp.getTime(), "v": data.getValueAt(r, "value"), "q": code})
	return {"json": rows}
```

With this source `mean`, `min`, `max`, `count` and `sum` are aggregated by the gateway (SimpleAverage, Minimum, Maximum, Count, Sum); `first` and `last` are computed by the bridge. The script follows the Ignition 8.1 scripting API; check the parameter names against your gateway's version.

## TimescaleDB and other SQL historians

`"type": "timescaledb"` or `"type": "sql"` reads a narrow table with one row per tag and time:

```json
{"type": "timescaledb", "name": "tsdb", "driver": "psycopg",
 "connect": {"host": "tsdb", "dbname": "telemetry", "user": "foames_read"},
 "table": "tag_history", "time_column": "time", "tag_column": "tag", "value_column": "value", "quality_column": "quality"}
```

- Column names default to `time`, `tag` and `value`; `quality_column` is optional and read as an OPC-style code (192 good). Table and column names must be plain identifiers (`schema.table` is allowed); values are always bound as parameters.
- `timescaledb` aggregates on the server with `time_bucket(<interval>, time, '1970-01-01')` and `avg`, `min`, `max`, `count`, `sum`, `first(value, time)` and `last(value, time)`, so buckets line up with the bridge's own.
- `sql` works with any DB-API driver; `"time_type"` says how the time column is stored: `timestamp` (default), `iso` (ISO 8601 text), `epoch_ms` or `epoch_s`. Aggregates are computed by the bridge. The driver's `paramstyle` is used unless `"paramstyle"` overrides it.

## From Python

The sources are usable without the command line, for example from an analysis notebook or an agent that needs a tag's history for a run:

```python
from datetime import timedelta
from foames_historian import PIWebAPISource, parse_time
from foames_historian.http import HttpClient, basic_auth

pi = PIWebAPISource("pi-main", HttpClient("https://pi.example.com/piwebapi", headers={"Authorization": basic_auth(user, password)}))
samples = pi.read("\\\\PISRV01\\Press1.Temperature", parse_time("now-8h"), parse_time("now"), interval=timedelta(minutes=5), aggregate="max")
```

`foames_historian.load("historian.json")` returns the configured source and tag map; `sync_once(...)` runs one pass with any `send` function.

## Checking that data arrives

1. `check` and `sync --dry-run` show what would be posted and list skipped samples with the reason (bad quality, a state not in the map, a non-numeric value).
2. In FoaMES, open the **Machine Event** list for the machine. Historian events have source Webhook and their payload's `provenance` names the historian, the source and the tag.
3. The sync summary counts accepted, already stored (duplicates, normal after a replay), rejected and skipped events. Rejections (usually an unknown machine Source ID) make the run exit non-zero and are listed; they do not hold the checkpoint back, so fix the cause and replay the window with `--start` and `--end`.

## Limits

- The bridge is alpha. It was written against the vendors' published interfaces and is tested against stand-ins (the PI Web API and InfluxDB JSON from their documentation, the Ignition historian schema in SQLite), not yet against a live PI server, InfluxDB, Ignition gateway or TimescaleDB.
- One configuration file holds one source; run one bridge per historian.
- PI AF event frames, Ignition alarm journals and transaction groups are not read.
- The bridge never writes to a historian and FoaMES does not query a historian on its own; history reaches FoaMES only as events this bridge posts.
