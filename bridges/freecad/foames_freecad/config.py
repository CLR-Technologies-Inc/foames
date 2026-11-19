# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Bridge configuration: where the FreeCAD runtime is and what it may touch.

Configuration is a JSON file; secrets never belong in it (this bridge needs
none). `allowed_roots` confines inspection to operator-chosen directories;
`max_bytes` and `timeout_seconds` bound each run. This module imports nothing
outside the standard library.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

DEFAULT_MAX_BYTES = 200 * 1024 * 1024  # 200 MiB
DEFAULT_TIMEOUT = 120.0
PROBE_NAME = "freecad_probe.py"


class ConfigError(Exception):
	pass


@dataclass
class Config:
	#: Path to FreeCAD's Python (or `freecadcmd`/`FreeCADCmd`); empty means "probe PATH".
	freecad_python: str = ""
	#: Directories inspection may read from; empty means the current directory only.
	allowed_roots: list = field(default_factory=list)
	max_bytes: int = DEFAULT_MAX_BYTES
	timeout_seconds: float = DEFAULT_TIMEOUT
	#: Optional: explicit path to freecad_probe.py (default: beside this package).
	probe_script: str = ""

	@classmethod
	def from_dict(cls, data: dict) -> "Config":
		if not isinstance(data, dict):
			raise ConfigError("configuration must be a JSON object")
		roots = data.get("allowed_roots") or []
		if not isinstance(roots, list) or not all(isinstance(r, str) for r in roots):
			raise ConfigError("allowed_roots must be a list of directory paths")
		max_bytes = int(data.get("max_bytes") or DEFAULT_MAX_BYTES)
		if max_bytes <= 0:
			raise ConfigError("max_bytes must be positive")
		timeout = float(data.get("timeout_seconds") or DEFAULT_TIMEOUT)
		if timeout <= 0:
			raise ConfigError("timeout_seconds must be positive")
		return cls(
			freecad_python=str(data.get("freecad_python") or ""),
			allowed_roots=[os.path.abspath(os.path.expanduser(r)) for r in roots],
			max_bytes=max_bytes,
			timeout_seconds=timeout,
			probe_script=str(data.get("probe_script") or ""),
		)

	@classmethod
	def load(cls, path: str) -> "Config":
		try:
			with open(path, "r", encoding="utf-8") as f:
				data = json.load(f)
		except OSError as e:
			raise ConfigError("cannot read configuration {0}: {1}".format(path, e)) from e
		except ValueError as e:
			raise ConfigError("configuration {0} is not valid JSON: {1}".format(path, e)) from e
		return cls.from_dict(data)

	def default_probe_script(self) -> str:
		import foames_freecad

		return os.path.join(os.path.dirname(os.path.abspath(foames_freecad.__file__)), PROBE_NAME)

	def probe(self) -> str:
		return self.probe_script or self.default_probe_script()
