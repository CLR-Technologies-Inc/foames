# FreeCAD

FoaMES can inspect native [FreeCAD](https://www.freecad.org/) documents — parts, assemblies, drawings — through a read-only bridge that runs **outside** the Frappe process. The bridge reports what a `.FCStd` document contains (objects, hierarchy, placements, bounding boxes, units) as a versioned JSON manifest, giving engineering and quality workflows structured design metadata without a CAD licence in the MES runtime and without ever modifying the source document.

FreeCAD remains the CAD system of record. This is document *inspection*, not editing, and not a PDM sync.

## What ships

| Piece | Where |
| --- | --- |
| Bridge package (`foames_freecad`) | `bridges/freecad/` |
| In-FreeCAD probe script | `bridges/freecad/foames_freecad/freecad_probe.py` |
| Configuration example | `bridges/freecad/examples/freecad.json` |
| Agent-facing rules | `bridges/freecad/AGENTS.md` |

## How it works

```
FoaMES / caller ──JSON envelope──▶ foames-freecad ──subprocess──▶ FreeCAD runtime
        ◀──manifest JSON──────────  (protocol v1)   ◀──worker JSON── freecad_probe.py
```

- The bridge never imports FreeCAD. It shells out to a FreeCAD Python runtime you configure (`freecad_python`, or `freecadcmd` on `PATH`) running `freecad_probe.py`, which opens the document read-only and prints JSON.
- `health` and `capabilities` report the runtime and the contract without touching a document; `inspect` returns the manifest.
- Everything is bounded: `allowed_roots` confines which directories can be read, `max_bytes` caps document size, `timeout_seconds` kills runaway inspections, and only `.FCStd` files are accepted.

## Setup

1. Install FreeCAD (any current release; the probe uses only stable document APIs — validate against the release you pin).
2. Install the bridge next to the other bridges:

   ```bash
   cd bridges/freecad
   pip install .
   ```

3. Write a configuration (see `examples/freecad.json`):

   ```json
   {
     "freecad_python": "",
     "allowed_roots": ["C:/cad/documents"],
     "max_bytes": 209715200,
     "timeout_seconds": 120
   }
   ```

   Leave `freecad_python` empty to use `freecadcmd` on `PATH`, or point it at FreeCAD's bundled Python.

4. Check it:

   ```bash
   python -m foames_freecad health --config freecad.json
   python -m foames_freecad inspect --config freecad.json part.FCStd
   ```

## The contract

Requests and responses are versioned JSON envelopes (`protocol: 1`):

```json
{"protocol": 1, "action": "inspect", "params": {"path": "part.FCStd"}}
```

```json
{"protocol": 1, "ok": true, "result": {"manifest_version": 1, "path": "...", "sha256": "...", "objects": [...]}}
```

The manifest carries the document's SHA-256 (provenance), a flat object list with types, parents, placements and bounding boxes where exposed, a units summary, and warnings for anything unreadable. Error responses use stable codes (`freecad_missing`, `path_rejected`, `too_large`, `timeout`, `document_unreadable`, `unsupported_protocol`, …).

## Limits

- **Read-only.** No save, no macro execution, no expression evaluation, no arbitrary Python from document content. Source files are opened read-only and never written.
- **Metadata, not geometry.** The manifest describes objects; heavy geometry export (STEP/BREP/STL) is a deliberate follow-up, not part of this scaffold.
- **Isolated runtime.** Inspection runs in the FreeCAD process only; Frappe and the bridge contain no FreeCAD dependency.

## Follow-on path

Geometry export for validation/metrology workflows, P&ID or Onshape handoffs, and any mutation would each be separate, write-gated proposals reviewed against `docs/read-only-mode.md` — none is enabled here.

## Documentation

- [FreeCAD Python API](https://wiki.freecad.org/FreeCAD_API)
- [FreeCAD source documentation](https://freecad.github.io/SourceDoc/)
- [FoaMES adapters and bridges](../../adapters.md)
