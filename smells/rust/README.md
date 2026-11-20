# smells Rust adapter (design)

A `smells-bench` bin crate that runs the same manifests as the Python harness
and emits `smells-result/1` JSON, targeting `aarch64-unknown-linux-gnu` for
plant-floor edge panels.

## Planned shape

```
smells/rust/
  Cargo.toml          bin crate; ort or candle; serde/serde_json; clap
  src/main.rs         CLI: run <manifest> --backend <name> --out <dir>
  src/manifest.rs     manifest parse + deterministic input generation
  src/metrics.rs      latency stats, peak RSS (/proc/self/status VmHWM), device info
  src/result.rs       smells-result/1 schema + verdict
  src/backend_ort.rs  ONNX Runtime via the `ort` crate (same .onnx files as python_onnx)
  src/backend_candle.rs candle alternative — no ONNX Runtime dependency
```

## Build profile (same discipline as native/foames-waft)

```toml
[profile.release]
lto = true
codegen-units = 1
panic = "abort"
strip = true
```

Cross-compile: `rustup target add aarch64-unknown-linux-gnu` + a linker for
the target (gcc-aarch64-linux-gnu). Static-ish linking preferred for panels
without a full userland.

## Contract

Identical to `smells/py/smells/backends/base.py`: `load(model, manifest)` once,
`infer(inputs)` per timed call, warmup then `iters` samples, metrics from
`/proc`, verdict against `budget`. Input generation must match the Python
harness — use a documented PRNG (e.g. SplitMix64 + Box-Muller) rather than
Python's `random`, since CPython's Mersenne Twister is not reproducible in
Rust; DESIGN.md tracks this as an open question.

## Backend choice

- `ort` first: loads the same `.onnx` files as `python_onnx`, giving the
  cleanest three-way comparison (CPython+ORt vs C+ORt vs Rust+ORt isolates
  language/runtime overhead from model format).
- `candle` second: pure-Rust, smaller dependency tree, better for targets
  where ONNX Runtime won't build.
