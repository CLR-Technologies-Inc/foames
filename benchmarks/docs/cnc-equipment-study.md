# CNC equipment study: a lathe and a milling fleet

This study is part of the [manufacturing-data validation track](manufacturing-data.md). It replays two public machining datasets through FoaMES and asks two questions:

1. **Does FoaMES compute the right numbers on real machine signals?** I-MR control limits and beyond-limit signals per sensor feature, energy per part through the specific-consumption KPI, and the Equipment Complexity Level (ECL) profile FoaMES gives each machine. These are graded checks.
2. **What would an equipment agent tied to these machines be able to see, and what is it allowed to say?** Which sensor separates which process deviation, how often limits raise false alarms, and whether one machine's limits carry over to another of the same kind. These are reported metrics, never graded, because an out-of-control point is not a confirmed defect.

```bash
cd benchmarks
python -m foames_bench data validate --synthetic --datasets cnc-turning-xquality cnc-milling-vibration
python -m foames_bench data fetch --datasets cnc-turning-xquality cnc-milling-vibration    # needs Kaggle credentials
python -m foames_bench data validate --stage full --datasets cnc-turning-xquality cnc-milling-vibration --out runs/cnc
```

Without Kaggle credentials, download each dataset in a browser, save the archives as `<cache>/_inbox/cnc-turning-xquality.zip` and `<cache>/_inbox/cnc-milling-vibration.zip`, and import both before you validate:

```bash
python -m foames_bench data import cnc-turning-xquality
python -m foames_bench data import cnc-milling-vibration
```

To study only one machine type, import that dataset and pass only its id to `data validate --datasets`.

## The equipment

| Dataset | Machines | Data | Labels | ECL class |
| --- | --- | --- | --- | --- |
| `cnc-turning-xquality` | One screw-machining CNC lathe with a bar feeder | 62 parts, two operations (OP120 roughing about 6 s, OP130 finishing about 20 s), 12 channels each: spindle power, cutting forces Fx, Fy and Fz, three accelerometers and a microphone, raw and running RMS, decimated to 1024 points | Per part: normal, or one of three known deviations: feedrate at 80 percent (10 parts), 316L instead of 303 stainless (5 parts), wrong tools mounted (4 parts) | `cnc-lathe`, ECL 3 |
| `cnc-milling-vibration` | Three brownfield CNC milling machines | 15 operations each, tri-axial vibration at 2 kHz, recorded in six timeframes from October 2018 to August 2021, about 1 GB as CSV | Per recording: good or bad | `cnc-machining-centre`, ECL 3 |

