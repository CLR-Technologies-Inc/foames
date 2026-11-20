# smells C adapter (design)

A small C11 benchmark runner that links a native inference runtime and emits
the same `smells-result/1` JSON as the Python harness, so results compare
across languages.

## Planned shape

```
smells/c/
  src/main.c          arg parse, run loop, JSON emit (cJSON or jsmn)
  src/manifest.c      minimal manifest reader (model path/format, iters, inputs)
  src/backend_onnx.c  ONNX Runtime C API adapter (onnxruntime_c_api.h)
  src/backend_tflite.c TFLite C adapter (tensorflow/lite/c/common)
  Makefile            -O2 -static-friendly, stripped binary
```

## Contract (mirrors smells/py/smells/backends/base.py)

1. Parse the manifest: model path + format, input shapes/dists/seed, `iters`,
   `warmup`, optional `budget`.
2. Load the model once; materialise the same deterministic inputs the Python
   harness produces (the `smells-json-mlp` reference and `uniform`/`normal`
   fills must match bit-for-bit where feasible — the Python `random` module is
   NOT portable, so for cross-language comparisons inputs should come from a
   shared raw file or a simple LCG documented in DESIGN.md's open questions).
3. Run `warmup` untimed inferences, then `iters` timed ones with
   `clock_gettime(CLOCK_MONOTONIC)`.
4. Report peak RSS via `getrusage(RUSAGE_SELF).ru_maxrss`, binary size via
   `stat` of the stripped executable, latency p50/p95/p99/mean, throughput.
5. Emit `smells-result/1` JSON to stdout or `--out`.

## Why C matters here

On a 128 MB rootfs industrial panel, "Python + onnxruntime" may not fit at
all; a stripped C binary linking ONNX Runtime or TFLite is the floor for
running *any* trained model. smells exists to prove which floor is real.
