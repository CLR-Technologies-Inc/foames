# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0


def check_risks():
	"""Scheduled daily: raise suggestions for risks above tolerance, overdue reviews and verifications,
	failed controls, breached indicators and sources that now rate higher."""
	from foames.foames_risk.register import check_risks as check

	return check()
