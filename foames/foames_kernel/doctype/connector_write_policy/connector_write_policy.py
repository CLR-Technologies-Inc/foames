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

import frappe
from frappe import _
from frappe.model.document import Document

from foames.foames_kernel import write_gate
from foames.foames_kernel.record_scope import policy_loosening

# Who may weaken a connector's write policy. Writing the policy (FoaMES Engineer, FoaMES Quality)
# is enough to tighten it; loosening it is a separate authority, so the people who request and
# execute writes cannot also lift the gate on them.
POLICY_ADMIN_ROLES = ("FoaMES Policy Administrator", "System Manager")


def may_loosen_policies(user: str | None = None) -> bool:
	user = user or frappe.session.user
	if user == "Administrator":
		return True
	return bool(set(POLICY_ADMIN_ROLES) & set(frappe.get_roles(user)))


class ConnectorWritePolicy(Document):
	"""Whether one connector (an adapter, an MES Connection, a bridge, the MCP server) may write."""

	def validate(self):
		self.connector = (self.connector or "").strip()
		if not self.connector:
			frappe.throw(_("A policy needs a connector key"))
		before = self.get_doc_before_save()
		self._check_authority(before)
		turned_writable = before and before.read_only and not self.read_only
		if turned_writable and not (self.approval_reference or "").strip():
			frappe.throw(
				_(
					"Record the change control or validation reference that approves writes before turning read-only off"
				)
			)

	def _check_authority(self, before):
		"""Refuse a change that weakens the gate unless the actor holds a policy administration role.
		The gate itself creates a connector's first policy exactly as the site settings say."""
		if self.flags.created_by_gate:
			return
		reasons = policy_loosening(before.as_dict() if before else None, self.as_dict())
		if reasons and not may_loosen_policies():
			frappe.throw(
				_("Only a FoaMES Policy Administrator can weaken a connector write policy ({0})").format(
					"; ".join(reasons)
				),
				frappe.PermissionError,
			)

	def on_update(self):
		write_gate.log_policy_change(
			self, _("Created on the connector's first write") if self.flags.created_by_gate else ""
		)

	def on_trash(self):
		# Deleting a policy makes the connector new again, which may let it write.
		if self.read_only and not may_loosen_policies():
			frappe.throw(
				_("Only a FoaMES Policy Administrator can delete a read-only connector write policy"),
				frappe.PermissionError,
			)
		write_gate.audit(
			write_gate.policy.EVENT_POLICY_CHANGED,
			self.connector,
			reason=_("Policy deleted; the connector is new again and starts as the site says"),
			details={"deleted": True, "read_only": self.read_only},
		)
