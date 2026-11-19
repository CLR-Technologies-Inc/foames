# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Case manifest validation: what a caller may ask the runner to simulate.

A case manifest names a built-in or operator-registered case plus bounded
numeric parameters. It never carries commands, paths outside the case
directory, or solver options: the runner maps manifests onto an allowlisted
pipeline (`blockMesh -> checkMesh -> <solver> -> postProcess`). This module is
pure.
"""

from __future__ import annotations

import hashlib
import json
import re

MAX_PARAMS = 32
MAX_PARAM_NAME = 64
MAX_VALUE = 1e12

_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


class ManifestError(Exception):
	pass


def validate_manifest(data: dict, *, known_cases: tuple | list | None = None) -> dict:
	"""Validate and normalise a case manifest; returns a canonical dict."""
	if not isinstance(data, dict):
		raise ManifestError("case manifest must be an object")
	case = data.get("case")
	if not isinstance(case, str) or not _NAME.match(case):
		raise ManifestError("case must be a lowercase name (a-z, 0-9, -, _)")
	if known_cases is not None and case not in known_cases:
		raise ManifestError("unknown case {0!r}; known cases: {1}".format(case, ", ".join(known_cases)))
	params = data.get("params") or {}
	if not isinstance(params, dict) or len(params) > MAX_PARAMS:
		raise ManifestError("params must be an object of at most {0} entries".format(MAX_PARAMS))
	clean = {}
	for key, value in params.items():
		if not isinstance(key, str) or not _NAME.match(key):
			raise ManifestError("param name {0!r} is not a safe identifier".format(key))
		if isinstance(value, bool) or not isinstance(value, (int, float)):
			raise ManifestError("param {0!r} must be numeric".format(key))
		if abs(float(value)) > MAX_VALUE:
			raise ManifestError("param {0!r} is out of range".format(key))
		clean[key] = float(value)
	return {"case": case, "params": clean}


def config_hash(manifest: dict, solver_version: str = "") -> str:
	"""Hash of the canonical manifest plus solver version: provenance for results."""
	canonical = json.dumps({"manifest": manifest, "solver_version": solver_version}, sort_keys=True, separators=(",", ":"))
	return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
