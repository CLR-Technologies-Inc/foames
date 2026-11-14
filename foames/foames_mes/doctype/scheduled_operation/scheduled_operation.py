# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""One operation placed by a Production Schedule. Written by the schedule's Build and replaced
each time it is built again; not edited by hand."""

from frappe.model.document import Document


class ScheduledOperation(Document):
	pass
