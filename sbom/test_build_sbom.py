# Copyright (c) 2026, CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for build_sbom.py. Standard library only: python -m unittest discover -s sbom"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_sbom

ENV_BOM = {
	"bomFormat": "CycloneDX",
	"specVersion": "1.7",
	"metadata": {
		"tools": {
			"components": [{"type": "application", "name": "cyclonedx-py", "version": "7.2.1"}],
		}
	},
	"components": [
		{"bom-ref": "frappe==15.0.0", "type": "library", "name": "frappe", "version": "15.0.0"},
		{"bom-ref": "requests==2.32.0", "type": "library", "name": "requests", "version": "2.32.0"},
		{"bom-ref": "paho-mqtt==2.1.0", "type": "library", "name": "paho_mqtt", "version": "2.1.0"},
		{"bom-ref": "asyncua==1.1.5", "type": "library", "name": "asyncua", "version": "1.1.5"},
		{"bom-ref": "cryptography==44.0.0", "type": "library", "name": "cryptography", "version": "44.0.0"},
		{"bom-ref": "pip==25.0", "type": "library", "name": "pip", "version": "25.0"},
	],
	"dependencies": [
		{"ref": "frappe==15.0.0", "dependsOn": ["requests==2.32.0"]},
		{"ref": "asyncua==1.1.5", "dependsOn": ["cryptography==44.0.0", "requests==2.32.0"]},
		{"ref": "requests==2.32.0"},
		{"ref": "paho-mqtt==2.1.0"},
		{"ref": "cryptography==44.0.0"},
		{"ref": "pip==25.0"},
	],
}


def build(env_bom=ENV_BOM):
	return build_sbom.build_bom(
		env_bom,
		build_sbom.load_json(build_sbom.HERE / "curated.json"),
		app_version="0.0.1",
		commit="abc123",
		frappe_line="v15",
		timestamp="2026-11-01T00:00:00Z",
	)


class TestBuildSbom(unittest.TestCase):
	def test_envelope_is_cyclonedx_1_7(self):
		bom = build()
		self.assertEqual(bom["specVersion"], "1.7")
		self.assertEqual(bom["$schema"], build_sbom.SCHEMA_URL)
		self.assertTrue(bom["serialNumber"].startswith("urn:uuid:"))
		self.assertEqual(bom["metadata"]["distributionConstraints"], {"tlp": "CLEAR"})

	def test_serial_number_is_stable_per_commit_and_frappe_line(self):
		self.assertEqual(build()["serialNumber"], build()["serialNumber"])
		other = build_sbom.build_bom(
			ENV_BOM,
			build_sbom.load_json(build_sbom.HERE / "curated.json"),
			app_version="0.0.1",
			commit="abc123",
			frappe_line="v16",
			timestamp="2026-11-01T00:00:00Z",
		)
		self.assertNotEqual(build()["serialNumber"], other["serialNumber"])

	def test_subject_is_foames_with_license_and_commit(self):
		root = build()["metadata"]["component"]
		self.assertEqual(root["bom-ref"], "foames")
		self.assertEqual(root["licenses"][0]["license"]["id"], "Apache-2.0")
		self.assertIn({"name": "foames:git:commit", "value": "abc123"}, root["properties"])
		self.assertEqual(root["purl"], "pkg:github/clr-technologies-inc/foames@abc123")

	def test_scopes_follow_the_graph(self):
		scopes = {c["name"]: c.get("scope") for c in build()["components"]}
		self.assertEqual(scopes["frappe"], "required")
		self.assertEqual(scopes["requests"], "required")  # needed by Frappe and by asyncua
		self.assertEqual(scopes["paho_mqtt"], "optional")
		self.assertEqual(scopes["asyncua"], "optional")
		self.assertEqual(scopes["cryptography"], "optional")  # only via asyncua
		self.assertEqual(scopes["pip"], "excluded")  # in the scan venv only
		self.assertEqual(scopes["erpnext"], "optional")

	def test_root_depends_on_frappe_optionals_crypto_and_services(self):
		bom = build()
		root = next(d for d in bom["dependencies"] if d["ref"] == "foames")
		for ref in (
			"frappe==15.0.0",
			"paho-mqtt==2.1.0",
			"asyncua==1.1.5",
			"pkg:github/frappe/erpnext",
			"crypto:algorithm:hmac-sha256",
			"service:sap-s4hana",
		):
			self.assertIn(ref, root["dependsOn"])
		self.assertNotIn("pip==25.0", root["dependsOn"])

	def test_every_reference_resolves(self):
		bom = build()
		refs = {c["bom-ref"] for c in bom["components"]}
		refs |= {s["bom-ref"] for s in bom["services"]}
		refs |= {t["bom-ref"] for t in bom["metadata"]["tools"]["components"]}
		refs |= {bom["metadata"]["component"]["bom-ref"], bom["metadata"]["supplier"]["bom-ref"]}
		for dependency in bom["dependencies"]:
			self.assertIn(dependency["ref"], refs)
			for target in dependency.get("dependsOn", []):
				self.assertIn(target, refs)
		for citation in bom["citations"]:
			self.assertIn(citation["attributedTo"], refs)
			self.assertEqual(len([k for k in ("pointers", "expressions") if k in citation]), 1)

	def test_bom_refs_are_unique(self):
		bom = build()
		refs = [c["bom-ref"] for c in bom["components"]]
		refs += [s["bom-ref"] for s in bom["services"]]
		refs += [t["bom-ref"] for t in bom["metadata"]["tools"]["components"]]
		refs += [bom["metadata"]["component"]["bom-ref"], bom["metadata"]["supplier"]["bom-ref"]]
		refs += [c["bom-ref"] for c in bom["citations"]]
		self.assertEqual(len(refs), len(set(refs)))

	def test_scanner_is_cited_for_the_inventory(self):
		bom = build()
		inventory = next(c for c in bom["citations"] if c["bom-ref"] == "citation:inventory")
		self.assertEqual(inventory["attributedTo"], "tool:cyclonedx-py")

	def test_without_a_scan_frappe_is_still_declared(self):
		bom = build({})
		names = {c["name"]: c for c in bom["components"]}
		self.assertEqual(names["frappe"]["scope"], "required")
		self.assertNotIn("citation:inventory", {c["bom-ref"] for c in bom["citations"]})

	def test_crypto_assets_use_1_7_algorithm_families(self):
		crypto = [c for c in build()["components"] if c["type"] == "cryptographic-asset"]
		families = {
			c["name"]: c["cryptoProperties"]["algorithmProperties"]["algorithmFamily"]
			for c in crypto
			if c["cryptoProperties"]["assetType"] == "algorithm"
		}
		self.assertEqual(families, {"HMAC-SHA256": "HMAC", "SHA-256": "SHA-2"})

	def test_curated_source_locations_exist(self):
		curated = build_sbom.load_json(build_sbom.HERE / "curated.json")
		for asset in curated["cryptographic_assets"]:
			for prop in asset.get("properties", []):
				if prop["name"] == "foames:crypto:sourceLocation":
					self.assertTrue((build_sbom.REPO_ROOT / prop["value"]).is_file(), prop["value"])

	def test_output_is_json_serialisable(self):
		json.dumps(build())


if __name__ == "__main__":
	unittest.main()
