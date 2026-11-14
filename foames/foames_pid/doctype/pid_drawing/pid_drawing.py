# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""A P&ID sheet: its title block, its layout and the connections drawn on it.

A drawing is filled either from a DEXPI file (Import DEXPI) or by hand (components that name the
drawing, and connection rows). The tag register lives in PID Component; importing again updates
what the file says about each tag (type, class, description, location, attributes) and never
touches what people set on the FoaMES side (the machine, the signal, the range, the ERP link).
"""

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from foames.foames_pid import dexpi
from foames.foames_pid.doctype.pid_component.pid_component import build_overlay, signal_components
from foames.foames_pid.isa51 import normalise
from foames.foames_pid.svg import auto_layout, render_svg

# Attributes beyond this many per component are left out of the register (they stay in the file).
MAX_ATTRIBUTES = 60


class PIDDrawing(Document):
	def validate(self):
		for row in self.connections:
			if row.from_component == row.to_component:
				frappe.throw(_("Row {0}: a connection needs two different components").format(row.idx))

	@frappe.whitelist()
	def import_dexpi(self):
		"""Read the attached DEXPI file into the tag register and this drawing's layout."""
		self.check_permission("write")
		if not self.source_file:
			frappe.throw(_("Attach a DEXPI file first"))
		file = frappe.get_doc("File", {"file_url": self.source_file})
		content = file.get_content()
		try:
			diagram = dexpi.parse(content)
		except dexpi.DexpiError as error:
			frappe.throw(_("The DEXPI file could not be read: {0}").format(str(error)))
		return self.apply_diagram(diagram)

	def apply_diagram(self, diagram: dexpi.PlantDiagram) -> dict:
		created, updated, elsewhere = [], [], []
		imported: dict[str, dexpi.Component] = {}
		for component in diagram.components:
			tag = normalise(component.tag)
			if not tag or tag in imported:
				continue
			imported[tag] = component
			if frappe.db.exists("PID Component", tag):
				doc = frappe.get_doc("PID Component", tag)
				if doc.drawing and doc.drawing != self.name:
					elsewhere.append(tag)  # that drawing owns the tag; this one only shows it
					continue
				updated.append(tag)
			else:
				doc = frappe.new_doc("PID Component")
				doc.tag = tag
				created.append(tag)
			doc.component_type = component.component_type
			doc.component_class = component.component_class or doc.component_class
			doc.description = component.description or doc.description
			doc.loop_number = component.loop_number or doc.loop_number
			doc.drawing = self.name
			doc.plant_area = doc.plant_area or self.plant_area
			doc.dexpi_id = component.item_id
			doc.set(
				"attributes",
				[
					{
						"attribute": name[:140],
						"value": str(value.get("value"))[:140],
						"units": value.get("units"),
					}
					for name, value in list(component.attributes.items())[:MAX_ATTRIBUTES]
				],
			)
			doc.save()

		# Parents once every tag exists; a parent the file names but does not tag is left empty.
		for tag, component in imported.items():
			if tag in elsewhere or not component.parent_tag:
				continue
			parent = normalise(component.parent_tag)
			if parent != tag and frappe.db.exists("PID Component", parent):
				frappe.db.set_value("PID Component", tag, "parent_component", parent, update_modified=False)

		self.set("connections", [])
		for link in diagram.connections:
			a, b = normalise(link.from_tag), normalise(link.to_tag)
			if a != b and frappe.db.exists("PID Component", a) and frappe.db.exists("PID Component", b):
				self.append(
					"connections",
					{"kind": link.kind, "from_component": a, "to_component": b, "via": link.via},
				)

		previous = set(frappe.get_all("PID Component", filters={"drawing": self.name}, pluck="name"))
		gone = sorted(previous - set(imported))

		self.view = json.dumps(diagram.view())
		self.source_format = "DEXPI"
		self.dexpi_version = diagram.dexpi_version
		self.originating_system = (diagram.originating_system or "")[:140]
		self.imported_on = now_datetime()
		self.title = self.title or diagram.title or diagram.drawing_name
		self.revision = self.revision or diagram.revision
		self.component_count = frappe.db.count("PID Component", {"drawing": self.name})
		lines = [_("{0} created, {1} updated.").format(len(created), len(updated))]
		if elsewhere:
			lines.append(_("Owned by another drawing, left as they are: {0}").format(", ".join(elsewhere)))
		if gone:
			lines.append(
				_("On this drawing before but not in the file (kept, check them): {0}").format(
					", ".join(gone)
				)
			)
		lines += diagram.warnings[:20]
		self.import_summary = "\n".join(lines)
		self.save()
		return {
			"created": created,
			"updated": updated,
			"elsewhere": elsewhere,
			"not_in_file": gone,
			"warnings": diagram.warnings,
			"summary": diagram.summary(),
		}

	def get_view(self) -> dict:
		"""The layout: the imported one, or one built from the register for a manual drawing."""
		if self.view:
			view = json.loads(self.view) if isinstance(self.view, str) else self.view
			if view and view.get("items") is not None:
				return view
		components = frappe.get_all(
			"PID Component",
			filters={"drawing": self.name, "disabled": 0},
			fields=[
				"tag",
				"component_type",
				"component_class",
				"parent_component",
				"pos_x",
				"pos_y",
			],
			order_by="name asc",
			limit_page_length=0,
		)
		for component in components:
			component["parent_tag"] = component.pop("parent_component") or ""
		connections = [
			{
				"kind": row.kind,
				"from_tag": row.from_component,
				"to_tag": row.to_component,
				"via": row.via or "",
			}
			for row in self.connections
		]
		view = auto_layout(components, connections)
		placed = {c["tag"]: (c["pos_x"], c["pos_y"]) for c in components if c.get("pos_x") or c.get("pos_y")}
		for item in view["items"]:
			if item["tag"] in placed:
				item["x"], item["y"] = placed[item["tag"]]
		return view

	def render(self, with_values: bool = True) -> dict:
		view = self.get_view()
		tags = {item.get("tag") for item in view.get("items") or [] if item.get("tag")}
		components = signal_components({"name": ["in", list(tags)]}) if tags else []
		overlay = build_overlay(components) if with_values else {}
		descriptions = {c["tag"]: c.get("description") or "" for c in components}
		return {
			"drawing": self.name,
			"title": self.title,
			"revision": self.revision,
			"svg": render_svg(view, overlay, descriptions),
			"overlay": overlay,
			"tags": sorted(tags),
		}
