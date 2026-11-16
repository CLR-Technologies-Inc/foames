# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""The 5 x 5 heat map of open risks: impact down the side from 5 to 1, likelihood across from 1 to 5,
the number of risks in each cell. Residual risk by default, or inherent risk to see what the
controls are doing."""

import frappe
from frappe import _

from foames.foames_mes.report.utils import summary_item
from foames.foames_risk.register import heat_map_rows, settings
from foames.foames_risk.risk import IMPACT_LABELS, LIKELIHOOD_LABELS, heat_map, rating


def execute(filters=None):
	filters = frappe._dict(filters or {})
	which = "inherent" if filters.get("basis") == "Inherent" else "residual"
	risks = heat_map_rows(filters)
	grid = heat_map(risks, which)
	bands = settings().get("bands")
	rows = []
	for i, counts in enumerate(grid):
		impact = 5 - i
		row = {"impact": impact, "impact_label": _(IMPACT_LABELS[impact])}
		for likelihood in range(1, 6):
			row[f"l{likelihood}"] = counts[likelihood - 1]
			row[f"r{likelihood}"] = rating(impact * likelihood, bands)
		rows.append(row)
	columns = [
		{"fieldname": "impact_label", "label": _("Impact"), "fieldtype": "Data", "width": 130},
		*[
			{
				"fieldname": f"l{n}",
				"label": _("Likelihood {0}: {1}").format(n, _(LIKELIHOOD_LABELS[n])),
				"fieldtype": "Int",
				"width": 150,
			}
			for n in range(1, 6)
		],
	]
	high = sum(
		grid[5 - impact][likelihood - 1]
		for impact in range(1, 6)
		for likelihood in range(1, 6)
		if rating(impact * likelihood, bands) in ("High", "Very High")
	)
	return (
		columns,
		rows,
		None,
		None,
		[
			summary_item(_("Open Risks"), len(risks), "Int", "Blue"),
			summary_item(_("High or Very High"), high, "Int", "Red"),
		],
	)
