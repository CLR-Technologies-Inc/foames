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

"""What the P&ID viewer and the rules say about a tag's live signal. Pure: no Frappe."""

from __future__ import annotations

from datetime import datetime, timedelta

STALE_MINUTES = 60


def overlay_entry(
	component: dict,
	machine_status: str | None,
	last: dict | None,
	now: datetime,
	stale_minutes: int = STALE_MINUTES,
) -> dict:
	"""{state, value, unit, at, flag} for one tag.

	`last` is the latest Machine Event for the tag's signal ({value, timestamp}) or None. The flag
	is "high" or "low" when the value is at or beyond the instrument's range (a reading pinned at a
	range limit is not a measurement), "stale" when the last value is older than `stale_minutes`,
	"none" when a linked signal has never reported, else None.
	"""
	entry: dict = {
		"state": None,
		"value": None,
		"unit": component.get("engineering_unit") or "",
		"at": None,
		"flag": None,
	}
	if component.get("machine") and (
		component.get("component_type") == "Equipment" or component.get("event_type") == "State"
	):
		entry["state"] = machine_status or "Unknown"
	if component.get("event_type") not in ("Measurement", "Count") or not component.get("signal_name"):
		return entry
	if not last:
		entry["flag"] = "none"
		return entry
	value = last.get("value")
	entry["value"] = value
	entry["at"] = last.get("timestamp")
	low, high = component.get("range_low"), component.get("range_high")
	has_range = low is not None and high is not None and high > low
	if isinstance(value, int | float) and has_range and value >= high:
		entry["flag"] = "high"
	elif isinstance(value, int | float) and has_range and value <= low:
		entry["flag"] = "low"
	elif isinstance(last.get("timestamp"), datetime) and now - last["timestamp"] > timedelta(
		minutes=stale_minutes
	):
		entry["flag"] = "stale"
	return entry


def signal_findings(components: list[dict], overlay: dict[str, dict], window_hours: int = 24) -> list[dict]:
	"""Agent Suggestion findings for linked instruments: silent signals and readings at a range limit.

	`overlay` is {tag: overlay_entry} computed with `stale_minutes = window_hours * 60`.
	"""
	findings = []
	for component in components:
		tag = component["tag"]
		entry = overlay.get(tag) or {}
		flag = entry.get("flag")
		if flag in ("none", "stale"):
			findings.append(
				{
					"rule_key": f"pid-signal-silent:{tag}",
					"category": "Machine Data",
					"severity": "Warning",
					"title": f"{tag} has not reported for {window_hours} hours",
					"suggestion": (
						f"{tag} ({component.get('description') or component.get('component_type')}) is linked to "
						f"{component.get('signal_name')!r} on machine {component.get('machine')}, but no value has "
						f"arrived in the last {window_hours} hours. Check the gateway mapping and the instrument, or "
						"clear the link on the P&ID component if the tag is out of service."
					),
					"reference_doctype": "PID Component",
					"reference_name": tag,
					"evidence": {
						"machine": component.get("machine"),
						"signal_name": component.get("signal_name"),
						"signal_address": component.get("signal_address"),
						"last_value_at": str(entry.get("at")) if entry.get("at") else None,
					},
				}
			)
		elif flag in ("high", "low"):
			limit = component.get("range_high") if flag == "high" else component.get("range_low")
			findings.append(
				{
					"rule_key": f"pid-range-{flag}:{tag}",
					"category": "Machine Data",
					"severity": "Warning",
					"title": f"{tag} reads at its {flag} range limit",
					"suggestion": (
						f"{tag} last read {entry.get('value')} {entry.get('unit') or ''}, at or beyond its calibrated "
						f"range limit of {limit}. A transmitter pinned at a range limit is no longer measuring: the "
						"process may be outside the range, or the instrument may have failed. Check it before "
						"relying on the value."
					),
					"reference_doctype": "PID Component",
					"reference_name": tag,
					"evidence": {
						"value": entry.get("value"),
						"at": str(entry.get("at")),
						"range_low": component.get("range_low"),
						"range_high": component.get("range_high"),
					},
				}
			)
	return findings
