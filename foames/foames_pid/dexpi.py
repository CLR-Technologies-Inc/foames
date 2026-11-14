# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Read a DEXPI P&ID exchange file (Proteus XML, DEXPI 1.x). Pure: no Frappe.

DEXPI is the open, vendor-neutral P&ID exchange standard (dexpi.org) written by P&ID tools such
as AVEVA, Hexagon Smart P&ID, AutoCAD Plant 3D and others. Its 1.x exchange format is the Proteus
XML schema: a `PlantModel` with `Equipment` (and its `Nozzle`s), `PipingNetworkSystem`s (one per
line, split into `PipingNetworkSegment`s that hold `PipingComponent`s such as valves and are
joined by `Connection FromID/ToID`), `ProcessInstrumentationFunction`s (the instrument bubbles,
with `ProcessSignalGeneratingFunction`s and `InformationFlow`s for measuring and signal lines),
`ActuatingSystem`s and `InstrumentationLoopFunction`s. Attributes travel in
`GenericAttributes Set="DexpiAttributes"` as `GenericAttribute Name Value Units`.

This module turns such a file into a `PlantDiagram`: the drawing's metadata, every drawn item
with its position, the lines and signal lines as polylines, the tagged components that belong in
a tag register, and the process connections between tagged components. It reads what FoaMES
needs and ignores the rest (graphics catalogue, text styles, shapes).

DEXPI 2.x files (a `Model` of typed `Object`s with `Data` properties, `References` and a separate
diagram part) are read by `_ModelReader` into the same PlantDiagram: the plant objects give the
tag register and the connections, and the diagram's representation groups give the positions.

What it does not do: write DEXPI, or validate against the schema.

The parser refuses a document with a DOCTYPE or entity declaration, so an uploaded file cannot use
entity expansion; DEXPI files never need one.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from foames.foames_pid.isa51 import compose_tag

MAX_BYTES = 50 * 1024 * 1024

EQUIPMENT = "Equipment"
INSTRUMENT = "Instrument"
LINE = "Line"
VALVE = "Valve"
COMPONENT_TYPES = (EQUIPMENT, INSTRUMENT, LINE, VALVE, "Actuator", "Other")


class DexpiError(ValueError):
	pass


@dataclass
class Item:
	"""Anything drawn on the sheet that the viewer shows."""

	id: str
	kind: str  # Equipment, Nozzle, Valve, Piping, Instrument, OffPage, Actuator
	component_class: str = ""
	tag: str = ""
	x: float | None = None
	y: float | None = None
	parent_id: str = ""
	location: str = ""  # instruments: Field, CentralLocation, ... as DEXPI says
	attributes: dict[str, dict] = field(default_factory=dict)

	def as_dict(self) -> dict:
		return {
			"id": self.id,
			"kind": self.kind,
			"component_class": self.component_class,
			"tag": self.tag,
			"x": self.x,
			"y": self.y,
			"parent_id": self.parent_id,
			"location": self.location,
		}


@dataclass
class Polyline:
	id: str
	kind: str  # Process, Measuring, Signal
	points: list[tuple[float, float]]
	tag: str = ""  # the line number for process lines

	def as_dict(self) -> dict:
		return {"id": self.id, "kind": self.kind, "tag": self.tag, "points": [list(p) for p in self.points]}


@dataclass
class Component:
	"""A tagged item for the tag register."""

	tag: str
	component_type: str
	component_class: str = ""
	description: str = ""
	parent_tag: str = ""
	item_id: str = ""
	loop_number: str = ""
	attributes: dict[str, dict] = field(default_factory=dict)

	def as_dict(self) -> dict:
		return {
			"tag": self.tag,
			"component_type": self.component_type,
			"component_class": self.component_class,
			"description": self.description,
			"parent_tag": self.parent_tag,
			"item_id": self.item_id,
			"loop_number": self.loop_number,
			"attributes": self.attributes,
		}


@dataclass
class Connection:
	kind: str  # Process or Signal
	from_tag: str
	to_tag: str
	via: str = ""  # line number for process connections

	def as_dict(self) -> dict:
		return {"kind": self.kind, "from_tag": self.from_tag, "to_tag": self.to_tag, "via": self.via}


@dataclass
class PlantDiagram:
	drawing_name: str = ""
	drawing_number: str = ""
	revision: str = ""
	title: str = ""
	schema_version: str = ""
	dexpi_version: str = ""
	originating_system: str = ""
	units: str = ""
	extent: tuple[float, float, float, float] = (0.0, 0.0, 420.0, 297.0)  # min x, min y, max x, max y
	items: list[Item] = field(default_factory=list)
	lines: list[Polyline] = field(default_factory=list)
	components: list[Component] = field(default_factory=list)
	connections: list[Connection] = field(default_factory=list)
	warnings: list[str] = field(default_factory=list)

	def view(self) -> dict:
		"""The geometry the viewer draws, as plain JSON-able data. Y grows upwards, as in DEXPI."""
		return {
			"extent": list(self.extent),
			"units": self.units,
			"items": [i.as_dict() for i in self.items if i.x is not None],
			"lines": [line.as_dict() for line in self.lines],
		}

	def summary(self) -> dict:
		counts: dict[str, int] = {}
		for component in self.components:
			counts[component.component_type] = counts.get(component.component_type, 0) + 1
		return {
			"drawing_name": self.drawing_name,
			"drawing_number": self.drawing_number,
			"revision": self.revision,
			"dexpi_version": self.dexpi_version,
			"originating_system": self.originating_system,
			"items": len(self.items),
			"lines": len(self.lines),
			"components": counts,
			"connections": len(self.connections),
			"warnings": list(self.warnings),
		}


