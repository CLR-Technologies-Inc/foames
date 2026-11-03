# Worked run: the Winter Lab (Yale) publication list

A run of [research-to-code.md](research-to-code.md) against the publications of the Winter Lab at Yale, a chemical and environmental engineering group working on plasma-activated and electrochemical conversion: nitrogen fixation, CO2 and light-alkane upgrading, electrified membranes for nitrate reduction, green ammonia routes. It was chosen as a test set precisely because it is not manufacturing-execution research. The run shows the playbook rejecting every paper on triage and still finding one transfer worth building.

**Sourcing note.** The session that ran this could not reach the lab site, Google Scholar, PubMed, OSTI, Semantic Scholar or the publishers; only web search results were reachable. The list below is therefore the part of the lab's output that search results confirmed, read from abstracts, database records and press coverage, and every number from coverage is marked unverified. A third-party profile counts around 29 papers for the principal investigator; the ones not listed here are the earlier Columbia-era plasma catalysis studies that the same triage would reject for the same reasons. Anyone with access to the lab's page should rerun step 1 for completeness, but the verdicts will not change: the research question of every paper is chemistry and reactor design.

## Summary

| Paper | Venue | Verdict | Residual transfer |
| --- | --- | --- | --- |
| Highly efficient metal-free nitrate reduction enabled by electrified membrane filtration | Nature Water 2024 | No-go | Metric: conversion per pass; data shape: flow-through units count by totaliser |
| Tuning nitrate reduction reaction selectivity via selective adsorption in electrified membranes | Nature Chemical Engineering 2025 | No-go | Metric: selectivity; vocabulary |
| Pathways to a Green Ammonia Future | ACS Energy Letters 2022 | No-go | Loss category: running to the electricity supply, not the order book; metric: specific energy |
| N2 Fixation by Plasma-Activated Processes | Joule 2021 | No-go | Metric: specific energy consumption as the figure plants are compared by |
| Oxygenate Production from Plasma-Activated Reaction of CO2 and Ethane | ACS Energy Letters 2022 | No-go | Metric: selectivity; none beyond the nitrate papers |
| Challenges and opportunities in plasma-activated reactions of CO2 with light alkanes | Journal of Energy Chemistry 2023 | No-go | None beyond the above |
| Plasma-activated co-conversion of N2 and C1 gases towards value-added products | Current Opinion in Green and Sustainable Chemistry 2025 | No-go | None beyond the above |
| Unlocking reaction pathways for CO2 and CO electrocatalytic reduction to C3+ hydrocarbons and oxygenates using plasma activation | Nature Catalysis 2026 | No-go | None beyond the above |
| Plasma-assisted catalysis for oxygenates from CO2 and CH4 (review) | ACS Catalysis 2020 | No-go | None |
| Sizing up hydrogen's hydrological footprint | Nature news feature, December 2023 | Not a lab publication | Listed on the lab's news page; a journalist's feature, skipped |

The residual transfers collapse to one idea that recurs in every paper: **an electrified process is judged by what it consumes per unit of product, and the worst case of that ratio is consumption with no product.** That became the change built below.

## Digests

### Metal-free nitrate reduction by electrified membrane filtration (Nature Water 2024)

Citation: Fan, Y. et al. Highly efficient metal-free nitrate reduction enabled by electrified membrane filtration. Nature Water 2: 684–696 (2024). https://www.nature.com/articles/s44221-024-00278-7
Read from: abstract and press coverage

Method: A nanoporous carbon-nanotube membrane is held at a cathodic potential while water flows through it; nitrate is reduced during a residence time of seconds. Output is nitrate conversion per pass and the product split. Coverage reports about 80 percent conversion in a 15-second filtration and removal below the drinking-water limit in spiked lake water (unverified against the paper).
Triage: data no-go (electrochemistry, water chemistry), question no-go (material and reactor design), actor no-go (a design result), invariants n/a.
Verdict: no-go.

Residual transfer:
- Metric: conversion per pass, the process-industry counterpart of first-pass yield. FoaMES already stores this shape as good and scrap counters; a flow-through unit reports feed and product as totaliser running totals.
- Data shape: a continuous unit has no cycle; its "count" is a flow totaliser. The counter rules already fit (running totals, delta, reset gives zero), which is now stated in `docs/machine-data.md`.

