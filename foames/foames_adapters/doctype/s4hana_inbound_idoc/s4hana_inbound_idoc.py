# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document

from foames.foames_adapters.s4hana import idoc as idoc_parser
from foames.foames_adapters.s4hana.adapter import ADAPTER_KEY


class S4HANAInboundIDoc(Document):
	"""An IDoc S/4HANA posted to FoaMES. Kept once per sender and IDoc number, so a resend is
	recognized and not processed twice."""

	def autoname(self):
		self.name = inbound_name(self.sender, self.idoc_number)


def inbound_name(sender: str, idoc_number: str) -> str:
	return f"{sender or 'S4HANA'}-{idoc_number}"


def receive(idoc: idoc_parser.IDoc) -> tuple[str, bool]:
	"""Store and process one parsed IDoc. Returns its record name and whether it was new."""
	name = inbound_name(idoc.sender, idoc.number)
	if frappe.db.exists("S4HANA Inbound IDoc", name):
		return name, False

	summary = idoc_parser.summarize(idoc)
	doc = frappe.get_doc(
		{
			"doctype": "S4HANA Inbound IDoc",
			"idoc_number": idoc.number,
			"message_type": idoc.message_type,
			"idoc_type": idoc.control.get("IDOCTYP", ""),
			"sender": idoc.sender,
			"control": json.dumps(idoc.control, indent=1),
			"segments": json.dumps(idoc.segments, indent=1),
			"summary": json.dumps(summary, indent=1) if summary else None,
		}
	).insert(ignore_permissions=True)

	frappe.db.savepoint("foames_s4hana_idoc")
	try:
		if summary.get("reference_type") and summary.get("external_id"):
			from foames.foames_kernel.doctype.external_reference.external_reference import get_reference

			doc.external_reference = get_reference(
				summary["reference_type"], summary["external_id"], ADAPTER_KEY
			)
		for handler in frappe.get_hooks("foames_s4hana_idoc_handlers", {}).get(idoc.message_type, []):
			frappe.get_attr(handler)(doc, idoc, summary)
		doc.status = "Processed"
	except Exception as e:
		frappe.db.rollback(save_point="foames_s4hana_idoc")
		doc.status = "Failed"
		doc.error = str(e)[:1000]
		frappe.log_error(title=_("S/4HANA IDoc {0} could not be processed").format(name))
	doc.save(ignore_permissions=True)
	return doc.name, True
