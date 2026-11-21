# Manufacturing-data validation track

The agent benchmark asks whether an AI agent can change FoaMES correctly. This track asks a different question: **does FoaMES itself handle real manufacturing data correctly?** It replays public datasets through FoaMES's pure code (counter deltas, the OEE time ledger, SPC charts, process-mining views) and compares every result with a value computed independently, inside the benchmark, from the raw rows.

The track is deterministic, so each stage runs once. Repetitions belong to the agent benchmark, where agent behaviour and inference latency vary.

```bash
cd benchmarks
python -m foames_bench data list                              # datasets, status, license
python -m foames_bench data validate --synthetic              # offline, invented data in each dataset's shape
python -m foames_bench data fetch                             # download the enabled datasets into the cache
python -m foames_bench data validate --stage dev --out runs/mfg
```

The cache is `$FOAMES_BENCH_DATA`, or `~/.cache/foames-bench/datasets`. Nothing is downloaded into the repository and no dataset is vendored.

## Pipeline

1. **Manifest** ([datasets/manifest.json](../datasets/manifest.json)): source, accepted licenses, citation, column names, how to split the data.
2. **Fetch**: downloads a dataset only when its status is `enabled`. A Kaggle source needs Kaggle credentials (`KAGGLE_USERNAME` and `KAGGLE_KEY`, `KAGGLE_API_TOKEN`, or `~/.kaggle/kaggle.json`); the fetch reads the license Kaggle states and refuses one the manifest does not accept before it downloads anything, and the credentials are never sent on to the storage the download redirects to. Without credentials, download the archive in a browser and run `foames-bench data import <dataset> <zip>`, which applies the manifest's verified license, the same zip rules and writes the same provenance. For a Zenodo record, it reads the license the record states at download time and refuses one the manifest does not accept. It also checks each file's MD5 against Zenodo's checksum. For a direct URL, it requires a license verified in the manifest and checks a pinned SHA-256 when one is set. Zip members cannot write outside the dataset folder. Each dataset folder gets a `provenance.json` with the license, DOI, version, creators, file sizes and checksums.
3. **Adapters**: normalise timestamps, sessions, phases, downtime intervals, counts and measurements. When a file's columns do not match the manifest, the adapter stops and lists the headers it found, so fixing the mapping is a one-line manifest change.
4. **Checks**: run FoaMES and compare. A check passes or fails. **Metrics** (for example SPC precision against fail labels) are reported but not graded.
5. **Report**: `manufacturing-data.md` and `.json` in `--out`.

Fetch stages every selected file, extracted ZIP member and the new provenance before replacing cached payloads. A later file's checksum, filename decoding or decompression failure leaves existing dataset bytes and provenance unchanged. Publication preflights destination conflicts, then replaces individual files and publishes provenance last. This does not guarantee a crash-atomic filesystem transaction or concurrent-writer coordination; avoid simultaneous fetches into one dataset folder.

## Stages

| Stage | Rows | SPC features | Runs | When |
| --- | --- | --- | --- | --- |
| `smoke` | 500 | 5 | 1 | Every relevant code change |
| `dev` | 5,000 | 20 | 1 | Normal integration testing |
| `full` | all | 60 | 1 | Candidate and release validation |

Dataset size is not statistical sample size. Thousands of successive readings from one machine are correlated, so the splits are by time or by production session, never random rows.

## Datasets

