# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

import frappe
from frappe import _
from frappe.model.document import Document

from foames.foames_kernel import write_gate


class ConnectorWritePolicy(Document):
	"""Whether one connector (an adapter, an MES Connection, a bridge, the MCP server) may write."""

	def validate(self):
		self.connector = (self.connector or "").strip()
		if not self.connector:
			frappe.throw(_("A policy needs a connector key"))
		before = self.get_doc_before_save()
		turned_writable = before and before.read_only and not self.read_only
		if turned_writable and not (self.approval_reference or "").strip():
			frappe.throw(
				_(
					"Record the change control or validation reference that approves writes before turning read-only off"
				)
			)

	def on_update(self):
		write_gate.log_policy_change(
			self, _("Created on the connector's first write") if self.flags.created_by_gate else ""
		)

	def on_trash(self):
		write_gate.audit(
			write_gate.policy.EVENT_POLICY_CHANGED,
			self.connector,
			reason=_("Policy deleted; the connector is new again and starts as the site says"),
			details={"deleted": True, "read_only": self.read_only},
		)
