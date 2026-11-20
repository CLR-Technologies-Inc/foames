# AGENTS.md: FoaMES Simulation

Read this when you work in `foames/foames_simulation/`. The project-wide rules are in the root [AGENTS.md](../../AGENTS.md). The human guide is [docs/vendors/openfoam/](../../docs/vendors/openfoam/README.md); the provider it talks to is `bridges/openfoam/` (its own AGENTS.md there).

## What it is

The Frappe-side half of the optional OpenFOAM CFD integration: `Simulation Settings` (single: enabled, provider URL, bearer token Password field, timeout), `Simulation Run` (one record per provider run), whitelisted calls in `api.py` and the hourly `tasks.sync_runs`. OpenFOAM is a **solver, not a system of record** — this module is not an ERP adapter and registers nothing in `foames_erp_adapters`.

## Rules specific to this module

- **Isolation is the point.** The solver runs only inside the provider's container (`bridges/openfoam`). Frappe never shells out to OpenFOAM, never imports it, and a site without the provider works normally — `enabled` off means every entry point returns at once.
- **Permissioned submission.** `simulation_submit`/`simulation_cancel` need FoaMES Engineer or Supervisor; reads include Quality. Keep it that way — a CFD job is compute, but it is still an explicit action.
- **Candidate evidence only.** A `succeeded` run may feed Validation Protocol / Validation Execution as *unapproved* evidence. Nothing here auto-approves, and convergence is never claimed as physical validation.
- **No external writes.** A simulation must never send commands to plant equipment, SCADA, PLCs or an ERP. If a future feature wants that, it goes through `foames_kernel/write_gate.py`, never around it.
- **Secrets** live in the `provider_token` Password field, read with `get_password`, never logged.
- **Pure modules.** `simulation.py` (lifecycle mirror, evidence status, epoch conversion) and `client.py` (provider HTTP client, injectable transport) import nothing from Frappe; keep them that way so tests need no site.

## Package map

- `simulation.py` — pure lifecycle mirror of the provider's state machine plus `evidence_status`.
- `client.py` — pure `ProviderClient` for the provider contract (health/cases/submit/get/cancel/artifacts).
- `api.py` — whitelisted `simulation_cases`, `simulation_submit`, `simulation_status`, `simulation_cancel`.
- `tasks.py` — `sync_runs`, hourly: copies provider status onto active Simulation Run records; unreachable provider leaves them untouched.
- `doctype/simulation_settings`, `doctype/simulation_run` — thin DocType classes.

## Tests

`test_simulation.py` covers the client (fake transport) and the lifecycle mirror without a site. Run under `bench --site <site> run-tests --app foames --module foames.foames_simulation.test_simulation`.
