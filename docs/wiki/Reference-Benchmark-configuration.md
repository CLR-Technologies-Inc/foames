The agent benchmark lives in [`benchmarks/`](https://github.com/CLR-Technologies-Inc/foames/blob/main/benchmarks/README.md). It is outside the app: nothing in it is imported by `foames` and nothing in it runs in CI. Python 3.10 or later, standard library only.

## Commands

Run as `foames-bench <command>` after `pip install -e .` in `benchmarks/`, or `python -m foames_bench <command>`. A global `--agents-file PATH` chooses another agent configuration.

| Command | Options | Does |
| --- | --- | --- |
| `list` | `--tier pure\|frappe\|all` | Lists the tasks |
| `agents` | | Lists configured agents and whether each CLI and sandbox is available |
| `validate` | `--tasks`, `--tier`, `--repo`, `--out` | Runs the reference and no-op agents on each task; every reference must pass and every no-op fail |
| `run` | `--agents`, `--tasks`, `--tier`, `--reps` (1), `--repo`, `--out`, `--keep-workspaces`, `--cap-usd`, `--sandbox`, `--sandbox-image`, `--sandbox-network` | Runs tasks × agents × repetitions |
| `report` | `run_dir` | Writes `summary.md`, `summary.json`, `summary.csv` and prints the tables |
| `prepare` | `--task`, `--dest`, `--repo` | Makes one workspace (and `<dest parent>/<task>.prompt.md`) for a hand run |
| `grade` | `--task`, `--workspace`, `--repo`, `--seconds`, `--cost-usd`, `--full` | Grades a prepared workspace and prints the scores as JSON |
| `recommend` | `--trl N`, `--complexity low\|medium\|high`, `--results run_dir`, `--json` | The model tier for a cell, and with results, your qualifying agents ranked |
| `matrix` | | Prints the TRL × complexity matrix |
| `estimate` | `--agents` (4), `--tasks` (6), `--reps` (2), `--per-run` (1.0) | Pilot budget arithmetic |

`--repo` (or `FOAMES_REPO`) points at the FoaMES checkout to benchmark; the default is the parent of `benchmarks/`.

## Sandbox

| `--sandbox` | The agent sees | Needs |
| --- | --- | --- |
| `docker` | Only its workspace at `/workspace`, in the `foames-bench-agent` image, as your user | Docker and `docker build -t foames-bench-agent sandbox` |
| `unshare` | Your machine with `benchmarks/` emptied, the checkout read-only, its own process namespace; home and network stay | Linux with unprivileged user namespaces |
| `auto` (default) | Docker if available, else unshare, else the run stops. Never falls back to none | |
| `none` | Everything. Recorded and flagged as not publishable | |

Passed into the container when set: `ANTHROPIC_API_KEY`, `ANTHROPIC_BASE_URL`, `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `OPENROUTER_API_KEY`, `OLLAMA_HOST`, `HTTPS_PROXY`, `HTTP_PROXY`, `NO_PROXY`, plus any an agent lists. Image build arguments: `NPM_AGENTS` (default `@anthropic-ai/claude-code @openai/codex @google/gemini-cli opencode-ai`; replaces the list) and `PIP_AGENTS` (default empty).

The runner also hashes the task folder, the harness and the pristine regression tests before and after each run, and fails a run that changed them.

## agents.json

One object per agent under `"agents"`. Keys starting with `_` are comments.

| Field | Default | Meaning |
| --- | --- | --- |
| `name` | required | What you pass to `--agents` |
| `kind` | `command` | `command`, or the built-ins `reference` and `noop` |
| `command` | | Argument list run in the workspace. `{prompt}`, `{prompt_file}`, `{workspace}`, `{model}` are filled in |
| `stdin` | false | Also pipe the prompt to standard input |
| `model` | "" | Fills `{model}`; recorded with results |
| `harness` | "" | The CLI or framework, recorded with results |
| `tier` | "" | `oss`, `baseline` or `frontier` |
| `usage_parser` | `none` | `claude-json`, `codex-jsonl`, `gemini-json`, `generic` or `none` |
| `prices` | none | `input_per_mtok`, `cached_input_per_mtok`, `output_per_mtok` in dollars, to estimate cost from tokens |
| `fixed_cost_usd` | none | A fixed cost per run; 0.0 for local models |
| `env` | {} | Extra environment variables for the agent (placeholders allowed) |
| `timeout_factor` | 3.0 | The agent is stopped after this many times the task's time budget |
| `sandbox` | none | Docker options: `image`, `network`, `env` (variable names to pass in), `mounts` (`"host:target"` read-only or `"host:target:rw"`) |
| `notes` | "" | Free text |

Shipped entries: `reference`, `noop`, `claude-code-frontier`, `claude-code-baseline`, `codex-frontier`, `gemini-frontier`, `opencode-local`, `aider-local`. Check each command against your installed CLI version before a paid run.

## task.json

| Field | Meaning |
| --- | --- |
| `id`, `title` | Folder name and one-line title |
| `tier` | `pure` (Python only) or `frappe` (needs the dev bench) |
| `complexity` | `low`, `medium` or `high` |
| `trl_bands` | The TRL bands the task informs |
| `dimension` | What it measures |
| `hidden` | `{"functional": [...], "invariant": [...]}` test files in `hidden/` |
| `regression` | Repository tests run from the pristine checkout against the agent's code |
| `allowed_paths` | Globs the change should stay within (`BENCH_NOTES.md` always allowed) |
| `deliverables` | Files that must exist after the run |
| `rubric` | A rubric file, for document deliverables |
| `budget` | `{"usd": ..., "seconds": ...}`, the efficiency reference, not a limit |

## Scores

| Score | Computed as |
| --- | --- |
| Correctness (40 %) | 0.75 × hidden functional pass rate + 0.25 × regression pass rate; halved if a deliverable is missing |
| Process (35 %) | 0.5 × hidden invariant pass rate + 0.2 new passing tests + 0.15 in scope + 0.15 `BENCH_NOTES.md` (full at 80 words); a rubric-weighted variant for the specification task; halved on a purity violation |
| Efficiency (25 %) | Only on success: 0.5 × (1 − cost/budget) + 0.5 × (1 − time/budget), each floored at 0 |
| Quality | Correctness and process rescaled to 0..1; the ranking score |
| Composite | Weighted sum of all three |
| Success | Correctness ≥ 0.8, every invariant test passing, no purity violation |

Cost sources: *reported* (printed by the agent), *estimated* (tokens × `prices`), *local*, or *unknown* (left out of cost per success).

## Run directory

```
runs/<run id>/
  manifest.json            FoaMES commit, bench version, agents, tasks
  results.jsonl            one line per run; the report reads only this
  summary.md|json|csv      written by report
  <task>/<agent>/rep-<n>/
    prompt.md  agent.stdout  agent.stderr  change.patch  result.json
    workspace/             only with --keep-workspaces
```

`runs/` is git-ignored. More in [benchmarks/docs/methodology.md](https://github.com/CLR-Technologies-Inc/foames/blob/main/benchmarks/docs/methodology.md) and [model-matrix.md](https://github.com/CLR-Technologies-Inc/foames/blob/main/benchmarks/docs/model-matrix.md).
