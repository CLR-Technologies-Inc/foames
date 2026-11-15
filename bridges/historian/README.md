# foames-historian

Read-only bridge from process historians to FoaMES machine events through the signed machine-event webhook: AVEVA PI (PI Web API), InfluxDB (InfluxQL), the Ignition Tag Historian (its SQL tables or a WebDev endpoint), TimescaleDB, and any other SQL historian kept as one row per tag and time. Standard library only; a database driver is needed only for the SQL sources.

The guide, with the tag map, the sources and how the results feed OEE and SPC, is [docs/vendors/historian/](../../docs/vendors/historian/README.md).

```bash
pip install .                      # or .[postgres], .[mysql], .[mssql] for the SQL sources
export FOAMES_HISTORIAN_PASSWORD=...  # or FOAMES_HISTORIAN_TOKEN
export FOAMES_WEBHOOK_SECRET=...
python -m foames_historian check --config examples/pi.json
python -m foames_historian sync --config examples/pi.json --checkpoint state.json --dry-run
python -m unittest discover -s tests -v
```

Licensed under the Apache License, Version 2.0, like FoaMES. It contains no vendor code and uses only the historians' published interfaces.
