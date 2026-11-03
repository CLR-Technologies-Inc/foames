# Research-to-code playbook: turning a public paper into a FoaMES change

This playbook is for a coding agent or developer who has a published paper, preprint, thesis or technical article and wants to know whether and how it belongs in FoaMES. It is deliberately strict: most papers do not translate, and the useful result of a run is often a short note that says so and names the one idea that does carry over. The worked run in [research-to-code-example.md](research-to-code-example.md) shows the playbook rejecting a whole publication list and still producing a change.

Read [AGENTS.md](../../AGENTS.md) first. The invariants there are the test every method has to pass.

## What a run produces

| Output | Where it goes |
| --- | --- |
| A digest per paper: citation, method, verdict, residual transfer | A design note; not committed unless it is a worked example under `docs/agents/` |
| For each transferable idea: a pure function with a test, or a rule, report or process-mining analysis | The landing zones in step 5 |
| A sentence in the module docstring or the test naming the source | Next to the code |
| A line in the human-facing guide the change touches | `docs/` |

A run that ends with "no change" is a complete run. Record it so the next person does not repeat it.

## Step 0: sourcing rules

- Read open-access text only: the publisher's open-access page, a preprint server, an institutional repository, a government research database, a lab page. Do not fetch paywalled full text, and do not ask a site to bypass a paywall. If only the abstract and press coverage are reachable, say so in the digest and treat every number from coverage as unverified against the paper.
- Record where each fact was read. A number from a press release or a news article is marked as such.
- Implementing a published method from its description is ordinary engineering. Copying code from a paper's companion repository is third-party code: it needs a compatible license, a credit and the license notice shipped with it, as the conventions in AGENTS.md require. Decide which of the two you are doing before writing anything.
- If the session cannot reach the hosts the papers live on, stop fetching after the first failures, work from what search results give, and say in the digest which hosts were unreachable.

## Step 1: record the citation

For every paper, before reading further:

```
Title:
Authors:
Venue, volume, pages, year:
DOI or URL:
Read from: (open-access full text | abstract | press coverage | search snippet)
```

## Step 2: triage, go or no-go

Answer four questions in one line each. The answers decide whether the paper gets a full digest or a one-paragraph one.

| Question | Go when | No-go when |
| --- | --- | --- |
| **Data.** Does the method consume something FoaMES records? | State events, counter running totals, downtime records with reasons, measurements, the OEE ledger, the process event log (case, activity, lifecycle, resource, objects), ERP references | Sensor waveforms, spectra, chemistry, images, labelled failure histories, anything FoaMES does not hold and no gateway sends |
| **Question.** Does it answer a question a plant asks of an MES? | Why is this machine down, where is the loss, how much did we make, what path did the order take, what should a person look at next | How to design a catalyst, a reactor, a material, a control law, a market |
| **Actor.** Can the result be an Agent Suggestion with evidence, a report, or a KPI? | Yes | It only makes sense as an automatic action, a setpoint change, a command to a machine |
| **Invariants.** Does the method respect the AGENTS.md invariants as published? | Yes, or with a stated restriction | It infers output or run time from gaps in data, it needs a Link to an ERP DocType, it posts to an ERP without idempotency |

Four go answers: full digest, continue at step 3. Any no-go: write the one-paragraph digest, then look for **residual transfer** before closing the paper. Residual transfer is the part of a no-go paper that still carries over, and it is almost always one of these:

- **A metric.** The figure the field compares its results by (specific energy, conversion, selectivity, first-pass yield, takt adherence). If plants running such a process would want it beside OEE, it is a candidate for `kpi.py` and a rule.
- **A loss category.** A reason for stopping or running badly that the Downtime Reason list or the OEE notes do not name yet.
- **A data shape.** A kind of signal the process emits (a flow totaliser, an energy meter, a batch boundary) and how it maps to Machine Event types.
- **A vocabulary.** Terms a user from that industry will expect to see on the Floor View or in a report.

Residual transfer is config or a small pure function with a test, never a new module. If nothing carries over, say "none" and stop.

## Step 3: extract the method

For a paper that passed triage, write down, from the paper and not from memory:

- **Inputs**, with units and sampling: what the method needs, how often, over what window.
- **Outputs**, with units: what it produces and how the authors interpret the number.
- **Assumptions**: stationarity, complete data, known cycle times, a planned schedule, labelled history. Each one is a place the method can break on real floor data.
- **The worked example**: the paper's own table, figure or numeric example, so the test in step 6 can reproduce one published number. A method without a reproducible example is implemented as a best effort and the test says so.
- **What the authors say it does not do**: limitations sections are the most useful paragraph of a paper for this purpose.

## Step 4: map to FoaMES data

