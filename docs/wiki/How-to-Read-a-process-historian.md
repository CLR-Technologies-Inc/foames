**Goal:** read tag history from a process historian into FoaMES as machine events, without writing anything back to the historian.

**Supported sources:** AVEVA PI (PI Web API), InfluxDB, Ignition Tag Historian (from its database or through a WebDev endpoint), TimescaleDB and other SQL historians (PostgreSQL, MySQL, SQL Server).

**You need:** Machines in FoaMES with Source IDs, the webhook secret from Machine Data Settings, a **read-only** historian account, and a host that can reach both the historian and the FoaMES site. The bridge runs there, outside the bench.

## Steps

1. Install the bridge from the repository: `pip install ./bridges/historian`, adding `[postgres]`, `[mysql]` or `[mssql]` for a SQL source.
2. Write a configuration file that names the source and maps each tag to a machine:

   ```json
   {
     "source": {"type": "pi", "name": "pi-main", "url": "https://pi.example.com/piwebapi", "auth": "basic", "username": "svc-foames-read"},
     "tags": [
       {"tag": "\\\\PISRV01\\Press1.Temperature", "machine": "press-1", "name": "temperature"},
       {"tag": "\\\\PISRV01\\Press1.GoodCount", "machine": "press-1", "type": "Count", "counter": "good"},
       {"tag": "\\\\PISRV01\\Press1.Status", "machine": "press-1", "type": "State", "states": {"Running": "Running", "Stopped": "Down"}}
     ]
   }
   ```

   Map a **totaliser** as a Count, never an "increment per shift" tag. A numeric state needs a `states` map.
3. Put secrets in the environment, never in the file:

   ```bash
   export FOAMES_HISTORIAN_PASSWORD=...   # or FOAMES_HISTORIAN_TOKEN
   export FOAMES_WEBHOOK_SECRET=...
   ```

4. Check, dry-run, then sync:

   ```bash
   python -m foames_historian check --config historian.json
   python -m foames_historian sync  --config historian.json --checkpoint state.json --dry-run
   python -m foames_historian sync  --config historian.json --checkpoint state.json --site https://mes.example.com --follow 60
   ```

5. Keep the `--follow` process running under a supervisor.

## Backfilling

Use `--start` and `--end` to replay a fixed window. Event ids make a replay safe. Backfill a machine's **counters before** the live gateway starts sending them, because a counter reading that arrives after a later one counts as zero.

Examples for every source and all options are in [docs/vendors/historian](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/vendors/historian/README.md).

For lab and pilot instruments driven by Bluesky, with data in a Tiled catalog, a similar bridge is described in [docs/vendors/bluesky](https://github.com/CLR-Technologies-Inc/foames/blob/main/docs/vendors/bluesky/README.md).
