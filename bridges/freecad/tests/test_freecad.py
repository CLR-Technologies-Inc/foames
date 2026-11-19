# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

import json
import os
import tempfile
import unittest

from foames_freecad import manifest as manifest_mod
from foames_freecad.config import Config, ConfigError
from foames_freecad.inspect import InspectError, check_path, inspect_document
from foames_freecad.manifest import ManifestError, build_manifest, normalise_object, validate_manifest
from foames_freecad.protocol import (
	ACTIONS,
	BridgeError,
	PROTOCOL_VERSION,
	decode_request,
	decode_response,
	encode,
)


def worker_payload(**over):
	payload = {
		"probe_version": 1,
		"freecad_version": "0.21.2",
		"python_version": "3.11.10",
		"document": {"name": "bracket", "label": "Bracket", "schema": "4"},
		"objects": [
			{
				"id": "Body", "name": "Body", "label": "Body", "type": "PartDesign::Body",
				"parent": "", "placement": {"x": 0.0, "y": 0.0, "z": 0.0},
				"bbox": [0, 0, 0, 10, 20, 5], "properties": {"Tip": "Pad"},
			},
			{
				"id": "Pad", "name": "Pad", "label": "Pad", "type": "PartDesign::Pad",
				"parent": "Body", "bbox": None,
			},
		],
		"units": {"schema": "4"},
		"warnings": [],
	}
	payload.update(over)
	return payload


class ProtocolTests(unittest.TestCase):
	def test_round_trip(self):
		request = decode_request(json.dumps({"protocol": 1, "action": "inspect", "params": {"path": "a.FCStd"}}))
		self.assertEqual(request.action, "inspect")
		self.assertEqual(request.params["path"], "a.FCStd")

	def test_unknown_action_rejected(self):
		with self.assertRaises(BridgeError) as ctx:
			decode_request(json.dumps({"action": "delete"}))
		self.assertEqual(ctx.exception.code, "unknown_action")

	def test_protocol_mismatch_rejected(self):
		with self.assertRaises(BridgeError) as ctx:
			decode_request(json.dumps({"protocol": 99, "action": "health"}))
		self.assertEqual(ctx.exception.code, "unsupported_protocol")

	def test_bad_json_rejected(self):
		with self.assertRaises(BridgeError):
			decode_request("{nope")

	def test_response_envelope(self):
		text = encode(_ok())
		response = decode_response(text)
		self.assertTrue(response.ok)
		self.assertEqual(response.result["n"], 1)

	def test_error_envelope(self):
		text = encode(_fail("timeout", "too slow"))
		response = decode_response(text)
		self.assertFalse(response.ok)
		self.assertEqual(response.error_code, "timeout")

	def _ok():
		from foames_freecad.protocol import Response

		return Response.success({"n": 1})

	def _fail(code, message):
		from foames_freecad.protocol import Response

		return Response(ok=False, error_code=code, error_message=message)

	def test_actions_cover_the_issue(self):
		self.assertEqual(set(ACTIONS), {"health", "capabilities", "inspect"})
		self.assertEqual(PROTOCOL_VERSION, 1)


class ConfigTests(unittest.TestCase):
	def test_defaults_and_load(self):
		with tempfile.TemporaryDirectory() as tmp:
			path = os.path.join(tmp, "c.json")
			with open(path, "w") as f:
				json.dump({"allowed_roots": [tmp], "max_bytes": 1024, "timeout_seconds": 5}, f)
			config = Config.load(path)
			self.assertEqual(config.max_bytes, 1024)
			self.assertEqual(config.allowed_roots, [os.path.abspath(tmp)])

	def test_bad_values_rejected(self):
		with self.assertRaises(ConfigError):
			Config.from_dict({"allowed_roots": "notalist"})
		with self.assertRaises(ConfigError):
			Config.from_dict({"max_bytes": 0})


