# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Lineside stock read from ERPNext, for the material flow check. Read only.

ERPNext keeps one Bin row per item and warehouse with the actual, ordered, reserved and projected
quantities. A Lineside Bin names the item and, as its ERP location, the warehouse that holds the
lineside stock; with no warehouse the item's quantities are summed over every warehouse.
"""

from __future__ import annotations

import frappe

from foames.foames_adapters.erpnext import erpnext_installed

QUANTITIES = ("actual_qty", "projected_qty", "ordered_qty", "reserved_qty", "indented_qty")


def read_stock(item: str, location: str | None = None) -> dict | None:
	"""Quantities of an item in a warehouse (or in all of them), or None when ERPNext is not installed
	or does not know the item."""
	if not item or not erpnext_installed() or not frappe.db.exists("Item", item):
		return None
	bin_ = frappe.qb.DocType("Bin")
	from frappe.query_builder.functions import Sum

	query = (
		frappe.qb.from_(bin_).select(*(Sum(bin_[q]).as_(q) for q in QUANTITIES)).where(bin_.item_code == item)
	)
	if location:
		query = query.where(bin_.warehouse == location)
	row = query.run(as_dict=True)
	row = row[0] if row else {}
	return {
		"source": "ERPNext",
		"item": item,
		"location": location,
		**{q: float(row.get(q) or 0) for q in QUANTITIES},
	}
