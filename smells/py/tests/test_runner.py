# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Stdlib-only tests for the smells harness. Run: python -m unittest discover -s tests"""

import json
import tempfile
import unittest
from pathlib import Path

from smells import manifest, metrics, runner
from smells.backends.python_ref import JsonMlpBackend


def write_manifest(tmp: Path, model: dict, **overrides) -> Path:
	model_path = tmp / "model.json"
	model_path.write_text(json.dumps(model), encoding="utf-8")
	data = {
		"name": "test",
		"model": {"path": "model.json", "format": "smells-json-mlp"},
		"inputs": [{"shape": [1, 2], "dist": "uniform", "seed": 3}],
		"iters": 10,
		"warmup": 2,
	}
	data.update(overrides)
	path = tmp / "manifest.json"
	path.write_text(json.dumps(data), encoding="utf-8")
	return path


MLP = {
	"format": "smells-json-mlp",
	"layers": [
		{"units": 2, "activation": "relu", "weights": [[1.0, 0.0], [0.0, 1.0]], "bias": [0.0, 0.0]},
		{"units": 1, "activation": "linear", "weights": [[1.0, 1.0]], "bias": [0.0]},
	],
}


class TestManifest(unittest.TestCase):
	def test_load_and_inputs_are_deterministic(self):
		with tempfile.TemporaryDirectory() as d:
			m = manifest.load(write_manifest(Path(d), MLP))
			a, b = manifest.make_inputs(m), manifest.make_inputs(m)
			self.assertEqual(a, b)
			self.assertEqual(m["iters"], 10)

	def test_rejects_bad_manifest(self):
		with tempfile.TemporaryDirectory() as d:
			tmp = Path(d)
			(tmp / "model.json").write_text("{}")
			bad = tmp / "bad.json"
			bad.write_text(json.dumps({"name": "x"}))
			with self.assertRaises(manifest.ManifestError):
				manifest.load(bad)


class TestRefBackend(unittest.TestCase):
	def test_mlp_forward_pass(self):
		with tempfile.TemporaryDirectory() as d:
			mp = write_manifest(Path(d), MLP)
			m = manifest.load(mp)
			backend = JsonMlpBackend()
			backend.load(str(manifest.model_path(m)), m)
			# identity first layer (relu on positive), sum second -> x0 + x1
			inputs = [[[2.0, 3.0]]]
			self.assertAlmostEqual(backend.infer(inputs)[0], 5.0)


class TestRunner(unittest.TestCase):
	def test_run_produces_schema_and_verdict(self):
		with tempfile.TemporaryDirectory() as d:
			tmp = Path(d)
			mp = write_manifest(tmp, MLP, budget={"latency_ms.p95": 60_000})
			m = manifest.load(mp)
			result = runner.run(m, backend_name="python_ref")
			self.assertEqual(result["schema"], "smells-result/1")
			self.assertEqual(result["backend"]["name"], "python_ref")
			self.assertEqual(result["verdict"], "pass")
			self.assertEqual(len(result["metrics"]["latency_ms"]), 4)
			self.assertIsNotNone(result["device"]["arch"])

	def test_verdict_fail_and_unknown(self):
		with tempfile.TemporaryDirectory() as d:
			tmp = Path(d)
			mp = write_manifest(tmp, MLP, budget={"latency_ms.p95": 0.0001})
			m = manifest.load(mp)
			self.assertEqual(runner.run(m, "python_ref")["verdict"], "fail")
			mp2 = write_manifest(tmp, MLP)
			m2 = manifest.load(mp2)
			self.assertEqual(runner.run(m2, "python_ref")["verdict"], "unknown")


class TestMetrics(unittest.TestCase):
	def test_percentile(self):
		self.assertEqual(metrics.percentile([1, 2, 3, 4], 50), 2)
		self.assertIsNone(metrics.percentile([], 50))

	def test_latency_stats_keys(self):
		stats = metrics.latency_stats([1.0, 2.0, 3.0])
		for k in ("p50", "p95", "p99", "mean", "min", "max"):
			self.assertIn(k, stats)


if __name__ == "__main__":
	unittest.main()