class PathTests(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.TemporaryDirectory()
		self.addCleanup(self.tmp.cleanup)
		self.dir = self.tmp.name
		self.doc = os.path.join(self.dir, "part.FCStd")
		with open(self.doc, "wb") as f:
			f.write(b"PK\x03\x04fake")

	def config(self, **kw):
		values = {"allowed_roots": [self.dir], "max_bytes": 1 << 20, "timeout_seconds": 5}
		values.update(kw)
		return Config.from_dict(values)

	def test_allowed_file_passes(self):
		self.assertEqual(check_path(self.doc, self.config()), os.path.abspath(self.doc))

	def test_suffix_enforced(self):
		other = os.path.join(self.dir, "part.step")
		with open(other, "wb") as f:
			f.write(b"x")
		with self.assertRaises(InspectError) as ctx:
			check_path(other, self.config())
		self.assertEqual(ctx.exception.code, "path_rejected")

	def test_outside_roots_rejected(self):
		outside = os.path.join(tempfile.gettempdir(), "elsewhere.FCStd")
		with self.assertRaises(InspectError) as ctx:
			check_path(outside, self.config())
		self.assertEqual(ctx.exception.code, "path_rejected")

	def test_missing_file_rejected(self):
		with self.assertRaises(InspectError) as ctx:
			check_path(os.path.join(self.dir, "gone.FCStd"), self.config())
		self.assertEqual(ctx.exception.code, "document_unreadable")

	def test_traversal_rejected(self):
		# A path that lexically escapes the root resolves outside it.
		link = os.path.join(self.dir, "..", "..", "escape.FCStd")
		with self.assertRaises(InspectError):
			check_path(link, self.config())


class InspectTests(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.TemporaryDirectory()
		self.addCleanup(self.tmp.cleanup)
		self.doc = os.path.join(self.tmp.name, "part.FCStd")
		with open(self.doc, "wb") as f:
			f.write(b"PK\x03\x04fake-document")
		self.config = Config.from_dict(
			{"allowed_roots": [self.tmp.name], "max_bytes": 1 << 20, "timeout_seconds": 5}
		)

	def fake_runner(self, payload=None, code=0, stderr=""):
		def run(path, timeout):
			return json.dumps(payload if payload is not None else worker_payload()), stderr, code
		return run

	def test_manifest_from_fake_runner(self):
		manifest = inspect_document(self.doc, self.config, runner=self.fake_runner())
		data = manifest.to_dict()
		self.assertEqual(data["manifest_version"], 1)
		self.assertEqual(len(data["objects"]), 2)
		self.assertEqual(data["objects"][0]["bbox"]["xmax"], 10.0)
		self.assertTrue(data["sha256"])

	def test_probe_failure_maps_to_error(self):
		with self.assertRaises(InspectError) as ctx:
			inspect_document(self.doc, self.config, runner=self.fake_runner(code=1, stderr="boom\nlast line"))
		self.assertEqual(ctx.exception.code, "document_unreadable")
		self.assertIn("last line", ctx.exception.message)

	def test_non_json_probe_output_rejected(self):
		def run(path, timeout):
			return "not json", "", 0
		with self.assertRaises(InspectError):
			inspect_document(self.doc, self.config, runner=run)

	def test_timeout_maps_to_error(self):
		def run(path, timeout):
			raise InspectError("timeout", "too slow")
		with self.assertRaises(InspectError) as ctx:
			inspect_document(self.doc, self.config, runner=run)
		self.assertEqual(ctx.exception.code, "timeout")


class ManifestTests(unittest.TestCase):
	def test_normalise_object_bbox_and_warnings(self):
		row, warnings = normalise_object(
			{"id": "P", "name": "Pad", "type": "PartDesign::Pad", "bbox": [0, 0, 0, 1, 2, 3]}, 0
		)
		self.assertEqual(row["bbox"]["zmax"], 3.0)
		row2, warnings2 = normalise_object({"id": "S", "name": "Sketch", "type": "Sketcher::SketchObject"}, 1)
		self.assertTrue(any("no geometry" in w for w in warnings2))

	def test_bad_bbox_dropped(self):
		row, _ = normalise_object({"id": "X", "name": "X", "type": "Part::Feature", "bbox": [0, 1]}, 0)
		self.assertNotIn("bbox", row)

	def test_build_manifest_truncates_objects(self):
		with tempfile.NamedTemporaryFile(suffix=".FCStd", delete=False) as f:
			path = f.name
		self.addCleanup(os.unlink, path)
		payload = worker_payload(objects=[{"id": str(i), "name": str(i), "type": "App::DocumentObject"} for i in range(6000)])
		manifest = build_manifest(path, payload)
		self.assertEqual(len(manifest.objects), manifest_mod.MAX_OBJECTS)
		self.assertTrue(any("truncated" in w for w in manifest.warnings))

	def test_validate_rejects_bad_version(self):
		with self.assertRaises(ManifestError):
			validate_manifest({"manifest_version": 99, "path": "x", "sha256": "y", "objects": []})


if __name__ == "__main__":
	unittest.main()
