# FoaMES agent benchmark

A small, reproducible benchmark of how well coding agents use and develop FoaMES. Every agent gets the same task, on the same commit, in a clean copy of the repository. Hidden tests check the result against FoaMES's manufacturing invariants, and each run records its time, tokens and cost. The benchmark then suggests which kind of model to start with for a project's technology readiness level (TRL) and process complexity.

It is written for senior design teams, master's students and PhD researchers who build on FoaMES and want evidence, not opinions, about which agent to trust with which part of the work.

- **Standard library only.** Python 3.10 or later. No Frappe site and no database for the six pure-Python tasks.
- **Sandboxed.** Agents run where they can see their workspace and nothing of the benchmark: in a Docker container, or on Linux in a private mount namespace. See [Sandbox](#sandbox).
- **Any agent.** Claude Code, Codex CLI, Gemini CLI, OpenCode, Aider, or your own script. An agent is a command line in [agents.json](agents.json).
- **Outside the app.** Nothing here is imported by the `foames` app, and nothing here runs in CI.

## Install

```bash
git clone https://github.com/CLR-Technologies-Inc/foames.git
cd foames/benchmarks
python -m foames_bench validate        # works without installing anything
pip install -e .                       # optional: adds the `foames-bench` command
pip install -e ".[inspect]"            # optional: the Inspect AI front end (experimental)
```

The editable install matters: the tasks live next to the package, not inside it. To benchmark another FoaMES checkout, such as your own fork, pass `--repo /path/to/foames` or set `FOAMES_REPO`.

## Quick start

```bash
foames-bench list                       # the tasks
foames-bench validate                   # reference solutions pass, a no-op fails: the grader works
docker build -t foames-bench-agent sandbox   # the agent sandbox image (from benchmarks/)
foames-bench agents                     # which agent CLIs and sandboxes are available here
foames-bench estimate --agents 4 --tasks 6 --reps 2 --per-run 1.00
foames-bench run --agents claude-code-baseline opencode-local --reps 2 --cap-usd 25
foames-bench report runs/<run id>
foames-bench recommend --trl 5 --complexity medium --results runs/<run id>
foames-bench matrix                     # the TRL x complexity table
```

To run an agent by hand, or from another harness, make a workspace and grade it afterwards:

```bash
foames-bench prepare --task oee-unknown-time --dest /tmp/ws    # writes /tmp/oee-unknown-time.prompt.md too
# ... run your agent in /tmp/ws with that prompt ...
foames-bench grade --task oee-unknown-time --workspace /tmp/ws --seconds 412 --cost-usd 0.38
```

## Sandbox

`foames-bench run` puts every command agent, and every test that imports its code, in a sandbox. The configurations in `agents.json` switch the agents' permission prompts off so they can work unattended (`--dangerously-skip-permissions`, `--full-auto`, `--yolo`, `--yes-always`), so the sandbox is what stops an agent from reading the hidden tests and the reference solutions, or from touching the rest of your machine.

| `--sandbox` | What the agent sees | Needs |
| --- | --- | --- |
| `docker` | Only its workspace, at `/workspace`, in a container built from [sandbox/Dockerfile](sandbox/Dockerfile). Runs as your user. Network `bridge` by default (`--sandbox-network none` for local models on a socket you mount, or a custom network). | Docker on Linux, macOS or Windows, and the image: `docker build -t foames-bench-agent sandbox` |
| `unshare` | Your machine, except that the whole `benchmarks/` folder is replaced by an empty one, the FoaMES checkout is read-only, and the agent has its own process namespace. Your home directory and network stay, so CLI logins work. | Linux with unprivileged user namespaces and util-linux `unshare` |
| `auto` (default) | `docker` when the daemon answers and the image exists, else `unshare`, else the run stops and says what to do. It never falls back to no sandbox. | |
| `none` | Everything. Only for trying an agent out: the run is recorded as `none` and the report says not to publish it. | |

Docker is the one to use for results you publish. In the container an agent has only the environment variables it needs: the API keys and proxy settings in `DEFAULT_PASSTHROUGH` ([sandbox.py](foames_bench/sandbox.py)) when they are set, plus any an agent lists. An agent CLI must be in the image (`foames-bench agents` and `run` check). The image installs Claude Code, Codex CLI, Gemini CLI and OpenCode from npm; choose others, or pin versions, with `--build-arg NPM_AGENTS=...` and `--build-arg PIP_AGENTS="aider-chat"`, and record the image digest with your results. Per-agent options go in `agents.json`:

```json
"sandbox": {"env": ["MY_PROVIDER_KEY"], "mounts": ["~/.config/opencode:/tmp/.config/opencode:rw"], "network": "host"}
```

An agent that logs in through a browser rather than an API key needs its login folder mounted (`:rw`, since the CLI refreshes tokens), or use `unshare`. A model served by Ollama on the host is at `http://host.docker.internal:11434` from the container on macOS and Windows; on Linux use `"network": "host"`.

Isolation is one of two defences. The runner also hashes the task folder, the harness and the pristine regression tests before and after each run, and fails a run that changed them. Do not run agents on a machine whose files matter even so, and check each agent command against your installed version once before a paid run, because the CLIs change their flags.

## The tasks

| Task | Complexity | What the agent must do | How it is scored |
| --- | --- | --- | --- |
| `counter-reset` | low | Find why a PLC restart added 4,800 phantom parts and fix it | Exact counts; the counter invariants (first reading, reset, out-of-order, rollover) as property tests |
| `oee-unknown-time` | medium | Build an OEE time ledger from a state timeline with network gaps | Minute-by-minute ledger values; unknown time stays loss; every minute is accounted once |
| `spc-ewma-chart` | medium | Add an EWMA chart for small drifts | Values against an independent computation; detection of a 1-sigma shift; a bound on false alarms; purity |
| `process-mining-analysis` | medium | Answer a production engineer's questions about a welding cell's event log | Variants, cycle time, rework, bottleneck and open orders; the answers must regenerate from the script and follow the data |
| `erp-retry-after` | high | Honour S/4HANA throttling, and find why a confirmation was posted twice | Retry-After parsing and backoff; no duplicate posting after a 504; idempotency rules intact |
| `process-spec-network-loss` | high | Turn an incomplete plant request into a specification with executable acceptance criteria | A written rubric; the acceptance tests must pass now and must catch three planted regressions |

The tasks use only public FoaMES code and invented data. Each one lives in [tasks/](tasks/) with its prompt, an optional setup that plants the defect, hidden tests, and a reference solution. Hidden tests and reference solutions are never copied into the agent's workspace, the [sandbox](#sandbox) keeps the agent from reading them elsewhere, and a run that edits them fails. They are public in this repository, though, so a model trained on it may have seen them; see [docs/methodology.md](docs/methodology.md#contamination).

## Scoring

| Dimension | Weight | Measured by |
| --- | --- | --- |
| Engineering correctness | 40 % | Hidden functional tests (75 %), the repository's own tests taken from the pristine checkout (25 %) |
| Process-development quality | 35 % | Hidden invariant tests, tests the agent wrote, staying in scope, notes on assumptions; a rubric for the specification task |
| Delivery efficiency | 25 % | Cost and wall time against the task's budget |

A run **succeeds** only when correctness reaches 0.8 and every invariant test passes, because a change that breaks a FoaMES invariant is not merged. Efficiency is paid only on success, so a cheap wrong answer never outranks a correct one. Rankings use **quality** (correctness and process, without cost), and cost per success is reported next to it. Details are in [docs/methodology.md](docs/methodology.md).

Each run records the pass rate with a 95 % interval, first-attempt success, reproducibility across repetitions, regressions, wall time, tokens, dollars and where the dollar figure came from (reported by the agent, estimated from token prices, or local). Every patch, prompt and agent transcript is kept in the run directory.

## Which model for which project

[docs/model-matrix.md](docs/model-matrix.md) gives a starting recommendation for each TRL band (1-3, 4-6, 7-9) and process complexity (low, medium, high): open-weight models, low-cost hosted "baseline" models, or frontier models. It says which benchmark tasks a model must pass to qualify for that cell. **The matrix is dated (2026-11-04) and has not yet been backed by real agent runs.** Run the qualifying tasks with your own agents and `foames-bench recommend --results` ranks them for your cell.

## Pilot budget

Four agents, six tasks and two repetitions are 48 runs. At an assumed $1 a run that is $48. That figure is an assumption, not a provider price. The task budgets in `task.json` add up to $7.50 per agent per repetition, and they are scoring references, not limits. Use `--cap-usd` to stop starting new runs once the spend you can see reaches a cap. Open-weight models on your own hardware cost electricity and time, which are not tracked. Start with the pure tasks. Frappe integration tasks will cost more.

## Layout

```
benchmarks/
  agents.json              agent command lines, usage parsers, prices, sandbox options
  sandbox/Dockerfile       the image agents run in with --sandbox docker
  foames_bench/            the harness (cli, runner, workspace, sandbox, agents, grading, scoring, usage, report, recommend)
    stubs/frappe/          a stand-in so FoaMES's pure modules import without a bench
    inspect_eval.py        optional Inspect AI front end (experimental)
  tasks/<id>/              task.json, prompt.md, setup.py, reference.py, hidden/
  data/recommendations.json  the TRL x complexity matrix
  docs/                    methodology, model matrix, writing tasks
  tests/                   self-tests of the harness
```

Run the harness's own tests with `python -m unittest discover tests` from this directory.

## Licence

Apache-2.0, as FoaMES. Copyright 2026 CLR Technologies Inc.
