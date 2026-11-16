# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""One operation placed by a Production Schedule. Written by the schedule's Build and replaced
each time it is built again; not edited by hand."""

from frappe.model.document import Document


class ScheduledOperation(Document):
	pass
