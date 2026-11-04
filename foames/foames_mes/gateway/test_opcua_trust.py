# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Server certificate validation for the OPC UA gateway: pure, needs only `cryptography`."""

import asyncio
import datetime as dt
import types
import unittest

try:
	from cryptography import x509
	from cryptography.hazmat.primitives import hashes, serialization
	from cryptography.hazmat.primitives.asymmetric import rsa
	from cryptography.x509.oid import NameOID
except ImportError:  # pragma: no cover - the gateway needs cryptography; Frappe installs it
	x509 = None

from foames.foames_mes.gateway import opcua_trust

NOW = dt.datetime(2026, 11, 4, 12, 0, tzinfo=dt.timezone.utc)
SERVER_URI = "urn:plant:line1:opcua-server"


def make_cert(common_name, *, issuer=None, uri=None, not_before=None, not_after=None, ca=False):
	"""A certificate with its key. Self-signed unless `issuer` is a (certificate, key) pair."""
	key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
	subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
	issuer_name, signing_key = (issuer[0].subject, issuer[1]) if issuer else (subject, key)
	builder = (
		x509.CertificateBuilder()
		.subject_name(subject)
		.issuer_name(issuer_name)
		.public_key(key.public_key())
		.serial_number(x509.random_serial_number())
		.not_valid_before(not_before or NOW - dt.timedelta(days=1))
		.not_valid_after(not_after or NOW + dt.timedelta(days=365))
		.add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
	)
	if uri:
		builder = builder.add_extension(
			x509.SubjectAlternativeName([x509.UniformResourceIdentifier(uri)]), critical=False
		)
	return builder.sign(signing_key, hashes.SHA256()), key


def pem(*certs) -> bytes:
	return b"\n".join(c.public_bytes(serialization.Encoding.PEM) for c in certs)


def der(cert) -> bytes:
	return cert.public_bytes(serialization.Encoding.DER)


