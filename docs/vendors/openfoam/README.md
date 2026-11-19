# OpenFOAM

FoaMES can run computational fluid dynamics cases through an **isolated OpenFOAM v2606 worker**: an engineering case goes in as a versioned manifest, the solver runs `blockMesh → checkMesh → <solver> → postProcess` inside its own container, and the results — mesh status, residuals, logs and artifact references — come back as **candidate validation evidence** for a person to review.

OpenFOAM is a solver, not a system of record. It is not an ERP adapter, it cannot command plant equipment, SCADA or an ERP, and a converged solve is never automatic approval.

## What ships

| Piece | Where |
| --- | --- |
| Provider service + runner (`foames_openfoam`) | `bridges/openfoam/` |
| Worker container definition | `bridges/openfoam/worker/Dockerfile` |
| Frappe side (settings, run records, API, hourly sync) | `foames/foames_simulation/` |
| Agent-facing rules | `bridges/openfoam/AGENTS.md` *(to be added)* and `foames/foames_simulation/AGENTS.md` |

## Architecture

```
FoaMES (Simulation Run) ──POST /runs──▶ foames-openfoam provider ──▶ worker thread
        ◀──status/result──────────────  (run-*.json store)   ──▶ blockMesh/checkMesh/solver/postProcess
                                             in a per-run work dir, allowlisted commands only
```

- **Provider contract**: `POST /runs` (case manifest + requester), `GET /runs/{id}`, `POST /runs/{id}/cancel`, `GET /runs/{id}/artifacts[/{name}]`, `GET /cases`, `GET /health`. Bearer-token auth when configured.
- **Case manifests** name a registered case (`pitzdaily`, `cavity`) and numeric params only — never commands, paths or solver options. Submission is idempotent: the manifest's hash is the idempotency key, so a retry after a timeout returns the same run.
- **Lifecycle**: `draft → queued → running → succeeded | failed | cancelled | timed_out`, enforced on both sides.
- **Frappe**: `Simulation Settings` holds the provider URL and token; `simulation_submit` creates a local `Simulation Run`; the hourly `sync_runs` copies provider status, residual summaries and artifact lists onto active records.

## Setup

1. Build or obtain the worker image. `worker/Dockerfile` is a **scaffold**: verify the OpenFOAM v2606 image tag against OpenFOAM's published packages before use (see [OpenFOAM v2606](https://www.openfoam.com/news/main-news/openfoam-v2606)).

   ```bash
   docker build -t foames-openfoam-worker:2606 bridges/openfoam/worker
   docker run -d --name openfoam -p 8765:8765 \
     -e FOAMES_OPENFOAM_TOKEN=<token> \
     -v openfoam-work:/work foames-openfoam-worker:2606 serve
   ```

2. In Frappe, open **Simulation Settings**: enable, set the provider URL (`http://<host>:8765`) and token, save.
3. Submit from the desk or API:

   ```python
   frappe.call("foames.foames_simulation.api.simulation_submit",
               manifest={"case": "pitzdaily", "params": {"end_time": 300}})
   ```

## Guardrails

- Non-root worker, per-run work directories, allowlisted binaries and commands, no shell, no arbitrary paths — manifests can only pick registered cases and numeric params.
- CPU/RAM/time budgets via `command_timeout`/`run_timeout`; cancellation at command boundaries; retries cannot duplicate jobs (idempotency key).
- GPL: OpenFOAM binaries/source stay in the worker image; nothing is copied into the Apache-2.0 package. Review GPL obligations for your deployment.
- Results carry provenance: solver version, config hash (manifest + solver version), per-step logs and residual summaries. No claim of physical validation from convergence alone.

## Follow-on path

Geometry/mesh import (including an Onshape handoff), parameter sweeps, ParaView/VTK exports and digital-triplet workflows are documented extension points — not part of this scaffold.

## Documentation

- [OpenFOAM v2606 C++ API reference](https://api.openfoam.com/2606/) — note: this is the C++ API, **not** an HTTP endpoint; this integration uses the command-line tools.
- [OpenFOAM v2606 quickstart and pitzDaily](https://doc.openfoam.com/2606/quickstart/)
- [FoaMES read-only mode](../../read-only-mode.md)
