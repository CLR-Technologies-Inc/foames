# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""A shift calendar machines share: shifts with start, length and weekdays, plus non-working days.

The arithmetic lives in foames.foames_mes.shifts; this class only checks the rows and turns them
into that module's types.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate

from foames.foames_mes.shifts import WEEKDAYS, make_shift, problems


class ShiftPattern(Document):
	def validate(self):
		found = problems(shifts_of(self))
		if found:
			frappe.throw("<br>".join(_(p) for p in found), title=_("Invalid Shift Pattern"))
		dates = [str(getdate(h.holiday_date)) for h in self.holidays]
		duplicate = sorted({d for d in dates if dates.count(d) > 1})
		if duplicate:
			frappe.throw(_("Non-working day {0} is listed more than once").format(", ".join(duplicate)))


def shifts_of(doc) -> list:
	return [
		make_shift(
			row.shift_name,
			row.start_time,
			row.duration_minutes,
			**{day: row.get(day) for day in WEEKDAYS},
		)
		for row in doc.shifts
	]


def load_pattern(name: str):
	"""(shifts, holidays) of a pattern, for foames.foames_mes.shifts."""
	doc = frappe.get_cached_doc("Shift Pattern", name)
	return shifts_of(doc), frozenset(getdate(h.holiday_date) for h in doc.holidays)
