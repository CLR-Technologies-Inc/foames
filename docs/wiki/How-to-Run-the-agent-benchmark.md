**Goal:** compare several coding agents on all six FoaMES tasks, with repetitions, inside a sandbox, under a spending cap, and turn the results into a model choice for your project.

> **CI-tested.** The commands on this page run, as written, in the [Docker smoke test](https://github.com/CLR-Technologies-Inc/foames/actions/workflows/docker-smoke.yml) on every change to them. Steps that need your own agent or API key are the exception.

**You need:** the setup from [Tutorial 4](Tutorial-4-Your-first-agent-benchmark-run): `foames-bench` installed, `validate` passing, the Docker image built, and your agents listed as available by `foames-bench agents`.

## 1. Choose the scenarios

| Task | Complexity | The agent must |
| --- | --- | --- |
| `counter-reset` | low | Find why a PLC restart added 4,800 phantom parts and fix it |
| `oee-unknown-time` | medium | Build an OEE time ledger from a state timeline with network gaps |
| `spc-ewma-chart` | medium | Add an EWMA chart that catches small drifts |
| `process-mining-analysis` | medium | Answer an engineer's questions about a welding cell's event log |
| `erp-retry-after` | high | Honour S/4HANA throttling and find why a confirmation was posted twice |
| `process-spec-network-loss` | high | Turn an incomplete plant request into a specification with executable acceptance tests |

All six use only public FoaMES code and invented data, and need no Frappe site. Pick all of them (the default), or the ones your project relies on with `--tasks`.

## 2. Estimate the cost

```bash
foames-bench estimate --agents 3 --tasks 6 --reps 2 --per-run 1.00
```

The per-run figure is your assumption, not a quote. Fill in current token prices under `prices` in `agents.json` for agents that do not report cost themselves, or runs are costed as unknown.

## 3. Run

```bash
foames-bench run --agents claude-code-baseline codex-frontier opencode-local --reps 2 --sandbox docker --cap-usd 25
```

| Option | Use |
| --- | --- |
| `--agents` | Names from `agents.json` |
| `--tasks`, `--tier` | Limit the tasks |
| `--reps` | Repetitions per agent and task. 2 shows whether a setup works; 5 or more for a claim you will publish |
| `--sandbox docker` | Required for results you publish. `unshare` is a Linux alternative that keeps CLI logins; `none` is only for trying an agent out |
| `--sandbox-network none` | For local models on a socket you mount |
| `--cap-usd` | Stop starting new runs once visible spend reaches this |
| `--keep-workspaces` | Keep each agent's working copy for inspection |
| `--out` | Choose the run directory |
| `--repo` | Benchmark another FoaMES checkout, such as your fork |

Each agent is stopped after three times the task's time budget. Keep the machine otherwise idle so wall times compare.

## 4. Read the results

```bash
foames-bench report runs/<run id>
```

The first table ranks agents by **quality** and shows success rate with its 95 % interval, first-try success, composite score, mean time, total cost and **cost per success**. The second breaks it down by agent and task, with correctness and process separately.

- Prefer the agent with the highest quality whose cost per success you can afford.
- A high correctness with a low process score means the code passed but the agent wrote no tests, strayed out of scope or did not explain its assumptions.
- Any run with sandbox `none` is flagged: it could read the hidden tests, so do not publish it.
- For any surprising row, open `<task>/<agent>/rep-<n>/` and read `change.patch`, `agent.stdout` and `result.json`.

## 5. Turn it into a choice

```bash
foames-bench matrix
foames-bench recommend --trl 5 --complexity medium --results runs/<run id>
foames-bench recommend --trl 5 --complexity medium --ecl 3 --results runs/<run id>
```

`matrix` prints the starting recommendation for each technology readiness level band and process complexity. It is a dated prior, not a measurement. `recommend --results` keeps your runs of that cell's qualifying tasks and lists the agents that ran all of them, met the minimum quality and succeeded on every repetition, cheapest per success first. Add `--ecl N` when the work is tied to a machine: the [Equipment Complexity Level](Explanation-Equipment-complexity-levels) raises the tier to its minimum, drops agents below that tier, marks ECL 4 **Human Expert Recommended** (one expert), and marks ECL 5 **Expert Team Required** (a distributed team of experts).

## 6. Report it

With every result, record the FoaMES commit (in `manifest.json`), the agent CLI and model versions, the sandbox image digest, the date and the bench version. Models change within months.

## Testing by hand, or from any harness

When your harness cannot be driven from a command line, prepare a workspace, run the agent yourself, then grade:

```bash
foames-bench prepare --task oee-unknown-time --dest /tmp/ws     # also writes /tmp/oee-unknown-time.prompt.md
# run your agent in /tmp/ws with that prompt, unattended
foames-bench grade --task oee-unknown-time --workspace /tmp/ws --seconds 412 --cost-usd 0.38
```

`grade` prints the scores as JSON. A hand run is not sandboxed by the benchmark, so isolate the agent yourself and say so when you report it.

Every option and score is on [Benchmark configuration](Reference-Benchmark-configuration); the reasoning is in [How the benchmark scores agents](Explanation-How-the-benchmark-scores-agents).
