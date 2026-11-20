# foaMES-smells — Small Model Execution: Lightweight Language Simulation

**smells** is a testbench for running trained small models on memory-constrained
assets — the industrial ARM panels and edge boxes that sit next to foaMES
gateways. It answers one question with numbers: *which language runtime can
execute this model, on this device, inside this budget?*

The name is deliberate: like the waft bridge, smells owns measurement only.
It does not run models inside foaMES, does not advise machines, and does not
replace `foames_mes/ecl.py` — it produces the evidence ECL's tier floors are
currently priors for.

## What it is

A model-agnostic benchmark harness with three language backends:

| Backend | Runtime | Status |
| --- | --- | --- |
| `python` | CPython 3.10+ on Linux/ARM; `python_ref` (pure stdlib) and `python_onnx` (onnxruntime) adapters | skeleton in this PR |
| `c` | ONNX Runtime C API or TFLite C on aarch64-linux-gnu | designed, not built |
| `rust` | `ort` (ONNX Runtime) or `candle` on aarch64-unknown-linux-gnu | designed, not built |

Models are **user-supplied**. smells ships no model zoo; it ships the manifest
format, the adapters, and the scoring rules. A "model" is whatever a backend
adapter can load — ONNX today, the smells JSON-MLP reference format for
zero-dependency smoke tests, GGUF or TFLite later.

## Device tiers

The first target is **plant-floor edge**: aarch64 Linux, 1–4 GB RAM, no GPU,
industrial temperature range, often on an isolated OT network. The harness
records the device it ran on (`uname`, RAM, CPU model) in every result so a
pass on a Pi 5 is never mistaken for a pass on a panel PC.

Future tiers, in ascending capability: MCU (MicroPython/C, ~256 KB SRAM),
Linux SBC, plant-floor edge, plant server. The tier is a property of the
result, not of the tool — the same manifest runs everywhere a backend exists.

## How a run works

```
manifest.json ──▶ backend adapter ──▶ warmup ──▶ N timed inferences ──▶ metrics ──▶ result JSON
                     (load model,          (untimed)   (per-call        (RSS peak,     (schema
                      build inputs)                      latency)        p50/p95/p99,   below)
                                                                            throughput,
                                                                            cold start,
                                                                            size, budget)
```

1. The runner reads a **manifest** (see `manifest.example.json`): model path
   and format, input tensors (shape + deterministic fill), iteration count,
   warmup count, and an optional budget.
2. The **backend adapter** loads the model and produces identical inputs on
   every iteration (seeded), so backends are compared on equal work.
3. Warmup iterations run untimed; timed iterations record per-call latency.
4. Metrics are collected around the whole process where the OS allows:
   peak RSS (`getrusage`/`/proc`), wall cold-start (process spawn to first
   inference), binary/runtime size, per-call latency percentiles, throughput.
5. A **result JSON** is written. If the manifest declared a budget, the
   result carries `verdict: pass|fail` per budget line.

## Metrics

| Metric | Definition | Source |
| --- | --- | --- |
| `peak_rss_mb` | Peak resident set size of the whole benchmark process | `resource.getrusage` (Linux), `/proc/self/status` fallback |
| `binary_size_bytes` | Size of the deployed artifact (binary, or runtime+deps manifest for interpreted) | adapter-reported |
| `cold_start_ms` | Process start → first inference complete | runner wall clock around spawn, or in-process approximation |
| `latency_ms.p50/p95/p99` | Per-inference wall time percentiles | `time.perf_counter` around `infer()` |
| `inferences_per_s` | `iters / total_infer_seconds` | derived |
| `model_load_ms` | Adapter load time, reported separately from inference | adapter |

Energy (joules/mW) is a stated non-goal for v1 — plant-floor panels rarely
expose it; where they do (e.g. INA219, RAPL on x86) a backend may add an
`energy` block without schema changes.

## Result schema (v1)

```json
{
  "schema": "smells-result/1",
  "run": {
    "id": "2026-11-19T…Z", "manifest": "manifest.json", "manifest_sha256": "…",
    "started_utc": "…", "duration_s": 12.3
  },
  "device": {"arch": "aarch64", "os": "linux", "cpu_model": "…", "mem_total_mb": 4096},
  "backend": {"name": "python", "adapter": "python_onnx", "runtime": "CPython 3.12.1", "versions": {"onnxruntime": "1.20"}},
  "model": {"path": "model.onnx", "format": "onnx", "size_bytes": 123456},
  "metrics": {
    "peak_rss_mb": 182.4, "binary_size_bytes": null, "cold_start_ms": 410.2,
    "model_load_ms": 95.0,
    "latency_ms": {"p50": 3.1, "p95": 4.8, "p99": 7.2, "mean": 3.4},
    "inferences_per_s": 294.1
  },
  "budget": {"peak_rss_mb": 256, "latency_ms.p95": 10},
  "verdict": "pass",
  "notes": []
}
```

