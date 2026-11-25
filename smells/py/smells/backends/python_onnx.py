# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""ONNX Runtime backend — the realistic CPython-on-edge path.

Requires `pip install onnxruntime` (aarch64 wheels exist). numpy is a hard
dependency of onnxruntime and is used to materialise inputs.
"""

from __future__ import annotations

import importlib

from .base import Backend

_ONNX_TENSOR_DTYPES = {
	"tensor(bool)": "bool",
	"tensor(float16)": "float16",
	"tensor(float)": "float32",
	"tensor(double)": "float64",
	"tensor(int8)": "int8",
	"tensor(int16)": "int16",
	"tensor(int32)": "int32",
	"tensor(int64)": "int64",
	"tensor(uint8)": "uint8",
	"tensor(uint16)": "uint16",
	"tensor(uint32)": "uint32",
	"tensor(uint64)": "uint64",
}


def _np_dtype(np, onnx_type: str):
	"""Map an ONNX input type string to a numpy dtype, defaulting to float32."""
	if not onnx_type.startswith("tensor("):
		raise ValueError(f"unsupported ONNX input type {onnx_type!r}")
	return getattr(np, _ONNX_TENSOR_DTYPES.get(onnx_type, "float32"))


class OnnxBackend(Backend):
	name = "python_onnx"

	def __init__(self):
		self._session = None
		self._np = None
		self._inputs = []
		self._input_dtypes = []

	def load(self, model_path: str, manifest: dict) -> None:
		ort = importlib.import_module("onnxruntime")
		np = importlib.import_module("numpy")
		self._np = np
		self._session = ort.InferenceSession(model_path, providers=["CPUExecutionProvider"])
		self._inputs = self._session.get_inputs()
		self._input_dtypes = [_np_dtype(np, i.type) for i in self._inputs]

	def infer(self, inputs: list):
		feeds = {
			i.name: self._np.asarray(t, dtype=dtype)
			for i, t, dtype in zip(self._inputs, inputs, self._input_dtypes, strict=True)
		}
		return self._session.run(None, feeds)

	@staticmethod
	def versions() -> dict:
		try:
			ort = importlib.import_module("onnxruntime")
			return {"onnxruntime": ort.__version__}
		except Exception:
			return {}

	@staticmethod
	def runtime() -> str:
		import platform

		return f"CPython {platform.python_version()}"

	@staticmethod
	def artifact_size_bytes() -> int | None:
		# For interpreted backends the meaningful number is runtime+deps, reported as None.
		return None
