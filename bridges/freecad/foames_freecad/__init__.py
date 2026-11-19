# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Read-only FreeCAD document inspection bridge for FoaMES.

FreeCAD is a desktop CAD application, not a service: this package never imports
FreeCAD. It prepares a versioned request, runs `freecad_probe.py` inside a
separate FreeCAD Python runtime the operator configures, and normalises the
result into a stable JSON manifest. Standard library only.
"""

from foames_freecad.manifest import MANIFEST_VERSION, ManifestError, build_manifest, validate_manifest
from foames_freecad.protocol import PROTOCOL_VERSION, BridgeError, Response, Request, decode, encode

__version__ = "0.1.0"

__all__ = [
	"MANIFEST_VERSION",
	"PROTOCOL_VERSION",
	"BridgeError",
	"ManifestError",
	"Request",
	"Response",
	"build_manifest",
	"decode",
	"encode",
	"validate_manifest",
]