`verdict` is `pass` only when every declared budget line holds;
`unknown` when no budget was declared; budget keys are dotted paths into
`metrics`.

## Relation to ECL

`foames_mes/ecl.py` maps equipment complexity to a *minimum model tier*
(`oss`/`baseline`/`frontier`) using dated priors. smells supplies the missing
measurement half:

- A smells result says "runtime X + model Y needs Z MB RSS and W ms p95 on
  device class D" — evidence for whether an `oss`-tier edge runtime can serve
  a given machine's agent tasks.
- The planned integration is a read-only importer: smells results land as
  files (or a small API later); a future `foames_mes` module can cite them as
  `Agent Suggestion` evidence when recommending tier changes. **No DocType
  and no write path exists yet** — this PR is measurement infrastructure only.
- smells never decides eligibility. `ecl.eligibility()` remains the only
  authority; smells output is advisory evidence a person reviews.

## Backend adapter contract

Every backend implements the same four calls; the harness does not know which
language produced the numbers:

```python
class Backend(Protocol):
    name: str
    def load(self, model_path: str, manifest: dict) -> None: ...
    def infer(self, inputs: list) -> object: ...   # one timed call
    def peak_memory_bytes(self) -> int | None: ... # None if the OS won't say
    def artifact_size_bytes(self) -> int | None: ...
```

Inputs are materialised once per run from the manifest (shape + `zeros` |
`random` + `seed`) and handed to `infer` as a list of arrays in declared
order. Backends must not mutate them between iterations.

### Python (`smells/py/`)

- `python_ref` — pure-stdlib MLP evaluator for the smells JSON format
  (`{"format": "smells-json-mlp", "layers": [...]}`). Zero dependencies;
  exists so the harness runs on the smallest Linux image and as a correctness
  reference for the other adapters.
- `python_onnx` — onnxruntime; requires `pip install onnxruntime` (aarch64
  wheels exist). This is the realistic CPython-on-edge path and the baseline
  smells numbers will be quoted against.
- Later: `python_tflite` (tflite-runtime), `micropython` target.

### C (`smells/c/`, designed)

A small C11 runner linking ONNX Runtime's C API (`onnxruntime_c_api.h`) or
TFLite C. Same manifest JSON parsed with a minimal reader (or a generated
header). Measures via `getrusage`; binary size is `stat` of the stripped
executable — the number that matters on a 128 MB rootfs.

### Rust (`smells/rust/`, designed)

A bin crate `smells-bench` using `ort` (ONNX Runtime bindings, loads the same
`.onnx` files) with `candle` as the no-ONNX-dependency alternative. Cross-
compile target `aarch64-unknown-linux-gnu`; `panic=abort`, stripped, LTO —
same profile discipline as foames-waft. Result JSON emitted by the same
schema so `smells-report` can merge runs across languages.

## Non-goals

- No model training, conversion, or zoo — users bring trained models.
- No accuracy scoring in v1 (top-1 agreement can come later; smells measures
  *fitness to run*, not *quality of answers*).
- No power/energy metrology yet.
- No Frappe integration yet — smells is a standalone tool under `smells/`;
  it must not import `foames` and must run with no bench present.
- No claims about MCU tiers until a MicroPython/C backend exists.

## Layout

```
smells/
  DESIGN.md            this document
  README.md            quick start
  manifest.example.json
  py/                  Python harness (this PR's runnable part)
    smells/            package: manifest, metrics, runner, backends
    tests/
  c/                   C adapter (design only for now)
  rust/                Rust adapter (design only for now)
  results/             run outputs (git-ignored)
```

## Open questions

- Quantisation: report FP32 vs INT8 as separate runs of the same manifest —
  likely just a manifest `model` swap, no schema change needed.
- Should `verdict` support per-device budgets (a `budgets` map keyed by
  device class) rather than one inline budget? Deferred until real panels
  report in.
- Streaming/generative models (token-by-token) need a second timing mode
  (`tokens_per_s`); schema has room via adapter `notes`, revisit when a
  generative backend lands.

## License

Same as the repository: Apache-2.0, copyright CLR Technologies Inc.
Contributions need the CLA in CONTRIBUTING.md.
