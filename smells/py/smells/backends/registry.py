# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Backend registry. `auto` picks the adapter from the manifest's model format."""

from __future__ import annotations

from .base import Backend
from .python_ref import JsonMlpBackend

_AUTO = {"smells-json-mlp": "python_ref", "onnx": "python_onnx"}


def get_backend(name: str | None, model_format: str) -> Backend:
	if name in (None, "", "auto"):
		name = _AUTO.get(model_format)
		if not name:
			raise ValueError(f"no adapter for model format {model_format!r}; pass --backend")
	if name == "python_ref":
		return JsonMlpBackend()
	if name == "python_onnx":
		from .python_onnx import OnnxBackend

		return OnnxBackend()
	raise ValueError(f"unknown backend {name!r}; known: python_ref, python_onnx")
