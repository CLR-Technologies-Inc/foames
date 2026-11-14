# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Suggest which machine and which signal each P&ID tag is. Pure: no Frappe.

A P&ID names an instrument `FIC-101`; the SCADA system publishes it as an OPC UA node
`ns=2;s=[default]Area1/FIC_101/PV` or a Sparkplug metric `Line1/FIC101/pv`, and FoaMES records it
as a Measurement named after whatever the gateway sent. These functions compare the tag's
letters-and-digits key with the keys of each part of those names and return candidate links,
each with the reason it was proposed. People confirm them; nothing is linked on its own.
"""

from __future__ import annotations

import re

from foames.foames_pid.isa51 import tag_key, try_parse_tag

# Words a SCADA path adds after the tag for the value itself.
VALUE_WORDS = {
	"PV",
	"VALUE",
	"VAL",
	"OUT",
	"OP",
	"SP",
	"MV",
	"CV",
	"IN",
	"INPUT",
	"OUTPUT",
	"STATE",
	"STATUS",
}


def _segments(text: str) -> list[str]:
	"""The parts of a node id or metric path: `ns=2;s=[default]A1/FIC_101/PV` -> keys of each part."""
	text = re.sub(r"^ns=\d+;[sig]=", "", text or "", flags=re.IGNORECASE)
	text = re.sub(r"\[[^\]]*\]", "/", text)  # Ignition tag provider
	coarse = re.split(r"[/\\:;|]+", text)  # keeps DEXPI-style loop numbers such as PT4712.01 whole
	fine = [piece for part in coarse for piece in part.split(".")]
	keys = []
	for part in coarse + fine:
		key = tag_key(part)
		if key and key not in keys:
			keys.append(key)
	return keys


def matches(tag: str, text: str) -> str:
	"""How `text` (a node id, metric path, measurement name or machine code) names `tag`.

	Returns "exact" when the whole text is the tag, "segment" when one part of a path is the tag,
	"prefix" when a part starts with the tag followed by a value word (`FIC101PV`), or "".
	"""
	key = tag_key(tag)
	if not key or not text:
		return ""
	if tag_key(text) == key:
		return "exact"
	for part in _segments(text):
		if part == key:
			return "segment"
		if part.startswith(key) and part[len(key) :] in VALUE_WORDS:
			return "prefix"
	return ""


SCORES = {"exact": 3, "segment": 2, "prefix": 1}


def suggest_links(
	components: list[dict],
	machines: list[dict],
	node_maps: list[dict],
	measurements: list[dict],
) -> list[dict]:
	"""Candidate links for components that are not linked yet.

	- components: {tag, component_type, machine, signal_name, signal_address}
	- machines: {name, title, source_id}
	- node_maps: {machine, source, node_id, event_type, name_or_counter} (Machine Data Settings rows)
	- measurements: {machine, measurement_name} seen in Machine Events

	Each suggestion is {tag, machine, event_type, signal_name, signal_source, signal_address,
	reason, score}. The best candidate per tag is returned; ties keep the first found.
	"""
	best: dict[str, dict] = {}

	def offer(tag: str, candidate: dict) -> None:
		current = best.get(tag)
		if current is None or candidate["score"] > current["score"]:
			best[tag] = candidate

	for component in components:
		tag = component.get("tag") or ""
		kind = component.get("component_type")
		has_machine = bool(component.get("machine"))
		has_signal = bool(component.get("signal_name") or component.get("signal_address"))
		if kind in ("Equipment", "Line") or (kind not in ("Instrument", "Valve") and not has_machine):
			if has_machine:
				continue
			for machine in machines:
				for field in ("name", "source_id", "title"):
					how = matches(tag, machine.get(field) or "")
					if how == "exact":
						offer(
							tag,
							{
								"tag": tag,
								"machine": machine["name"],
								"event_type": "State",
								"signal_name": "",
								"signal_source": "",
								"signal_address": "",
								"reason": f"Machine {field.replace('_', ' ')} {machine.get(field)!r} is the tag",
								"score": SCORES[how] + (1 if field == "name" else 0),
							},
						)
			continue
		if has_signal and has_machine:
			continue
		parsed = try_parse_tag(tag)
		event_type = "Measurement"
		if parsed and (parsed.is_switch or parsed.is_alarm) and not parsed.reads_value:
			event_type = "Alarm" if parsed.is_alarm else "State"
		for row in node_maps:
			how = matches(tag, row.get("node_id") or "")
			if how:
				offer(
					tag,
					{
						"tag": tag,
						"machine": row.get("machine") or "",
						"event_type": row.get("event_type") or event_type,
						"signal_name": row.get("name_or_counter") or "",
						"signal_source": row.get("source") or "",
						"signal_address": row.get("node_id") or "",
						"reason": f"{row.get('source') or 'Node'} {row.get('node_id')!r} is mapped in Machine Data Settings",
						"score": SCORES[how] + 1,
					},
				)
		for seen in measurements:
			how = matches(tag, seen.get("measurement_name") or "")
			if how:
				offer(
					tag,
					{
						"tag": tag,
						"machine": seen.get("machine") or "",
						"event_type": "Measurement",
						"signal_name": seen.get("measurement_name") or "",
						"signal_source": "",
						"signal_address": "",
						"reason": f"Machine {seen.get('machine')} reports a measurement named {seen.get('measurement_name')!r}",
						"score": SCORES[how],
					},
				)
	return sorted(best.values(), key=lambda s: (-s["score"], s["tag"]))
