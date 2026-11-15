The agent benchmark asks three questions about a coding agent working on FoaMES: is its work reliable, what does that reliability cost, and does it understand manufacturing process development, not only code? Its scoring rules follow from those questions.

## Breaking an invariant is failing

FoaMES has rules a change must keep: counters never invent production, silence is loss in OEE, writes to an ERP are never performed twice, pure modules stay free of Frappe. A pull request that breaks one is not merged, however good the rest is. The benchmark applies the same gate: a run **succeeds** only if correctness reaches 0.8 **and** every hidden invariant test passes. Many invariant tests are property tests over random inputs, so a change that handles the three examples in the prompt but not the general case is caught.

## Cheap and wrong never beats correct

Efficiency (cost and time against the task's budget) counts for a quarter of the composite, but is paid **only on success**. Agents are ranked by **quality**, which leaves cost out, and cost per success is reported beside it. That way the table answers "which agent is right most often" first and "which is cheapest among those" second.

## Process counts, not only the patch

A third of the score is process: did the agent keep the invariants, write tests that pass, stay inside the files the task concerns, and write down what it assumed in `BENCH_NOTES.md`? An agent that guesses the right patch but leaves no tests or explanation is harder to trust on the next task. One task, `process-spec-network-loss`, has no code answer at all: the agent must turn an incomplete plant request into a specification whose acceptance tests pass now and catch three planted regressions.

## The agent cannot see the answers

Each run starts from a fresh copy of the repository with a single commit, so a planted defect cannot be read from history. Hidden tests and reference solutions are copied in only after the agent stops. The agent runs in a sandbox that shows it only its workspace, and the runner fails any run that changed the task, the harness or the regression tests. The tasks are public, so a model may have seen them in training; the methodology page discusses that contamination openly.

## An agent is a harness and a model together

The same model can score differently through two CLIs. The benchmark records both, so you can compare across agents (each harness with its usual model) or hold the model fixed and vary the harness.

## Evidence over opinion

The TRL × complexity matrix is a dated starting point, not a measurement. Its purpose is to be replaced: `recommend --results` ranks your own agents on the tasks that qualify them for your project's cell. Two repetitions show whether a setup works; five or more, with intervals and a paired test across tasks, support a published claim.

Details: [benchmarks/docs/methodology.md](https://github.com/CLR-Technologies-Inc/foames/blob/main/benchmarks/docs/methodology.md). Commands and fields: [Benchmark configuration](Reference-Benchmark-configuration).
