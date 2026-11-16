# Sector case studies

One benchmark task per major industrial sector, each built on an improvement that a US government document or record reports. The agent gets a week of FoaMES machine events before the change and a week after it, and must measure the result the way FoaMES's rules require, set it against the document's claim, and write the case study up in the shape of [docs/case-studies/_template.md](../../docs/case-studies/_template.md).

Run them with `--suite sector-case-study`:

```bash
foames-bench list --suite sector-case-study
foames-bench validate --suite sector-case-study
foames-bench run --suite sector-case-study --agents claude-code-baseline --reps 1 --cap-usd 50
```

`foames-bench run` without `--suite` or `--tasks` runs only the core tasks, so adding this suite does not make an existing paid run larger. Twenty-nine tasks at the task budget of $1.50 are $43.50 per agent per repetition; that is a scoring reference, not a price.

## What every task asks

The situation differs by sector; the job is the same, so results can be compared across sectors:

1. Write `analysis/case_study.py`, which reads `data/case/case.json` and `data/case/events.csv` (a Machine Event export in arrival order) and writes `case_study.json`: for each window, the planned minutes by state, good and scrap output, energy, availability, performance, quality, OEE, specific energy, good output per planned hour and changeovers; then the annualised energy saving and a `claim_check` with the measured value, its ratio to the claim and a verdict.
2. Write `CASE_STUDY.md`, labelled Illustrative, citing the source by its URL.

The full specification is in [tasks/_sector-case-study/prompt.md](../tasks/_sector-case-study/prompt.md); each task's own `prompt.md` gives the plant's situation and the source.

## How it is scored

| Group | Checks |
| --- | --- |
| Functional (hidden) | Every number in `case_study.json` against an independent computation ([_mv_reference.py](../tasks/_sector-case-study/hidden/_mv_reference.py)) on data rebuilt from the task's hidden parameters, so editing `data/` gains nothing; the write-up cites the source, says Illustrative and states the verdict |
| Invariant (hidden) | The agent's script, run on four new exports it has not seen: a gateway silent for six hours (time beyond `mark_unknown_after_minutes` must be Unknown, which is loss), a PLC restart (adds nothing), late and repeated readings (add nothing), an energy meter that rolls over (unwrapped with the machine's rollover). The ledger must account for every planned minute, the committed JSON must regenerate from the script, and `data/` and `foames/` must be unchanged |
| Rubric | `CASE_STUDY.md` has the template's sections and covers claim against measurement, unknown time as loss, counter rules, confounders such as production volume, the government source, and the anonymised plant ([rubric.json](../tasks/_sector-case-study/rubric.json)) |
| Regression | FoaMES's own counter and OEE tests, from the pristine checkout |

The reference solution ([solution_case_study.py](../tasks/_sector-case-study/solution_case_study.py)) uses `foames.foames_mes.counters.counter_delta` and `foames.foames_mes.oee.compute_oee`, and is a separate implementation from the hidden one, so each checks the other. `foames-bench validate` shows the reference passing and a no-op failing on every sector. Four plausible mistakes each fail every sector: counting the first reading after a PLC restart as production, comparing a late reading with the previous arrival instead of the latest timestamp, trusting a state through a network gap, and ignoring the meter's rollover.

## The sectors and their sources

Sectors follow NAICS 2022: the manufacturing subsectors 311 to 339, plus oil and gas extraction and mining (21) and utilities (22). Each task's `hidden/sector.json` holds the full citation and the claim.

