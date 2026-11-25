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

"""Suggestion rules over the P&ID tag register, registered under `foames_suggestion_rules`."""

from __future__ import annotations

from foames.foames_pid.doctype.pid_component.pid_component import build_overlay, signal_components
from foames.foames_pid.overlay import signal_findings

WINDOW_HOURS = 24


def instrument_signals(snapshot: dict) -> list[dict]:
	"""Linked instruments that stopped reporting, or that read at a calibrated range limit."""
	components = [
		c
		for c in signal_components({"machine": ["is", "set"], "event_type": ["in", ["Measurement", "Count"]]})
		if c.get("signal_name")
	]
	if not components:
		return []
	overlay = build_overlay(components, stale_minutes=WINDOW_HOURS * 60)
	return signal_findings(components, overlay, WINDOW_HOURS)
