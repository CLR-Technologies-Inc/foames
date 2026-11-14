# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""One tagged item of the plant's P&IDs: equipment, an instrument, a line or a valve.

The register is plant-wide: the tag is the record's name, so `FIC-101` is one record however many
drawings show it. The Live Signal section says which Machine Events carry the tag's value; the
viewer, the rules and agents read the value through it. FoaMES never writes to the instrument.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime

from foames.foames_pid.isa51 import normalise, try_parse_tag
from foames.foames_pid.overlay import STALE_MINUTES, overlay_entry

SIGNAL_FIELDS = [
	"name",
	"tag",
	"component_type",
	"component_class",
	"description",
	"drawing",
	"parent_component",
	"machine",
	"event_type",
	"signal_name",
	"signal_source",
	"signal_address",
	"historian_tag",
	"engineering_unit",
	"range_low",
	"range_high",
]


class PIDComponent(Document):
	def autoname(self):
		self.tag = normalise(self.tag)
		self.name = self.tag

	def validate(self):
		if self.is_new():
			self.tag = normalise(self.tag)
		if self.parent_component == self.name:
			frappe.throw(_("A component cannot be located on itself"))
		self.check_parent_cycle()
		self.set_isa_identification()
		if self.signal_name and not self.machine:
			frappe.throw(_("Choose the Machine that reports {0}").format(self.signal_name))
		if self.machine and self.signal_name and not self.event_type:
			self.event_type = "Measurement"
		if (
			self.range_low is not None
			and self.range_high is not None
			and (self.range_low or self.range_high)
			and self.range_high <= self.range_low
		):
			frappe.throw(_("Range High must be above Range Low"))

	def check_parent_cycle(self):
		seen = {self.name}
		current = self.parent_component
		while current:
			if current in seen:
				frappe.throw(_("Located On would make a loop through {0}").format(current))
			seen.add(current)
			current = frappe.db.get_value("PID Component", current, "parent_component")

	def set_isa_identification(self):
		if self.component_type not in ("Instrument", "Valve"):
			self.isa_meaning = self.measured_variable = self.functions = None
			return
		parsed = try_parse_tag(self.tag)
		if not parsed:
			self.isa_meaning = self.measured_variable = self.functions = None
			return
		self.isa_meaning = parsed.meaning
		self.measured_variable = parsed.variable
		self.functions = ", ".join(parsed.functions)
		self.loop_number = self.loop_number or parsed.loop_number


def latest_values(components: list[dict]) -> dict[str, dict]:
	"""The latest Machine Event value for each component's signal: {tag: {value, timestamp}}."""
	event = frappe.qb.DocType("Machine Event")
	result: dict[str, dict] = {}
	for component in components:
		if not (component.get("machine") and component.get("signal_name")):
			continue
		if component.get("event_type") not in ("Measurement", "Count"):
			continue
		if component.get("event_type") == "Count":
			condition = event.counter_name == component["signal_name"]
			value_field = event.counter_value
		else:
			condition = event.measurement_name == component["signal_name"]
			value_field = event.value
		rows = (
			frappe.qb.from_(event)
			.select(value_field.as_("value"), event.timestamp)
			.where(
				(event.machine == component["machine"])
				& (event.event_type == component["event_type"])
				& condition
			)
			.orderby(event.timestamp, order=frappe.qb.desc)
			.limit(1)
			.run(as_dict=True)
		)
		if rows:
			result[component["tag"]] = {
				"value": rows[0]["value"],
				"timestamp": get_datetime(rows[0]["timestamp"]),
			}
	return result


def build_overlay(components: list[dict], stale_minutes: int = STALE_MINUTES) -> dict[str, dict]:
	"""{tag: overlay entry} for components with a machine or a signal, as the viewer shows them."""
	linked = [c for c in components if c.get("machine")]
	if not linked:
		return {}
	statuses = dict(
		frappe.get_all(
			"Machine",
			filters={"name": ["in", list({c["machine"] for c in linked})]},
			fields=["name", "status"],
			as_list=True,
		)
	)
	values = latest_values(linked)
	now = now_datetime()
	overlay = {}
	for component in linked:
		entry = overlay_entry(
			component, statuses.get(component["machine"]), values.get(component["tag"]), now, stale_minutes
		)
		if entry.get("at"):
			entry["at"] = str(entry["at"])
		overlay[component["tag"]] = entry
	return overlay


def signal_components(filters: dict | None = None) -> list[dict]:
	"""Components with their signal fields, as the overlay and the rules read them."""
	return frappe.get_all(
		"PID Component",
		filters={"disabled": 0, **(filters or {})},
		fields=SIGNAL_FIELDS,
		order_by="name asc",
		limit_page_length=0,
	)
