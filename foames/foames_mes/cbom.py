# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""A site's cryptography bill of materials (CBOM) with the certificates it actually deploys.

Pure: nothing from Frappe. `cryptography` is imported inside the functions that read certificates.

The published FoaMES SBOM (see docs/sbom.md) describes the OPC UA gateway's certificates in the
abstract, because subject, issuer, key size and validity belong to the plant that issued them. This
module fills those in for one site: it takes the curated cryptographic assets from `sbom/curated.json`,
the certificates attached to Machine Data Settings and the configured security mode and policy, and
returns a CycloneDX 1.7 document a plant can hand to its own SBOM tooling, which then watches the
certificates expire. Deployment facts that CycloneDX has no standard field for travel as `foames:`
properties, so the document stays valid for every 1.7 consumer.
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import uuid
from collections.abc import Iterable

SPEC_VERSION = "1.7"
SCHEMA_URL = "http://cyclonedx.org/schema/bom-1.7.schema.json"
ROOT_REF = "foames-site"

CLIENT_CERTIFICATE_REF = "crypto:certificate:opcua-client"
SERVER_CERTIFICATE_REF = "crypto:certificate:opcua-server"
TRUSTED_CERTIFICATE_REF = "crypto:certificate:opcua-trusted"
PRIVATE_KEY_REF = "crypto:material:opcua-client-private-key"
PROTOCOL_REF = "crypto:protocol:opcua-secure-channel"

# Certificate signature algorithm OID -> the curated algorithm asset it is an instance of.
SIGNATURE_ALGORITHM_REFS = {
	"1.2.840.113549.1.1.11": "crypto:algorithm:rsa-pkcs1v15-sha256",  # sha256WithRSAEncryption
	"1.2.840.113549.1.1.10": "crypto:algorithm:rsa-pss-sha256",  # RSASSA-PSS
}


def _utc(moment: dt.datetime) -> str:
	return moment.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _validity(cert) -> tuple[dt.datetime, dt.datetime]:
	before = getattr(cert, "not_valid_before_utc", None)
	after = getattr(cert, "not_valid_after_utc", None)
	if before is None or after is None:
		before = cert.not_valid_before.replace(tzinfo=dt.timezone.utc)
		after = cert.not_valid_after.replace(tzinfo=dt.timezone.utc)
	return before, after


def certificate_status(cert, now: dt.datetime) -> tuple[str, int]:
	"""('active' | 'expired' | 'not-yet-valid', days until the certificate expires; negative once it has)."""
	before, after = _validity(cert)
	days = (after - now).days
	if now < before:
		return "not-yet-valid", days
	if now > after:
		return "expired", days
	return "active", days


def public_key_info(cert) -> tuple[str, int | None]:
	"""('RSA' | 'EC' | 'Ed25519' | 'Ed448' | 'other', key size in bits where the key has one)."""
	from cryptography.hazmat.primitives.asymmetric import ec, ed448, ed25519, rsa

	key = cert.public_key()
	if isinstance(key, rsa.RSAPublicKey):
		return "RSA", key.key_size
	if isinstance(key, ec.EllipticCurvePublicKey):
		return "EC", key.curve.key_size
	if isinstance(key, ed25519.Ed25519PublicKey):
		return "Ed25519", 256
	if isinstance(key, ed448.Ed448PublicKey):
		return "Ed448", 456
	return "other", None


def _uris(cert) -> list[str]:
	from cryptography import x509

	try:
		san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
	except x509.ExtensionNotFound:
		return []
	return list(san.get_values_for_type(x509.UniformResourceIdentifier))


def describe_certificate(cert, now: dt.datetime | None = None) -> dict:
	"""The CycloneDX `certificateProperties` of a deployed certificate and the `foames:` properties
	that carry what 1.7 has no field for (status, days to expiry, fingerprint, key, URIs)."""
	from cryptography.hazmat.primitives.serialization import Encoding

	now = now or dt.datetime.now(dt.timezone.utc)
	before, after = _validity(cert)
	status, days = certificate_status(cert, now)
	key_algorithm, key_size = public_key_info(cert)
	der = cert.public_bytes(Encoding.DER)

	certificate_properties = {
		"subjectName": cert.subject.rfc4514_string(),
		"issuerName": cert.issuer.rfc4514_string(),
		"notValidBefore": _utc(before),
		"notValidAfter": _utc(after),
		"certificateFormat": "X.509",
	}
	signature_ref = SIGNATURE_ALGORITHM_REFS.get(cert.signature_algorithm_oid.dotted_string)
	if signature_ref:
		certificate_properties["signatureAlgorithmRef"] = signature_ref

	properties = [
		{"name": "foames:certificate:status", "value": status},
		{"name": "foames:certificate:daysToExpiry", "value": str(days)},
		{"name": "foames:certificate:serialNumber", "value": format(cert.serial_number, "x")},
		{"name": "foames:certificate:fingerprintSha256", "value": hashlib.sha256(der).hexdigest()},
		{"name": "foames:certificate:signatureAlgorithm", "value": cert.signature_algorithm_oid._name},
		{"name": "foames:certificate:keyAlgorithm", "value": key_algorithm},
	]
	if key_size:
		properties.append({"name": "foames:certificate:keySize", "value": str(key_size)})
	for uri in _uris(cert):
		properties.append({"name": "foames:certificate:applicationUri", "value": uri})
	return {
		"certificateProperties": certificate_properties,
		"properties": properties,
		"key_algorithm": key_algorithm,
		"key_size": key_size,
		"status": status,
	}


