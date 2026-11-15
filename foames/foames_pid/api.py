# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Whitelisted methods for P&IDs: the viewer, the tag register and the links to live signals.

Reads check Frappe permissions on PID Drawing and PID Component for the caller, as the desk does.
The writes (importing a register, applying suggested links) need write on PID Component and only
change FoaMES records; nothing here writes to an instrument, a PLC or a SCADA system.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint

from foames.foames_pid import isa51, linking, register
from foames.foames_pid.doctype.pid_component.pid_component import (
	SIGNAL_FIELDS,
	build_overlay,
	latest_values,
)

MAX_LIMIT = 1000


def _load(value):
	if isinstance(value, str):
		try:
			return json.loads(value)
		except ValueError:
			frappe.throw(_("Expected JSON"))
	return value


@frappe.whitelist()
def get_drawing_view(drawing: str, with_values: int | str = 1) -> dict:
	"""The drawing as SVG with each tag's live state or value overlaid, and the overlay itself."""
	frappe.has_permission("PID Drawing", "read", drawing, throw=True)
	doc = frappe.get_doc("PID Drawing", drawing)
	result = doc.render(with_values=bool(cint(with_values)))
	result["status"] = doc.status
	return result


@frappe.whitelist()
def get_live_values(drawing: str) -> dict:
	"""{tag: {state, value, unit, at, flag}} for the tags on a drawing, for refreshing the viewer."""
	frappe.has_permission("PID Drawing", "read", drawing, throw=True)
	return frappe.get_doc("PID Drawing", drawing).render(with_values=True)["overlay"]


@frappe.whitelist()
def get_drawing(drawing: str) -> dict:
	"""A drawing's title block, its components and its connections, without the picture."""
	frappe.has_permission("PID Drawing", "read", drawing, throw=True)
	doc = frappe.get_doc("PID Drawing", drawing)
	return {
		"drawing": doc.name,
		"title": doc.title,
		"revision": doc.revision,
		"status": doc.status,
		"plant_area": doc.plant_area,
		"source_format": doc.source_format,
		"dexpi_version": doc.dexpi_version,
		"imported_on": str(doc.imported_on) if doc.imported_on else None,
		"components": list_components(drawing=doc.name, limit=MAX_LIMIT),
		"connections": [
			{"kind": row.kind, "from": row.from_component, "to": row.to_component, "via": row.via}
			for row in doc.connections
		],
	}


@frappe.whitelist()
def list_components(
	drawing: str | None = None,
	component_type: str | None = None,
	machine: str | None = None,
	linked: int | str | None = None,
	search: str | None = None,
	limit: int | str = 100,
) -> list[dict]:
	"""Tagged components, filtered. `linked=1` only those tied to a machine, `linked=0` the rest."""
	filters: dict = {"disabled": 0}
	if drawing:
		filters["drawing"] = drawing
	if component_type:
		filters["component_type"] = component_type
	if machine:
		filters["machine"] = machine
	if linked not in (None, ""):
		filters["machine"] = ["is", "set"] if cint(linked) else ["is", "not set"]
	or_filters = None
	if search:
		like = f"%{search}%"
		or_filters = {"name": ["like", like], "description": ["like", like]}
	return frappe.get_list(
		"PID Component",
		filters=filters,
		or_filters=or_filters,
		fields=[*SIGNAL_FIELDS, "plant_area", "loop_number", "isa_meaning"],
		order_by="name asc",
		limit_page_length=min(max(cint(limit) or 100, 1), MAX_LIMIT),
	)


@frappe.whitelist()
def get_component(tag: str) -> dict:
	"""One component: its register entry, the ISA-5.1 reading of its tag, its live value, and what
	it is connected to on the drawings."""
	tag = isa51.normalise(tag)
	frappe.has_permission("PID Component", "read", tag, throw=True)
	doc = frappe.get_doc("PID Component", tag)
	data = {field: doc.get(field) for field in SIGNAL_FIELDS}
	data.update(
		{
			"plant_area": doc.plant_area,
			"loop_number": doc.loop_number,
			"isa_meaning": doc.isa_meaning,
			"external_reference": doc.external_reference,
			"attributes": [
				{"attribute": a.attribute, "value": a.value, "units": a.units} for a in doc.attributes
			],
		}
	)
	parsed = isa51.try_parse_tag(tag)
	data["isa"] = parsed.as_dict() if parsed and doc.component_type in ("Instrument", "Valve") else None
	data["live"] = build_overlay([data]).get(tag)
	data["children"] = frappe.get_all("PID Component", filters={"parent_component": tag}, pluck="name")
	row = frappe.qb.DocType("PID Connection")
	data["connections"] = (
		frappe.qb.from_(row)
		.select(row.parent.as_("drawing"), row.kind, row.from_component, row.to_component, row.via)
		.where((row.parenttype == "PID Drawing") & ((row.from_component == tag) | (row.to_component == tag)))
		.run(as_dict=True)
	)
	return data


@frappe.whitelist()
def parse_instrument_tag(tag: str) -> dict:
	"""Read an instrument tag by the ISA-5.1 letter code (FIC-101: flow indicate control, loop 101)."""
	try:
		return isa51.parse_tag(tag).as_dict()
	except isa51.TagError as error:
		frappe.throw(str(error))


