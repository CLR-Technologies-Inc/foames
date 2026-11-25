# Copyright 2026 CLR Technologies Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

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

			# receive_idoc checked the caller's permission on the IDoc; the reference it derives is
			# recorded with that authority, since integration users cannot create references.
			doc.external_reference = get_reference(
				summary["reference_type"], summary["external_id"], ADAPTER_KEY, ignore_permissions=True
			)
		for handler in frappe.get_hooks("foames_s4hana_idoc_handlers", {}).get(idoc.message_type, []):
			frappe.get_attr(handler)(doc, idoc, summary)
		doc.status = "Processed"
	except Exception as e:
		frappe.db.rollback(save_point="foames_s4hana_idoc")
		doc.external_reference = None  # rolled back with the savepoint
		doc.status = "Failed"
		doc.error = str(e)[:1000]
		frappe.log_error(title=_("S/4HANA IDoc {0} could not be processed").format(name))
	doc.save(ignore_permissions=True)
	return doc.name, True
