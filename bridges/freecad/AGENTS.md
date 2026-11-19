# AGENTS.md: the FreeCAD bridge

Read this when you work in `bridges/freecad/`. The project-wide rules are in the root [AGENTS.md](../../AGENTS.md); the human guide is [docs/vendors/freecad/](../../docs/vendors/freecad/README.md).

## What it is

A standalone Python package (`foames_freecad`) that inspects `.FCStd` documents in an isolated FreeCAD runtime and returns a versioned JSON manifest to FoaMES. It is **not** an ERP adapter, not part of the Frappe app, and never imported by it: FoaMES invokes the CLI (`python -m foames_freecad …` or the `foames-freecad` script) as a subprocess.

## Package map

All modules import only the standard library — tests need no FreeCAD and no Frappe site:

- `protocol.py` — the versioned request/response envelope (`protocol: 1`), the three actions (`health`, `capabilities`, `inspect`) and the stable error codes.
- `manifest.py` — the inspection manifest schema (`manifest_version: 1`): document identity + SHA-256 provenance, flat object list (id/name/label/type/parent/placement/bbox/properties), units, warnings. `validate_manifest` is the contract check.
- `config.py` — JSON configuration: `freecad_python` (FreeCAD's Python or `freecadcmd`), `allowed_roots`, `max_bytes`, `timeout_seconds`, optional `probe_script`.
- `inspect.py` — guardrail enforcement (`check_path`: `.FCStd` suffix + allowed roots; `check_size`), the subprocess runner, `inspect_document` and `health`. Errors map to protocol codes.
- `freecad_probe.py` — the script that runs **inside** the FreeCAD runtime (FreeCADCmd or FreeCAD's bundled Python). It opens the document read-only, walks objects, and prints the worker JSON. It is never imported by the bridge; it is executed by path.
- `__main__.py` — CLI: `health`, `capabilities`, `inspect <file>`, and `request` (one JSON envelope on stdin → one on stdout, the transport a caller uses).

## Rules

- **Read-only by default.** The probe opens documents without saving, executes no macros, and the bridge exposes no mutation action. Any future export (STEP/BREP/STL) or edit must be a separately scoped, write-gated feature — see the root AGENTS.md write-gate invariant before adding one.
- **Isolation.** `allowed_roots` confines file access; `max_bytes` and `timeout_seconds` bound each run; the probe writes nothing but stdout. Do not add features that read files outside `allowed_roots`, evaluate expressions from document content, or run arbitrary Python supplied by a caller.
- **No FreeCAD import in the bridge.** `import FreeCAD` may appear only inside `freecad_probe.py`, which runs in the FreeCAD runtime. A missing runtime must produce `freecad_missing`/unavailable answers, never an import error in FoaMES.
- **Stable contract.** Bump `PROTOCOL_VERSION`/`MANIFEST_VERSION` on incompatible changes; add error codes, never rename them.
- Tests live in `tests/` and run with `python -m unittest discover -s tests -v` from `bridges/freecad` — no FreeCAD, no Frappe, no network.

## CI

The `bridges` job in `.github/workflows/ci.yml` runs this suite on Python 3.10 and 3.13. Real-FreeCAD smoke tests are opt-in and pinned to a documented FreeCAD release; they must not be required for CI.
