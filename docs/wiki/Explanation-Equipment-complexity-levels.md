# Equipment complexity levels (ECL)

Technology readiness levels (TRL) tell a researcher or a student how mature a method is. A manufacturer usually has a different question: *how complex is the machine the agent is being tied to, and is any model good enough to advise on it?* The Equipment Complexity Level (ECL) answers that question. It is a FoaMES concept. Its 1 to 5 scale abstracts what a piece of equipment does into the kind of model needed to reason about it.

Two examples anchor the scale. A torque wrench sits at ECL 1. Its physics is basic (torque is force times lever arm, and a click or a reading at a set point), so a small language model, such as a Phi-class model, is usually enough. A lithography scanner sits at ECL 5. It is made of many tightly coupled subsystems governed by proprietary physics models. Reasoning about it may need a mixture-of-experts frontier model that has not been built yet. Until then, the answer is **Expert Team Required**.

The top two levels differ in *who* must stay in charge. At ECL 4, one human expert is enough. A photomask (lithography plate) is an example: a single mask specialist can judge an agent's suggestion about writing or inspecting it, so the result is **Human Expert Recommended**. At ECL 5, no single person covers the whole system. Lithography itself spans optics, stages, metrology, resist chemistry and the process, so a distributed team of experts decides together, and the result is **Expert Team Required**.

## What ECL is built from

As far as we found, no single standard rates equipment by how capable an AI model must be to work with it. Industry does, however, already classify equipment by complexity, by embedded software and by how decisions are shared between people and automation. ECL is a mapping onto that existing language, not a replacement for it:

| Existing classification | What it classifies | How ECL uses it |
| --- | --- | --- |
| USP <1058> instrument groups A, B, C ([overview](https://www.agilent.com/cs/library/whitepaper/public/5994-9418EN_led_1058_whitepaper.pdf)) | Laboratory apparatus with no measurement (A), instruments that give measured values (B), and computerized systems (C) | The closest established complexity classes. ECL 1 is A or B, ECL 2 is B, and ECL 3 to 5 are C |
| IEC 61508-2 Type A and Type B elements ([exida note](https://www.exida.com/Company/News/new_whitepaper_n_iec_61508_2010_definitions_regarding_minimum_hardware)) | Whether an element's failure modes are well defined and its behaviour under fault can be completely determined (Type A), or not (Type B) | Type A equipment can be reasoned about from first principles. Type B equipment needs more capable models, more data, or both |
| GAMP 5 software categories 1, 3, 4, 5 ([summary](https://qbdgroup.com/md/en/blog/gamp-categories)) | Infrastructure, non-configured, configured and custom software | The embedded software an agent has to understand grows from none (ECL 1) to custom (ECL 5) |
| ISA-95 / IEC 62264 and ISA-88 equipment hierarchy ([ISA-95](https://www.isa.org/standards-and-publications/isa-standards/isa-95-standard)) | Where equipment sits: enterprise, site, area, work centre, work unit, equipment module, control module | ECL rates one item of equipment wherever it sits. A whole line takes the ECL of its most complex member that the agent is tied to |
| ISO 14224 equipment taxonomy and criticality ([ISO 14224](https://www.iso.org/standard/64076.html)) | Equipment class, subunit and maintainable item, and a separate criticality ranking | ECL is complexity, not criticality. A simple valve can be critical. Use both, and keep criticality in your maintenance ranking |
| Levels of automation, Sheridan and Verplanck, refined by Parasuraman, Sheridan and Wickens ([2000 paper](https://doi.org/10.1109/3468.844354)) | Ten levels, from "the computer offers no assistance" to "the computer acts entirely on its own" | Sets the agent's role at each ECL. FoaMES never goes above level 4 (suggest one action, a person decides), and lowers it as ECL rises |
| TRL ([NASA](https://esto.nasa.gov/trl)) and MRL ([DoD](https://acqnotes.com/acqnote/tasks/manufacturing-readiness-level)) | How mature a technology, or a manufacturing process, is | Different axes. TRL and process complexity choose the starting tier, and ECL can only raise it |
| SAE J3016 driving automation levels ([SAE](https://saemobilus.sae.org/content/j3016_202104)) and FDA device classes I to III ([FDA](https://www.fda.gov/medical-devices/overview-device-regulation/classify-your-medical-device)) | Vehicle autonomy, and device risk | Analogies only. They show that a short numbered scale is easy to adopt. Neither one measures equipment complexity |

## The levels

| ECL | Equipment | Examples | USP <1058> | IEC 61508 | GAMP 5 | Minimum model tier | Agent role (level of automation) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Simple tool or apparatus | Torque wrench, hand gauge, timer, stirrer, scale | A or B | Type A | None or Category 1 | Open weights. A small model, such as a Phi-class model, is usually enough | 4: suggests one action, a person acts |
| 2 | Single-function machine | Filler, capper, press, conveyor, packaging machine with a PLC and counters | B | Type A, or Type B for the controller | Category 3 | Open weights, if they pass the qualifying tasks | 4 |
| 3 | Configurable multi-step machine or work cell | CNC machining centre, injection moulding cell, batch reactor with recipes, a line of several machines | C | Type B | Category 4 | Baseline (low-cost hosted) | 4 |
| 4 | Coupled process equipment | Photomask (lithography plate) writing and inspection, CVD or PVD chamber, bioreactor, heat-treatment furnace with process control | C | Type B | Category 4 or 5 | Frontier, and **Human Expert Recommended** (one expert) | 3: narrows the options, the expert chooses |
| 5 | Frontier equipment | Lithography (the scanner and its process), and other systems of many tightly coupled subsystems | C | Type B | Category 5 | **None adequate. Expert Team Required** (a distributed team of experts) | 2: lists options for the expert team and decides nothing |

The examples are typical, not fixed. A CNC machine with a simple fixed cycle may be ECL 2, and a "simple" press with adaptive force control may be ECL 3. Rate the equipment the agent will actually reason about.

## How ECL changes a recommendation

The benchmark's TRL × complexity matrix picks a starting model tier for a project. ECL then sets a floor under that choice:

1. If the cell's tier is below the ECL's minimum tier, the tier is raised to that minimum, and an alternative below the minimum is dropped.
2. Whatever the score, every recommendation at ECL 4 is marked **Human Expert Recommended** (one expert), and every one at ECL 5 is marked **Expert Team Required** (a distributed team of experts).
3. At ECL 5 no tier is adequate, so no agent qualifies, however well it scores. Agents may only list options for the expert team.
4. When you rank your own agents, an agent whose tier is below the ECL minimum does not qualify, even if it passed the qualifying tasks.

```bash
foames-bench recommend --trl 5 --complexity low --ecl 4
foames-bench matrix          # the TRL x complexity matrix, then the ECL table
```

Each benchmark task carries the ECL and machine class of the scenario it simulates. The current six tasks are at ECL 2 and 3, and the ERP integration task, which involves no equipment, has none. ECL 4 and 5 are therefore covered by the prior recommendations only. No task measures them yet, which is one more reason the expert stays in charge there. See [How the benchmark scores agents](Explanation-How-the-benchmark-scores-agents) and [Benchmark configuration](Reference-Benchmark-configuration).

## Why the expert stays in the loop

FoaMES already ends every agent action in a suggestion that a person accepts (see [Agents suggest, people act](Explanation-Agents-suggest-people-act)). ECL decides *which* person, and how much the agent may narrow the choice first. At low ECL, an operator can judge a suggestion about a torque wrench. At ECL 4, only an expert in that equipment can tell a plausible suggestion from a correct one. At ECL 5, even one expert can't. The judgement is spread across a team, so the agent's output goes to the team, not to one reviewer. These are exactly the levels where models are weakest and mistakes cost the most.

## What is planned

Today ECL exists in the benchmark and its recommendations. An ECL field on the Machine record, with agent eligibility tied to it (an agent registered for a machine only if its tier meets the machine's ECL), is planned and listed under [Upcoming features](Upcoming-features).

The tier floors in the table are dated prior recommendations, like the TRL matrix. They are not measured results, so replace them with your own runs.