| Priority | Dataset | Status | What it checks |
| --- | --- | --- | --- |
| 1 | Five-axis CNC milling with multiple changeovers (Zenodo 15735480) | enabled | Phase segments, process-mining variants, median phase durations, repeated phases, setup time, and that the OEE ledger accounts for every minute of each session |
| 2 | Industrial beverage bottling line (Zenodo 18146866) | enabled | Hourly counts replayed as a PLC counter with a 16-bit rollover and with a controller restart, which must give the source total exactly. Also availability from merged downtime, every minute accounted for, and missing signal counted as loss |
| 3 | SECOM semiconductor manufacturing (UCI) | enabled | I-MR limits and beyond-limit signals against an independent computation, missing values never charted, time-aware precision and recall against pass/fail (reported) |
| 4 | XQuality CNC turning: one CNC lathe, 62 labelled parts (Kaggle) | enabled | I-MR limits and signals on per-part sensor features, spindle energy per part, ECL profile and agent eligibility. Part of the [CNC equipment study](cnc-equipment-study.md) |
| 5 | CNC milling fleet: three mills, 15 operations, vibration 2018-2021 (Kaggle CSV of the upstream repository) | enabled | I-MR limits per machine and operation, fleet ECL. Part of the [CNC equipment study](cnc-equipment-study.md) |
| 6 | NoBOOM chemical processes | planned | The first continuous-process anomaly benchmark, once its license and a non-Kaggle download are confirmed |
| 7-10 | Multi-stage continuous flow, CNC tool wear, AI4I 2020, NASA C-MAPSS | planned | See the manifest notes |
| later | Bosch production line (about 14 GB), IoT-enriched smart-factory event log (about 1.9 GB) | later | Too large to start with; the event log will come in later as a compact extract |

Notes on interpretation:

- **Bottling efficiency is not OEE.** The source's efficiency figure comes from aggregated measurements. It does not have the planned-time, ideal-cycle-time and quality inputs that OEE needs, so the track checks availability and counts only.
- **An SPC signal is not a defect.** SECOM's fail labels grade the signals as a reported metric. Limits come from the earliest 30 percent of samples, and only later samples are graded.
- **A restart on a counter that also has a rollover value set** cannot be told apart from a wrap by the readings alone. The bottling report shows the phantom units this would add (`reset_on_rollover_counter_phantom_units`). The size of that number is the case for a reset signal from the gateway.
- **ERP retry behaviour stays synthetic.** Public manufacturing datasets have no request/response history, so `erp-retry-after` remains an engineered fault-injection task.

## Licenses and attribution

| Dataset | License | Evidence | Citation |
| --- | --- | --- | --- |
| SECOM | CC BY 4.0 | [UCI dataset page](https://archive.ics.uci.edu/dataset/179/secom), checked 2026-11-16 | McCann, M. & Johnston, A. (2008). SECOM [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C54305 |
| AI4I 2020 | CC BY 4.0 | [UCI dataset page](https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset), checked 2026-11-16 | AI4I 2020 Predictive Maintenance Dataset [Dataset]. (2020). UCI Machine Learning Repository. https://doi.org/10.24432/C5HS5C |
| CNC changeover, beverage bottling | CC BY 4.0 expected | Checked against the Zenodo record's own license field at every fetch | Creators and DOI as Zenodo lists them, recorded in `provenance.json` |
| XQuality CNC turning, CNC milling fleet | CC BY 4.0 | See the [CNC equipment study](cnc-equipment-study.md#sources-and-licenses), checked 2026-11-21; Kaggle fetches also check the license Kaggle states | See the study |
| Other Kaggle-hosted sets | not yet confirmed | | |

If you publish results, cite each dataset you used, link its license, and say that FoaMES normalised the data (CC BY 4.0 asks you to indicate changes). The synthetic fixtures (`--synthetic`) are invented and carry no third-party terms.

## Status

The adapters for the two Zenodo datasets follow the sources' published descriptions. Their columns are marked `verified: false` in the manifest until the first fetch confirms them. SECOM's layout is documented by UCI. The self-tests (`python -m unittest tests.test_mfgdata`) cover the checks on synthetic data, the fetcher's license, checksum and zip rules with a fake downloader, and planted FoaMES defects. The defects are a ledger that drops unknown time, a counter that counts resets, and widened SPC limits, and the checks must catch each of them.

## Adding a dataset

Add a manifest entry. Its `status` is `planned` until the license is confirmed on the source page. If the new dataset's `kind` matches an existing one, the adapter already exists. Otherwise, add a loader and a `check_<kind>` function to [mfgdata.py](../foames_bench/mfgdata.py), a synthetic fixture in the same shape, and a self-test that a planted defect fails. Compute expected values from the raw rows, never by calling the FoaMES function under test.
