# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""ONNX Runtime backend — the realistic CPython-on-edge path.

Requires `pip install onnxruntime` (aarch64 wheels exist). numpy is a hard
dependency of onnxruntime and is used to materialise inputs.
"""

from __future__ import annotations

import importlib

from .base import Backend


class OnnxBackend(Backend):
	name = "python_onnx"

	def __init__(self):
		self._session = None
		self._input_names = []

	def load(self, model_path: str, manifest: dict) -> None:
		ort = importlib.import_module("onnxruntime")
		np = importlib.import_module("numpy")
		self._np = np
		self._session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
		self._input_names = [i.name for i in self._session.get_inputs()]

	def infer(self, inputs: list):
		feeds = {
			name: self._np.asarray(t, dtype=self._np.float32)
			for name, t in zip(self._input_names, inputs)
		}
		return self._session.run(None, feeds)

	def versions(self) -> dict:
		try:
			ort = importlib.import_module("onnxruntime")
			return {"onnxruntime": ort.__version__}
		except Exception:
			return {}

	def runtime(self) -> str:
		import platform

		return f"CPython {platform.python_version()}"

	def artifact_size_bytes(self) -> int | None:
		# For interpreted backends the meaningful number is runtime+deps, reported as None.
		return None
