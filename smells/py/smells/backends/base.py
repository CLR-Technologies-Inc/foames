# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""The backend protocol, documented for C and Rust adapters to mirror."""

from __future__ import annotations


class Backend:
	"""Base class. Subclasses set `name` and implement load/infer."""

	name = "base"

	def load(self, model_path: str, manifest: dict) -> None:
		raise NotImplementedError

	def infer(self, inputs: list):
		raise NotImplementedError

	def peak_memory_bytes(self) -> int | None:
		"""Backend-private peak memory if measurable; the harness uses process RSS."""
		return None

	def artifact_size_bytes(self) -> int | None:
		"""Deployed artifact size (binary for compiled backends); None if not meaningful."""
		return None

	def versions(self) -> dict:
		return {}

	def runtime(self) -> str | None:
		return None


def flatten(vector) -> list[float]:
	"""Nested lists -> flat list of floats, for MLP-style backends."""
	out = []

	def walk(v):
		if isinstance(v, list):
			for x in v:
				walk(x)
		else:
			out.append(float(v))

	walk(vector)
	return out
