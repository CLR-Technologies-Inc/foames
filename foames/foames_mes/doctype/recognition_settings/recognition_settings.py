# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""How recognition shows on the floor, what FoaMES recognizes on its own, and who opted out.
Read it through foames.foames_mes.doctype.recognition.recognition.recognition_settings, which fills
in the defaults for values never saved."""

import frappe
from frappe import _
from frappe.model.document import Document

from foames.foames_mes.recognition import parse_thresholds


class RecognitionSettings(Document):
	def validate(self):
		seen = set()
		for row in self.opt_out:
			if row.user in seen:
				frappe.throw(_("{0} is listed twice").format(row.user))
			seen.add(row.user)
		self.milestone_thresholds = ",".join(str(t) for t in parse_thresholds(self.milestone_thresholds))
