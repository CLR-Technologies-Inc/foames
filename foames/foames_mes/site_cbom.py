# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The CBOM of this site: the curated cryptographic assets plus the OPC UA certificates it deploys.

    bench --site <site> execute foames.foames_mes.site_cbom.write --kwargs "{'out': 'site-cbom.cdx.json'}"

or `GET /api/method/foames.foames_mes.site_cbom.get_site_cbom` as a System Manager. The arithmetic is
in `foames.foames_mes.cbom`; this module only reads Machine Data Settings and the attached files.
"""

import datetime as dt
import json
from pathlib import Path

import frappe
from frappe import _

import foames
from foames.foames_mes.cbom import build_site_cbom
from foames.foames_mes.gateway.opcua import attached_file_path

CURATED = Path(foames.__file__).resolve().parent.parent / "sbom" / "curated.json"


def curated_assets() -> list[dict]:
	"""The hand-curated cryptographic assets shipped with the source, or none on a stripped install."""
	if not CURATED.is_file():
		return []
	return json.loads(CURATED.read_text(encoding="utf-8")).get("cryptographic_assets") or []


def _certificates(file_url):
	from foames.foames_mes.gateway.opcua_trust import load_certificates

	path = attached_file_path(file_url)
	if not path:
		return []
	try:
		return load_certificates(Path(path).read_bytes())
	except (OSError, ValueError) as e:
		frappe.throw(_("{0} could not be read as a certificate: {1}").format(file_url, e))


def build(now: dt.datetime | None = None) -> dict:
	"""The CycloneDX 1.7 CBOM of this site as a dict."""
	settings = frappe.get_single("Machine Data Settings")
	client = _certificates(settings.get("opcua_client_certificate"))
	server = _certificates(settings.get("opcua_server_certificate"))
	return build_site_cbom(
		curated_assets(),
		site=frappe.local.site,
		app_version=foames.__version__,
		security={
			"mode": settings.get("opcua_security_mode") or "None",
			"policy": settings.get("opcua_security_policy"),
			"endpoint": settings.get("opcua_endpoint"),
		},
		client_certificate=client[0] if client else None,
		server_certificate=server[0] if server else None,
		trusted_certificates=_certificates(settings.get("opcua_trusted_certificates")),
		now=now,
	)


def write(out: str = "site-cbom.cdx.json") -> str:
	"""Write the site CBOM to `out` (relative to the bench directory under `bench execute`)."""
	bom = build()
	path = Path(out)
	path.parent.mkdir(parents=True, exist_ok=True)
	path.write_text(json.dumps(bom, indent=2) + "\n", encoding="utf-8")
	print(f"wrote {path} ({len(bom['components'])} cryptographic assets)")
	return str(path)


@frappe.whitelist()
def get_site_cbom() -> dict:
	"""The site CBOM for a System Manager, as JSON."""
	frappe.only_for("System Manager")
	return build()
