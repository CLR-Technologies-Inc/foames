# Methodology

## What the benchmark answers

1. Which agent produces the most reliable FoaMES changes?
2. Which agent gives the best quality per dollar?
3. Which agent understands manufacturing process development, not just code generation?

The first is answered by success rate and correctness, the second by cost per success at a given quality, and the third by the invariant tests, the specification task and the process score.

## One run

1. **Workspace.** The FoaMES checkout is copied without `.git`, without `benchmarks/` and without caches. The task's setup runs (for a bug task it plants the defect), and the copy is committed as a fresh one-commit repository tagged `task-start`. The agent cannot read the defect back from history, and the hidden tests and reference solution are not in its workspace.
2. **Sandbox.** The agent runs in a sandbox that shows it the workspace and nothing of the benchmark: a Docker container that mounts only the workspace, or on Linux a private mount and PID namespace that hides `benchmarks/` and makes the checkout read-only (see the [README](../README.md#sandbox)). The run records which one it used; a run with `--sandbox none` could read the hidden tests and is not a result to publish. As a second check the runner hashes the task folder, the harness and the pristine regression tests before and after each run, and fails a run that changed them.
3. **Agent.** The agent's command runs in the workspace with the prompt (the task's `prompt.md` followed by [tasks/_common.md](../tasks/_common.md)). It is stopped after three times the task's time budget.
4. **Change.** Everything the agent changed, committed or not, is taken as one patch against `task-start`.
5. **Grading.** The hidden tests are copied into the workspace (under `.foames-bench/grade/`, removed afterwards and never part of the patch) only after the agent has stopped, and run in the same sandbox with the workspace first on the import path, because they import the agent's code. The repository's own tests for the area run too, taken from the **pristine** checkout so that an agent cannot pass them by editing them. The agent's own new tests run, and the change is checked for scope (files outside `allowed_paths`) and purity (a pure module that starts importing Frappe).
6. **Usage.** Tokens, turns and cost come from the agent's own output (see [usage.py](../foames_bench/usage.py)). A dollar figure the agent printed is "reported"; one priced from tokens with `agents.json` prices is "estimated"; a local model is "local" at $0; anything else is "unknown" and that run is left out of cost-per-success.

## Scores

| Score | How it is computed |
| --- | --- |
| Correctness (40 %) | 0.75 × hidden functional pass rate + 0.25 × regression pass rate. For the specification task, the agent's acceptance tests take the place of the functional tests. Halved when a required deliverable is missing. |
| Process (35 %) | 0.5 × hidden invariant pass rate + 0.2 for new tests that pass + 0.15 for staying in scope + 0.15 for `BENCH_NOTES.md` (full at 80 words). For the specification task: 0.45 × rubric + 0.25 × invariants + 0.1 each for tests, scope and notes. Halved on a purity violation. |
| Efficiency (25 %) | Only on success: 0.5 × (1 − cost / budget) + 0.5 × (1 − time / budget), each floored at 0. Time alone when cost is unknown. |
| Quality | Correctness and process, rescaled to 0..1. The ranking score. |
| Composite | The weighted sum of all three. |
| Success | Correctness ≥ the task's gate (0.8) and every invariant test passing and no purity violation. |

The invariant gate follows AGENTS.md: "A pull request that breaks one will not be merged." A run that breaks an invariant is a failure however good the rest is.

## Measurements

| Measurement | Field in results.jsonl | Purpose |
| --- | --- | --- |
| Pass rate | `scores.success`, summarised with a 95 % Wilson interval | Did it meet the requirements? |
| First-attempt correctness | `rep == 1` rows | Did it succeed without a second chance? |
| Process quality | `scores.process`, `graded.agent_tests`, `graded.rubric` | Did it keep the invariants, verify and explain? |
| Regressions | `graded.regression` | Did it break existing behaviour? |
| Wall-clock time | `seconds` | How quickly? |
| Tokens and dollars | `usage` | What did it cost, and how sure is that figure? |
| Isolation | `sandbox` | Could the agent see the answers? |
| Human intervention | none by design | The prompt forbids questions; a run that stalls waiting for input times out. |
| Reproducibility | `reproducible_tasks` in the summary | Does it succeed again? |

## Comparing harnesses and models

An agent here is a harness and a model together. To separate them, run two experiments:

- **Across agents:** each harness with its default or recommended model (the four-agent pilot).
- **Same model, different harness:** one model through several harnesses, for example an open-weight model through OpenCode and through Aider, or one hosted model through two CLIs that both support it. [OpenBench](https://github.com/minghinmatthewlam/openbench) (MIT) is built for exactly this question and is worth reading before designing that experiment.

Keep everything else fixed: the FoaMES commit (recorded in `manifest.json`), the task set, the prompts, the machine.

## Statistics for theses

Two repetitions are enough to see whether a setup works at all, not to rank two agents. Two successes out of two give a 95 % interval of 34 % to 100 %. For a claim in a thesis, run at least five repetitions per task and agent, report success rates with their intervals, and compare agents with a paired test across tasks (for example a sign test or McNemar's test on per-task outcomes). Report the FoaMES commit, the agent and model versions, the date and the bench version with every result, because the model landscape changes within months.

## Process quality and the "lucky pass"

Passing tests is not the same as working well. The paper "AgentLens: Revealing The Lucky Pass Problem in SWE-Agent Evaluation" ([arXiv:2605.12925](https://arxiv.org/abs/2605.12925), May 2026) describes agents whose patches pass while their trajectories are unreliable. This benchmark addresses that in three deterministic ways: invariant tests that a plausible but wrong fix fails, a requirement that the agent's own tests pass, and the specification task's mutation check (its acceptance tests must catch three planted regressions). It does not yet score the trajectory itself. Transcripts are kept in each run directory (`agent.stdout`), so a trajectory analysis or an LLM judge can be added later without re-running agents.

The specification task's rubric is a keyword and section check. It is a floor: it can tell a plan that never mentions idempotency from one that does, but not a deep plan from a shallow one that uses the right words. For research use, add an LLM judge or two human raters on the saved `PLAN.md` files, with the rubric's concepts as the marking scheme.

## Contamination

The hidden tests and reference solutions are public in this repository, so a model trained on it after this was published may have seen them. Keeping them out of the workspace stops an agent from reading them during a run, not from having memorised them. For a result you need to defend, write a private variant of each task (change the numbers, the names and the fixture seed) and keep it out of public repositories. A separate private task repository would make that easy if it becomes necessary.

## The Frappe tier

The six tasks are pure Python because that is what runs anywhere at near-zero cost. Tasks that need a Frappe site (a DocType, a whitelisted method, the outbox DocTypes, the ERPNext adapter) are the next tier. They would use the [Docker dev bench](../../docs/dev-bench.md) as the workspace runtime and mark `"tier": "frappe"` in `task.json`. None is included yet.

## Tools considered

Checked on 2026-11-04.

| Tool | What it is | Status | Use here |
| --- | --- | --- | --- |
| [Inspect AI](https://inspect.aisi.org.uk/) | Evaluation framework from the UK AI Security Institute: tasks, scorers, sandboxes, MCP tools, logs | Confirmed. Runs external agents (Claude Code, Codex CLI, Gemini CLI, OpenCode and others) through [inspect_swe](https://github.com/meridianlabs-ai/inspect_swe) (MIT) | Optional front end, [inspect_eval.py](../foames_bench/inspect_eval.py). Not yet run end to end. The standard-library runner works without it. |
| [OpenBench](https://github.com/minghinmatthewlam/openbench) (minghinmatthewlam) | Compares coding-agent harnesses with the model pinned | Confirmed, MIT. Installs as `obench`. Not the same project as groq/openbench, a general LLM eval suite on Inspect AI | Method for the same-model experiment |
| [SWE-bench](https://github.com/SWE-bench/SWE-bench) | Patches for real GitHub issues, Docker evaluation | Confirmed, MIT | Method reference: hidden tests on a fixed commit |
| AgentLens | Trajectory analysis of SWE agents | The paper exists (arXiv:2605.12925). The repository link given in the original design (microsoft/code-agent-state-trajectories) could not be opened, and Microsoft authorship was not confirmed | Motivation for the process score |
| [Aider leaderboards](https://aider.chat/docs/leaderboards/) | Model comparison on Exercism exercises in six languages | Confirmed | General reference, not FoaMES-specific |
| [OpenCode](https://opencode.ai/) | Open-source coding agent, local models, `opencode run` for scripts | Confirmed, MIT. The repository moved from sst/opencode to anomalyco/opencode | The open-weight harness in `agents.json` |
