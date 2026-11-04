# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""OPC UA message security, certificates and username auth taken from Machine Data Settings.
asyncua is optional, so `apply_security` runs against stand-in modules and a stand-in client."""

import asyncio
import sys
import types
from unittest import mock

import frappe

from foames.foames_mes.gateway import opcua
from foames.tests_compat import IntegrationTestCase


def attach(name, *, private=True):
	return frappe.get_doc(
		{"doctype": "File", "file_name": name, "content": f"test {name}", "is_private": int(private)}
	).insert(ignore_permissions=True)


def settings(**values):
	key_pass = values.pop("key_pass", None)
	base = {
		"opcua_security_mode": "None",
		"opcua_security_policy": "Basic256Sha256",
		"opcua_client_certificate": None,
		"opcua_private_key": None,
		"opcua_server_certificate": None,
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

	async def set_security(self, *args, **kwargs):
		self.calls.append(("set_security", args, kwargs))

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
		[(name, args, kwargs), user, password] = client.calls
		self.assertEqual(name, "set_security")
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

	def test_saving_settings_validates_security(self):
		doc = frappe.get_single("Machine Data Settings")
		doc.opcua_security_mode = "SignAndEncrypt"
		doc.opcua_client_certificate = None
		doc.opcua_private_key = None
		with self.assertRaises(frappe.ValidationError):
			doc.save()
