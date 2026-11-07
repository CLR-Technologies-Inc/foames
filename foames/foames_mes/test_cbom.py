# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The site CBOM: pure, needs only `cryptography`."""

import datetime as dt
import json
import unittest
from pathlib import Path

try:
	from cryptography import x509
except ImportError:  # pragma: no cover
	x509 = None

from foames.foames_mes import cbom
from foames.foames_mes.gateway.test_opcua_trust import NOW, SERVER_URI, make_cert

CURATED = Path(__file__).resolve().parents[2] / "sbom" / "curated.json"


def curated_assets():
	return json.loads(CURATED.read_text(encoding="utf-8"))["cryptographic_assets"]


@unittest.skipUnless(x509, "cryptography is not installed")
class TestSiteCbom(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.ca, cls.ca_key = make_cert("Plant CA", ca=True)
		cls.gateway, _ = make_cert(
			"FoaMES gateway", uri="urn:plant:foames", not_after=NOW + dt.timedelta(days=40)
		)
		cls.server, _ = make_cert("Line 1 server", issuer=(cls.ca, cls.ca_key), uri=SERVER_URI)

	def test_describe_certificate_reads_the_deployment_facts(self):
		described = cbom.describe_certificate(self.gateway, NOW)
		props = described["certificateProperties"]
		self.assertEqual(props["subjectName"], "CN=FoaMES gateway")
		self.assertEqual(props["issuerName"], "CN=FoaMES gateway")
		self.assertEqual(props["certificateFormat"], "X.509")
		self.assertEqual(props["signatureAlgorithmRef"], "crypto:algorithm:rsa-pkcs1v15-sha256")
		self.assertTrue(props["notValidAfter"].endswith("Z"))
		values = {p["name"]: p["value"] for p in described["properties"]}
		self.assertEqual(values["foames:certificate:status"], "active")
		self.assertEqual(values["foames:certificate:daysToExpiry"], "40")
		self.assertEqual(values["foames:certificate:keyAlgorithm"], "RSA")
		self.assertEqual(values["foames:certificate:keySize"], "2048")
		self.assertEqual(values["foames:certificate:applicationUri"], "urn:plant:foames")
		self.assertEqual(len(values["foames:certificate:fingerprintSha256"]), 64)

	def test_status_follows_the_clock(self):
		self.assertEqual(cbom.certificate_status(self.gateway, NOW + dt.timedelta(days=41))[0], "expired")
		self.assertEqual(
			cbom.certificate_status(self.gateway, NOW - dt.timedelta(days=5))[0], "not-yet-valid"
		)

	def build(self, **kwargs):
		kwargs.setdefault(
			"security", {"mode": "SignAndEncrypt", "policy": "Basic256Sha256", "endpoint": "opc.tcp://x:4840"}
		)
		return cbom.build_site_cbom(
			curated_assets(), site="plant.example", app_version="0.0.1", now=NOW, **kwargs
		)

	def test_secure_site_fills_the_certificates_and_keeps_only_its_policy(self):
		bom = self.build(
			client_certificate=self.gateway, server_certificate=self.server, trusted_certificates=[self.ca]
		)
		by_ref = {c["bom-ref"]: c for c in bom["components"]}
		self.assertEqual(bom["specVersion"], "1.7")
		client = by_ref[cbom.CLIENT_CERTIFICATE_REF]["cryptoProperties"]["certificateProperties"]
		self.assertEqual(client["subjectName"], "CN=FoaMES gateway")
		server = by_ref[cbom.SERVER_CERTIFICATE_REF]["cryptoProperties"]["certificateProperties"]
		self.assertEqual(server["issuerName"], "CN=Plant CA")
		trusted = by_ref[f"{cbom.TRUSTED_CERTIFICATE_REF}-1"]
		self.assertEqual(trusted["cryptoProperties"]["certificateProperties"]["subjectName"], "CN=Plant CA")
		key = by_ref[cbom.PRIVATE_KEY_REF]["cryptoProperties"]["relatedCryptoMaterialProperties"]
		self.assertEqual(key["size"], 2048)
		suites = by_ref[cbom.PROTOCOL_REF]["cryptoProperties"]["protocolProperties"]["cipherSuites"]
		self.assertEqual([s["name"] for s in suites], ["Basic256Sha256"])
		root = bom["metadata"]["component"]
		self.assertIn({"name": "foames:site", "value": "plant.example"}, root["properties"])
		self.assertIn({"name": "foames:opcua:endpoint", "value": "opc.tcp://x:4840"}, root["properties"])
		# Every reference resolves and the curated algorithms are still there.
		refs = {c["bom-ref"] for c in bom["components"]}
		self.assertIn("crypto:algorithm:hmac-sha256", refs)
		for dependency in bom["dependencies"]:
			self.assertTrue(dependency["ref"] == cbom.ROOT_REF or dependency["ref"] in refs)
			for target in dependency.get("dependsOn", []):
				self.assertIn(target, refs)
		json.dumps(bom)

	def test_mode_none_lists_no_suite_and_marks_the_certificates(self):
		bom = self.build(security={"mode": "None", "policy": "Basic256Sha256", "endpoint": None})
		by_ref = {c["bom-ref"]: c for c in bom["components"]}
		self.assertNotIn("cipherSuites", by_ref[cbom.PROTOCOL_REF]["cryptoProperties"]["protocolProperties"])
		status = {p["name"]: p["value"] for p in by_ref[cbom.CLIENT_CERTIFICATE_REF]["properties"]}
		self.assertEqual(status["foames:certificate:status"], "not-configured")
		status = {p["name"]: p["value"] for p in by_ref[cbom.SERVER_CERTIFICATE_REF]["properties"]}
		self.assertEqual(status["foames:certificate:status"], "not-pinned")
		self.assertIn(
			{"name": "foames:opcua:securityPolicy", "value": "none"},
			bom["metadata"]["component"]["properties"],
		)

	def test_secure_mode_without_a_certificate_is_marked_missing(self):
		bom = self.build()
		by_ref = {c["bom-ref"]: c for c in bom["components"]}
		status = {p["name"]: p["value"] for p in by_ref[cbom.CLIENT_CERTIFICATE_REF]["properties"]}
		self.assertEqual(status["foames:certificate:status"], "missing")

	def test_works_without_the_curated_file(self):
		bom = cbom.build_site_cbom(
			[],
			site="s",
			app_version="0.0.1",
			now=NOW,
			security={"mode": "Sign", "policy": "Aes256_Sha256_RsaPss"},
			client_certificate=self.gateway,
		)
		refs = [c["bom-ref"] for c in bom["components"]]
		self.assertEqual(refs, [cbom.CLIENT_CERTIFICATE_REF, cbom.SERVER_CERTIFICATE_REF])


if __name__ == "__main__":
	unittest.main()
