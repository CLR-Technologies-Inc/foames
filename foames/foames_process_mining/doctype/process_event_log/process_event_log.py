# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""A saved extraction: the events in a window from chosen sources, kept as JSON on the record so
the same log can be analysed, compared and exported again. Extraction runs on demand from the
form or the API; a scheduled extraction is one `frappe.enqueue` call away."""

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

from foames.foames_process_mining import conformance, discovery
from foames.foames_process_mining.eventlog import EventLog
from foames.foames_process_mining.extractors import build_event_log
from foames.foames_process_mining.ocel import to_ocel_json
from foames.foames_process_mining.xes import to_xes


class ProcessEventLog(Document):
	def validate(self):
		if self.from_time and self.to_time and self.to_time <= self.from_time:
			frappe.throw(_("To must be after From"))

	@frappe.whitelist()
	def extract(self) -> dict:
		"""Build the log from the sources and store it on the record."""
		frappe.has_permission(self.doctype, "write", self, throw=True)
		try:
			log = build_event_log(
				self.from_time,
				self.to_time,
				[row.source for row in self.sources] or None,
				name=self.title,
				built_in=bool(self.include_built_in),
			)
		except Exception:
			# Not re-raised: an exception would roll the request back and lose the Failed state.
			frappe.log_error(title=f"Process Event Log {self.name}", message=frappe.get_traceback())
			self.db_set({"status": "Failed", "extraction_note": frappe.get_traceback()[-500:]})
			frappe.msgprint(_("Extraction failed; see the note and the Error Log"), indicator="red")
			return {"status": "Failed", "error": frappe.get_traceback().strip().splitlines()[-1]}
		summary = log.summary()
		self.events_json = json.dumps(log.to_dicts(), default=str)
		self.event_count = summary["events"]
		self.case_count = summary["cases"]
		self.variant_count = summary["variants"]
		self.activity_count = summary["activities"]
		self.extracted_on = now_datetime()
		self.status = "Extracted"
		self.extraction_note = ""
		self.save()
		return summary

	def load(self) -> EventLog:
		rows = self.events_json
		if isinstance(rows, str):
			rows = json.loads(rows or "[]")
		return EventLog.from_dicts(rows or [], name=self.title)

	@frappe.whitelist()
	def discover(self, min_edge_count: int = 1) -> dict:
		frappe.has_permission(self.doctype, "read", self, throw=True)
		log = self.load()
		dfg = discovery.discover_dfg(log).filter(min_edge_count=int(min_edge_count))
		return {
			"dfg": dfg.to_dict(),
			"dot": dfg.to_dot(),
			"variants": discovery.variant_table(log, limit=25),
			"throughput": discovery.throughput(log),
			"bottlenecks": discovery.bottlenecks(log),
			"rework": discovery.rework(log),
		}

	@frappe.whitelist()
	def check_against(self, reference: str) -> dict:
		"""Conformance of this log against the graph discovered from another Process Event Log."""
		frappe.has_permission(self.doctype, "read", self, throw=True)
		model = discovery.discover_dfg(frappe.get_doc(self.doctype, reference).load())
		return conformance.check_conformance(self.load(), model).to_dict()

	@frappe.whitelist()
	def export_file(self, fmt: str = "xes") -> str:
		"""Write the log as an XES or OCEL file attached to this record; returns the file URL."""
		frappe.has_permission(self.doctype, "write", self, throw=True)
		fmt = (fmt or "xes").lower()
		if fmt == "xes":
			content, extension = to_xes(self.load()), "xes"
		elif fmt in ("ocel", "ocel2", "json"):
			content, extension = to_ocel_json(self.load()), "jsonocel"
		else:
			frappe.throw(_("Unknown format {0}; use xes or ocel").format(fmt))
		file = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": f"{frappe.scrub(self.name)}.{extension}",
				"attached_to_doctype": self.doctype,
				"attached_to_name": self.name,
				"content": content,
				"is_private": 1,
			}
		).insert()
		return file.file_url
