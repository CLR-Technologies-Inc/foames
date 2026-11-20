# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Manifest loading and input materialisation. Pure stdlib, no Frappe, no numpy."""

from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

REQUIRED = ("name", "model", "inputs", "iters")
MODEL_FORMATS = ("smells-json-mlp", "onnx")
DISTS = ("zeros", "uniform", "normal")


class ManifestError(ValueError):
	pass


def load(path: str | Path) -> dict:
	"""Read and validate a smells manifest. Returns the manifest plus _path/_dir/_sha256."""
	path = Path(path)
	try:
		raw = path.read_bytes()  # NOSONAR -- the operator's manifest path
		data = json.loads(raw)
	except (OSError, ValueError) as e:
		raise ManifestError(f"cannot read manifest {path}: {e}") from e
	if not isinstance(data, dict):
		raise ManifestError("manifest must be a JSON object")
	_validate(data)
	data["_path"] = str(path)
	data["_dir"] = path.parent
	data["_sha256"] = hashlib.sha256(raw).hexdigest()
	return data


def _validate(data: dict) -> None:
	missing = [k for k in REQUIRED if k not in data]
	if missing:
		raise ManifestError(f"manifest missing keys: {', '.join(missing)}")
	_check_model(data["model"])
	_check_inputs(data["inputs"])
	_check_iterations(data)
	_check_budget(data)


def _check_model(model) -> None:
	if not isinstance(model, dict) or not model.get("path") or not model.get("format"):
		raise ManifestError("manifest 'model' needs 'path' and 'format'")
	if model["format"] not in MODEL_FORMATS:
		raise ManifestError(f"unknown model format {model['format']!r}; known: {', '.join(MODEL_FORMATS)}")


def _check_inputs(inputs) -> None:
	if not isinstance(inputs, list) or not inputs:
		raise ManifestError("manifest 'inputs' must be a non-empty list")
	for spec in inputs:
		_check_input(spec)


def _check_iterations(data: dict) -> None:
	for key in ("iters", "warmup"):
		if key in data and (not isinstance(data[key], int) or data[key] < 0):
			raise ManifestError(f"{key!r} must be a non-negative integer")
	data.setdefault("iters", 0)
	if data["iters"] < 1:
		raise ManifestError("manifest 'iters' must be at least 1")
	data.setdefault("warmup", 0)


def _check_budget(data: dict) -> None:
	if "budget" not in data:
		return
	budget = data["budget"]
	if not isinstance(budget, dict):
		raise ManifestError("'budget' must be an object of dotted metric -> limit")
	for key, limit in budget.items():
		if isinstance(limit, bool) or not isinstance(limit, (int, float)):
			raise ManifestError(f"budget limit for {key!r} must be a number, got {limit!r}")


def _check_input(spec):
	if not isinstance(spec, dict) or "shape" not in spec:
		raise ManifestError("each input needs a 'shape' list")
	shape = spec["shape"]
	if not isinstance(shape, list) or not shape or not all(isinstance(d, int) and d > 0 for d in shape):
		raise ManifestError(f"input shape must be a non-empty list of positive ints, got {shape!r}")
	dist = spec.get("dist", "zeros")
	if dist not in DISTS:
		raise ManifestError(f"input dist must be one of {', '.join(DISTS)}, got {dist!r}")


def model_path(manifest: dict) -> Path:
	p = Path(manifest["model"]["path"])
	return p if p.is_absolute() else Path(manifest["_dir"]) / p


def make_inputs(manifest: dict) -> list:
	"""Deterministic input tensors as nested lists, one per declared input, in order."""
	inputs = []
	for i, spec in enumerate(manifest["inputs"]):
		rng = random.Random(spec.get("seed", i))
		shape = spec["shape"]
		count = 1
		for d in shape:
			count *= d
		dist = spec.get("dist", "zeros")
		if dist == "zeros":
			flat = [0.0] * count
		elif dist == "uniform":
			low, high = float(spec.get("low", -1.0)), float(spec.get("high", 1.0))
			flat = [rng.uniform(low, high) for _ in range(count)]
		else:
			mu, sigma = float(spec.get("mu", 0.0)), float(spec.get("sigma", 1.0))
			flat = [rng.gauss(mu, sigma) for _ in range(count)]
		inputs.append(_unflatten(flat, shape))
	return inputs


def _unflatten(flat: list, shape: list):
	if len(shape) == 1:
		return flat
	step = 1
	for d in shape[1:]:
		step *= d
	return [_unflatten(flat[i * step : (i + 1) * step], shape[1:]) for i in range(shape[0])]
