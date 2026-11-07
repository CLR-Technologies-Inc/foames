# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""OPC UA message security, certificates and username auth taken from Machine Data Settings.
asyncua is optional, so `apply_security` runs against stand-in modules and a stand-in client."""

import asyncio
import datetime as dt
import sys
import types
import unittest
from unittest import mock

import frappe

from foames.foames_mes import site_cbom
from foames.foames_mes.gateway import opcua, opcua_trust
from foames.tests_compat import IntegrationTestCase

try:
	from cryptography.hazmat.primitives.serialization import Encoding

	from foames.foames_mes.gateway.test_opcua_trust import NOW, make_cert
except ImportError:  # pragma: no cover - Frappe depends on cryptography
	Encoding = None


def attach(name, *, private=True, content=None):
	return frappe.get_doc(
		{
			"doctype": "File",
			"file_name": name,
			"content": content if content is not None else f"test {name}",
			"is_private": int(private),
		}
	).insert(ignore_permissions=True)


def pem(cert) -> bytes:
	return cert.public_bytes(Encoding.PEM)


def settings(**values):
	key_pass = values.pop("key_pass", None)
	base = {
		"opcua_security_mode": "None",
		"opcua_security_policy": "Basic256Sha256",
		"opcua_client_certificate": None,
		"opcua_private_key": None,
		"opcua_server_certificate": None,
		"opcua_trusted_certificates": None,
		"opcua_application_uri": None,
		"opcua_username": None,
	}
	base.update(values)
	passwords = {"opcua_password": "op-secret", "opcua_private_key_password": key_pass}
	doc = frappe._dict(base)
	doc.get_password = lambda field, raise_exception=True: passwords.get(field)
	return doc


class FakeClient:
	def __init__(self):
		self.calls = []
		self.application_uri = "urn:freeopcua:client"
		self.certificate_validator = None

	async def set_security(self, *args, **kwargs):
		# asyncua fetches and validates the server certificate inside set_security, so the hook must
		# already be installed here; remember what it saw.
		self.calls.append(("set_security", args, kwargs, self.certificate_validator))

	def set_user(self, user):
		self.calls.append(("set_user", user))

	def set_password(self, password):
		self.calls.append(("set_password", password))


def fake_asyncua():
	ua = types.SimpleNamespace(MessageSecurityMode=types.SimpleNamespace(None_=1, Sign=2, SignAndEncrypt=3))
	policies = types.ModuleType("asyncua.crypto.security_policies")
	for cls in opcua.SECURITY_POLICIES.values():
		setattr(policies, cls, type(cls, (), {}))
	asyncua = types.ModuleType("asyncua")
	asyncua.ua = ua
	crypto = types.ModuleType("asyncua.crypto")
	crypto.security_policies = policies
	return {"asyncua": asyncua, "asyncua.crypto": crypto, "asyncua.crypto.security_policies": policies}


class TestOPCUASecurity(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.cert = attach("gw-cert.der", private=False)
		self.key = attach("gw-key.pem")
		self.server = attach("server-cert.der", private=False)

	def secured(self, **values):
		base = {
			"opcua_security_mode": "SignAndEncrypt",
			"opcua_client_certificate": self.cert.file_url,
			"opcua_private_key": self.key.file_url,
		}
		base.update(values)
		return settings(**base)

	def test_mode_none_needs_no_certificate(self):
		self.assertIsNone(opcua.security_config(settings()))
		self.assertIsNone(opcua.security_config(settings(opcua_security_mode=None)))

	def test_sign_and_encrypt_resolves_the_attached_files(self):
		config = opcua.security_config(
			self.secured(
				opcua_server_certificate=self.server.file_url,
				opcua_application_uri=" urn:plant:foames ",
				key_pass="k3y",
			)
		)
		self.assertEqual((config["mode"], config["policy"]), ("SignAndEncrypt", "Basic256Sha256"))
		self.assertEqual(config["certificate"], self.cert.get_full_path())
		self.assertEqual(config["private_key"], self.key.get_full_path())
		self.assertEqual(config["server_certificate"], self.server.get_full_path())
		self.assertEqual(config["private_key_password"], "k3y")
		self.assertEqual(config["application_uri"], "urn:plant:foames")

	def test_secure_mode_without_certificate_or_key_is_refused(self):
		for missing in ("opcua_client_certificate", "opcua_private_key"):
			with self.assertRaises(frappe.ValidationError):
				opcua.security_config(self.secured(**{missing: None}))

	def test_public_private_key_is_refused(self):
		public_key = attach("leaked-key.pem", private=False)
		with self.assertRaises(frappe.ValidationError):
			opcua.security_config(self.secured(opcua_private_key=public_key.file_url))

	def test_unknown_mode_or_policy_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			opcua.security_config(settings(opcua_security_mode="Encrypt"))
		with self.assertRaises(frappe.ValidationError):
			opcua.security_config(self.secured(opcua_security_policy="Basic128Rsa15"))

	def test_missing_attachment_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			opcua.security_config(self.secured(opcua_client_certificate="/private/files/nope.der"))

	def test_apply_security_configures_policy_mode_and_user(self):
		client = FakeClient()
		modules = fake_asyncua()
		with mock.patch.dict(sys.modules, modules):
			asyncio.run(
				opcua.apply_security(
					client,
					self.secured(
						opcua_security_mode="Sign",
						opcua_security_policy="Aes256_Sha256_RsaPss",
						opcua_application_uri="urn:plant:foames",
						opcua_username="foames",
					),
				)
			)
		[(name, args, kwargs, validator), user, password] = client.calls
		self.assertEqual(name, "set_security")
		self.assertIsNone(validator)  # no trusted bundle: the server certificate is taken as presented
		policies = modules["asyncua.crypto.security_policies"]
		self.assertIs(args[0], policies.SecurityPolicyAes256Sha256RsaPss)
		self.assertEqual(args[1:], (self.cert.get_full_path(), self.key.get_full_path()))
		self.assertEqual(kwargs["mode"], 2)
		self.assertIsNone(kwargs["server_certificate"])
		self.assertEqual(client.application_uri, "urn:plant:foames")
		self.assertEqual((user, password), (("set_user", "foames"), ("set_password", "op-secret")))

	def test_apply_security_with_mode_none_sets_only_the_user(self):
		client = FakeClient()
		asyncio.run(opcua.apply_security(client, settings(opcua_username="foames")))
		self.assertEqual(client.calls, [("set_user", "foames"), ("set_password", "op-secret")])
		self.assertEqual(client.application_uri, "urn:freeopcua:client")

	def test_trusted_bundle_is_checked_when_the_settings_are_saved(self):
		junk = attach("not-a-cert.pem", private=False, content="hello")
		with self.assertRaisesRegex(frappe.ValidationError, "Trusted Certificates"):
			opcua.security_config(self.secured(opcua_trusted_certificates=junk.file_url))
		empty = attach("empty.pem", private=False, content="   ")
		with self.assertRaisesRegex(frappe.ValidationError, "no certificate"):
			opcua.security_config(self.secured(opcua_trusted_certificates=empty.file_url))

	@unittest.skipUnless(Encoding, "cryptography is not installed")
	def test_trusted_bundle_installs_a_validator_before_set_security(self):
		ca, ca_key = make_cert("Plant CA", ca=True)
		server, _ = make_cert("Line 1", issuer=(ca, ca_key), uri="urn:plant:line1")
		stranger, _ = make_cert("Stranger", uri="urn:plant:line1")
		bundle = attach("trusted.pem", private=False, content=pem(ca).decode())
		client = FakeClient()
		with mock.patch.dict(sys.modules, fake_asyncua()):
			asyncio.run(
				opcua.apply_security(client, self.secured(opcua_trusted_certificates=bundle.file_url))
			)
		(name, _args, _kwargs, validator) = client.calls[0]
		self.assertEqual(name, "set_security")
		self.assertIs(validator, client.certificate_validator)
		self.assertEqual(len(validator.trusted), 1)
		# The hook accepts the plant's server and refuses an unknown one, like asyncua will.
		description = types.SimpleNamespace(ApplicationUri="urn:plant:line1")
		asyncio.run(validator(server, description))
		with self.assertRaises(opcua_trust.ServerCertificateRejected):
			asyncio.run(validator(stranger, description))

	@unittest.skipUnless(Encoding, "cryptography is not installed")
	def test_trusted_bundle_needs_an_asyncua_with_the_hook(self):
		ca, _ = make_cert("Plant CA", ca=True)
		bundle = attach("trusted-old.pem", private=False, content=pem(ca).decode())
		client = FakeClient()
		del client.certificate_validator  # asyncua before 1.1 has no such attribute
		with mock.patch.dict(sys.modules, fake_asyncua()):
			with self.assertRaisesRegex(frappe.ValidationError, "asyncua 1.1"):
				asyncio.run(
					opcua.apply_security(client, self.secured(opcua_trusted_certificates=bundle.file_url))
				)

	@unittest.skipUnless(Encoding, "cryptography is not installed")
	def test_site_cbom_reads_the_attached_certificates(self):
		ca, ca_key = make_cert("Plant CA", ca=True)
		gateway, _ = make_cert(
			"FoaMES gateway", uri="urn:plant:foames", not_after=NOW + dt.timedelta(days=30)
		)
		server, _ = make_cert("Line 1", issuer=(ca, ca_key), uri="urn:plant:line1")
		doc = frappe.get_single("Machine Data Settings")
		original = {
			f: doc.get(f)
			for f in (
				"opcua_security_mode",
				"opcua_security_policy",
				"opcua_client_certificate",
				"opcua_private_key",
				"opcua_server_certificate",
				"opcua_trusted_certificates",
			)
		}
		try:
			doc.opcua_security_mode = "SignAndEncrypt"
			doc.opcua_security_policy = "Aes256_Sha256_RsaPss"
			doc.opcua_client_certificate = attach(
				"site-gw.pem", private=False, content=pem(gateway).decode()
			).file_url
			doc.opcua_private_key = self.key.file_url
			doc.opcua_server_certificate = attach(
				"site-server.pem", private=False, content=pem(server).decode()
			).file_url
			doc.opcua_trusted_certificates = attach(
				"site-ca.pem", private=False, content=pem(ca).decode()
			).file_url
			doc.save()
			bom = site_cbom.build(now=NOW)
		finally:
			for field, value in original.items():
				doc.set(field, value)
			doc.save()
		self.assertEqual(bom["bomFormat"], "CycloneDX")
		by_ref = {c["bom-ref"]: c for c in bom["components"]}
		client = by_ref["crypto:certificate:opcua-client"]
		self.assertEqual(
			client["cryptoProperties"]["certificateProperties"]["subjectName"], "CN=FoaMES gateway"
		)
		values = {p["name"]: p["value"] for p in client["properties"]}
		self.assertEqual(values["foames:certificate:daysToExpiry"], "30")
		self.assertEqual(
			by_ref["crypto:certificate:opcua-server"]["cryptoProperties"]["certificateProperties"][
				"issuerName"
			],
			"CN=Plant CA",
		)
		self.assertIn("crypto:certificate:opcua-trusted-1", by_ref)
		suites = by_ref["crypto:protocol:opcua-secure-channel"]["cryptoProperties"]["protocolProperties"][
			"cipherSuites"
		]
		self.assertEqual([s["name"] for s in suites], ["Aes256_Sha256_RsaPss"])
		self.assertIn(
			{"name": "foames:site", "value": frappe.local.site}, bom["metadata"]["component"]["properties"]
		)

	def test_site_cbom_without_opcua_security_still_builds(self):
		bom = site_cbom.build()
		refs = {c["bom-ref"] for c in bom["components"]}
		self.assertIn("crypto:certificate:opcua-client", refs)
		self.assertIn("crypto:algorithm:hmac-sha256", refs)  # the curated assets ship with the source

	def test_saving_settings_validates_security(self):
		doc = frappe.get_single("Machine Data Settings")
		doc.opcua_security_mode = "SignAndEncrypt"
		doc.opcua_client_certificate = None
		doc.opcua_private_key = None
		with self.assertRaises(frappe.ValidationError):
			doc.save()
