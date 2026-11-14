# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Scheduler entry points for commissioning."""


def check_commissioning():
	"""Scheduled daily: suggestions for overdue punch items and packages past their planned handover."""
	from foames.foames_commissioning.doctype.commissioning_package.commissioning_package import (
		check_commissioning as check,
	)

	return check()
