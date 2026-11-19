# AGENTS.md: the OpenFOAM runner

Read this when you work in `bridges/openfoam/`. The Frappe side is `foames/foames_simulation/` (its own AGENTS.md); the project-wide rules are in the root [AGENTS.md](../../AGENTS.md). The human guide is [docs/vendors/openfoam/](../../docs/vendors/openfoam/README.md).

## What it is

A standalone provider service (`foames_openfoam`) that runs version-pinned OpenFOAM command-line tools in an isolated worker and exposes a small run-lifecycle HTTP API. OpenFOAM is a solver, not a system of record: nothing here is an ERP adapter, and a CFD job must never command plant equipment, SCADA, PLCs or an ERP.

## Package map

All modules import only the standard library — tests need no OpenFOAM and no Frappe site:

- `lifecycle.py` — the state machine (`draft → queued → running → succeeded|failed|cancelled|timed_out`), idempotency keys, `Run` records and the JSON `RunStore`.
- `manifest.py` — case-manifest validation: registered case names and bounded numeric params only; `config_hash` for provenance.
- `cases.py` — `CaseSpec`s: tutorial path + fixed command pipeline + allowed params (`pitzdaily`, `cavity`).
- `runner.py` — copies the case into a per-run work dir, applies declared params to `system/controlDict` only, runs the allowlisted pipeline with timeouts and cancel flags, extracts residual summaries. No shell, no caller commands.
- `service.py` — the HTTP provider (stdlib `http.server`): health, cases, submit/status/cancel/artifacts, bearer auth, idempotent submit.
- `__main__.py` — `serve`, `run` (one-shot), `cases`.
- `worker/Dockerfile` — scaffold worker image; the OpenFOAM tag must be verified before use.

## Rules

- **GPL boundary.** OpenFOAM is GPL: binaries and source live only in the worker image or host install. Never copy OpenFOAM code, tutorials verbatim into this package, or link against it. This package shells out to the CLI as a separate process.
- **Allowlist, don't generalise.** New solvers/cases go through `cases.py` as reviewed `CaseSpec`s. Never accept commands, arbitrary paths or solver options from a manifest.
- **Idempotency and cancellation.** Submission dedupes on `idempotency_key`; cancellation is cooperative at command boundaries (`CANCEL` flag); timeouts are per-command and per-run.
- **Provenance.** Every run records solver version, `config_hash`, per-step logs and residual summaries. Convergence is not validation.
- Tests live in `tests/` (`python -m unittest discover -s tests -v`); the opt-in v2606 container smoke test must stay out of required CI.