### Selective adsorption in electrified membranes (Nature Chemical Engineering 2025)

Citation: Fan, Y. et al. Tuning nitrate reduction reaction selectivity via selective adsorption in electrified membranes. Nature Chemical Engineering 2: 379–390 (2025). https://doi.org/10.1038/s44286-025-00237-3
Read from: abstract and press coverage

Method: A nitrite-binding ionophore is added to a copper and carbon-nanotube electrified membrane so the intermediate stays near the catalyst until it is reduced to ammonia. Output is ammonia selectivity and conversion from low-concentration nitrate in real waters. Coverage reports about 92 percent ammonia selectivity in about six seconds (unverified).
Triage: all four no-go, as above.
Verdict: no-go.

Residual transfer:
- Metric: selectivity, product of interest over all products. In FoaMES terms this is quality (good over good plus scrap) when by-products are counted as scrap, which the OEE quality factor already computes. Nothing new to build; the vocabulary mapping is noted here for a plant that runs such a unit.

### Pathways to a Green Ammonia Future (ACS Energy Letters 2022)

Citation: Lee, B., Winter, L. R., Lee, H., Lim, D., Lim, H., Elimelech, M. Pathways to a Green Ammonia Future. ACS Energy Letters 7: 3032–3038 (2022). https://doi.org/10.1021/acsenergylett.2c01615
Read from: abstract and search snippets

Method: A perspective comparing routes to low-carbon ammonia: Haber-Bosch fed by electrolytic hydrogen, electrochemical synthesis, plasma-activated synthesis, with the choice of electrolyser and the dependence on renewable electricity.
Triage: data no-go, question no-go (route economics), actor no-go, invariants n/a.
Verdict: no-go.

Residual transfer:
- Loss category: a plant on renewable electricity runs to the supply, not only to the order book. A stop for curtailment or price is planned from the plant's point of view and is neither a breakdown nor no-material. FoaMES already lets a Downtime Reason be marked as counting as planned; a site running such a process adds a reason such as "Energy curtailment" in the Planned category. Configuration only.
- Metric: specific energy per unit of ammonia is the figure the routes are compared by. See the Joule digest.

### N2 Fixation by Plasma-Activated Processes (Joule 2021)

Citation: Winter, L. R., Chen, J. G. N2 Fixation by Plasma-Activated Processes. Joule 5: 300–315 (2021). https://doi.org/10.1016/j.joule.2020.11.009
Read from: abstract, open-access supplementary PDF, database record

Method: A review comparing plasma-activated nitrogen fixation with Haber-Bosch on energy consumption per unit of fixed nitrogen, and setting out what the plasma routes must reach to compete.
Triage: data no-go, question no-go, actor no-go, invariants n/a.
Verdict: no-go.

Residual transfer:
- Metric: **specific energy consumption**, energy per unit of product, is the number the whole field reports and compares by, and the number a plant running an electrified unit will expect beside OEE. The inputs exist in FoaMES already: an energy meter reports a running total exactly as a parts counter does, so its delta over a window is energy consumed, and the good count over the same window is the product. The ratio is a pure function. Its boundary case matters: a window with no product has no rate, and that is precisely the case worth a suggestion, because a plasma or electrolysis unit held at power with no feed is loss that OEE time accounting books as Idle without pricing it. Landing zones: `kpi.py` for the figure, `suggestions.py` for the no-output case, `counters.py` to recognise metered inputs by name.

### Oxygenate production from CO2 and ethane (ACS Energy Letters 2022)

Citation: Winter, L. R., Chen, J. G. et al. Oxygenate Production from Plasma-Activated Reaction of CO2 and Ethane. ACS Energy Letters (2022). https://doi.org/10.1021/acsenergylett.1c02355
Read from: abstract and database record

Method: Non-thermal plasma converts CO2 and ethane at ambient pressure into alcohols, aldehydes, acids and C1 to C5+ hydrocarbons; the abstract reports a maximum total oxygenate selectivity of 12 percent.
Triage: all four no-go.
Verdict: no-go. Residual transfer: selectivity, covered above.

### Plasma-activated reactions of CO2 with light alkanes (Journal of Energy Chemistry 2023)