| Task | NAICS | Sector | Source (US government) | Claim checked | Verdict in the data |
| --- | --- | --- | --- | --- | --- |
| `sector-211-oil-gas` | 211 | Oil and gas extraction (gas wells) | EPA Natural Gas STAR, *Lessons Learned: Installing Plunger Lift Systems in Gas Wells* (2006), [PDF](https://19january2017snapshot.epa.gov/sites/production/files/2016-06/documents/ll_plungerlift.pdf) | production ratio 1.545 (167 to 258 Mcf/d) | supported |
| `sector-212-mining` | 212 | Coal preparation | DOE Office of Industrial Technologies, *Optimized Pump Systems Save Coal Preparation Plant Money and Energy* (1999), [PDF](https://www.energy.gov/sites/prod/files/2014/05/f16/optimized_coal_plant_pump.pdf) | 87,184 kWh/yr | supported |
| `sector-2213-wastewater` | 2213 | Municipal wastewater | DOE ITP, *Process Optimization Saves Energy at Metropolitan Syracuse Wastewater Treatment Plant*, DOE/GO-102005-2136, [OSTI](https://www.osti.gov/servlets/purl/1218544) | 2.81 million kWh/yr | supported |
| `sector-311-food` | 311 | Food (nutritional powders) | DOE OIT, *Compressed Air System Renovation Project Improves Production at a Food Processing Facility*, DOE/GO-102001-1330, [PDF](https://nrel.gov/docs/fy01osti/30231.pdf) | 2,542,000 kWh/yr | supported |
| `sector-312-beverage` | 312 | Beverage (bottling) | DOE AMO Industrial Assessment Centers, case study BS0001 (Boise State IAC), [PDF](https://iac.university/case_studies/BS0001CaseStudy.pdf) | 320,526 kWh/yr (recommended) | not supported |
| `sector-313-textile-mills` | 313 | Textile mills | DOE AMO, *Improving Ventilation System Energy Efficiency in a Textile Plant*, [PDF](https://www.energy.gov/sites/prod/files/2014/05/f16/case_study_ventilation_textile.pdf) | 1,579,400 kWh/yr | supported |
| `sector-314-carpet` | 314 | Textile products (carpet) | DOE ITP, *Save Energy Now Assessment Helps Expand Energy Management Program*, DOE/GO-102008-2537, [PDF](https://www1.eere.energy.gov/manufacturing/tech_assistance/pdfs/42460.pdf) | 93,000 MMBtu/yr | supported |
| `sector-315-apparel` | 315 | Apparel (cut and sew) | DOE Industrial Assessment Centers, assessment record UK1905 (University of Kentucky IAC, 2019), [record](https://itac.university/assessment/UK1905) | 251,963 kWh/yr (implemented) | supported |
| `sector-316-footwear` | 316 | Leather and allied products (footwear) | DOE Industrial Assessment Centers, assessment record GT0630 (Georgia Tech IAC, 1997), [record](https://itac.university/assessment/GT0630) | 217,761 kWh/yr (implemented) | supported |
| `sector-321-wood` | 321 | Wood products (sawmill) | DOE Industrial Assessment Centers, assessment record LT0121 (Louisiana Tech IAC, 1988), [record](https://itac.university/assessment/LT0121) | 33,705 kWh/yr (recommended, none implemented) | not supported |
| `sector-322-paper` | 322 | Paper (coated paper mill) | DOE ITP, *Significant Natural Gas Savings Achieved Following Save Energy Now Assessment*, DOE/GO-102008-2525, [PDF](https://www1.eere.energy.gov/manufacturing/tech_assistance/pdfs/42352.pdf) | 58,200 MMBtu/yr | supported |
| `sector-323-printing` | 323 | Printing (checks) | DOE OIT, *Compressed Air Project Improves Efficiency and Production at Harland Publishing Facility*, DOE/GO-102002-1546, [PDF](https://docs.nrel.gov/docs/fy02osti/31713.pdf) | 2.9 million kWh/yr | supported |
| `sector-324-refining` | 324 | Petroleum refining | DOE ITP, *Refinery Identifies $4.4 Million in Annual Savings by Using Process Simulation Models*, DOE/GO-102004-1759, [PDF](https://nrel.gov/docs/fy04osti/34403.pdf) | 25,528 MMBtu/yr | supported |
| `sector-325-chemicals` | 325 | Chemicals (petrochemicals) | DOE ITP, *Assessment Leads to Steam System Energy Savings in a Petrochemical Plant*, DOE/GO-102007-2467, [PDF](https://www1.eere.energy.gov/manufacturing/tech_assistance/pdfs/42009.pdf) | 272,000 MMBtu/yr | supported |
| `sector-3254-pharmaceuticals` | 3254 | Pharmaceutical preparations | DOE Industrial Assessment Centers, assessment record MI0445 (University of Miami IAC, 2024), [record](https://itac.university/assessment/MI0445) | 2,207,693 kWh/yr (implemented) | supported |
| `sector-326-plastics` | 326 | Plastics (blow moulding) | DOE AMO Industrial Assessment Centers, case study UA0108 (University of Alabama IAC), [PDF](https://iac.university/case_studies/UA0108CaseStudy.pdf) | 361,081 kWh/yr | supported |
| `sector-3272-glass` | 3272 | Glass (automotive glass) | DOE OIT, *Compressed Air System Upgrade Improves Production at an Automotive Glass Plant*, DOE/GO-102003-1657, [PDF](https://nrel.gov/docs/fy03osti/33096.pdf) | 7.9 million kWh/yr | supported |
| `sector-3273-cement` | 3273 | Cement | DOE OIT, *Fan System Optimization Improves Production and Saves Energy at Ash Grove Cement Plant*, DOE/GO-102002-1599, [PDF](https://nrel.gov/docs/fy02osti/32107.pdf) | 175,000 kWh/yr | supported |
| `sector-331-aluminum` | 331 | Primary metals (aluminum) | DOE ITP, *Energy Assessment Helps Kaiser Aluminum Save Energy and Improve Productivity*, DOE/GO-102008-2561, [PDF](https://www1.eere.energy.gov/manufacturing/tech_assistance/pdfs/42782.pdf) | 45,000 MMBtu/yr | supported |
| `sector-3315-foundry` | 3315 | Metal casting | DOE ITP, *Foundry Saves Energy with Compressed Air System Retrofit*, DOE/GO-102004-1726, [PDF](https://nrel.gov/docs/fy04osti/33903.pdf) | 242,000 kWh/yr | supported |
| `sector-332-forging` | 332 | Fabricated metals (forging) | DOE ITP, *Compressed Air System Optimization Project Saves Energy and Improves Production at Forging Plant*, DOE/GO-102003-1654, [OSTI](https://www.osti.gov/biblio/15003882) | 820,000 kWh/yr | supported |
| `sector-332-machine-shop` | 332 | Fabricated metals (machining) | NIST MEP, *Success Story: Improvement Effort Reduces Changeover Time* (2018), [page](https://www.nist.gov/blogs/manufacturing-innovation-blog/success-story-improvement-effort-reduces-changeover-time) | 70 % shorter changeover | supported |
| `sector-333-machinery` | 333 | Machinery (diesel engines) | DOE AMO, *SEP Measurement & Verification Case Study Webinar* (2015), [slides](https://www.energy.gov/sites/prod/files/2015/12/f27/Cummins%20MV%20Slides%20r3_17Nov2016.pdf) | 12.6 % lower energy per unit (new kind `specific_energy_reduction`) | supported |
| `sector-3344-semiconductors` | 3344 | Semiconductors | DOE ITP, *Freescale Semiconductor Successfully Implements an Energy Management System*, DOE/EE-0579, [PDF](https://www1.eere.energy.gov/manufacturing/tech_assistance/pdfs/freescale_case_study.pdf) | 2.55 million kWh/yr | not supported (the week-to-week noise is larger than the saving) |
| `sector-335-electrical-equipment` | 335 | Electrical equipment (switchgear) | DOE AMO Industrial Assessment Centers, case study TT0052 (Tennessee Tech IAC), [PDF](https://iac.university/case_studies/TT0052CaseStudy.pdf) | 201,360 kWh/yr (estimate) | not supported |
| `sector-3361-motor-vehicles` | 3361 | Motor vehicle assembly | DOE ITP, *Save Energy Now Assessment Enables a Vehicle Assembly Complex to Achieve Significant Natural Gas Savings*, DOE/GO-102008-2485, [PDF](https://nrel.gov/docs/fy08osti/42136.pdf) | 70,000 MMBtu/yr | supported |
| `sector-3364-aerospace` | 3364 | Aerospace parts | NIST MEP, *Total Productive Maintenance Reduces Equipment Downtime and Lost Capacity* (2022), [page](https://www.nist.gov/mep/successstories/2022/total-productive-maintenance-reduces-equipment-downtime-and-lost-capacity) | OEE 45 % after | supported |
| `sector-337-furniture` | 337 | Furniture | NIST MEP, *Lean Is A "Game-Changer," Shortening Furniture Production Time From Days to Hours*, [page](https://www.nist.gov/mep/successstories/2024/lean-game-changer-shortening-furniture-production-time-days-hours) | 20-minute lead time | not measurable (FoaMES events carry no lead time) |
| `sector-3391-medical-devices` | 3391 | Medical devices | NIST MEP, *Learning, Doubling Throughput, and Having Fun*, [page](https://www.nist.gov/mep/successstories/2025/learning-doubling-throughput-and-having-fun) | throughput doubled | supported |

The verdict column is what the illustrative data was built to show, not a finding about the plant in the source. Each verdict follows from the data: the after week's energy use is calibrated so the measured saving lands at a stated share of the claim (`target_ratio` in `sector.json`), and the operating parameters decide the OEE, changeover and throughput results.

### Sources searched for the second batch

Each of the six sectors that the first batch left open now has a task. The second batch (issue #74) searched further:

- **USDA** (Forest Products Laboratory, rural energy programmes): kiln and sawmill guides, but no dated plant result FoaMES events could check. The wood products task uses a DOE Industrial Assessment Center record instead.
- **Department of Commerce** (NIST beyond MEP, ITA, EDA): no plant-level result for the open sectors beyond the MEP stories already used.
- **FDA** (advanced and continuous manufacturing): programme figures and approval timelines, not a plant's before and after. The pharmaceutical task uses an IAC record.
- **EPA**: Natural Gas STAR lessons learned papers give partner well data; the oil and gas task uses one.
- **European sources**: the European Commission's and CORDIS's legal notices allow reuse of EU-owned editorial content under CC BY 4.0 (Commission Decision 2011/833/EU) with credit and an indication of changes, except third-party works, logos and names, and material from grant beneficiaries, which follows the grant's terms. The CORDIS project pages read (kiln control, particleboard, heat pump drying, leather finishing) give project targets or percentages without a plant baseline. A LIFE project page on tanning (LIFE13 ENV/IT/000840) is marked "All rights reserved", and a European Cluster Collaboration Platform story on a sawmill is built from the company's own material, with reuse terms that could not be retrieved, so neither is used. A European source that meets the rules is still welcome for any sector; a percentage claim fits the `specific_energy_reduction` kind.

IAC assessment records are entries in DOE's Industrial Assessment Center database, written by the university centres from their site visits. Their savings are the centre's estimates, and the record marks which recommendations the plant implemented; the tasks check the implemented total (or, for LT0121, the recommended total, since none was implemented).

## Rules for sources

- **US government works first.** DOE (EERE, the Office of Industrial Technologies, the Industrial Technologies Program, the Advanced Manufacturing Office, the Industrial Assessment Center database), EPA and NIST MEP publications. A non-US public source is used only when its terms allow reuse, and it is credited as they require. Works of the US government are not subject to copyright in the US (17 U.S.C. 105). DOE case studies printed by a national laboratory for DOE, and the Industrial Assessment Center case studies written by DOE-funded university centres and published by DOE's Advanced Manufacturing Office, may not be strictly federal works; for them, as for all, the tasks take only facts (figures, units, the kind of change), which are not copyrightable, and cite the document.
- **No third-party material.** No text is copied beyond short factual statements of the claim, and no image, logo or chart. Several sources carry photos credited to the company or to another organisation (for example the IAC case studies and DOE/EE-0579); none is reproduced.
- **The plant is Plant A.** Prompts, data and write-ups describe an anonymised, illustrative plant. Companies are named only in the citation of the source; a hidden test and a harness test check that the prompt does not name them.
- **Claims are claims.** Where a source is internally inconsistent (cost and payback in DOE/GO-102001-1330, the unreconciled total in DOE/GO-102008-2537, the percentage in the coal pump fact sheet, the dollar figure in DOE/GO-102004-1759, the 2.9 million kWh given only in the summary of DOE/GO-102002-1546, the plunger lift table's footnote that calls 1,348 Mcf/d both the initial production and the increase), the task states the figure it checks and the prompt or claim text notes the inconsistency rather than resolving it.
- **Public code and invented data.** The tasks use only FoaMES's public `main` and generated events, like every benchmark task ([writing-tasks.md](writing-tasks.md#rules)).

## Adding a sector

1. Make `tasks/sector-<naics>-<name>/` with `task.json` (copy one, change `id` and `title`), a `prompt.md` with the plant's situation and the source's URL, and `hidden/sector.json`.
2. In `sector.json`, set the source, the claim (`kind` is `annual_energy_saving`, `specific_energy_reduction`, `oee_after`, `setup_reduction`, `throughput_ratio`, or any other kind for a claim FoaMES events cannot measure), the windows, planned hours and units, the line's and meter's parameters for each window, the planted conditions (`traps`), and for an energy claim (`annual_energy_saving` or `specific_energy_reduction`) the `target_ratio`.
3. Run `foames-bench validate --tasks <id>` and `python -m unittest discover tests` from `benchmarks/`.
