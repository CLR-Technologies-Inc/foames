# foaMES-smells

**Small Model Execution — Lightweight Language Simulation.** A testbench that
measures whether a trained small model can run on a memory-constrained asset —
industrial ARM panels and edge boxes on the plant floor — inside a declared
budget of memory, latency and size.

smells is model-agnostic and language-plural: the same benchmark manifest runs
against Python (CPython + onnxruntime, or a zero-dependency reference backend),
C (ONNX Runtime C API / TFLite) and Rust (`ort` / `candle`) adapters, and every
run emits the same result JSON for comparison and for future foaMES ECL
evidence.

Full design: [DESIGN.md](DESIGN.md). This directory is standalone tooling — it
does not import `foames` and needs no bench.

## Quick start (Python)

```bash
cd smells/py
python -m unittest discover -s tests          # stdlib-only tests
python -m smells run ../manifest.example.json --backend python_ref
# -> results/<run>-python_ref.json, verdict pass|fail|unknown
```

`python_ref` needs nothing installed. For real models:

```bash
pip install -r requirements.txt                # onnxruntime + numpy (aarch64 wheels exist)
python -m smells run my-manifest.json --backend python_onnx
```

## Layout

| Path | What |
| --- | --- |
| `DESIGN.md` | Architecture, metrics, result schema, ECL relationship, roadmap |
| `manifest.example.json` + `models/` | Smoke-test manifest and a tiny JSON-MLP model |
| `py/` | Python harness (runnable today) |
| `c/` | C adapter — design only |
| `rust/` | Rust adapter — design only |
| `results/` | Run outputs (git-ignored) |
