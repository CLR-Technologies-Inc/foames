# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Parse IDocs that S/4HANA posts over HTTP (an XML HTTP port, transaction WE21).

One post holds one or more `<IDOC>` elements, each with a control record (`EDI_DC40`) and data
segments. Segments become nested dicts: field name -> text, child segment name -> list of dicts.
`summarize` pulls the few fields FoaMES needs out of the message types it knows (LOIPRO for orders,
MATMAS for materials, BATMAS for batches); every other message is stored as parsed.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

CONTROL_FIELDS = (
	"DOCNUM",
	"MESTYP",
	"IDOCTYP",
	"CIMTYP",
	"SNDPRN",
	"SNDPRT",
	"SNDPOR",
	"RCVPRN",
	"CREDAT",
	"CRETIM",
)


class IDocError(ValueError):
	pass


@dataclass
class IDoc:
	control: dict
	segments: dict = field(default_factory=dict)

	@property
	def number(self) -> str:
		return self.control.get("DOCNUM", "").lstrip("0") or "0"

	@property
	def message_type(self) -> str:
		return self.control.get("MESTYP", "")

	@property
	def sender(self) -> str:
		return self.control.get("SNDPRN", "")


def parse(xml: bytes | str) -> list[IDoc]:
	if isinstance(xml, str):
		xml = xml.encode("utf-8")
	# IDocs never need a DTD. Refusing one rules out entity-expansion attacks.
	head = xml[:4096].upper()
	if b"<!DOCTYPE" in head or b"<!ENTITY" in xml.upper():
		raise IDocError("IDoc XML with a DOCTYPE or ENTITY declaration is not accepted")
	try:
		root = ET.fromstring(xml)
	except ET.ParseError as e:
		raise IDocError(f"Not well-formed XML: {e}")

	elements = [root] if local(root.tag) == "IDOC" else [el for el in root.iter() if local(el.tag) == "IDOC"]
	if not elements:
		raise IDocError("No IDOC element found")

	idocs = []
	for element in elements:
		control, segments = {}, {}
		for child in element:
			name = local(child.tag)
			if name == "EDI_DC40":
				control = {local(f.tag): (f.text or "").strip() for f in child}
			else:
				segments.setdefault(name, []).append(segment(child))
		if not control.get("DOCNUM") or not control.get("MESTYP"):
			raise IDocError("IDoc control record is missing DOCNUM or MESTYP")
		idocs.append(
			IDoc(control={k: control.get(k, "") for k in CONTROL_FIELDS if k in control}, segments=segments)
		)
	return idocs


def segment(element) -> dict:
	data = {}
	for child in element:
		name = local(child.tag)
		if len(child):
			data.setdefault(name, []).append(segment(child))
		else:
			data[name] = (child.text or "").strip()
	return data


def local(tag: str) -> str:
	return tag.rsplit("}", 1)[-1]


def first(segments: dict, name: str) -> dict:
	rows = segments.get(name) or []
	return rows[0] if rows else {}


def summarize(idoc: IDoc) -> dict:
	"""Key fields of the message types FoaMES knows. Unknown types return an empty summary."""
	message_type = idoc.message_type
	if message_type == "LOIPRO":
		order = first(idoc.segments, "E1AFKOL")
		operations = []
		for sequence in order.get("E1AFFLL", []):
			for operation in sequence.get("E1AFVOL", []):
				operations.append(
					{
						"operation": operation.get("VORNR", ""),
						"work_center": operation.get("ARBPL", ""),
						"description": operation.get("LTXA1", ""),
					}
				)
		return {
			"reference_type": "Work Order",
			"external_id": order.get("AUFNR", "").lstrip("0"),
			"material": order.get("MATNR", ""),
			"plant": order.get("WERKS", ""),
			"quantity": order.get("GAMNG", ""),
			"unit": order.get("GMEIN", ""),
			"order_type": order.get("AUART", ""),
			"operations": operations,
		}
	if message_type == "MATMAS":
		material = first(idoc.segments, "E1MARAM")
		descriptions = material.get("E1MAKTM", [])
		return {
			"reference_type": "Item",
			"external_id": material.get("MATNR", ""),
			"base_unit": material.get("MEINS", ""),
			"description": descriptions[0].get("MAKTX", "") if descriptions else "",
		}
	if message_type == "BATMAS":
		batch = first(idoc.segments, "E1BATMAS")
		return {
			"reference_type": "Batch",
			# Same layout as the Batch entity key: MATERIAL|BATCH, or MATERIAL|PLANT|BATCH at plant level.
			"external_id": "|".join(
				p for p in (batch.get("MATERIAL", ""), batch.get("PLANT", ""), batch.get("BATCH", "")) if p
			),
			"plant": batch.get("PLANT", ""),
		}
	return {}