@frappe.whitelist()
def export_tag_register(drawing: str | None = None) -> str:
	"""The tag register as CSV (all drawings, or one)."""
	rows = list_components(drawing=drawing, limit=MAX_LIMIT * 100)
	for row in rows:
		row["tag"] = row["name"]
		row["parent_tag"] = row.get("parent_component") or ""
	return register.write_register(rows)


@frappe.whitelist(methods=["POST"])
def import_tag_register(csv_text: str, drawing: str | None = None) -> dict:
	"""Create or update components from an instrument index or equipment list in CSV.

	Columns are matched by name (Tag, Type, Description, P&ID, Machine, Signal Name, Address, URV,
	LRV, ...); see foames.foames_pid.register. Blank cells leave a field as it is.
	"""
	frappe.has_permission("PID Component", "create", throw=True)
	if drawing:
		frappe.has_permission("PID Drawing", "read", drawing, throw=True)
	try:
		rows, warnings = register.read_register(csv_text)
	except register.RegisterError as error:
		frappe.throw(str(error))
	created, updated = [], []
	for row in rows:
		tag = row["tag"]
		if frappe.db.exists("PID Component", tag):
			doc = frappe.get_doc("PID Component", tag)
			updated.append(tag)
		else:
			doc = frappe.new_doc("PID Component")
			doc.tag = tag
			created.append(tag)
		for field in register.COLUMNS:
			if field in ("tag", "parent_tag", "drawing"):
				continue
			value = row.get(field)
			if value not in (None, ""):
				doc.set(field, value)
		target = row.get("drawing") or drawing
		if target and frappe.db.exists("PID Drawing", target):
			doc.drawing = target
		elif target:
			warnings.append(_("{0}: drawing {1} does not exist; left empty").format(tag, target))
		if doc.machine and not frappe.db.exists("Machine", doc.machine):
			warnings.append(_("{0}: machine {1} does not exist; link left empty").format(tag, doc.machine))
			doc.machine = None
			doc.signal_name = None
		existing = {a.attribute: a for a in doc.attributes}
		for name, value in (row.get("attributes") or {}).items():
			name = name[:140]
			if name in existing:
				existing[name].value = str(value)[:140]
			else:
				doc.append("attributes", {"attribute": name, "value": str(value)[:140]})
		doc.save()
	for row in rows:
		parent = row.get("parent_tag")
		if parent and parent != row["tag"] and frappe.db.exists("PID Component", parent):
			doc = frappe.get_doc("PID Component", row["tag"])
			doc.parent_component = parent
			doc.save()
	return {"created": created, "updated": updated, "warnings": warnings}


@frappe.whitelist()
def suggest_links(drawing: str | None = None) -> list[dict]:
	"""Candidate machine and signal links for unlinked components, with the reason for each.

	Compares tags with machine codes and Source IDs, with the nodes and metrics mapped in Machine
	Data Settings, and with the measurement names machines have reported in the last 30 days.
	Nothing is linked until a person applies a suggestion.
	"""
	frappe.has_permission("PID Component", "read", throw=True)
	components = list_components(drawing=drawing, limit=MAX_LIMIT * 10)
	for component in components:
		component["tag"] = component["name"]
	machines = frappe.get_list("Machine", fields=["name", "title", "source_id"], limit_page_length=0)
	node_maps = []
	if frappe.has_permission("Machine Data Settings", "read"):
		node_maps = frappe.get_all(
			"Machine Node Map",
			filters={"parenttype": "Machine Data Settings"},
			fields=["machine", "source", "node_id", "event_type", "name_or_counter"],
			limit_page_length=0,
		)
	measurements = []
	if frappe.has_permission("Machine Event", "read"):
		event = frappe.qb.DocType("Machine Event")
		measurements = (
			frappe.qb.from_(event)
			.select(event.machine, event.measurement_name)
			.where(
				(event.event_type == "Measurement")
				& (event.timestamp >= frappe.utils.add_days(frappe.utils.now_datetime(), -30))
			)
			.groupby(event.machine, event.measurement_name)
			.run(as_dict=True)
		)
	return linking.suggest_links(components, machines, node_maps, measurements)


@frappe.whitelist(methods=["POST"])
def apply_links(links: str | list) -> list[str]:
	"""Apply suggestions a person chose: each {tag, machine, event_type, signal_name, signal_source,
	signal_address}. Returns the tags updated."""
	links = _load(links) or []
	done = []
	for link in links:
		tag = isa51.normalise(link.get("tag") or "")
		frappe.has_permission("PID Component", "write", tag, throw=True)
		doc = frappe.get_doc("PID Component", tag)
		for field in ("machine", "event_type", "signal_name", "signal_source", "signal_address"):
			if link.get(field):
				doc.set(field, link[field])
		doc.save()
		done.append(tag)
	return done


def latest_value(tag: str) -> dict | None:
	"""The latest value of a component's signal, for code inside the bench."""
	component = frappe.db.get_value("PID Component", isa51.normalise(tag), SIGNAL_FIELDS, as_dict=True)
	if not component:
		return None
	return latest_values([component]).get(component["tag"])
