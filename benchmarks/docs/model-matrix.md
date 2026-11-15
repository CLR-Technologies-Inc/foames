# Model recommendations by TRL and process complexity

**As of 2026-11-04. Review by 2027-02-01, or sooner when a major model is released.** These are informed starting points, not measurements. No real agent has yet been run through this benchmark to back them. Run the qualifying tasks with your own agents and let the results replace the prior:

```bash
foames-bench run --tasks erp-retry-after process-spec-network-loss --agents <yours> --reps 3
foames-bench recommend --trl 6 --complexity high --results runs/<run id>
```

The data behind this page is [data/recommendations.json](../data/recommendations.json); `foames-bench matrix` prints it.

## The matrix

Each cell gives the tier to start with, the alternative, the minimum quality a model must reach on the qualifying tasks (with every repetition succeeding), and the human review that should go with it.

| TRL band | Low complexity | Medium complexity | High complexity |
| --- | --- | --- | --- |
| **1-3** concept and research | **Open weights**, alt. baseline. Min quality 0.7. Spot check. Qualify on `counter-reset`. | **Open weights**, alt. baseline. 0.7. Review the method. Qualify on `oee-unknown-time`, `process-mining-analysis`. | **Baseline**, alt. frontier. 0.7. Supervisor reviews the specification. Qualify on `process-spec-network-loss`. |
| **4-6** lab and pilot validation | **Baseline**, alt. open weights. 0.8. Code review before the pilot. Qualify on `counter-reset`, `oee-unknown-time`. | **Baseline**, alt. frontier. 0.8. Code review and a check against plant data. Qualify on `oee-unknown-time`, `spc-ewma-chart`, `process-mining-analysis`. | **Frontier**, alt. baseline. 0.85. Design review with the process owner. Qualify on `erp-retry-after`, `process-spec-network-loss`. |
| **7-9** qualified and in production | **Baseline**, alt. frontier. 0.9. Two-person review, tests required. Qualify on `counter-reset`, `oee-unknown-time`. | **Frontier**, alt. baseline. 0.9. Two-person review, validation on historical data. Qualify on the three medium tasks. | **Frontier**, no alternative. 0.9. Formal change control: the agent proposes, people approve. Qualify on `erp-retry-after`, `process-spec-network-loss`, `counter-reset`. |

The reasoning behind the pattern: as TRL rises, a wrong answer costs more (product, money, a duplicated ERP posting), so first-attempt reliability is worth more than a low price per run. As complexity rises, the hard part shifts from writing code to recognising ambiguity and keeping invariants across modules and systems, which is where larger models have been stronger. Open-weight models are a good fit wherever retries are cheap and a person reads every diff, which describes most student work at TRL 1-3.

## The tiers

**Free / open weights.** Models whose weights you can download and run on your own hardware or a university cluster, through an open harness such as OpenCode or Aider. No per-token cost. Examples as of mid-2026:

| Family | Sizes that fit | Licence |
| --- | --- | --- |
| Qwen3-Coder | 30B-A3B on a laptop or one GPU; 480B-A35B on a server | Apache-2.0 |
| gpt-oss | 20b on a laptop; 120b on one 80 GB GPU | Apache-2.0 |
| DeepSeek V3.x | 671B mixture of experts, cluster or hosted | MIT |
| GLM-4.x | Air on a workstation; full on a cluster | MIT |
| Kimi K2 | 1T mixture of experts, cluster or hosted | Modified MIT |

**Baseline.** Smaller or mid-sized commercial models, cheap per task and good at well-specified single-module changes: the current Claude Haiku or Sonnet through Claude Code, a Gemini Flash-class model through Gemini CLI, a GPT mini-class model through Codex CLI.

**Frontier.** The most capable commercial models: the current Claude Opus through Claude Code, a GPT-5.x Codex-class model through Codex CLI, a Gemini Pro-class model through Gemini CLI.

Model names are given by family on purpose. Versions change every few months, so check what is current when you run the benchmark and record the exact version with your results.

## Assumptions

1. **TRL applies to the manufacturing process being developed**, not to FoaMES itself, on the usual nine-level scale (1-3 research and proof of concept, 4-6 validation in the lab and in a relevant environment, 7-9 demonstration, qualification and operation).
2. **Process complexity** is low for one module and one data source with discrete counts; medium for several modules or a statistical method (shifts with OEE, SPC, process mining, batch steps); high for several systems or regulated traceability (ERP postings, retries and idempotency, a part that changes designation between batch and discrete, an ambiguous requirement that must become a specification).
3. **The harness matters as much as the model.** The recommendations are for a harness and model together. The same model can score differently through two harnesses, which is why the benchmark records both.
4. **Model knowledge is from public information up to mid-2026.** Families, sizes and licences were correct as far as known then; prices were not used, because they change too often to print. Fill in current prices in `agents.json` to get cost estimates.
5. **Open-weight hardware** is assumed to be a laptop with 32 GB or more of memory, a workstation with one GPU, or a shared cluster. Smaller machines need smaller models and will score lower.
6. **Human review is part of every cell.** FoaMES's own rule is that agents suggest and people act; no cell recommends letting an agent change a production system unreviewed.
7. **The minimum quality bars are judgement calls**, set so that a model that passes at TRL 7-9 has passed every hidden test and nearly every process check. Tighten them for regulated industries.

## Replacing the prior with evidence

`foames-bench recommend --results` takes a run directory, keeps the runs of the cell's qualifying tasks, and ranks your agents. An agent qualifies when it ran every qualifying task, its mean quality reaches the cell's minimum, and every repetition succeeded. Qualified agents are listed cheapest per success first. Use at least two repetitions to qualify an agent, and five or more if the result goes into a thesis ([methodology](methodology.md#statistics-for-theses)).
