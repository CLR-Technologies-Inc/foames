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


def check_stale_points():
	"""Every five minutes: building points that stopped reporting raise a communication-loss alarm."""
	from foames.foames_bms.engine import check_stale_points as check

	check()


def check_bms():
	"""Hourly: unacknowledged Critical and High building alarms, and unwatched hazmat storage."""
	from foames.foames_bms.engine import check_bms as check

	check()