# --------------------------------------------------------------------------------------------
# Reading


def _local(tag: str) -> str:
	return tag.rsplit("}", 1)[-1]


def _attr_name(element: ET.Element) -> str:
	name = element.get("Name") or element.get("AttributeURI") or ""
	return re.split(r"[/#]", name)[-1]


def generic_attributes(element: ET.Element) -> dict[str, dict]:
	"""Every GenericAttribute directly under `element`, by name: {name: {"value", "units"}}.

	A name that repeats (a description in several languages) keeps the first, or the English one.
	"""
	result: dict[str, dict] = {}
	for group in element:
		if _local(group.tag) != "GenericAttributes":
			continue
		for attribute in group:
			if _local(attribute.tag) != "GenericAttribute":
				continue
			name = _attr_name(attribute)
			if not name:
				continue
			value = attribute.get("Value")
			if value is None:
				continue
			if name in result and attribute.get("Language") not in ("en", None):
				continue
			result[name] = {"value": value, "units": attribute.get("Units") or ""}
	return result


def _get(attrs: dict[str, dict], *names: str) -> str:
	"""First non-empty value among `names`, matching with or without the AssignmentClass suffix."""
	for name in names:
		for candidate in (name, name + "AssignmentClass", name.removesuffix("AssignmentClass")):
			value = (attrs.get(candidate) or {}).get("value")
			if value not in (None, ""):
				return str(value).strip()
	return ""


def _position(element: ET.Element) -> tuple[float | None, float | None]:
	for child in element:
		if _local(child.tag) == "Position":
			for location in child:
				if _local(location.tag) == "Location":
					try:
						return float(location.get("X")), float(location.get("Y"))
					except (TypeError, ValueError):
						return None, None
	return None, None


def _polyline(element: ET.Element) -> list[tuple[float, float]]:
	points: list[tuple[float, float]] = []
	for child in element:
		if _local(child.tag) in ("CenterLine", "PolyLine"):
			for coordinate in child:
				if _local(coordinate.tag) == "Coordinate":
					try:
						points.append((float(coordinate.get("X")), float(coordinate.get("Y"))))
					except (TypeError, ValueError):
						continue
	return points


def _associations(element: ET.Element) -> list[tuple[str, str]]:
	return [
		((child.get("Type") or "").strip().lower(), child.get("ItemID") or "")
		for child in element
		if _local(child.tag) == "Association"
	]


def _equipment_tag(attrs: dict[str, dict]) -> str:
	tag = _get(attrs, "TagNameAssignmentClass", "TagName")
	if tag:
		return tag
	parts = [_get(attrs, f"TagName{part}AssignmentClass") for part in ("Prefix", "SequenceNumber", "Suffix")]
	return "".join(parts) if parts[1] else ""


def _drawing_title(attrs: dict[str, dict]) -> str:
	return " ".join(
		part for part in (_get(attrs, "DrawingName"), _get(attrs, "DrawingSubTitle")) if part
	).strip()


def check_safe(data: bytes) -> None:
	if len(data) > MAX_BYTES:
		raise DexpiError(f"The file is larger than {MAX_BYTES // (1024 * 1024)} MB")
	head = data[:4096].lstrip()
	if b"<!DOCTYPE" in data or b"<!ENTITY" in data:
		raise DexpiError("The file declares a DOCTYPE or entities; DEXPI files never need one")
	if not head.startswith(b"<"):
		raise DexpiError("The file is not XML")


def parse(data: bytes | str) -> PlantDiagram:
	"""Parse a DEXPI 1.x (Proteus XML) file into a PlantDiagram."""
	if isinstance(data, str):
		data = data.encode("utf-8")
	check_safe(data)
	try:
		root = ET.fromstring(data)
	except ET.ParseError as error:
		raise DexpiError(f"The file is not well-formed XML: {error}") from error
	if _local(root.tag) == "Model":
		return _ModelReader(root).read()
	if _local(root.tag) != "PlantModel":
		raise DexpiError(f"Expected a DEXPI PlantModel or Model, found <{_local(root.tag)}>")
	return _Reader(root).read()


