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

	@staticmethod
	def peak_memory_bytes() -> int | None:
		"""Backend-private peak memory if measurable; the harness uses process RSS."""
		return None

	@staticmethod
	def artifact_size_bytes() -> int | None:
		"""Deployed artifact size (binary for compiled backends); None if not meaningful."""
		return None

	@staticmethod
	def versions() -> dict:
		return {}

	@staticmethod
	def runtime() -> str | None:
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
