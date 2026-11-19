# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""The inspection manifest: the stable JSON shape `inspect` returns.

The manifest is what FoaMES (and later validation, metrology or process-planning
steps) consumes. It carries document identity and provenance, a flat list of
objects with their hierarchy, placements and whatever geometric descriptors the
document exposes, plus explicit warnings for anything that could not be read.
Missing properties are reported, never guessed. This module imports nothing
outside the standard library.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

MANIFEST_VERSION = 1

MAX_OBJECTS = 5000
MAX_NAME = 500

# Object types the bridge reports geometry descriptors for; everything else is
# listed with its type and a warning that no geometry was extracted.
_GEOMETRY_TYPES = {"Part::Feature", "PartDesign::Feature", "Part::FeaturePython", "Mesh::Feature"}


class ManifestError(Exception):
	pass


@dataclass
class Manifest:
	version: int
	path: str
	sha256: str
	byte_size: int
	document: dict
	objects: list = field(default_factory=list)
	units: dict = field(default_factory=dict)
	warnings: list = field(default_factory=list)

	def to_dict(self) -> dict:
		return {
			"manifest_version": self.version,
			"path": self.path,
			"sha256": self.sha256,
			"byte_size": self.byte_size,
			"document": self.document,
			"objects": self.objects,
			"units": self.units,
			"warnings": self.warnings,
		}


def sha256_file(path: str) -> str:
	"""SHA-256 of the source document, streamed; provenance for the manifest."""
	digest = hashlib.sha256()
	with open(path, "rb") as f:
		for chunk in iter(lambda: f.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _num(value):
	"""A finite float or None; booleans, strings and NaN never pass as numbers."""
	if isinstance(value, bool) or not isinstance(value, (int, float)):
		return None
	f = float(value)
	return f if math.isfinite(f) else None


def _bbox(value) -> dict | None:
	"""Normalise a bounding box to {xmin,ymin,zmin,xmax,ymax,zmax} floats, or None."""
	if not isinstance(value, (list, tuple)) or len(value) != 6:
		return None
	vals = [_num(v) for v in value]
	if any(v is None for v in vals):
		return None
	return {
		"xmin": vals[0], "ymin": vals[1], "zmin": vals[2],
		"xmax": vals[3], "ymax": vals[4], "zmax": vals[5],
	}


def _text(value, limit: int = MAX_NAME) -> str:
	return str(value)[:limit] if value is not None else ""


def normalise_object(raw: dict, index: int) -> tuple[dict | None, list]:
	"""One worker-reported object into a manifest row, plus warnings it earned."""
	warnings = []
	if not isinstance(raw, dict):
		return None, ["object {0}: not an object, skipped".format(index)]
	obj_type = _text(raw.get("type")) or "Unknown"
	row = {
		"id": _text(raw.get("id") or raw.get("Name")),
		"name": _text(raw.get("name") or raw.get("Name")),
		"label": _text(raw.get("label") or raw.get("Label")),
		"type": obj_type,
		"parent": _text(raw.get("parent")),
	}
	placement = raw.get("placement")
	if isinstance(placement, dict):
		row["placement"] = {k: _num(v) for k, v in placement.items() if _num(v) is not None}
	bbox = _bbox(raw.get("bbox") or raw.get("bound_box"))
	if bbox:
		row["bbox"] = bbox
	elif obj_type in _GEOMETRY_TYPES:
		warnings.append("object {0} ({1}): no bounding box reported".format(row["name"] or index, obj_type))
	if obj_type not in _GEOMETRY_TYPES and obj_type != "App::Part":
		warnings.append("object {0}: type {1} carries no geometry descriptors".format(row["name"] or index, obj_type))
	props = raw.get("properties")
	if isinstance(props, dict):
		row["properties"] = {str(k)[:100]: _text(v, 200) for k, v in list(props.items())[:50]}
	return row, warnings


def build_manifest(path: str, worker_payload: dict, *, byte_size: int | None = None) -> Manifest:
	"""Combine the probe's JSON with file provenance into a validated manifest."""
	if not isinstance(worker_payload, dict):
		raise ManifestError("worker output is not a JSON object")
	digest = worker_payload.get("sha256") or sha256_file(path)
	size = byte_size if byte_size is not None else int(worker_payload.get("byte_size") or 0)
	document = worker_payload.get("document")
	if not isinstance(document, dict):
		document = {}
	objects_raw = worker_payload.get("objects") or []
	if not isinstance(objects_raw, list):
		raise ManifestError("worker objects is not a list")
	objects, warnings = [], []
	for index, raw in enumerate(objects_raw[:MAX_OBJECTS]):
		row, row_warnings = normalise_object(raw, index)
		warnings.extend(row_warnings)
		if row is not None:
			objects.append(row)
	if len(objects_raw) > MAX_OBJECTS:
		warnings.append("object list truncated at {0} entries".format(MAX_OBJECTS))
	units = worker_payload.get("units")
	manifest = Manifest(
		version=MANIFEST_VERSION,
		path=path,
		sha256=str(digest),
		byte_size=size,
		document={
			"name": _text(document.get("name")),
			"label": _text(document.get("label")),
			"schema": _text(document.get("schema")),
			"program_version": _text(document.get("program_version") or document.get("programVersion")),
			"company": _text(document.get("company")),
		},
		objects=objects,
		units=units if isinstance(units, dict) else {},
		warnings=warnings,
	)
	validate_manifest(manifest.to_dict())
	return manifest


def validate_manifest(data: dict) -> None:
	"""Structural check of a manifest dict; raises ManifestError on defects."""
	if not isinstance(data, dict):
		raise ManifestError("manifest is not an object")
	if data.get("manifest_version") != MANIFEST_VERSION:
		raise ManifestError("unsupported manifest_version {0!r}".format(data.get("manifest_version")))
	for key in ("path", "sha256"):
		if not data.get(key):
			raise ManifestError("manifest is missing {0}".format(key))
	if not isinstance(data.get("objects"), list):
		raise ManifestError("manifest objects must be a list")
	if len(data["objects"]) > MAX_OBJECTS:
		raise ManifestError("manifest exceeds {0} objects".format(MAX_OBJECTS))