class _Reader:
	def __init__(self, root: ET.Element):
		self.root = root
		self.diagram = PlantDiagram()
		self.items: dict[str, Item] = {}
		self.parent: dict[str, str] = {}  # item id -> containing equipment / segment / system id
		self.system_of: dict[str, str] = {}  # piping item id -> piping network system id
		self.line_tag: dict[str, str] = {}  # piping network system id -> line number
		self.equipment_of: dict[str, str] = {}  # nozzle or sub-equipment id -> top tagged equipment id
		self.tags: dict[str, str] = {}  # item id -> tag in the register
		self.components: dict[str, Component] = {}

	# -- helpers --------------------------------------------------------------------------

	def add_item(self, item: Item) -> Item:
		self.items[item.id] = item
		self.diagram.items.append(item)
		return item

	def add_component(self, component: Component) -> None:
		if not component.tag:
			return
		existing = self.components.get(component.tag)
		if existing:
			if existing.item_id != component.item_id:
				self.diagram.warnings.append(
					f"Tag {component.tag} appears more than once; the first ({existing.item_id}) is kept"
				)
			return
		self.components[component.tag] = component
		self.diagram.components.append(component)
		if component.item_id:
			self.tags[component.item_id] = component.tag

	def owner_tag(self, item_id: str) -> str:
		"""The tag of the equipment or line an item belongs to."""
		seen = set()
		current = item_id
		while current and current not in seen:
			seen.add(current)
			if current in self.tags and self.components[self.tags[current]].component_type in (
				EQUIPMENT,
				LINE,
			):
				return self.tags[current]
			if current in self.system_of:
				return self.line_tag.get(self.system_of[current], "")
			current = self.parent.get(current, "")
		return ""

	# -- passes ---------------------------------------------------------------------------

	def read(self) -> PlantDiagram:
		self.read_header()
		for child in self.root:
			name = _local(child.tag)
			if name == "Equipment":
				self.read_equipment(child, parent_id="")
			elif name == "PipingNetworkSystem":
				self.read_system(child)
		for child in self.root:
			name = _local(child.tag)
			if name == "ProcessInstrumentationFunction":
				self.read_instrument(child)
			elif name == "ActuatingSystem":
				self.read_actuating_system(child)
			elif name == "InstrumentationLoopFunction":
				self.read_loop(child)
		self.read_connections()
		return self.diagram

	def read_header(self) -> None:
		info = next((c for c in self.root if _local(c.tag) == "PlantInformation"), None)
		if info is not None:
			self.diagram.schema_version = info.get("SchemaVersion") or ""
			self.diagram.dexpi_version = info.get("ApplicationVersion") or ""
			system = info.get("OriginatingSystem") or ""
			vendor = info.get("OriginatingSystemVendor") or ""
			self.diagram.originating_system = f"{system} ({vendor})" if vendor else system
			self.diagram.units = info.get("Units") or ""
		metadata = next((c for c in self.root if _local(c.tag) == "MetaData"), None)
		if metadata is not None:
			attrs = generic_attributes(metadata)
			self.diagram.drawing_number = _get(attrs, "DrawingNumberAssignmentClass", "DrawingNumber")
			self.diagram.revision = _get(attrs, "RevisionNumberAssignmentClass", "RevisionNumber")
			self.diagram.title = _drawing_title(attrs)
		drawing = next((c for c in self.root if _local(c.tag) == "Drawing"), None)
		if drawing is not None:
			self.diagram.drawing_name = drawing.get("Name") or ""
			extent = next((c for c in drawing if _local(c.tag) == "Extent"), None)
			if extent is not None:
				lo = next((c for c in extent if _local(c.tag) == "Min"), None)
				hi = next((c for c in extent if _local(c.tag) == "Max"), None)
				try:
					self.diagram.extent = (
						float(lo.get("X")),
						float(lo.get("Y")),
						float(hi.get("X")),
						float(hi.get("Y")),
					)
				except (AttributeError, TypeError, ValueError):
					self.diagram.warnings.append("The drawing extent could not be read; A3 is assumed")

	def read_equipment(self, element: ET.Element, parent_id: str) -> None:
		item_id = element.get("ID") or ""
		attrs = generic_attributes(element)
		x, y = _position(element)
		tag = _equipment_tag(attrs)
		item = self.add_item(
			Item(
				id=item_id,
				kind="Equipment",
				component_class=element.get("ComponentClass") or "",
				tag=tag,
				x=x,
				y=y,
				parent_id=parent_id,
				attributes=attrs,
			)
		)
		if parent_id:
			self.parent[item_id] = parent_id
		if tag:
			self.add_component(
				Component(
					tag=tag,
					component_type=EQUIPMENT,
					component_class=item.component_class,
					description=_get(attrs, "EquipmentDescriptionAssignmentClass", "Description"),
					parent_tag=self.owner_tag(parent_id) if parent_id else "",
					item_id=item_id,
					attributes=attrs,
				)
			)
		for child in element:
			name = _local(child.tag)
			if name == "Equipment":
				self.read_equipment(child, parent_id=item_id)
			elif name == "Nozzle":
				nozzle_id = child.get("ID") or ""
				nx, ny = _position(child)
				self.add_item(
					Item(
						id=nozzle_id,
						kind="Nozzle",
						component_class="Nozzle",
						tag=_get(generic_attributes(child), "SubTagNameAssignmentClass"),
						x=nx,
						y=ny,
						parent_id=item_id,
					)
				)
				self.parent[nozzle_id] = item_id

	def read_system(self, system: ET.Element) -> None:
		system_id = system.get("ID") or ""
		attrs = generic_attributes(system)
		line_number = _get(attrs, "LineNumberAssignmentClass", "LineNumber")
		self.line_tag[system_id] = line_number
		if line_number:
			description = " ".join(
				part
				for part in (
					_get(attrs, "NominalDiameterRepresentationAssignmentClass"),
					_get(attrs, "FluidCodeAssignmentClass"),
					_get(attrs, "PipingClassCodeAssignmentClass"),
				)
				if part
			)
			self.add_component(
				Component(
					tag=line_number,
					component_type=LINE,
					component_class="PipingNetworkSystem",
					description=description,
					item_id=system_id,
					attributes=attrs,
				)
			)
		for segment in system:
			if _local(segment.tag) != "PipingNetworkSegment":
				continue
			segment_id = segment.get("ID") or ""
			self.system_of[segment_id] = system_id
			points = _polyline(segment)
			if points:
				self.diagram.lines.append(
					Polyline(id=segment_id, kind="Process", points=points, tag=line_number)
				)
			for child in segment:
				name = _local(child.tag)
				if name == "CenterLine":
					continue
				if name in ("PipingComponent", "PipeOffPageConnector", "PropertyBreak"):
					self.read_piping_item(child, segment_id, system_id)

	def read_piping_item(self, element: ET.Element, segment_id: str, system_id: str) -> None:
		item_id = element.get("ID") or ""
		component_class = element.get("ComponentClass") or ""
		attrs = generic_attributes(element)
		x, y = _position(element)
		if _local(element.tag) == "PipeOffPageConnector":
			kind = "OffPage"
		elif "Valve" in component_class or "Damper" in component_class or "Cock" in component_class:
			kind = "Valve"
		else:
			kind = "Piping"
		# A piping item has a plant-wide tag only when it is numbered as a position (a safety
		# valve, SV 104.01) or named as one; the component number (C1, C2) is per line.
		tag = _get(attrs, "PositionNumberAssignmentClass", "TagNameAssignmentClass")
		self.add_item(
			Item(
				id=item_id,
				kind=kind,
				component_class=component_class,
				tag=tag,
				x=x,
				y=y,
				parent_id=segment_id,
				attributes=attrs,
			)
		)
		self.parent[item_id] = segment_id
		self.system_of[item_id] = system_id
		if tag:
			self.add_component(
				Component(
					tag=tag,
					component_type=VALVE if kind == "Valve" else "Other",
					component_class=component_class,
					description=_get(attrs, "PipingComponentNameAssignmentClass"),
					parent_tag=self.line_tag.get(system_id, ""),
					item_id=item_id,
					attributes=attrs,
				)
			)

	def read_instrument(self, element: ET.Element) -> None:
		item_id = element.get("ID") or ""
		attrs = generic_attributes(element)
		x, y = _position(element)
		category = _get(attrs, "ProcessInstrumentationFunctionCategoryAssignmentClass")
		functions = _get(attrs, "ProcessInstrumentationFunctionsAssignmentClass")
		modifier = _get(attrs, "ProcessInstrumentationFunctionModifierAssignmentClass")
		number = _get(attrs, "ProcessInstrumentationFunctionNumberAssignmentClass")
		tag = compose_tag(category, functions, number, modifier=modifier) if (category and number) else ""
		location = _get(attrs, "LocationSpecialization", "Location")
		self.add_item(
			Item(
				id=item_id,
				kind="Instrument",
				component_class=element.get("ComponentClass") or "ProcessInstrumentationFunction",
				tag=tag,
				x=x,
				y=y,
				location=location,
				attributes=attrs,
			)
		)
		# Where it measures: the signal generating function "is located in" a piping item or a
		# nozzle; that gives the line or equipment the instrument belongs to.
		located_in = ""
		generators: list[tuple[str, str, ET.Element]] = []
		for child in element:
			name = _local(child.tag)
			if name == "ProcessSignalGeneratingFunction":
				child_attrs = generic_attributes(child)
				for kind, target in _associations(child):
					if kind == "is located in" and target:
						located_in = located_in or target
				generators.append(
					(
						child.get("ID") or "",
						_get(child_attrs, "ProcessSignalGeneratingFunctionNumberAssignmentClass"),
						child,
					)
				)
			elif name == "InformationFlow":
				points = _polyline(child)
				if points:
					flow_class = child.get("ComponentClass") or ""
					self.diagram.lines.append(
						Polyline(
							id=child.get("ID") or "",
							kind="Measuring" if "Measuring" in flow_class else "Signal",
							points=points,
						)
					)
		parent_tag = self.owner_tag(located_in) if located_in else ""
		if tag:
			self.add_component(
				Component(
					tag=tag,
					component_type=INSTRUMENT,
					component_class=location or "ProcessInstrumentationFunction",
					description="",  # the ISA meaning is derived on the record, not file data
					parent_tag=parent_tag,
					item_id=item_id,
					loop_number=number.lstrip("-_ "),
					attributes=attrs,
				)
			)
		else:
			self.diagram.warnings.append(f"Instrument {item_id} has no category or number and is not tagged")
		for generator_id, generator_tag, generator in generators:
			self.parent[generator_id] = item_id
			if not generator_tag:
				continue
			# The primary element or transmitter (PT4712.01), in the register under its bubble.
			self.add_component(
				Component(
					tag=generator_tag,
					component_type=INSTRUMENT,
					component_class="ProcessSignalGeneratingFunction",
					description="",  # the ISA meaning is derived on the record, not file data
					parent_tag=tag or parent_tag,
					item_id=generator_id,
					loop_number=number.lstrip("-_ "),
					attributes=generic_attributes(generator),
				)
			)

	def read_actuating_system(self, element: ET.Element) -> None:
		attrs = generic_attributes(element)
		number = _get(attrs, "ActuatingSystemNumberAssignmentClass")
		valve_id = ""
		actuator: Item | None = None
		for child in element:
			if _local(child.tag) != "ActuatingSystemComponent":
				continue
			for kind, target in _associations(child):
				if kind == "refers to" and target:
					valve_id = target
			x, y = _position(child)
			if x is not None:
				actuator = self.add_item(
					Item(
						id=child.get("ID") or "",
						kind="Actuator",
						component_class=child.get("ComponentClass") or "",
						tag=_get(generic_attributes(child), "SubTagNameAssignmentClass"),
						x=x,
						y=y,
					)
				)
		if not number:
			return
		# The actuating system's number tags the valve it operates (PV4712.02 on GlobeValve-1).
		valve = self.items.get(valve_id)
		if valve is not None and not valve.tag:
			valve.tag = number
		self.add_component(
			Component(
				tag=number,
				component_type=VALVE,
				component_class=valve.component_class if valve is not None else "ActuatingSystem",
				description="",  # the ISA meaning is derived on the record, not file data
				parent_tag=self.owner_tag(valve_id) if valve_id else "",
				item_id=valve_id or (actuator.id if actuator else ""),
				attributes=attrs,
			)
		)

	def read_loop(self, element: ET.Element) -> None:
		number = _get(generic_attributes(element), "InstrumentationLoopFunctionNumberAssignmentClass")
		if not number:
			return
		for kind, target in _associations(element):
			if kind.startswith("is a collection including") and target in self.tags:
				component = self.components[self.tags[target]]
				component.loop_number = component.loop_number or number

	def piping_edges(self) -> list[tuple[str, str, str]]:
		"""(from item id, to item id, line number) for every Connection in every segment."""
		result = []
		for system in self.root:
			if _local(system.tag) != "PipingNetworkSystem":
				continue
			line = self.line_tag.get(system.get("ID") or "", "")
			for segment in system:
				if _local(segment.tag) != "PipingNetworkSegment":
					continue
				for child in segment:
					if _local(child.tag) == "Connection":
						result.append((child.get("FromID") or "", child.get("ToID") or "", line))
		return result

	def read_connections(self) -> None:
		"""Process connections between tagged equipment, followed along the piping.

		Segments are joined end to end through piping items (tees, valves, reducers); a nozzle
		stands for its equipment. Each tagged equipment reached from another one downstream
		becomes one Process connection, labelled with the line it leaves by.
		"""
		edges: dict[str, set[str]] = {}
		line_of_edge: dict[tuple[str, str], str] = {}
		for a, b, line in self.piping_edges():
			if a and b:
				edges.setdefault(a, set()).add(b)
				line_of_edge[(a, b)] = line

		def endpoint(item_id: str) -> str:
			"""The tagged equipment a nozzle belongs to, or '' for a piping item."""
			item = self.items.get(item_id)
			if item is None or item.kind not in ("Nozzle", "Equipment"):
				return ""
			current = item_id
			best = ""
			while current:
				if current in self.tags and self.components[self.tags[current]].component_type == EQUIPMENT:
					best = self.tags[current]
				current = self.parent.get(current, "")
			return best

		seen: set[tuple[str, str]] = set()
		for start in list(edges):
			source = endpoint(start)
			if not source:
				continue
			stack = [(start, "")]
			visited = {start}
			while stack:
				node, via = stack.pop()
				for nxt in edges.get(node, ()):
					if nxt in visited:
						continue
					visited.add(nxt)
					line = via or line_of_edge.get((node, nxt), "")
					target = endpoint(nxt)
					if target and target != source:
						if (source, target) not in seen:
							seen.add((source, target))
							self.diagram.connections.append(Connection("Process", source, target, line))
						continue
					if not target:
						stack.append((nxt, line))
		for component in self.diagram.components:
			if component.component_type == INSTRUMENT and component.parent_tag:
				self.diagram.connections.append(Connection("Signal", component.parent_tag, component.tag))


