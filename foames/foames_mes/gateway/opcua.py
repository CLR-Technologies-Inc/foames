# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""OPC UA gateway: polls the nodes mapped in Machine Data Settings and records events.

    bench --site <site> execute foames.foames_mes.gateway.opcua.run

It needs the optional `asyncua` package (pip install asyncua). Each mapped node becomes one event
per poll when its value changed: a Count node gives a Count event with the running total, a State
node is translated through its state map, and Measurement nodes give Measurement events.

Message security (Sign or SignAndEncrypt with Basic256Sha256, Aes128_Sha256_RsaOaep or
Aes256_Sha256_RsaPss), the client certificate and key, an optional pinned server certificate, an
optional bundle of trusted certificates that the server's certificate must chain to, and username
authentication all come from Machine Data Settings; see `security_config` and `opcua_trust`.
"""

import asyncio
import inspect
from pathlib import Path

import frappe
from frappe import _

from foames.foames_mes.gateway.mapping import EventError, parse_state_map


def node_value_to_raw(row, value) -> dict:
	"""Turn a polled node value into a raw event dict for `record_event`."""
	raw = {"machine": frappe.db.get_value("Machine", row.machine, "source_id"), "type": row.event_type}
	if row.event_type == "State":
		state = parse_state_map(row.state_map).get(str(value), value)
		raw["state"] = state
	elif row.event_type == "Count":
		raw["counter"] = row.name_or_counter or "good"
		raw["value"] = value
	elif row.event_type == "Measurement":
		raw["name"] = row.name_or_counter or row.node_id
		raw["value"] = value
	elif row.event_type == "Alarm":
		raw["value"] = value
	else:
		raw["text"] = str(value)
	return raw


SECURITY_MODES = ("None", "Sign", "SignAndEncrypt")

# Security policy name in Machine Data Settings -> asyncua.crypto.security_policies class name.
SECURITY_POLICIES = {
	"Basic256Sha256": "SecurityPolicyBasic256Sha256",
	"Aes128_Sha256_RsaOaep": "SecurityPolicyAes128Sha256RsaOaep",
	"Aes256_Sha256_RsaPss": "SecurityPolicyAes256Sha256RsaPss",
}


def attached_file_path(file_url: str | None, *, must_be_private: bool = False) -> str | None:
	"""The path on disk of a file attached to Machine Data Settings, or None when nothing is attached."""
	if not file_url:
		return None
	name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not name:
		frappe.throw(_("Attached file {0} was not found").format(file_url))
	file = frappe.get_doc("File", name)
	if must_be_private and not file.is_private:
		frappe.throw(
			_("{0} must be uploaded as a private file, because it is a private key").format(file.file_name)
		)
	return file.get_full_path()


def security_config(settings) -> dict | None:
	"""What the gateway passes to asyncua's `Client.set_security`, or None for mode None.

	Raises a validation error when Sign or SignAndEncrypt is chosen without a certificate and key,
	or when the private key is not a private file."""
	mode = settings.opcua_security_mode or "None"
	if mode not in SECURITY_MODES:
		frappe.throw(_("Unknown OPC UA message security mode {0}").format(mode))
	if mode == "None":
		return None
	policy = settings.opcua_security_policy or "Basic256Sha256"
	if policy not in SECURITY_POLICIES:
		frappe.throw(_("Unknown OPC UA security policy {0}").format(policy))
	if not settings.opcua_client_certificate or not settings.opcua_private_key:
		frappe.throw(
			_("OPC UA security mode {0} needs a Client Certificate and a Client Private Key").format(mode)
		)
	trusted_certificates = attached_file_path(settings.get("opcua_trusted_certificates"))
	if trusted_certificates:
		check_trusted_certificates(trusted_certificates)
	return {
		"mode": mode,
		"policy": policy,
		"certificate": attached_file_path(settings.opcua_client_certificate),
		"private_key": attached_file_path(settings.opcua_private_key, must_be_private=True),
		"private_key_password": settings.get_password("opcua_private_key_password", raise_exception=False)
		or None,
		"server_certificate": attached_file_path(settings.opcua_server_certificate),
		"trusted_certificates": trusted_certificates,
		"application_uri": (settings.opcua_application_uri or "").strip() or None,
	}


def check_trusted_certificates(path: str) -> int:
	"""The number of certificates in the trusted bundle at `path`; a validation error when it holds
	none or cannot be parsed, so a bad upload is caught when the settings are saved."""
	try:
		from foames.foames_mes.gateway.opcua_trust import load_certificates

		certificates = load_certificates(Path(path).read_bytes())
	except ImportError:
		return -1  # cryptography is not installed here; the gateway host checks the bundle at start
	except (OSError, ValueError) as e:
		frappe.throw(
			_("Trusted Certificates could not be read as PEM or DER certificates: {0}").format(str(e))
		)
	if not certificates:
		frappe.throw(_("Trusted Certificates holds no certificate"))
	return len(certificates)


async def apply_security(client, settings) -> None:
	"""Configure message security and username authentication on an asyncua Client before connect()."""
	config = security_config(settings)
	if config:
		from asyncua import ua
		from asyncua.crypto import security_policies

		if config["application_uri"]:
			client.application_uri = config["application_uri"]
		install_certificate_validator(client, config)
		result = client.set_security(
			getattr(security_policies, SECURITY_POLICIES[config["policy"]]),
			config["certificate"],
			config["private_key"],
			private_key_password=config["private_key_password"],
			server_certificate=config["server_certificate"],
			mode=getattr(ua.MessageSecurityMode, config["mode"]),
		)
		if inspect.isawaitable(result):  # async from asyncua 1.0, plain in older releases
			await result
	else:
		frappe.logger("foames.opcua").warning(
			"OPC UA message security mode is None: traffic to the server is neither signed nor encrypted"
		)
	if settings.opcua_username:
		# Credentials must be set before connect(), which `async with` calls on entry.
		client.set_user(settings.opcua_username)
		client.set_password(settings.get_password("opcua_password", raise_exception=False))


def install_certificate_validator(client, config: dict) -> None:
	"""Make asyncua validate the server's certificate against the trusted bundle, before `set_security`
	fetches it from the endpoint. Without a bundle the gateway keeps the old behaviour, pinned or as
	presented, and says so in the log."""
	log = frappe.logger("foames.opcua")
	if not config.get("trusted_certificates"):
		if config.get("server_certificate"):
			log.info("OPC UA server certificate is pinned to the attached Server Certificate")
		else:
			log.warning(
				"OPC UA server certificate is accepted as the server presents it: attach Trusted "
				"Certificates or a Server Certificate in Machine Data Settings to check it"
			)
		return
	if not hasattr(client, "certificate_validator"):
		frappe.throw(
			_(
				"Trusted Certificates need asyncua 1.1 or later, which validates the server certificate "
				"through Client.certificate_validator; upgrade asyncua or clear the field"
			)
		)
	from foames.foames_mes.gateway.opcua_trust import make_validator

	validator = make_validator(Path(config["trusted_certificates"]).read_bytes())
	client.certificate_validator = validator
	log.info(f"OPC UA server certificate must chain to one of {len(validator.trusted)} trusted certificates")


async def poll_forever(settings):
	from asyncua import Client

	from foames.foames_mes.api import record_event

	last: dict[str, object] = {}
	client = Client(url=settings.opcua_endpoint)
	await apply_security(client, settings)
	async with client:
		nodes = [
			(row, client.get_node(row.node_id))
			for row in settings.node_map
			if (row.source or "OPC UA") == "OPC UA"
		]
		while True:
			for row, node in nodes:
				try:
					value = await node.read_value()
				except Exception:
					frappe.log_error(title=f"OPC UA read {row.node_id}", message=frappe.get_traceback())
					continue
				if row.node_id in last and last[row.node_id] == value:
					continue
				try:
					record_event(node_value_to_raw(row, value), source="OPC UA")
					frappe.db.commit()
				except EventError as e:
					# The same value would be rejected again, so remember it and stop retrying it.
					frappe.logger("foames.opcua").warning(f"rejected {row.node_id}: {e}")
				except Exception:
					# Leave the cache alone: the next poll records this change again.
					frappe.db.rollback()
					frappe.log_error(title="OPC UA gateway", message=frappe.get_traceback())
					continue
				last[row.node_id] = value
			await asyncio.sleep(settings.opcua_poll_seconds or 5)


def run():
	try:
		import asyncua
	except ImportError:
		raise SystemExit("The OPC UA gateway needs asyncua: pip install asyncua")
	settings = frappe.get_single("Machine Data Settings")
	if not settings.opcua_enabled:
		raise SystemExit("OPC UA is not enabled in Machine Data Settings")
	asyncio.run(poll_forever(settings))
