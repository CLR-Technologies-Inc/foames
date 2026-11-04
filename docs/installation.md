# Installing FoaMES

FoaMES is a Frappe app. It installs on any Frappe v15 or v16 site, with or without an ERP, and needs nothing outside the bench except the optional gateway packages described below.

## Requirements

| Requirement | Notes |
| --- | --- |
| Frappe v15 or v16 | Both are tested in CI. The app depends on the Frappe framework only. |
| Python 3.10 or later | Set by `pyproject.toml`. Frappe v15 benches run 3.10 to 3.12; v16 benches run 3.12 or later. |
| MariaDB | Whatever the bench already uses. |
| An ERP | Optional. Adapters connect FoaMES to an ERP, whether it runs on the same site or remotely; nothing in FoaMES imports an ERP's package. What each adapter needs is in its guide under [vendors/](vendors/README.md). |
| `paho-mqtt` | Optional. Needed only by the MQTT gateway and the Sparkplug B gateway. |
| `asyncua` | Optional. Needed only by the OPC UA gateway. |

## Install on a bench

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/CLR-Technologies-Inc/foames
bench --site $SITE install-app foames
```

Installing an ERP on the same site is independent of FoaMES. Install it before or after; an adapter checks for its ERP at run time, not at install time.

Installation creates six roles before the DocTypes are synced:

| Role | Meant for | What it can do |
| --- | --- | --- |
| FoaMES Engineer | Process and manufacturing engineers | Full access to Machines, Downtime Reasons, Machine Data Settings, OEE Periods and Agent Suggestions; may post machine events. |
| FoaMES Operator | Shop-floor users | Create and edit Machines, Downtime Records and Agent Suggestions; create Machine Events (manual entry or unsigned test posts); read Downtime Reasons and OEE Periods. |
| FoaMES Quality | Quality staff | Edit (not create) Machines, Downtime Records and Agent Suggestions; read Machine Events, Downtime Reasons and OEE Periods. |
| FoaMES Supervisor | Shift and production supervisors | Read and report on everything in the MES module; edit Machines, create and edit Downtime Records, Downtime Reasons, Agent Suggestions and Process Event Logs. Opens the Supervisor workspace. |
| FoaMES Maintenance | Maintenance technicians and planners | Read Machines, Machine Events and OEE Periods; create and edit Downtime Records and Downtime Reasons; create and edit Agent Suggestions; create Machine Events; create, edit and delete Maintenance Plans and Maintenance Work Orders. Opens the Maintenance workspace. |

Operators and Quality staff can therefore change a Machine's source id, OEE parameters and disabled flag. If that should be reserved to engineers, tighten the Machine permissions in Role Permissions Manager on the site.
| FoaMES Integration | Service users for other systems | Creates the inbound-message and outbox records an adapter receives from another system. Give it to the user whose API key that system uses; the vendor's guide says which records and endpoints it needs. |

System Manager keeps full access to everything, including FoaMES Settings, the adapters' Settings and External References.

Each role has a workspace of its own with the cards, charts and reports for that job; see [dashboards.md](dashboards.md).

## Update

```bash
cd $PATH_TO_YOUR_BENCH
bench update --apps foames
# or, on a bench without `bench update`:
cd apps/foames && git pull && cd ../..
bench --site $SITE migrate
```

Any Frappe patch FoaMES ships runs from `foames/patches.txt` during `migrate`.

## Uninstall

```bash
bench --site $SITE uninstall-app foames
```

This drops the FoaMES DocTypes and their data. Export OEE Periods or Downtime Records first if you need the history.

## First configuration

Everything below is done in the desk (the `/app` UI) as a System Manager.

1. **FoaMES Settings.** Set **Default ERP System** to the key of the adapter new External References should use (the keys on a site are listed by `foames.foames_adapters.get_available_erp_systems`), or leave it empty to run without an ERP. Leave **Skip Resolving References on Save** off unless the ERP is slow to answer and you prefer to resolve references by hand.
2. **Downtime Reasons.** Create the reasons operators will pick, and tick **Counts As Planned Downtime** on the ones that should not count against availability (scheduled maintenance, planned changeovers). See [oee.md](oee.md).
3. **Machines.** One record per machine, with a short **Code**, the **Ideal Cycle Time** in seconds, and a **Shift Start** plus **Scheduled Minutes Per Day** for the daily OEE window. **Source ID** defaults to the code and is what the gateways use to find the machine.
4. **Machine Data Settings.** Set the webhook secret and whichever of MQTT, Sparkplug B or OPC UA you will use. See [machine-data.md](machine-data.md) and, for a SCADA product with a guide, [vendors/](vendors/README.md).
5. **The Settings of each adapter** you connect, if any. Each adapter's guide under [vendors/](vendors/README.md) says what to fill in and how to switch it on.

Give people the roles above through their User records. The Floor View is at `/app/floor-view`.

## The scheduler

FoaMES relies on the Frappe scheduler for four jobs. Make sure it is enabled on the site:

```bash
bench --site $SITE enable-scheduler
bench --site $SITE scheduler status
```

| Job | When | What it does |
| --- | --- | --- |
| `foames.foames_mes.tasks.mark_stale_machines_unknown` | Every 5 minutes | Marks a machine Unknown when it has not reported within **Mark Machine Unknown After** (15 minutes by default). |
| `foames.foames_mes.tasks.run_suggestion_rules` | Hourly | Runs the built-in suggestion rules over the last day. |
| `foames.foames_mes.tasks.check_maintenance_plans` | Hourly | Reads every Maintenance Plan's meter and raises suggestions for plans that are due soon, due or overdue. See [maintenance.md](maintenance.md). |
| `foames.foames_mes.tasks.compute_daily_oee` | Daily | Creates one OEE Period per enabled machine for the previous day. |
| Each adapter's jobs | As its guide says | Adapters register their own jobs (an outbox that sends due postings, a roll-up of machine counts). Each returns at once unless that adapter is enabled in its Settings. |

On a development bench with `developer_mode` on, the scheduler is often paused. Run a job by hand when you need it:

```bash
bench --site $SITE execute foames.foames_mes.tasks.compute_daily_oee
```

## The gateways

The webhook needs no process of its own: it is a whitelisted method served by the web workers. The three gateways are long-running processes you start inside the bench and keep alive with a supervisor.

| Gateway | Package | Command |
| --- | --- | --- |
| MQTT | `paho-mqtt` | `bench --site $SITE execute foames.foames_mes.gateway.mqtt.run` |
| Sparkplug B | `paho-mqtt` | `bench --site $SITE execute foames.foames_mes.gateway.sparkplug.run` |
| OPC UA | `asyncua` | `bench --site $SITE execute foames.foames_mes.gateway.opcua.run` |

Install the packages into the bench's own environment:

```bash
cd $PATH_TO_YOUR_BENCH
./env/bin/pip install paho-mqtt        # MQTT and Sparkplug B
./env/bin/pip install asyncua          # OPC UA
```

Each gateway exits with a message when its package is missing or when its path is not enabled in Machine Data Settings, so a misconfigured gateway fails fast rather than running silently.

On a production bench managed by supervisor, add a program per gateway to the bench's supervisor configuration (usually `config/supervisor.conf`, included from `/etc/supervisor/conf.d/`). Put it in the bench's group so `bench restart` covers it:

```ini
[program:frappe-bench-foames-sparkplug]
command=/usr/local/bin/bench --site site1.local execute foames.foames_mes.gateway.sparkplug.run
directory=/home/frappe/frappe-bench
user=frappe
autostart=true
autorestart=true
startretries=10
stdout_logfile=/home/frappe/frappe-bench/logs/foames-sparkplug.log
stderr_logfile=/home/frappe/frappe-bench/logs/foames-sparkplug.error.log
```

Adjust the `bench` path (`which bench`), the bench directory and the site. Then `sudo supervisorctl reread && sudo supervisorctl update`. A systemd unit with the same command, `WorkingDirectory` and `Restart=always` works the same way. Run one gateway process per site; a gateway serves the site named in its command only.

Each gateway reads Machine Data Settings once at start-up. Restart the gateway after changing the broker, the endpoint, the Sparkplug group or the node map.

## Frappe Cloud and other hosted benches

FoaMES can be added to a private bench as a custom app from its GitHub repository. `pyproject.toml` declares no apt packages, so no extra system dependencies are needed. The webhook and the scheduler work as on any bench. The three gateways are long-running processes started with `bench execute`, which a hosted bench may not let you run. In that case use the signed webhook: a small bridge of your own on a machine near the broker or the OPC UA server subscribes or polls there and posts events to the site over HTTPS, as in the gateway-script examples in the [vendor guides](vendors/README.md).

## Check that it works

1. Open `/app/floor-view`. With no machines yet, it says so.
2. Create a Machine with code `press-1`.
3. Post a test event. Signed in as a FoaMES Operator or Engineer, this works without a signature; the example uses an API key and secret from the user's settings:

   ```bash
   curl -X POST https://$SITE/api/method/foames.foames_mes.api.ingest_machine_events \
     -H "Authorization: token $API_KEY:$API_SECRET" \
     -H "Content-Type: application/json" \
     -d '{"events": [
           {"machine": "press-1", "type": "State", "state": "Running"},
           {"machine": "press-1", "type": "Count", "counter": "good", "value": 100},
           {"machine": "press-1", "type": "Count", "counter": "good", "value": 112}
         ]}'
   ```

   The response lists the accepted Machine Event names and the reason for any rejection.
4. Refresh the Floor View. The tile for `press-1` is green, and the good count is 12, not 112: the first reading of a counter sets the baseline and the second yields the delta.
5. Ask for OEE on demand (the parameters are those of `get_oee`):

   ```bash
   curl "https://$SITE/api/method/foames.foames_mes.doctype.oee_period.oee_period.get_oee?machine=press-1&from_time=2026-01-01%2006:00:00&to_time=2026-01-01%2014:00:00" \
     -H "Authorization: token $API_KEY:$API_SECRET"
   ```

For a signed request from a system with no Frappe user, see the signing description in [machine-data.md](machine-data.md) and the script examples in the [vendor guides](vendors/README.md).

## Development setup

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/CLR-Technologies-Inc/foames
bench new-site dev.localhost --admin-password admin
bench --site dev.localhost install-app foames
bench --site dev.localhost set-config allow_tests true
bench --site dev.localhost run-tests --app foames
cd apps/foames && pre-commit install
```

The modules that hold the arithmetic and parsing (`foames/foames_mes/oee.py`, `counters.py`, `suggestions.py`, `signing.py`, `gateway/mapping.py`, `gateway/sparkplug.py`) import nothing from Frappe, and their tests run anywhere with plain Python:

```bash
python -m unittest foames.foames_mes.test_oee_and_rules foames.foames_mes.test_machine_data_logic foames.foames_mes.test_sparkplug
```

The rest of the tests need a site, so run them with `bench run-tests` as above. CI runs the whole suite on Frappe v15, on v16, and on v16 with an ERP app installed. Without a bench on the machine, the [Docker dev bench](dev-bench.md) runs the same matrix locally.
