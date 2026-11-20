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
from pathlib import Path

from .base import Backend, flatten

_ACTIVATIONS = {
	"linear": lambda x: x,
	"relu": lambda x: max(0.0, x),
	"sigmoid": lambda x: 1.0 / (1.0 + math.exp(-x)),
	"tanh": math.tanh,
}


class JsonMlpBackend(Backend):
	name = "python_ref"

	def load(self, model_path: str, manifest: dict) -> None:
		data = json.loads(Path(model_path).read_text(encoding="utf-8"))
		if data.get("format") != "smells-json-mlp":
			raise ValueError(f"{model_path} is not a smells-json-mlp model")
		self._layers = []
		for layer in data["layers"]:
			act = layer.get("activation", "linear")
			if act not in _ACTIVATIONS:
				raise ValueError(f"unknown activation {act!r}")
			self._layers.append(
				(layer["weights"], layer.get("bias") or [0.0] * len(layer["weights"]), _ACTIVATIONS[act])
			)

	def infer(self, inputs: list):
		# One input tensor expected; extra inputs are concatenated for convenience.
		x = flatten(inputs[0] if len(inputs) == 1 else [v for t in inputs for v in flatten(t)])
		for weights, bias, act in self._layers:
			x = [act(sum(w * v for w, v in zip(row, x)) + b) for row, b in zip(weights, bias)]
		return x

	def versions(self) -> dict:
		import platform

		return {"python": platform.python_version()}

	def runtime(self) -> str:
		import platform

		return f"CPython {platform.python_version()}"