# --------------------------------------------------------------------------------------------
# DEXPI 2.x


def _type_name(element: ET.Element) -> tuple[str, str]:
	"""("Piping", "BallValve") from type="Plant/Piping.BallValve"."""
	kind = (element.get("type") or "").split("/", 1)[-1]
	package, _, name = kind.rpartition(".")
	return package, name


def _scalar(value: ET.Element):
	name = _local(value.tag)
	if name == "DataReference":
		return (value.get("data") or "").rsplit(".", 1)[-1]
	if name in ("Double", "Integer"):
		try:
			return float(value.text) if name == "Double" else int(value.text)
		except (TypeError, ValueError):
			return None
	if name == "Boolean":
		return (value.text or "").strip().lower() == "true"
	if name == "String":
		return (value.text or "").strip()
	if name == "AggregatedDataValue":
		fields = {}
		for data in value:
			if _local(data.tag) == "Data" and len(data):
				fields[data.get("property")] = _scalar(data[0])
		kind = (value.get("type") or "").rsplit(".", 1)[-1]
		if kind == "PhysicalQuantity":
			return {"value": fields.get("Value"), "units": fields.get("Unit") or ""}
		if kind == "MultiLanguageString":
			strings = fields.get("SingleLanguageStrings")
			return strings.get("Value") if isinstance(strings, dict) else strings
		return fields
	return None