Both ratings come from the public [ECL list](https://github.com/CLR-Technologies-Inc/equipment-complexity-levels). They are `ai-initial` drafts, so the report marks them as drafts until a person reviews them, the same way the equipment agent does.

## Method

**Lathe.** Each part becomes one row of features: for every operation and channel, the signal's mean, peak and RMS, the operation's duration, and its spindle energy (power integrated over time). Parts are taken in production order (part 020 to 081). Limits come from the first 20 normal parts. Every later part is judged against them, including the two normal parts made after the abnormal batches (076 and 077), which act as a check on false alarms. The feature budget of a stage (5, 20 or 60) is spread over channels and both operations: means first, then peaks, then RMS.

**Milling fleet.** Each recording becomes per-axis RMS and peak acceleration, mean-removed, and a duration. Within each machine and operation, limits come from the earliest 30 percent of readable good recordings (at least eight). Every recording made after the last baseline recording, good or bad, is judged against them in time order; a group is left out only when it has fewer than eight readable good recordings or nothing after its baseline. A stage's row limit becomes a file budget spread evenly over machines and operations: the baseline is still the earliest readable good recordings (shortened to at least eight), and the budget thins the recordings judged after it.

**Graded checks**, each compared with a value computed inside the benchmark from the raw signals:

| Check | What FoaMES must get right |
| --- | --- |
| `spc/imr-limits` | Centre line, UCL, LCL and within sigma of every chart, from FoaMES's `spc.imr_chart` |
| `spc/beyond-limit-signals` | The points FoaMES flags as beyond the limits (Nelson rule 1) |
| `spc/no-missing-values-charted` | No NaN reaches a chart |
| `kpi/energy-per-part` | Spindle energy per normal part, per operation, from `kpi.specific_consumption`; and no rate at all when nothing was produced (lathe only) |
| `ecl/profile-matches-recommended-floors` | For each machine, the minimum model tier and the eligibility of `oss`, `baseline` and `frontier` agents from `ecl.profile` and `ecl.eligibility`, against the level floors in [recommendations.json](../data/recommendations.json) |
| `ecl/fleet-level` | A line's ECL is that of its most complex member (`ecl.group_ecl`) |

The self-tests plant defects (widened limits, dropped signals, an energy rate with no output, a drifted ECL floor) and the checks must catch each.

**Reported study** (in `manufacturing-data.md` under "Equipment study"):

- Lathe: parts flagged per batch, part recall and the false-alarm rate on later normal parts; for each deviation, the five features that separate it most from the baseline (Cohen's d) and how many of its parts each one flagged; spindle energy per operation per batch, as a change from the baseline.
- Milling fleet: per machine, bad recordings flagged and good recordings flagged (false alarms); and **transfer**, the share of a mill's good recordings flagged by limits learned on another mill for the same operation. When transfer raises far more alarms than a mill's own limits do, the report says to set limits per machine rather than per machine model.
- Both: an equipment table with each machine's ECL class, level, minimum agent tier, oversight, and which tiers may advise on it.

## How this connects to the equipment agent

The [equipment agent](../../docs/agents/equipment-agent/SKILL.md) may advise on a machine only after it is rated, and only at or above its level's minimum tier. Both machine types here are ECL 3: a `baseline` tier agent or better may suggest one action, and a person acts. The study is evidence for what that suggestion can rest on:

- The deviation table shows which signals an agent should quote for a suspected feedrate, material or tooling problem on a lathe. It is evidence for an engineer, not a diagnosis rule.
- The false-alarm rate shows how many charted features a site can watch before alarms stop meaning anything. Every extra feature adds false alarms.
- Transfer shows whether a new machine can borrow limits from a sister machine, or needs its own baseline first.

## Caveats

- The lathe release is decimated to 1024 points per signal whatever the operation's length, so spindle energy is good for comparing parts, not for an energy audit, and frequency analysis is out of scope.
- The lathe data has one acquisition per operation per part, from one machine and one tool. Its deviations are planted experiments, not production faults.
- Column and file names follow the data cards; the manifest marks them `verified: false` until a real fetch confirms them. An adapter that finds something else stops and lists what it found.
- The milling recordings are labelled per recording, not per cause, so the fleet study reports detection only.

## Sources and licenses

| Dataset | License | Evidence | Cite |
| --- | --- | --- | --- |
| XQuality CNC turning | CC BY 4.0 | [Kaggle dataset page](https://www.kaggle.com/datasets/cetimai/xquality-cnc-turning-data), license field and data card, checked 2026-11-21; the fetch also checks the license Kaggle states at download time | CETIM, Senlis, France. XQuality - CNC Turning Data [Data set]. Kaggle. https://www.kaggle.com/datasets/cetimai/xquality-cnc-turning-data |
| CNC milling vibration | CC BY 4.0 (data; the upstream code is BSD-3-Clause) | [Upstream repository](https://github.com/boschresearch/CNC_Machining) and the [Kaggle CSV conversion](https://www.kaggle.com/datasets/maximilianfellhuber/cnc-machining-data), checked 2026-11-21 | Tnani, M.-A.; Feil, M.; Diepold, K. Smart Data Collection System for Brownfield CNC Milling Machines: A New Benchmark Dataset for Data-Driven Machine Monitoring. Procedia CIRP 2022, 107, 131-136 |

Nothing is vendored: both datasets are downloaded into the local cache. CC BY 4.0 permits redistribution with credit, but the track keeps raw data out of the repository regardless. If you publish results, cite the dataset, link the license, and say that FoaMES derived features from the signals.
