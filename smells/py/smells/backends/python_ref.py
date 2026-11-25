# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Zero-dependency reference backend for the smells-json-mlp format.

Model file:

    {"format": "smells-json-mlp",
     "layers": [{"units": 8, "activation": "relu",
                 "weights": [[...]],   # [out][in]
                 "bias": [...]}]}

Pure Python, so it runs on the smallest Linux image and doubles as the
correctness reference the ONNX adapter is checked against.
"""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from pathlib import Path

from .base import Backend, flatten


def _sigmoid(x: float) -> float:
	if x >= 0:
		return 1.0 / (1.0 + math.exp(-x))
	e = math.exp(x)
	return e / (1.0 + e)


_ACTIVATIONS: dict[str, Callable[[float], float]] = {
	"linear": lambda x: x,
	"relu": lambda x: max(0.0, x),
	"sigmoid": _sigmoid,
	"tanh": math.tanh,
}


def _check_layer(weights, bias):
	"""Validate a layer's weights and bias; returns them with bias defaulted to zeros."""
	if (
		not isinstance(weights, list)
		or not weights
		or not all(isinstance(row, list) and row for row in weights)
	):
		raise ValueError("layer 'weights' must be a non-empty list of non-empty rows")
	width = len(weights[0])
	if any(len(row) != width for row in weights):
		raise ValueError("layer 'weights' rows must all have the same length")
	if not bias:
		return weights, [0.0] * len(weights)
	if not isinstance(bias, list) or len(bias) != len(weights):
		raise ValueError(f"layer 'bias' must have one entry per output row, got {bias!r}")
	return weights, bias


class JsonMlpBackend(Backend):
	name = "python_ref"

	def __init__(self):
		self._layers = []

	def load(self, model_path: str, manifest: dict) -> None:
		data = json.loads(Path(model_path).read_text(encoding="utf-8"))
		if data.get("format") != "smells-json-mlp":
			raise ValueError(f"{model_path} is not a smells-json-mlp model")
		self._layers = []
		for layer in data["layers"]:
			act = layer.get("activation", "linear")
			if act not in _ACTIVATIONS:
				raise ValueError(f"unknown activation {act!r}")
			weights, bias = _check_layer(layer.get("weights"), layer.get("bias"))
			self._layers.append((weights, bias, _ACTIVATIONS[act]))

	def infer(self, inputs: list):
		# One input tensor expected; extra inputs are concatenated for convenience.
		x = flatten(inputs[0] if len(inputs) == 1 else [v for t in inputs for v in flatten(t)])
		for weights, bias, act in self._layers:
			if len(x) != len(weights[0]):
				raise ValueError(f"input width {len(x)} does not match layer width {len(weights[0])}")
			x = [
				act(sum(w * v for w, v in zip(row, x, strict=True)) + b)
				for row, b in zip(weights, bias, strict=True)
			]
		return x

	@staticmethod
	def versions() -> dict:
		import platform

		return {"python": platform.python_version()}

	@staticmethod
	def runtime() -> str:
		import platform

		return f"CPython {platform.python_version()}"