def _data(element: ET.Element) -> dict:
	"""The direct Data properties of an Object, as plain values."""
	result = {}
	for data in element:
		if _local(data.tag) == "Data" and len(data):
			value = _scalar(data[0])
			if value not in (None, "", {}):
				result[data.get("property")] = value
	return result


def _as_attributes(data: dict) -> dict[str, dict]:
	attrs = {}
	for name, value in data.items():
		if isinstance(value, dict) and "value" in value:
			attrs[name] = {"value": str(value["value"]), "units": value.get("units") or ""}
		elif isinstance(value, str | int | float | bool):
			attrs[name] = {"value": str(value), "units": ""}
	return attrs


def _refs(element: ET.Element, prop: str) -> list[str]:
	result = []
	for ref in element:
		if _local(ref.tag) == "References" and ref.get("property") == prop:
			result += [o.lstrip("#") for o in (ref.get("objects") or "").split() if o]
	return result


def _point(value) -> tuple[float, float] | None:
	if (
		isinstance(value, dict)
		and isinstance(value.get("X"), int | float)
		and isinstance(value.get("Y"), int | float)
	):
		return float(value["X"]), float(value["Y"])
	return None


class _ModelReader(_Reader):
	"""DEXPI 2.x: the same outputs as the 1.x reader, from the object model."""

	def __init__(self, root: ET.Element):
		super().__init__(root)
		self.positions: dict[str, tuple[float, float]] = {}
		self.node_positions: dict[str, tuple[float, float]] = {}  # node position id -> point
		self.edges: list[tuple[str, str, str]] = []
		self.segment_lines: dict[str, list[tuple[str, list[tuple[float, float]]]]] = {}

	def read(self) -> PlantDiagram:
		plant = None
		for element in self.root.iter():
			if _local(element.tag) != "Object":
				continue
			package, name = _type_name(element)
			if name == "PlantModel" and plant is None:
				plant = element
			elif name == "Diagram" and package == "Diagram":
				self.read_diagram(element)
			elif name == "PlantMetaData":
				data = _data(element)
				self.diagram.drawing_number = str(data.get("DrawingNumber") or "")
				self.diagram.revision = str(data.get("RevisionNumber") or "")
				self.diagram.title = " ".join(
					str(data[k]) for k in ("DrawingName", "DrawingSubTitle") if data.get(k)
				)
		for imported in self.root:
			if _local(imported.tag) == "Import" and imported.get("prefix") == "Plant":
				# https://data.dexpi.org/models/2.0.0/Plant.xml -> 2.0.0
				parts = (imported.get("source") or "").split("/")
				self.diagram.dexpi_version = parts[-2] if len(parts) >= 2 else ""
		self.diagram.units = "mm"
		if plant is None:
			raise DexpiError(
				"This DEXPI model has no Plant/PlantModel object. A DEXPI process model (Process/ProcessModel) "
				"describes process steps and streams, not a P&ID, and is not imported here"
			)
		self.read_representations()
		for child in self._children(plant):
			self.read_object(child, parent_id="", system_id="")
		for child in self._children(plant):
			_, name = _type_name(child)
			if name == "ProcessInstrumentationFunction":
				self.read_instrument_object(child)
		for child in self._children(plant):
			_, name = _type_name(child)
			if name == "ActuatingSystem":
				self.read_actuating_object(child)
			elif name == "InstrumentationLoopFunction":
				number = str(_data(child).get("InstrumentationLoopFunctionNumber") or "")
				for target in _refs(child, "ProcessInstrumentationFunctions"):
					if number and target in self.tags:
						component = self.components[self.tags[target]]
						component.loop_number = component.loop_number or number
		self.read_connections()
		return self.diagram

	@staticmethod
	def _children(element: ET.Element):
		for group in element:
			if _local(group.tag) == "Components":
				for child in group:
					if _local(child.tag) == "Object":
						yield child

	def read_diagram(self, element: ET.Element) -> None:
		data = _data(element)
		self.diagram.drawing_name = str(data.get("Name") or "")
		try:
			self.diagram.extent = (
				float(data.get("MinX", 0)),
				float(data.get("MinY", 0)),
				float(data["MaxX"]),
				float(data["MaxY"]),
			)
		except (KeyError, TypeError, ValueError):
			self.diagram.warnings.append("The drawing extent could not be read; A3 is assumed")

	def read_representations(self) -> None:
		"""Positions of plant objects and the polylines of pipes and signal lines."""
		for element in self.root.iter():
			if _local(element.tag) != "Object":
				continue
			_, name = _type_name(element)
			if name in ("PipingNodePosition", "InstrumentationNodePosition") and element.get("id"):
				point = _point(_data(element).get("Position"))
				if point:
					self.node_positions[element.get("id")] = point
		for element in self.root.iter():
			if _local(element.tag) != "Object" or _type_name(element)[1] != "RepresentationGroup":
				continue
			represents = _refs(element, "Represents")
			if not represents:
				continue
			target = represents[0]
			for inner in element.iter():
				if _local(inner.tag) != "Object":
					continue
				inner_name = _type_name(inner)[1]
				if inner_name == "ShapeUsage" and target not in self.positions:
					point = _point(_data(inner).get("Position"))
					if point:
						self.positions[target] = point
				elif inner_name == "ConnectorLine":
					points = []
					source = _refs(inner, "Source")
					if source and source[0] in self.node_positions:
						points.append(self.node_positions[source[0]])
					for data in inner:
						if _local(data.tag) == "Data" and data.get("property") == "InnerPoints":
							for value in data:
								point = _point(_scalar(value))
								if point:
									points.append(point)
					destination = _refs(inner, "Target")
					if destination and destination[0] in self.node_positions:
						points.append(self.node_positions[destination[0]])
					if len(points) >= 2:
						self.segment_lines.setdefault(target, []).append((inner_name, points))

	def read_object(self, element: ET.Element, parent_id: str, system_id: str) -> None:
		package, name = _type_name(element)
		item_id = element.get("id") or ""
		data = _data(element)
		attrs = _as_attributes(data)
		x, y = self.positions.get(item_id, (None, None))
		if package == "ProcessEquipment" and name != "Nozzle":
			tag = (
				str(data.get("TagName") or "")
				or "".join(
					str(data.get(k) or "")
					for k in ("TagNamePrefix", "TagNameSequenceNumber", "TagNameSuffix")
				)
				if data.get("TagNameSequenceNumber") or data.get("TagName")
				else ""
			)
			self.add_item(
				Item(
					id=item_id,
					kind="Equipment",
					component_class=name,
					tag=tag,
					x=x,
					y=y,
					parent_id=parent_id,
					attributes=attrs,
				)
			)
			if parent_id:
				self.parent[item_id] = parent_id
			if tag:
				self.add_component(
					Component(
						tag=tag,
						component_type=EQUIPMENT,
						component_class=name,
						description=str(data.get("EquipmentDescription") or ""),
						parent_tag=self.owner_tag(parent_id) if parent_id else "",
						item_id=item_id,
						attributes=attrs,
					)
				)
			for child in self._children(element):
				self.read_object(child, parent_id=item_id, system_id="")
		elif name == "Nozzle":
			self.add_item(
				Item(
					id=item_id,
					kind="Nozzle",
					component_class="Nozzle",
					tag=str(data.get("SubTagName") or ""),
					x=x,
					y=y,
					parent_id=parent_id,
				)
			)
			self.parent[item_id] = parent_id
		elif name == "PipingNetworkSystem":
			line_number = str(data.get("LineNumber") or "")
			self.line_tag[item_id] = line_number
			if line_number:
				self.add_component(
					Component(
						tag=line_number,
						component_type=LINE,
						component_class=name,
						description=" ".join(
							str(data[k])
							for k in ("NominalDiameterRepresentation", "FluidCode", "PipingClassCode")
							if data.get(k)
						),
						item_id=item_id,
						attributes=attrs,
					)
				)
			for child in self._children(element):
				self.read_object(child, parent_id=item_id, system_id=item_id)
		elif name == "PipingNetworkSegment":
			self.system_of[item_id] = system_id
			line = self.line_tag.get(system_id, "")
			for child in self._children(element):
				child_name = _type_name(child)[1]
				if child_name in ("Pipe", "DirectPipingConnection"):
					source, target = _refs(child, "SourceItem"), _refs(child, "TargetItem")
					self.edges.append((source[0] if source else "", target[0] if target else "", line))
					for _, points in self.segment_lines.get(child.get("id") or "", []):
						self.diagram.lines.append(
							Polyline(id=child.get("id") or "", kind="Process", points=points, tag=line)
						)
				else:
					self.read_piping_object(child, item_id, system_id)
		elif package == "Piping":
			self.read_piping_object(element, parent_id, system_id)

	def read_piping_object(self, element: ET.Element, segment_id: str, system_id: str) -> None:
		_, name = _type_name(element)
		if name in ("PipingNode",):
			return
		item_id = element.get("id") or ""
		data = _data(element)
		attrs = _as_attributes(data)
		x, y = self.positions.get(item_id, (None, None))
		if "OffPageConnector" in name:
			kind = "OffPage"
		elif any(word in name for word in ("Valve", "Damper", "Cock")):
			kind = "Valve"
		else:
			kind = "Piping"
		tag = str(data.get("PositionNumber") or data.get("TagName") or "")
		self.add_item(
			Item(
				id=item_id,
				kind=kind,
				component_class=name,
				tag=tag,
				x=x,
				y=y,
				parent_id=segment_id,
				attributes=attrs,
			)
		)
		self.parent[item_id] = segment_id
		self.system_of[item_id] = system_id
		if tag:
			self.add_component(
				Component(
					tag=tag,
					component_type=VALVE if kind == "Valve" else "Other",
					component_class=name,
					description=str(data.get("PipingComponentName") or ""),
					parent_tag=self.line_tag.get(system_id, ""),
					item_id=item_id,
					attributes=attrs,
				)
			)

	def read_instrument_object(self, element: ET.Element) -> None:
		item_id = element.get("id") or ""
		data = _data(element)
		category = str(data.get("ProcessInstrumentationFunctionCategory") or "")
		functions = str(data.get("ProcessInstrumentationFunctions") or "")
		modifier = str(data.get("ProcessInstrumentationFunctionModifier") or "")
		number = str(data.get("ProcessInstrumentationFunctionNumber") or "")
		tag = compose_tag(category, functions, number, modifier=modifier) if (category and number) else ""
		location = str(data.get("Location") or "")
		x, y = self.positions.get(item_id, (None, None))
		self.add_item(
			Item(
				id=item_id,
				kind="Instrument",
				component_class=_type_name(element)[1],
				tag=tag,
				x=x,
				y=y,
				location=location,
				attributes=_as_attributes(data),
			)
		)
		generators = []
		located_in = ""
		for child in self._children(element):
			child_name = _type_name(child)[1]
			if child_name == "ProcessSignalGeneratingFunction":
				sensing = _refs(child, "SensingLocation")
				located_in = located_in or (sensing[0] if sensing else "")
				generators.append((child, sensing[0] if sensing else ""))
			elif child_name in ("MeasuringLineFunction", "SignalConveyingFunction"):
				for _, points in self.segment_lines.get(child.get("id") or "", []):
					self.diagram.lines.append(
						Polyline(
							id=child.get("id") or "",
							kind="Measuring" if "Measuring" in child_name else "Signal",
							points=points,
						)
					)
		parent_tag = self.owner_tag(located_in) if located_in else ""
		if tag:
			self.add_component(
				Component(
					tag=tag,
					component_type=INSTRUMENT,
					component_class=location or "ProcessInstrumentationFunction",
					description="",  # the ISA meaning is derived on the record, not file data
					parent_tag=parent_tag,
					item_id=item_id,
					loop_number=number.lstrip("-_ "),
					attributes=_as_attributes(data),
				)
			)
		else:
			self.diagram.warnings.append(f"Instrument {item_id} has no category or number and is not tagged")
		for generator, _ in generators:
			generator_id = generator.get("id") or ""
			self.parent[generator_id] = item_id
			generator_tag = str(_data(generator).get("ProcessSignalGeneratingFunctionNumber") or "")
			if generator_tag:
				self.add_component(
					Component(
						tag=generator_tag,
						component_type=INSTRUMENT,
						component_class="ProcessSignalGeneratingFunction",
						description="",  # the ISA meaning is derived on the record, not file data
						parent_tag=tag or parent_tag,
						item_id=generator_id,
						loop_number=number.lstrip("-_ "),
					)
				)

	def read_actuating_object(self, element: ET.Element) -> None:
		number = str(_data(element).get("ActuatingSystemNumber") or "")
		valve_id = ""
		for child in self._children(element):
			child_name = _type_name(child)[1]
			if child_name == "OperatedValveReference":
				valves = _refs(child, "Valve")
				valve_id = valves[0] if valves else valve_id
			elif child.get("id") in self.positions:
				x, y = self.positions[child.get("id")]
				self.add_item(Item(id=child.get("id"), kind="Actuator", component_class=child_name, x=x, y=y))
		if not number:
			return
		valve = self.items.get(valve_id)
		if valve is not None and not valve.tag:
			valve.tag = number
		self.add_component(
			Component(
				tag=number,
				component_type=VALVE,
				component_class=valve.component_class if valve is not None else "ActuatingSystem",
				description="",  # the ISA meaning is derived on the record, not file data
				parent_tag=self.owner_tag(valve_id) if valve_id else "",
				item_id=valve_id,
			)
		)

	def piping_edges(self) -> list[tuple[str, str, str]]:
		return self.edges
