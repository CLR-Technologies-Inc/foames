# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""OPC UA gateway: polls the nodes mapped in Machine Data Settings and records events.

    bench --site <site> execute foames.foames_mes.gateway.opcua.run

It needs the optional `asyncua` package (pip install asyncua). Each mapped node becomes one event
per poll when its value changed: a Count node gives a Count event with the running total, a State
node is translated through its state map, and Measurement nodes give Measurement events.
"""

import asyncio

import frappe

from foames.foames_mes.gateway.mapping import EventError


def parse_state_map(text: str | None) -> dict[str, str]:
	mapping = {}
	for line in (text or "").splitlines():
		if "=" in line:
			key, value = line.split("=", 1)
			mapping[key.strip()] = value.strip()
	return mapping


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


async def poll_forever(settings):
	from asyncua import Client

	from foames.foames_mes.api import record_event

	last: dict[str, object] = {}
	async with Client(url=settings.opcua_endpoint) as client:
		if settings.opcua_username:
			client.set_user(settings.opcua_username)
			client.set_password(settings.get_password("opcua_password", raise_exception=False))
		nodes = [(row, client.get_node(row.node_id)) for row in settings.opcua_nodes]
		while True:
			for row, node in nodes:
				try:
					value = await node.read_value()
				except Exception:
					frappe.log_error(title=f"OPC UA read {row.node_id}", message=frappe.get_traceback())
					continue
				if last.get(row.node_id) == value:
					continue
				last[row.node_id] = value
				try:
					record_event(node_value_to_raw(row, value), source="OPC UA")
					frappe.db.commit()
				except EventError as e:
					frappe.logger("foames.opcua").warning(f"rejected {row.node_id}: {e}")
				except Exception:
					frappe.db.rollback()
					frappe.log_error(title="OPC UA gateway", message=frappe.get_traceback())
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