| The paper needs | FoaMES has | Module |
| --- | --- | --- |
| Machine state over time | `Machine Event` of type State; intervals in `ledger_from_states` | `foames_mes/oee.py` |
| Production counts | Counter deltas per counter name; good and scrap by name, metered inputs by name | `foames_mes/counters.py` |
| Stops with causes | `Downtime Record` with `Downtime Reason` (category, counts as planned) | `foames_mes/doctype/downtime_record` |
| Time accounting | The exhaustive `TimeLedger`: run, planned downtime, unplanned downtime, unknown | `foames_mes/oee.py` |
| Process measurements | `Machine Event` of type Measurement (name, value) | `foames_mes/doctype/machine_event` |
| Event logs with cases and activities | The process event log, XES and OCEL export, directly-follows graph, variants, conformance | `foames_process_mining/` |
| Order, job, item, batch identity | `External Reference` resolved by an adapter; never a Link to the ERP | `foames_kernel/`, `foames_adapters/` |
| Everything the floor shows | The floor snapshot dict | `foames_mes/floor.py` |

If the method needs something not in this table, it needs an extension app, not a change to FoaMES core: another app records the data and adds it to the snapshot through `foames_floor_snapshot_extensions`, then adds its rule through `foames_suggestion_rules`.

## Step 5: check the invariants and choose the landing zone

Go through the nine invariants in AGENTS.md and write one line per invariant the method touches. The ones papers trip over most:

- **Counters never invent production (3).** A method that smooths, interpolates or extrapolates counts is applied to the deltas FoaMES already stored, and never writes a count back.
- **Unknown time is loss (4).** A method that estimates run time or output across a gap in events cannot be used to fill the ledger. It can raise a suggestion that says the gap looks like run time, with evidence, and a person decides.
- **Agents suggest; people act (5).** Any output that reads as an action becomes an Agent Suggestion with its evidence dict. No setpoints, no commands, no ERP postings.
- **Pure logic stays pure (7).** The arithmetic goes in a module that imports nothing from Frappe, next to `oee.py`, `kpi.py`, `suggestions.py` or the process-mining core, and the DocType or task that calls it stays thin.

Then choose exactly one landing zone:

| Landing zone | Choose it when | Example |
| --- | --- | --- |
| Pure function in `kpi.py`, `oee.py`, `counters.py` or the process-mining core | The result is a number or a table computed from data FoaMES already has | A new reliability estimator, a specific-consumption KPI |
| Rule in `suggestions.py` or a hook rule | The result is a finding a person should look at, computable from the floor snapshot | A machine consuming energy with no output |
| Script report under `foames_mes/report` | The result is a table or chart over history, with filters | A loss breakdown by a new taxonomy |
| Process-mining analysis in `discovery.py` or `conformance.py` | The input is the event log | A new discovery or conformance algorithm |
| Scheduled job in `tasks.py` | The method must run over a window periodically and store something | A daily period of a new kind |
| Configuration only | The transfer is a Downtime Reason, a counter name, a mapping | A planned reason for energy curtailment |
| Extension app | The data is not in FoaMES core | Vibration analysis on a sensor stream |
| Documentation only | The transfer is vocabulary or guidance | A paragraph in a guide |

## Step 6: test first, from the paper

Write the unit test before the function, with the paper's worked example as the fixture. The test reproduces one published number, within the precision the paper gives. If the paper gives none, the test fixes the behaviour at the boundaries the invariants care about: nothing produced, nothing known, a reset, a gap. Run the pure tests without a site:

```bash
python -m unittest foames.foames_mes.test_kpi foames.foames_mes.test_suggestion_rules foames.foames_process_mining.test_process_mining_logic
```

Then wire the function thinly to its DocType, rule list, report or task, and run the site suite on the Docker bench if the wiring touched Frappe code.

## Step 7: cite and document

- The module docstring or the function docstring says what the figure is and, where a paper defined it, which paper.
- The human-facing guide for the part changed gains a row or a sentence: `floor-view.md` for a rule, `oee.md` or `dashboards.md` for a KPI or report, `machine-data.md` for a data shape, `process-mining.md` for an analysis.
- `AGENTS.md` changes only when an invariant, a hook, a repository path or a test command changed.

## The digest template

```
## <Short title> (<venue> <year>)

Citation: <authors>. <title>. <venue> <volume>: <pages> (<year>). <DOI or URL>
Read from: <open-access full text | abstract | press coverage | search snippet>

Method: <two sentences: what goes in, what comes out>
Triage: data <go|no-go>, question <go|no-go>, actor <go|no-go>, invariants <go|no-go>
Verdict: <go | no-go>

Residual transfer (no-go only): <metric | loss category | data shape | vocabulary | none>, one line each

Mapping (go only): <paper input -> FoaMES field or module>, one line per input
Invariants touched: <number: how it is kept>
Landing zone: <one of the table>
Test fixture: <the published number the test reproduces, or "none published">
Built: <file paths> | Not built because: <reason>
```

## What this playbook is not

It is not a literature-review method and it does not rank papers. It does not make FoaMES a research platform: a method that needs its own data model belongs in an app built on FoaMES, which is what the hooks are for. And it does not override judgement: a paper that passes every question can still be left out because the plant question it answers is already answered well enough by what exists.
