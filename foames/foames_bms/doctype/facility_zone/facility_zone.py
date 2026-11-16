# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""A site, building, floor, room or area, as a tree. Building systems sit in a zone and serve one."""

from frappe.utils.nestedset import NestedSet


class FacilityZone(NestedSet):
	nsm_parent_field = "parent_facility_zone"
