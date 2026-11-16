# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0


def check_stale_points():
	"""Every five minutes: building points that stopped reporting raise a communication-loss alarm."""
	from foames.foames_bms.engine import check_stale_points as check

	check()


def check_bms():
	"""Hourly: unacknowledged Critical and High building alarms, and unwatched hazmat storage."""
	from foames.foames_bms.engine import check_bms as check

	check()