Citation: Winter, L. R., Chen, J. G. Challenges and opportunities in plasma-activated reactions of CO2 with light alkanes. Journal of Energy Chemistry 84: 424–427 (2023).
Read from: abstract and database record

Method: A perspective on one-step plasma-activated upgrading of CO2 with surplus light alkanes under mild conditions.
Verdict: no-go. Residual transfer: none beyond the above.

### Plasma-activated co-conversion of N2 and C1 gases (Current Opinion in Green and Sustainable Chemistry 2025)

Citation: Winter lab. Plasma-activated co-conversion of N2 and C1 gases towards value-added products. Current Opinion in Green and Sustainable Chemistry 51: 100985 (2025).
Read from: faculty-page listing in search results; abstract not reached

Verdict: no-go on the title and venue alone; a review of reaction chemistry. Residual transfer: none beyond the above.

### Plasma-activated CO2 and CO electroreduction to C3+ products (Nature Catalysis 2026)

Citation: Winter lab. Unlocking reaction pathways for CO2 and CO electrocatalytic reduction to C3+ hydrocarbons and oxygenates using plasma activation. Nature Catalysis (2026). https://www.nature.com/articles/s41929-026-01609-5
Read from: abstract and press coverage

Method: Non-thermal-plasma-activated CO2 or CO is delivered to a copper gas-diffusion electrode so the activated species are not quenched in the electrolyte; coverage reports more than 50 percent more C3+ product (unverified).
Verdict: no-go. Residual transfer: none beyond the above.

### Plasma-assisted catalysis for oxygenates from CO2 and CH4 (ACS Catalysis 2020)

Citation: Winter, L. R., Chen, J. G. et al. ACS Catalysis 10: 2855–2871 (2020).
Read from: database record

Verdict: no-go; a review of catalysis routes. Residual transfer: none.

## What was built

One transfer, three small pure additions and one rule, each with tests, no DocType or Frappe code changed:

| Change | File | What it does |
| --- | --- | --- |
| Metered inputs recognised by name | `foames/foames_mes/counters.py`: `RESOURCE_COUNTERS`, `is_resource_counter`, `resource_totals` | `energy`, `kwh`, `power`, `electricity`, `water`, `gas`, `feed`, `steam`, `air`, `fuel`, exactly or with a unit suffix such as `energy_kwh`, are consumed inputs, not production. They were already stored; now they are named |
| Specific consumption | `foames/foames_mes/kpi.py`: `specific_consumption`, `resource_intensity` | Resource per good unit from a machine's counter deltas; a window with no good output has no rate (None), the counter rule applied to a ratio |
| Consumption with no output | `foames/foames_mes/suggestions.py`: `resource_without_output` | Raises a Yield, Warning suggestion once per machine, resource and day when a metered input advanced over the window and no production was counted, with the consumption, counts and state as evidence |
| Tests | `test_machine_data_logic.py`, `test_kpi.py`, `test_suggestion_rules.py` | Boundary cases: no output, zero consumption, unit suffixes, one finding per resource, rule order |
| Guides | `docs/floor-view.md`, `docs/machine-data.md` | The new rule row; how to send a meter as a counter |

Invariants touched: 3 (a resource delta is a counter delta, nothing is invented; the ratio refuses to divide by nothing), 4 (idle consumption is priced as loss, never as output), 5 (a suggestion with evidence, no action), 7 (every addition is in a pure module).

Test fixture: the papers publish no worked example of the KPI in a form FoaMES can reproduce, so the tests fix the boundaries instead, as step 6 allows.

## What was not built, and why

- **Conversion and selectivity as their own KPIs.** They are first-pass yield and quality with different names; the OEE quality factor already computes them when by-product is counted as scrap. A naming layer would add surface without arithmetic.
- **A baseline for specific consumption**, so a rule could flag drift (energy per unit rising above the machine's norm). That needs a target per machine and resource, which means a field on Machine or a child table, a snapshot change and a site test. It is the natural next step for a plant that wants it, and it is a go on every triage question; it was left out because the papers give no basis for the threshold and the no-output case is the one they all agree on.
- **An "Energy curtailment" Downtime Reason.** Configuration for a site, not code: the Downtime Reason DocType already has a Planned category and a counts-as-planned flag.
- **Anything about the chemistry.** None of it is MES data.
