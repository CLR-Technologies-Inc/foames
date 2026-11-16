# Bluesky and Tiled: lab and pilot instruments into FoaMES

[Bluesky](https://github.com/bluesky/bluesky) is the experiment orchestration and data acquisition library used at most NSLS-II beamlines and in a growing number of labs; [Tiled](https://github.com/bluesky/tiled) serves the data Bluesky captures to browsers and analysis tools. Both are open source under the BSD-3-Clause license.

FoaMES does not replace either. The **Bluesky bridge** reads the documents Bluesky emits for each run and posts the readings to the signed webhook as `Measurement` events, so the instrument's results land on a Machine next to the plant's own data. Statistical process control, the Floor View, suggestions and process mining then work on them with no further code. Each event keeps where it came from: the run uid, scan id, plan, stream, sequence number, the data key's source and units, and the sample named in the run.

The bridge lives in [`bridges/bluesky/`](../../../bridges/bluesky/) of this repository. It is a separate Python package that runs next to Bluesky or Tiled, not on the bench, and it needs only the standard library. Nothing is installed into the FoaMES app.

| Path | Bluesky side | Choose it when |
| --- | --- | --- |
| Live callback | `RE.subscribe(FoaMESCallback(...))`, or the same callback on a 0MQ `RemoteDispatcher` or Kafka consumer | Runs should reach FoaMES while they are taken. Prefer a separate process on the document stream, so FoaMES being slow or down never touches acquisition. |
| Tiled replay | `python -m foames_bluesky tiled --uri <catalog> --uid <run uid>` | The runs are already in a Tiled catalog, or you want to backfill. |
| JSON Lines replay | `python -m foames_bluesky jsonl run.jsonl` | Runs were exported with suitcase-jsonl (one `[name, document]` array per line), or moved between sites as files. |

All three use the same mapping, so a run replayed after it was sent live produces the same event ids and is stored once.

## Setting it up

1. **Make a Machine for the instrument.** In FoaMES create a Machine for each instrument or beamline end station whose results you want to chart, and set its **Source ID**. The bridge takes the Source ID from `--machine`, or from the run's start document: the first of `foames_machine`, `beamline_id` or `instrument` that is set (change the keys with `--machine-key`). A run with neither is skipped and reported, never guessed.
2. **Set the webhook secret** in Machine Data Settings, and give it to the bridge in the `FOAMES_WEBHOOK_SECRET` environment variable. A Tiled API key, if the catalog needs one, goes in `TILED_API_KEY`. Neither is accepted on the command line. A key scoped to `read:metadata read:data` is enough for Tiled.
3. **Install the bridge** where Bluesky or the Tiled client runs: `pip install ./bridges/bluesky`, with `[tiled]` for the Tiled path.
4. **Try it dry.** `--dry-run` prints the events instead of posting them.

```bash
export FOAMES_WEBHOOK_SECRET=...      # from Machine Data Settings
python -m foames_bluesky jsonl run.jsonl --machine uvvis-1 --summary mean --dry-run
python -m foames_bluesky jsonl run.jsonl --machine uvvis-1 --summary mean --site https://foames.example.com
```

Live, from Python:

```python
from foames_bluesky import FoaMESCallback, RunMapper, WebhookSender

callback = FoaMESCallback(
	RunMapper("uvvis-1", summaries=("mean",), prefix="uvvis."),
	WebhookSender("https://foames.example.com", secret),
)
RE.subscribe(callback)
```

## What becomes what

| Bluesky document | FoaMES event |
| --- | --- |
| `start` | A `Message` on the Machine: "Bluesky run started: <plan>, scan <id>" |
| `descriptor` | Nothing. It decides which data keys are read: numeric scalars (`dtype` number or integer, no shape, not external) in the selected streams (`primary` unless `--stream` says otherwise), or only the keys named with `--field` |
| `event`, `event_page` | One `Measurement` per selected key per reading, named after the data key (with `--prefix` in front), at the reading's own timestamp. NaN, infinities, strings, booleans, arrays and externally stored data (images, spectra in files) are left out |
| `stop` with `exit_status` success | One `Measurement` per key for each `--summary` asked for (`mean`, `min`, `max`, `first`, `last`, `count`), named `<key>.<summary>`, at the stop time. Use these for run-to-run control charts |
| `stop`, any status | A `Message`: "Bluesky run ended (<status>)" with the reason. An aborted or failed run gets no summaries and is never turned into machine downtime |
| `resource`, `datum`, `stream_resource`, `stream_datum` | Ignored; they point at external array data |

Event ids are `bluesky:<event uid>:<key>` for readings, `bluesky:<run uid>:<key>:<summary>` for summaries, and `bluesky:<run uid>:start` or `:stop` for the messages. FoaMES deduplicates on them, so a retry or a second replay reports the repeat as "duplicate event id" and stores nothing twice.

The provenance block of each event is kept in the Machine Event's **Payload**:

```json
{"system": "bluesky", "run_uid": "6b2c...", "scan_id": 42, "plan_name": "count", "sample": "AuNR-batch-7",
 "units": "nm", "stream": "primary", "event_uid": "ev-1", "seq_num": 1, "data_key": "lspr_nm", "source": "PV:SPEC:LSPR"}
```

`sample`, `proposal_id` and `operator` are copied from the start document when present; name others with `--start-key`.

## Charting it

A run-level summary such as `uvvis.lspr_nm.mean` is a measurement like any other: open **SPC Control Chart** for the Machine and measurement, or call `foames.foames_mes.spc_monitor.get_control_chart`. Run-rule signals become Agent Suggestions on the next suggestion run, as described in [../../spc.md](../../spc.md). Per-reading measurements inside a scan follow whatever the plan scanned, so they are rarely a stable process; chart the summaries and keep the readings for traceability.

## Limits

- The bridge reads scalars. Spectra, images and other arrays stay in Bluesky and Tiled; reduce them there (or in an analysis package) to the scalar results you want charted, and record those as data keys or as a separate analysis stream.
- It only reads from Bluesky and Tiled, and only posts to the FoaMES webhook. It never writes to Tiled, never sends commands to a RunEngine, and never posts to an ERP.
- The Tiled path relies on the run nodes' `documents()` method from `bluesky-tiled-plugins` (or `databroker` 2 for older catalogs). It is tested against a stand-in, not a live Tiled server; treat it as alpha until you have run it against your catalog.
- The bridge is a separate package and is not part of the FoaMES app's SBOM.

## Testing

```bash
cd bridges/bluesky && python -m unittest discover -s tests -v
```

The tests need nothing installed. When run from a checkout of this repository they also pass every mapped event through FoaMES's own `normalise_event` and check the signature against `foames.foames_mes.signing`; when Bluesky and ophyd are installed they map a real `count` plan as well.

## Read-only mode

The Bluesky bridge reads runs and posts them to FoaMES as Measurement events; it writes nothing to Bluesky, Tiled or the instruments. In [read-only mode](../../read-only-mode.md) it keeps working as it is, because data coming into FoaMES is the read side of a connector. A write back to the beamline or a database would have to be registered in `foames_write_actions` and requested through the write gate.
