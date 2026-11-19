# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

import frappe
from frappe import _
from frappe.model.document import Document


class SimulationSettings(Document):
	def validate(self):
		if self.enabled and not (self.provider_url or "").strip():
			frappe.throw(_("Provider URL is required when simulation is enabled"))
		url = (self.provider_url or "").strip()
		if url and not url.lower().startswith(("http://", "https://")):
			frappe.throw(_("Provider URL must start with http:// or https://"))
