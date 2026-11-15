# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Comparability of one quality attribute between the sending and the receiving site.

The approach, margin and limits come from the attribute's row in the tech transfer package, so the
rule is fixed before the data is in. Every save recomputes the outcome with
foames.foames_lifesci.transfer.assess_comparability. Submitting records the review; it needs an
approved package, a decisive outcome (not Insufficient Data) and a reviewer other than the person
who entered the results.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime

from foames.foames_lifesci import transfer


class ComparabilityAssessment(Document):
	def validate(self):
		package = frappe.get_doc("Tech Transfer Package", self.tech_transfer_package)
		row = package.attribute(self.attribute)
		if not row:
			frappe.throw(
				_("{0} is not a quality attribute of {1}").format(self.attribute, self.tech_transfer_package)
			)
		if not row.approach:
			frappe.throw(_("The package sets no comparability approach for {0}").format(self.attribute))
		self.approach = row.approach
		self.limits = row.limits
		self.lower, self.upper = row.lower, row.upper
		self.margin, self.k = row.margin, row.k
		self.coverage = row.coverage if row.coverage else transfer.DEFAULT_COVERAGE
		result = transfer.assess_comparability(
			[flt(r.value) for r in self.results if r.site == "Sending"],
			[flt(r.value) for r in self.results if r.site == "Receiving"],
			self.approach,
			margin=flt(self.margin),
			k=flt(self.k) or transfer.DEFAULT_K,
			coverage=flt(self.coverage),
			limits=self.limits,
			lower=flt(self.lower),
			upper=flt(self.upper),
		)
		s, r, interval = result["sending"], result["receiving"], result["interval"] or {}
		self.update(
			{
				"sending_n": s["n"],
				"sending_mean": s["mean"],
				"sending_sd": s["sd"],
				"receiving_n": r["n"],
				"receiving_mean": r["mean"],
				"receiving_sd": r["sd"],
				"interval_low": interval.get("low"),
				"interval_high": interval.get("high"),
				"out_of_spec": len(result["out_of_spec"]),
				"outcome": result["outcome"],
				"outcome_detail": result["detail"],
			}
		)

	def before_submit(self):
		if frappe.db.get_value("Tech Transfer Package", self.tech_transfer_package, "docstatus") != 1:
			frappe.throw(_("Comparability is reviewed against an approved tech transfer package"))
		if self.outcome == "Insufficient Data":
			frappe.throw(_("There are not enough results to judge comparability"))
		if frappe.session.user == self.owner:
			frappe.throw(_("The review is recorded by someone other than the person who entered the results"))

	def on_submit(self):
		self.db_set({"reviewed_by": frappe.session.user, "reviewed_on": now_datetime()})
