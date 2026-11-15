# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""A directed link between two topology assets: a pipe, wiring or network link on the physical
layer, a data flow, derivation, posting or delegation on the data layer, or an agent running on
a host. Containment is not a link; it is Part Of on the asset."""

import frappe
from frappe import _
from frappe.model.document import Document

from foames.foames_topology import model


class TopologyLink(Document):
	def validate(self):
		if self.from_asset == self.to_asset:
			frappe.throw(_("A link needs two different assets"))
		self.layer = model.LINK_TYPES.get(self.link_type, model.DATA)
		self.link_key = f"{self.from_asset}|{self.link_type}|{self.to_asset}"
		self.tenant = check_same_tenant(self.from_asset, self.to_asset, self.tenant)


def check_same_tenant(a, b, tenant):
	"""The tenant a link or binding between a and b belongs to. Refuses one that joins two tenants."""
	tenants = {
		t
		for t in frappe.get_all("Topology Asset", {"name": ("in", [a, b])}, pluck="tenant")
		if t
	}
	if len(tenants) > 1:
		frappe.throw(_("{0} and {1} belong to different tenants").format(a, b))
	asset_tenant = next(iter(tenants), None)
	if tenant and asset_tenant and tenant != asset_tenant:
		frappe.throw(_("The assets belong to tenant {0}").format(asset_tenant))
	return tenant or asset_tenant
