# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""A company or site whose topology is kept apart from the others.

Assets, links and bindings carry a Tenant link, so a User Permission on Topology Tenant limits a
user to their own tenants' records in every list, report and graph read. A user with no such
restriction (an owner or an engineer) sees the combined view across tenants, read-only like
every topology view."""

from frappe.model.document import Document


class TopologyTenant(Document):
	def validate(self):
		self.title = self.title or self.tenant_name
