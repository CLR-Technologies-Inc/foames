# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0


def check_ehs():
	"""Scheduled hourly: expire permits, raise suggestions for overdue actions, investigations and reviews."""
	from foames.foames_ehs.rules import check_ehs as check

	check()
