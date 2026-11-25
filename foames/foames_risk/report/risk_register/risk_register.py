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

"""The risk register: one row per risk with the columns of a risk profile, from the statement and the
inherent rating through the response and the residual rating to the tolerance, the proposed response
and the owner. Open risks by default."""

import frappe
from frappe import _
from frappe.utils import getdate, nowdate

from foames.foames_mes.report.utils import chart_of, summary_item
from foames.foames_risk.register import OPEN_STATUSES
from foames.foames_risk.risk import RATINGS

FIELDS = (
	"name",
	"title",
	"category",
	"objective",
	"fraud_impact",
	"status",
	"risk_statement",
	"inherent_impact",
	"inherent_likelihood",
	"inherent_score",
	"inherent_rating",
	"response",
	"transfer_to",
	"strongest_control",
	"controls_in_place",
	"residual_impact",
	"residual_likelihood",
	"residual_score",
	"residual_rating",
	"tolerance",
	"within_tolerance",
	"accepted_by",
	"proposed_response",
	"target_score",
	"target_date",
	"risk_owner",
	"next_review_on",
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	rows = get_rows(filters)
	today = getdate(nowdate())
	for r in rows:
		r["review_overdue"] = int(bool(r.next_review_on and getdate(r.next_review_on) < today))
	counts = [sum(1 for r in rows if r.residual_rating == rating) for rating in RATINGS]
	return (
		get_columns(),
		rows,
		None,
		chart_of(
			[_(r) for r in RATINGS],
			[{"name": _("Risks"), "values": counts}],
			colors=["#29CD42"],
		)
		if rows
		else None,
		[
			summary_item(_("Risks"), len(rows), "Int", "Blue"),
			summary_item(
				_("Above Tolerance"),
				sum(1 for r in rows if not r.within_tolerance and not r.accepted_by),
				"Int",
				"Red",
			),
			summary_item(
				_("Accepted Above Tolerance"),
				sum(1 for r in rows if not r.within_tolerance and r.accepted_by),
				"Int",
				"Orange",
			),
			summary_item(_("Reviews Overdue"), sum(r["review_overdue"] for r in rows), "Int", "Orange"),
		],
	)


def get_rows(filters) -> list:
	conditions = {}
	if filters.get("status"):
		conditions["status"] = filters.status
	elif not filters.get("include_closed"):
		conditions["status"] = ("in", OPEN_STATUSES)
	for field in ("category", "risk_owner", "residual_rating", "objective", "machine"):
		if filters.get(field):
			conditions[field] = filters.get(field)
	if filters.get("above_tolerance"):
		conditions["within_tolerance"] = 0
	return frappe.get_list(
		"Enterprise Risk", filters=conditions, fields=list(FIELDS), order_by="residual_score desc, name asc"
	)


def get_columns() -> list[dict]:
	def col(fieldname, label, fieldtype="Data", width=100, **kw):
		return {"fieldname": fieldname, "label": _(label), "fieldtype": fieldtype, "width": width, **kw}

	return [
		col("name", "Risk", "Link", 140, options="Enterprise Risk"),
		col("title", "Risk Name", width=200),
		col("category", "Category", "Link", 150, options="Risk Category"),
		col("objective", "Objective"),
		col("risk_statement", "Risk Statement", width=300),
		col("inherent_impact", "Inherent Impact", "Int", 70),
		col("inherent_likelihood", "Inherent Likelihood", "Int", 70),
		col("inherent_score", "Inherent Score", "Int", 70),
		col("inherent_rating", "Inherent Rating"),
		col("response", "Response", width=90),
		col("transfer_to", "Transferred or Shared With", width=140),
		col("strongest_control", "Strongest Control", width=150),
		col("controls_in_place", "Controls in Place", "Int", 70),
		col("residual_impact", "Residual Impact", "Int", 70),
		col("residual_likelihood", "Residual Likelihood", "Int", 70),
		col("residual_score", "Residual Score", "Int", 70),
		col("residual_rating", "Residual Rating"),
		col("tolerance", "Tolerance"),
		col("within_tolerance", "Within Tolerance", "Check", 70),
		col("accepted_by", "Accepted By", "Link", 140, options="User"),
		col("proposed_response", "Proposed Response", width=90),
		col("target_score", "Target Score", "Int", 70),
		col("target_date", "Target Date", "Date", 100),
		col("risk_owner", "Risk Owner", "Link", 140, options="User"),
		col("status", "Status", width=90),
		col("next_review_on", "Next Review", "Date", 100),
		col("review_overdue", "Review Overdue", "Check", 70),
		col("fraud_impact", "Fraud Impact", width=110),
	]
