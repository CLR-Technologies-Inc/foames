# Writing a task

A task is a folder under [tasks/](../tasks/):

```
tasks/<id>/
  task.json        manifest
  prompt.md        what the agent is told (tasks/_common.md is appended)
  setup.py         optional: setup(workspace) changes the copy before the agent starts
  reference.py     apply(workspace): a correct solution, used by `foames-bench validate`
  hidden/          unittest files the agent never sees, plus any fixtures they read
  rubric.json      optional: a written-deliverable rubric
```

## task.json

| Field | Meaning |
| --- | --- |
| `id`, `title` | The folder name and a one-line title |
| `tier` | `pure` (runs with Python alone) or `frappe` (needs the dev bench) |
| `complexity` | `low`, `medium` or `high`, as defined in [model-matrix.md](model-matrix.md#assumptions) |
| `trl_bands` | The TRL bands the task is meant to inform |
| `dimension` | What it measures, in words |
| `hidden` | `{"functional": [files], "invariant": [files]}`: test files in `hidden/`. Every invariant test must pass for a run to succeed. |
| `regression` | Repository test files, run from the pristine checkout against the agent's code |
| `allowed_paths` | Glob patterns the change should stay within; `BENCH_NOTES.md` is always allowed |
| `deliverables` | Files that must exist after the run |
| `rubric` | A rubric file name, for tasks whose output is a document |
| `budget` | `{"usd": ..., "seconds": ...}`: the efficiency reference, not a limit |

## Rules

- **Public code and invented data only.** A task may use only what is on FoaMES's public `main` branch, and fixtures you generate. No plant's data, no customer's process, nothing held back from the public repository.
- **Put the essential rule in the invariant group.** For each task ask which FoaMES invariant a plausible but wrong answer would break, and write that as an invariant test. A property test over random inputs (with a fixed seed) catches more than a handful of examples.
- **Test behaviour, not wording.** Hidden tests call the agent's functions and check results. Do not require exact names beyond what the prompt specifies.
- **Specify the interface in the prompt.** If the hidden tests call `ewma_chart(values, lam, L, baseline)`, the prompt says so.
- **Planted defects must not be visible in history.** Put them in `setup.py`; the workspace is committed after setup, so `git log` shows a single commit.
- **Validate.** `foames-bench validate --tasks <id>` must show the reference passing and the no-op failing. If the no-op passes, the hidden tests do not test the task.
- **Hidden tests find the workspace** in `FOAMES_BENCH_WORKSPACE` and the Frappe stub in `FOAMES_BENCH_STUBS` when they need to run something there.
- **Tests run inside the sandbox.** Before grading, each test file is copied into the workspace with what it may read from its own folder: data files, helpers named `_*.py` or `test_*.py`, and `test_data/`, `fixtures/` or `data/` folders. A test that reads anything else of the benchmark finds nothing there. Run `python -m unittest tests.test_harness.TestSandbox` after changing a task.
