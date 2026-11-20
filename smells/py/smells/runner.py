# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""The benchmark runner: manifest -> warmup -> timed inferences -> result JSON.

Implements the contract in smells/DESIGN.md. `run()` returns the result dict;
`write_result()` persists it under results/.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from . import metrics
from .backends.registry import get_backend
from .manifest import make_inputs, model_path

SCHEMA = "smells-result/1"

# Dotted budget keys -> callables producing the metric value from a result's metrics dict.
_BUDGET_GETTERS = {
	"peak_rss_mb": lambda m: m.get("peak_rss_mb"),
	"binary_size_bytes": lambda m: m.get("binary_size_bytes"),
	"cold_start_ms": lambda m: m.get("cold_start_ms"),
	"model_load_ms": lambda m: m.get("model_load_ms"),
	"inferences_per_s": lambda m: m.get("inferences_per_s"),
	"latency_ms.p50": lambda m: (m.get("latency_ms") or {}).get("p50"),
	"latency_ms.p95": lambda m: (m.get("latency_ms") or {}).get("p95"),
	"latency_ms.p99": lambda m: (m.get("latency_ms") or {}).get("p99"),
	"latency_ms.mean": lambda m: (m.get("latency_ms") or {}).get("mean"),
}


def run(manifest: dict, backend_name: str = "auto", t0: float | None = None) -> dict:
	"""Execute one benchmark. `t0` is a perf_counter timestamp for cold-start
	approximation; callers that care pass their process start."""
	t0 = t0 if t0 is not None else time.perf_counter()
	model_file = model_path(manifest)
	if not model_file.is_file():
		raise FileNotFoundError(f"model not found: {model_file}")

	backend = get_backend(backend_name, manifest["model"]["format"])
	load_t0 = time.perf_counter()
	backend.load(str(model_file), manifest)
	model_load_ms = (time.perf_counter() - load_t0) * 1000

	inputs = make_inputs(manifest)
	for _ in range(manifest.get("warmup", 0)):
		backend.infer(inputs)

	first_infer_ms = None
	samples = []
	infer_t0 = time.perf_counter()
	for i in range(manifest["iters"]):
		call_t0 = time.perf_counter()
		backend.infer(inputs)
		call_ms = (time.perf_counter() - call_t0) * 1000
		if i == 0:
			first_infer_ms = call_ms
		samples.append(call_ms)
	infer_seconds = time.perf_counter() - infer_t0

	lat = metrics.latency_stats(samples)
	result_metrics = {
		"peak_rss_mb": metrics.peak_rss_mb(),
		"binary_size_bytes": backend.artifact_size_bytes(),
		"cold_start_ms": (time.perf_counter() - t0) * 1000,
		"model_load_ms": model_load_ms,
		"first_infer_ms": first_infer_ms,
		"latency_ms": {k: lat[k] for k in ("p50", "p95", "p99", "mean")},
		"inferences_per_s": manifest["iters"] / infer_seconds if infer_seconds > 0 else None,
	}

	result = {
		"schema": SCHEMA,
		"run": {
			"id": datetime.now(timezone.utc).isoformat(timespec="seconds"),
			"manifest": manifest["_path"],
			"manifest_sha256": manifest["_sha256"],
			"started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
			"duration_s": round(time.perf_counter() - t0, 3),
		},
		"device": metrics.device_info(),
		"backend": {
			"name": backend.name,
			"adapter": type(backend).__name__,
			"runtime": backend.runtime(),
			"versions": {**backend.versions(), **_python_versions()},
		},
		"model": {
			"path": manifest["model"]["path"],
			"format": manifest["model"]["format"],
			"size_bytes": model_file.stat().st_size,
		},
		"metrics": result_metrics,
		"budget": manifest.get("budget"),
		"verdict": _verdict(result_metrics, manifest.get("budget")),
		"notes": [],
	}
	return result


def _python_versions() -> dict:
	import platform

	return {"python": platform.python_version()}


def _verdict(metrics_out: dict, budget: dict | None) -> str:
	if not budget:
		return "unknown"
	unknown = False
	for key, limit in budget.items():
		get = _BUDGET_GETTERS.get(key)
		value = get(metrics_out) if get else None
		if value is None:
			unknown = True
			continue
		if value > limit:
			return "fail"
	return "unknown" if unknown else "pass"


def write_result(result: dict, out_dir: str | Path = "results") -> Path:
	out = Path(out_dir)
	out.mkdir(parents=True, exist_ok=True)
	name = f"{result['run']['id'].replace(':', '')}-{result['backend']['name']}.json"
	path = out / name
	path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
	return path
