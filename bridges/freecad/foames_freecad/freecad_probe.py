# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Runs INSIDE a FreeCAD Python runtime (FreeCADCmd or FreeCAD's bundled python).

    FreeCADCmd freecad_probe.py <document.FCStd>
    python freecad_probe.py <document.FCStd>        # when FreeCAD is importable

Prints one JSON document to stdout: document identity, the object tree with
placements and bounding boxes where the objects expose them, a units summary
and warnings. Read-only: the document is opened, inspected and closed; nothing
is saved and no macro is executed. This file is never imported by FoaMES.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

PROBE_VERSION = 1
MAX_OBJECTS = 5000
MAX_NAME = 500


def _text(value, limit=MAX_NAME):
	try:
		return str(value)[:limit]
	except Exception:
		return ""


def _num(value):
	try:
		f = float(value)
	except (TypeError, ValueError):
		return None
	return f if f == f and abs(f) != float("inf") else None


def _sha256(path):
	digest = hashlib.sha256()
	with open(path, "rb") as f:
		for chunk in iter(lambda: f.read(1024 * 1024), b""):
			digest.update(chunk)
	return digest.hexdigest()


def _placement(obj):
	"""Best-effort placement as plain floats; empty when unavailable."""
	try:
		pl = obj.Placement
		base = pl.Base
		rot = pl.Rotation
		return {
			"x": _num(base.x), "y": _num(base.y), "z": _num(base.z),
			"qx": _num(rot.Q[0]), "qy": _num(rot.Q[1]), "qz": _num(rot.Q[2]), "qw": _num(rot.Q[3]),
		}
	except Exception:
		return {}


def _bbox(obj):
	"""Bounding box via the shape's BoundBox, for solids and shells only."""
	try:
		shape = getattr(obj, "Shape", None)
		if shape is None:
			return None
		bb = shape.BoundBox
		vals = [_num(v) for v in (bb.XMin, bb.YMin, bb.ZMin, bb.XMax, bb.YMax, bb.ZMax)]
		if any(v is None for v in vals):
			return None
		return vals
	except Exception:
		return None


def _properties(obj):
	"""A small, safe property subset: scalars only, strings truncated."""
	out = {}
	try:
		props = obj.PropertiesList
	except Exception:
		return out
	for name in props[:80]:
		if name.startswith("Expression") or name in ("Shape", "Placement"):
			continue
		try:
			value = getattr(obj, name)
		except Exception:
			continue
		if isinstance(value, (bool, int, float, str)):
			out[_text(name, 100)] = _text(value, 200)
		elif isinstance(value, (list, tuple)) and len(value) <= 8:
			out[_text(name, 100)] = [_text(v, 80) for v in value]
	return out


def _children_map(doc):
	children = {}
	try:
		for obj in doc.Objects:
			for child in getattr(obj, "Group", []) or []:
				children[child.Name] = obj.Name
	except Exception:
		pass
	return children


def inspect(path):
	import FreeCAD as App  # noqa: F401 -- only present inside a FreeCAD runtime

	if not os.path.isfile(path):
		return {"error": "not a file: " + path}
	label = os.path.basename(path)
	doc_name = None
	try:
		doc = App.openDocument(path)
		doc_name = doc.Name
		children = _children_map(doc)
		objects = []
		warnings = []
		for obj in doc.Objects[:MAX_OBJECTS]:
			try:
				objects.append(
					{
						"id": _text(obj.Name),
						"name": _text(getattr(obj, "Name", "")),
						"label": _text(getattr(obj, "Label", "")),
						"type": _text(obj.TypeId),
						"parent": _text(children.get(obj.Name, "")),
						"placement": _placement(obj),
						"bbox": _bbox(obj),
						"properties": _properties(obj),
					}
				)
			except Exception as e:
				warnings.append("object skipped: {0}".format(_text(e, 200)))
		if len(doc.Objects) > MAX_OBJECTS:
			warnings.append("object list truncated at {0}".format(MAX_OBJECTS))
		units = {}
		try:
			param = doc.getObject("Params") or {}
			units = {"schema": _text(getattr(doc, "SchemaVersion", ""))}
		except Exception:
			pass
		return {
			"probe_version": PROBE_VERSION,
			"freecad_version": _text(getattr(App, "Version", lambda: "")()),
			"python_version": _text(sys.version.split()[0]),
			"sha256": _sha256(path),
			"byte_size": os.path.getsize(path),
			"document": {
				"name": _text(getattr(doc, "Name", label)),
				"label": _text(getattr(doc, "Label", label)),
				"schema": _text(getattr(doc, "SchemaVersion", "")),
				"program_version": _text(getattr(App, "Version", lambda: "")()),
			},
			"objects": objects,
			"units": units,
			"warnings": warnings,
		}
	finally:
		try:
			if doc_name:
				App.closeDocument(doc_name)
		except Exception:
			pass


def main(argv):
	if len(argv) != 2:
		print(json.dumps({"error": "usage: freecad_probe.py <document.FCStd>"}))
		return 2
	try:
		payload = inspect(argv[1])
	except Exception as e:  # FreeCAD-level failure: report, do not traceback into FoaMES
		print(json.dumps({"error": "{0}: {1}".format(type(e).__name__, _text(e, 300))}))
		return 1
	if "error" in payload:
		print(json.dumps(payload))
		return 1
	print(json.dumps(payload))
	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv))