def _merge_certificate(asset: dict, description: dict) -> None:
	asset.setdefault("cryptoProperties", {"assetType": "certificate"})
	asset["cryptoProperties"]["certificateProperties"] = description["certificateProperties"]
	asset["properties"] = [
		p for p in asset.get("properties", []) if not p["name"].startswith("foames:certificate:")
	] + description["properties"]


def _not_configured(asset: dict, reason: str) -> None:
	asset["properties"] = [
		p for p in asset.get("properties", []) if not p["name"].startswith("foames:certificate:")
	] + [{"name": "foames:certificate:status", "value": reason}]


def build_site_cbom(
	curated_assets: Iterable[dict],
	*,
	site: str,
	app_version: str,
	security: dict,
	client_certificate=None,
	server_certificate=None,
	trusted_certificates: Iterable = (),
	now: dt.datetime | None = None,
) -> dict:
	"""The CycloneDX 1.7 CBOM of one site.

	`curated_assets` are the `cryptographic_assets` of sbom/curated.json (an empty list works, the
	document then holds only the deployed certificates). `security` has `mode`, `policy` and `endpoint`
	from Machine Data Settings. The certificates are x509.Certificate objects or None."""
	now = now or dt.datetime.now(dt.timezone.utc)
	timestamp = _utc(now)
	mode = security.get("mode") or "None"
	policy = security.get("policy") if mode != "None" else None
	secure = mode != "None"

	components = [copy.deepcopy(a) for a in curated_assets]
	by_ref = {c.get("bom-ref"): c for c in components}

	def certificate_asset(ref: str, name: str) -> dict:
		asset = by_ref.get(ref)
		if asset is None:
			asset = {
				"bom-ref": ref,
				"type": "cryptographic-asset",
				"name": name,
				"cryptoProperties": {"assetType": "certificate"},
			}
			components.append(asset)
			by_ref[ref] = asset
		return asset

	client = certificate_asset(CLIENT_CERTIFICATE_REF, "OPC UA gateway application instance certificate")
	if client_certificate is not None:
		description = describe_certificate(client_certificate, now)
		_merge_certificate(client, description)
		key = by_ref.get(PRIVATE_KEY_REF)
		if key is not None and description["key_size"]:
			key.setdefault("cryptoProperties", {}).setdefault("relatedCryptoMaterialProperties", {})[
				"size"
			] = description["key_size"]
	else:
		_not_configured(client, "not-configured" if not secure else "missing")

	server = certificate_asset(SERVER_CERTIFICATE_REF, "OPC UA server certificate (pinned)")
	if server_certificate is not None:
		_merge_certificate(server, describe_certificate(server_certificate, now))
	else:
		_not_configured(server, "not-pinned")

	for index, cert in enumerate(trusted_certificates, start=1):
		asset = {
			"bom-ref": f"{TRUSTED_CERTIFICATE_REF}-{index}",
			"type": "cryptographic-asset",
			"name": f"OPC UA trusted certificate {index}",
			"description": "A certificate in the trusted bundle attached to Machine Data Settings. The "
			"OPC UA gateway accepts a server certificate only when it is one of these or chains to one.",
			"cryptoProperties": {"assetType": "certificate"},
		}
		_merge_certificate(asset, describe_certificate(cert, now))
		components.append(asset)

	protocol = by_ref.get(PROTOCOL_REF)
	if protocol is not None:
		protocol_properties = protocol.setdefault("cryptoProperties", {}).setdefault("protocolProperties", {})
		suites = protocol_properties.get("cipherSuites") or []
		protocol_properties["cipherSuites"] = [s for s in suites if secure and s.get("name") == policy]
		if not protocol_properties["cipherSuites"]:
			protocol_properties.pop("cipherSuites")
		protocol["properties"] = [
			p for p in protocol.get("properties", []) if not p["name"].startswith("foames:opcua:")
		] + [
			{"name": "foames:opcua:securityMode", "value": mode},
			{"name": "foames:opcua:securityPolicy", "value": policy or "none"},
		]

	root_properties = [
		{"name": "foames:site", "value": site},
		{"name": "foames:opcua:securityMode", "value": mode},
		{"name": "foames:opcua:securityPolicy", "value": policy or "none"},
	]
	if security.get("endpoint"):
		root_properties.append({"name": "foames:opcua:endpoint", "value": security["endpoint"]})

	refs = sorted(c["bom-ref"] for c in components if "bom-ref" in c)
	seed = f"foames-site-cbom:{site}:{timestamp}"
	return {
		"$schema": SCHEMA_URL,
		"bomFormat": "CycloneDX",
		"specVersion": SPEC_VERSION,
		"serialNumber": f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, seed)}",
		"version": 1,
		"metadata": {
			"timestamp": timestamp,
			"lifecycles": [{"phase": "operations"}],
			"component": {
				"type": "application",
				"bom-ref": ROOT_REF,
				"name": "foames",
				"version": app_version,
				"description": f"FoaMES as deployed on site {site}: the cryptography it uses and the certificates it holds",
				"properties": root_properties,
			},
		},
		"components": components,
		"dependencies": [{"ref": ROOT_REF, "dependsOn": refs}] + [{"ref": ref} for ref in refs],
	}