@unittest.skipUnless(x509, "cryptography is not installed")
class TestServerCertificateValidation(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.root, cls.root_key = make_cert("Plant Root CA", ca=True)
		cls.intermediate, cls.intermediate_key = make_cert(
			"Plant Issuing CA", issuer=(cls.root, cls.root_key), ca=True
		)
		cls.server, _ = make_cert(
			"Line 1 OPC UA Server", issuer=(cls.intermediate, cls.intermediate_key), uri=SERVER_URI
		)
		cls.stranger, _ = make_cert("Somebody Else", uri=SERVER_URI)

	def validate(self, cert, trusted, **kwargs):
		kwargs.setdefault("now", NOW)
		return opcua_trust.validate_server_certificate(cert, trusted, **kwargs)

	def test_loads_a_pem_bundle_and_a_single_der(self):
		bundle = opcua_trust.load_certificates(pem(self.root, self.intermediate))
		self.assertEqual([c.subject for c in bundle], [self.root.subject, self.intermediate.subject])
		self.assertEqual(opcua_trust.load_certificates(der(self.server))[0], self.server)
		self.assertEqual(opcua_trust.load_certificates(b"  \n"), [])
		with self.assertRaises(ValueError):
			opcua_trust.load_certificates(b"-----BEGIN CERTIFICATE-----\nabc\n")

	def test_a_pinned_leaf_is_trusted_on_its_own(self):
		summary = self.validate(self.server, [self.server])
		self.assertEqual(summary["chain_length"], 1)
		self.assertEqual(summary["application_uris"], [SERVER_URI])

	def test_a_chain_through_the_bundle_is_trusted(self):
		# The issuing CA is an anchor: the chain stops there even when the root is in the bundle too.
		self.assertEqual(self.validate(self.server, [self.intermediate, self.root])["chain_length"], 2)
		self.assertEqual(self.validate(self.server, [self.intermediate])["chain_length"], 2)
		# Only the root in the bundle: the chain walks leaf, intermediate, root when all are given.
		self.assertEqual(self.validate(self.intermediate, [self.root])["chain_length"], 2)
		# The root alone is not enough when the intermediate is not in the bundle.
		with self.assertRaisesRegex(opcua_trust.ServerCertificateRejected, "not trusted"):
			self.validate(self.server, [self.root])

	def test_der_bytes_are_accepted(self):
		self.assertEqual(self.validate(der(self.server), [self.server])["subject"], "CN=Line 1 OPC UA Server")

	def test_an_unknown_certificate_is_rejected(self):
		with self.assertRaisesRegex(opcua_trust.ServerCertificateRejected, "not trusted"):
			self.validate(self.stranger, [self.root, self.intermediate])
		with self.assertRaisesRegex(opcua_trust.ServerCertificateRejected, "empty"):
			self.validate(self.server, [])

	def test_a_forged_issuer_name_does_not_pass(self):
		forged, _ = make_cert("Forged", uri=SERVER_URI)
		# Same issuer name as the real intermediate signs, but a different key signed it.
		forged = (
			x509.CertificateBuilder()
			.subject_name(forged.subject)
			.issuer_name(self.intermediate.subject)
			.public_key(forged.public_key())
			.serial_number(1)
			.not_valid_before(NOW - dt.timedelta(days=1))
			.not_valid_after(NOW + dt.timedelta(days=1))
			.sign(rsa.generate_private_key(65537, 2048), hashes.SHA256())
		)
		self.assertFalse(opcua_trust.is_signed_by(forged, self.intermediate))
		with self.assertRaises(opcua_trust.ServerCertificateRejected):
			self.validate(forged, [self.intermediate, self.root])

	def test_expired_or_not_yet_valid_links_are_rejected(self):
		expired, _ = make_cert(
			"Expired",
			issuer=(self.intermediate, self.intermediate_key),
			uri=SERVER_URI,
			not_after=NOW - dt.timedelta(minutes=1),
		)
		with self.assertRaisesRegex(opcua_trust.ServerCertificateRejected, "expired"):
			self.validate(expired, [self.intermediate])
		future, _ = make_cert("Future", uri=SERVER_URI, not_before=NOW + dt.timedelta(days=1))
		with self.assertRaisesRegex(opcua_trust.ServerCertificateRejected, "not valid before"):
			self.validate(future, [future])
		# An expired CA in the chain fails the leaf too.
		old_ca, old_key = make_cert("Old CA", ca=True, not_after=NOW - dt.timedelta(days=1))
		leaf, _ = make_cert("Leaf", issuer=(old_ca, old_key), uri=SERVER_URI)
		with self.assertRaisesRegex(opcua_trust.ServerCertificateRejected, "Old CA.*expired"):
			self.validate(leaf, [old_ca])

	def test_the_application_uri_must_be_in_the_certificate(self):
		self.validate(self.server, [self.server], application_uri=SERVER_URI)
		with self.assertRaisesRegex(opcua_trust.ServerCertificateRejected, "application URI"):
			self.validate(self.server, [self.server], application_uri="urn:other:server")
		no_uri, _ = make_cert("No URI")
		with self.assertRaisesRegex(opcua_trust.ServerCertificateRejected, "no URI entry"):
			self.validate(no_uri, [no_uri], application_uri=SERVER_URI)
		# Without an endpoint URI to compare, the URI check is skipped.
		self.assertEqual(self.validate(no_uri, [no_uri])["application_uris"], [])

	def test_make_validator_gives_an_asyncua_hook(self):
		validator = opcua_trust.make_validator(pem(self.intermediate, self.root), now=NOW)
		description = types.SimpleNamespace(ApplicationUri=SERVER_URI)
		asyncio.run(validator(self.server, description))
		asyncio.run(validator(der(self.server), None))
		with self.assertRaises(opcua_trust.ServerCertificateRejected):
			asyncio.run(validator(self.stranger, description))
		with self.assertRaises(opcua_trust.ServerCertificateRejected):
			asyncio.run(validator(self.server, types.SimpleNamespace(ApplicationUri="urn:other")))
		with self.assertRaisesRegex(ValueError, "no certificate"):
			opcua_trust.make_validator(b"")


if __name__ == "__main__":
	unittest.main()
