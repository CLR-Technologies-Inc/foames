# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Server certificate validation for the OPC UA gateway.

Pure: nothing from Frappe. It needs the `cryptography` package, which asyncua (and Frappe) depend on,
and imports it inside the functions so that the module itself loads anywhere.

The gateway used to take the server certificate as presented, or pin one attached file. With a
trusted-certificates bundle attached to Machine Data Settings, `make_validator` gives asyncua a
`certificate_validator` hook that refuses the connection unless the server's certificate

- is one of the trusted certificates, or chains through them to one (an issuer in the bundle
  signed it, and so on up to a self-signed certificate in the bundle; every certificate in the
  bundle is an anchor, so a pinned leaf and a plant CA work the same way),
- is within its validity period, as is every certificate in the chain,
- and carries the server's application URI in its subjectAltName, when the endpoint says one.

Validation stays a decision about the server; FoaMES never changes anything on it.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable

PEM_BEGIN = b"-----BEGIN CERTIFICATE-----"
PEM_END = b"-----END CERTIFICATE-----"


class ServerCertificateRejected(Exception):
	"""The OPC UA server's certificate failed validation; the message says why."""


def load_certificates(data: bytes) -> list:
	"""Parse a PEM bundle (one or more certificates) or a single DER certificate."""
	from cryptography import x509

	data = data.strip()
	if not data:
		return []
	if PEM_BEGIN in data:
		certificates = []
		rest = data
		while True:
			start = rest.find(PEM_BEGIN)
			if start < 0:
				break
			end = rest.find(PEM_END, start)
			if end < 0:
				raise ValueError("PEM certificate without an END line")
			end += len(PEM_END)
			certificates.append(x509.load_pem_x509_certificate(rest[start:end]))
			rest = rest[end:]
		return certificates
	return [x509.load_der_x509_certificate(data)]


def certificate_uris(cert) -> list[str]:
	"""The URI entries of the certificate's subjectAltName, which OPC UA uses for the application URI."""
	from cryptography import x509

	try:
		san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
	except x509.ExtensionNotFound:
		return []
	return list(san.get_values_for_type(x509.UniformResourceIdentifier))


def _der(cert) -> bytes:
	from cryptography.hazmat.primitives.serialization import Encoding

	return cert.public_bytes(Encoding.DER)


def is_signed_by(cert, issuer) -> bool:
	"""True when `issuer` is the certificate's issuer by name and its key verifies the signature."""
	if cert.issuer != issuer.subject:
		return False
	try:
		cert.verify_directly_issued_by(issuer)
	except Exception:
		return False
	return True


def find_chain(cert, trusted: Iterable) -> list | None:
	"""The chain from `cert` to a trusted anchor, or None.

	Every certificate in `trusted` is an anchor: a trusted leaf gives a chain of one, a trusted CA a
	chain of the leaf and the CA. Intermediates are followed only when they are in the bundle too."""
	trusted = list(trusted)
	anchors = {_der(t) for t in trusted}
	chain = [cert]
	seen = {_der(cert)}
	current = cert
	while True:
		if _der(current) in anchors:
			return chain
		issuer = next((t for t in trusted if _der(t) not in seen and is_signed_by(current, t)), None)
		if issuer is None:
			return None
		chain.append(issuer)
		seen.add(_der(issuer))
		current = issuer


def _validity(cert) -> tuple[dt.datetime, dt.datetime]:
	# cryptography >= 42 has the timezone-aware pair; older releases only the naive one.
	before = getattr(cert, "not_valid_before_utc", None)
	after = getattr(cert, "not_valid_after_utc", None)
	if before is None or after is None:
		before = cert.not_valid_before.replace(tzinfo=dt.timezone.utc)
		after = cert.not_valid_after.replace(tzinfo=dt.timezone.utc)
	return before, after


def validate_server_certificate(
	cert, trusted: Iterable, *, application_uri: str | None = None, now: dt.datetime | None = None
) -> dict:
	"""Check the server certificate against the trusted bundle, the clock and the application URI.

	`cert` is an x509.Certificate or its DER bytes. Returns a summary dict on success and raises
	`ServerCertificateRejected` otherwise."""
	from cryptography import x509

	if isinstance(cert, (bytes, bytearray)):
		cert = x509.load_der_x509_certificate(bytes(cert))
	now = now or dt.datetime.now(dt.timezone.utc)
	trusted = list(trusted)
	if not trusted:
		raise ServerCertificateRejected("the trusted certificates bundle is empty")

	chain = find_chain(cert, trusted)
	if chain is None:
		raise ServerCertificateRejected(
			f"certificate {cert.subject.rfc4514_string()} is not trusted: it is not in the bundle and "
			"no certificate in the bundle issued it"
		)
	for link in chain:
		before, after = _validity(link)
		if now < before:
			raise ServerCertificateRejected(
				f"certificate {link.subject.rfc4514_string()} is not valid before {before.isoformat()}"
			)
		if now > after:
			raise ServerCertificateRejected(
				f"certificate {link.subject.rfc4514_string()} expired on {after.isoformat()}"
			)

	uris = certificate_uris(cert)
	if application_uri:
		if application_uri not in uris:
			raise ServerCertificateRejected(
				f"the server's application URI {application_uri} is not in the certificate's "
				f"subjectAltName ({', '.join(uris) or 'no URI entry'})"
			)
	return {
		"subject": cert.subject.rfc4514_string(),
		"issuer": cert.issuer.rfc4514_string(),
		"chain_length": len(chain),
		"application_uris": uris,
		"not_valid_after": _validity(cert)[1].isoformat(),
	}


def make_validator(trusted_data: bytes, *, now=None):
	"""An asyncua `Client.certificate_validator` hook: `await hook(certificate, application_description)`.

	The bundle is parsed once, here, so a bad file fails before any connection is attempted."""
	trusted = load_certificates(trusted_data)
	if not trusted:
		raise ValueError("the trusted certificates file holds no certificate")

	async def validate(cert, description=None) -> None:
		uri = getattr(description, "ApplicationUri", None) if description is not None else None
		validate_server_certificate(cert, trusted, application_uri=uri or None, now=now)

	validate.trusted = trusted  # type: ignore[attr-defined]
	return validate
