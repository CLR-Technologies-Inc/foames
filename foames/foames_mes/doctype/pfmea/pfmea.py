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

"""A process FMEA, kept next to the floor data it is about.

Each PFMEA Item row is one failure chain (effect, mode, cause) at a process step, rated for severity,
occurrence and detection and ranked by the AIAG-VDA action priority, with its optimization action
and re-rating, and the control plan columns. The arithmetic lives in `foames.foames_mes.pfmea`.

Released PFMEAs are observed once a day. For each row tied to a machine, FoaMES counts the incidents
the floor recorded over the observation window (counts on the row's own scrap counter, and Downtime
Records with the row's reason) against the units the machine produced, and the SPC signals raised on
the row's measurement. Where the floor disagrees with the rating, or an action is missing or late,
an Agent Suggestion asks the FMEA team to review. Ratings are never changed automatically.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cint, get_datetime, getdate, now_datetime, nowdate

from foames.foames_mes import pfmea as logic

DEFAULT_OBSERVATION_DAYS = 90
ITEM_FIELDS = (
	"name",
	"idx",
	"op_no",
	"process_step",
	"machine",
	"failure_mode",
	"severity",
	"occurrence",
	"detection",
	"action_priority",
	"measurement_name",
	"scrap_counter",
	"downtime_reason",
	"prevention_action",
	"detection_action",
	"responsible",
	"target_date",
	"action_status",
	"action_taken",
)


class PFMEA(Document):
	def validate(self):
		self.observation_days = max(cint(self.observation_days) or DEFAULT_OBSERVATION_DAYS, 1)
		rows = []
		for row in self.items:
			for field in ("measurement_name", "scrap_counter"):
				if row.get(field):
					# Machine Events store counter and measurement names as reported; counters in lower case.
					row.set(field, row.get(field).strip())
			if row.scrap_counter:
				row.scrap_counter = row.scrap_counter.lower()
			values = row.as_dict()
			problems = logic.check_item(values)
			if problems:
				frappe.throw(_("Row {0}: {1}").format(row.idx, "; ".join(problems)))
			if (row.scrap_counter or row.downtime_reason) and not row.machine:
				frappe.throw(
					_(
						"Row {0}: a scrap counter or downtime reason is observed on a machine; set the machine"
					).format(row.idx)
				)
			row.action_priority = logic.action_priority(row.severity, row.occurrence, row.detection)
			row.rpn = logic.rpn(row.severity, row.occurrence, row.detection)
			row.new_action_priority = logic.action_priority(
				row.new_severity, row.new_occurrence, row.new_detection
			)
			row.new_rpn = logic.rpn(row.new_severity, row.new_occurrence, row.new_detection)
			rows.append(row.as_dict())
		if self.status == "Released":
			problems = logic.check_release(rows)
			if problems:
				frappe.throw(_("Cannot release: {0}").format("; ".join(problems)))
			if not self.revision_date:
				self.revision_date = nowdate()
		summary = logic.summarize(rows)
		self.high_count = summary["high"]
		self.medium_count = summary["medium"]
		self.low_count = summary["low"]
		self.open_actions = summary["open_actions"]


# Observation


def observe_item(item, since, until) -> dict:
	"""What the floor recorded for one row between since and until."""
	from foames.foames_mes.doctype.maintenance_plan.maintenance_plan import production

	out = {
		"observed_units": None,
		"observed_incidents": None,
		"observed_per_thousand": None,
		"observed_occurrence": None,
		"spc_signals": 0,
		"latest_signal_at": None,
	}
	if item.get("machine") and (item.get("scrap_counter") or item.get("downtime_reason")):
		units = production(item["machine"], since, until)
		incidents = 0.0
		if item.get("scrap_counter"):
			incidents += production(item["machine"], since, until, item["scrap_counter"])
		if item.get("downtime_reason"):
			incidents += downtime_incidents(item["machine"], item["downtime_reason"], since, until)
		rate = logic.per_thousand(incidents, units)
		out.update(
			{
				"observed_units": units,
				"observed_incidents": incidents,
				"observed_per_thousand": rate,
				"observed_occurrence": logic.occurrence_from_rate(rate),
			}
		)
	if item.get("measurement_name"):
		out["spc_signals"], out["latest_signal_at"] = spc_signals(
			item.get("machine"), item["measurement_name"], since, until
		)
	return out


def downtime_incidents(machine: str, reason: str, since, until) -> int:
	record = frappe.qb.DocType("Downtime Record")
	rows = (
		frappe.qb.from_(record)
		.select(record.name)
		.where(
			(record.machine == machine)
			& (record.reason == reason)
			& (record.start_time >= since)
			& (record.start_time < until)
		)
		.run()
	)
	return len(rows)


def spc_signals(machine: str | None, measurement: str, since, until) -> tuple[int, str | None]:
	"""SPC suggestions on a measurement (on one machine, or on any) raised or re-raised in the window,
	and when the latest of them signalled. SPC rule keys read spc:<machine>:<measurement>:<chart>:<rule>."""
	suggestion = frappe.qb.DocType("Agent Suggestion")
	prefix = f"spc:{machine}:{measurement}:" if machine else "spc:"
	rows = (
		frappe.qb.from_(suggestion)
		.select(suggestion.rule_key, suggestion.evidence, suggestion.modified)
		.where(
			suggestion.rule_key.like(f"{prefix}%")
			& (suggestion.modified >= since)
			& (suggestion.modified < until)
		)
		.run(as_dict=True)
	)
	count, latest = 0, None
	for row in rows:
		parts = (row.rule_key or "").split(":")
		if len(parts) < 5 or parts[2] != measurement or (machine and parts[1] != machine):
			continue
		count += 1
		at = row.modified
		try:
			evidence = json.loads(row.evidence) if isinstance(row.evidence, str) else (row.evidence or {})
			at = evidence.get("latest_signal_at") or at
		except (ValueError, AttributeError):
			pass
		at = get_datetime(at)
		latest = at if latest is None or at > latest else latest
	return count, (str(latest) if latest else None)


def observe(name: str, now=None) -> list[dict]:
	"""Read the floor for every row of one PFMEA and store it on the rows without touching the
	PFMEA's Modified. Returns the rows with their observations, for the suggestion rules."""
	now = get_datetime(now) if now else now_datetime()
	days = cint(frappe.db.get_value("PFMEA", name, "observation_days")) or DEFAULT_OBSERVATION_DAYS
	since = add_days(now, -max(days, 1))
	items = frappe.get_all(
		"PFMEA Item",
		filters={"parent": name, "parenttype": "PFMEA", "parentfield": "items"},
		fields=list(ITEM_FIELDS),
		order_by="idx asc",
	)
	out = []
	for item in items:
		observed = observe_item(item, since, now)
		# Numeric columns are NOT NULL; a row with nothing to observe stores zeros (no observed occurrence).
		stored = {k: v or 0 for k, v in observed.items() if k != "latest_signal_at"}
		stored["observed_on"] = now
		frappe.db.set_value("PFMEA Item", item.name, stored, update_modified=False)
		out.append({**item, **observed, "row": item.name, "observed_since": since})
	frappe.db.set_value("PFMEA", name, "last_observed", now, update_modified=False)
	return out


@frappe.whitelist()
def observe_now(name: str) -> dict:
	"""The form button: read the floor for this PFMEA now. Returns the header summary."""
	frappe.has_permission("PFMEA", "write", doc=name, throw=True)
	rows = observe(name)
	return {
		"rows": len(rows),
		"above_rating": sum(
			1
			for r in rows
			if r.get("observed_occurrence")
			and logic.valid_rating(r.get("occurrence"))
			and r["observed_occurrence"] > int(r["occurrence"])
		),
		"spc_signals": sum(r.get("spc_signals") or 0 for r in rows),
	}


def _resolved_since_signal(finding: dict) -> bool:
	"""A dismissed SPC finding stays dismissed until the measurement signals again."""
	latest = (finding.get("evidence") or {}).get("latest_signal_at")
	if not finding["rule_key"].endswith(":spc") or not latest:
		return False
	resolved_on = frappe.db.get_value(
		"Agent Suggestion", {"rule_key": finding["rule_key"], "status": ("!=", "Open")}, "resolved_on"
	)
	return bool(resolved_on) and get_datetime(resolved_on) >= get_datetime(latest)


def check_pfmeas(now=None) -> list[str]:
	"""Scheduled daily: observe every Released PFMEA and raise the review suggestions. Returns the
	suggestions created or reopened."""
	from foames.foames_mes.doctype.agent_suggestion.agent_suggestion import raise_suggestions

	now = get_datetime(now) if now else now_datetime()
	out = []
	for doc in frappe.get_all(
		"PFMEA", filters={"status": "Released"}, fields=["name", "title"], order_by="name"
	):
		rows = observe(doc.name, now)
		found = [f for f in logic.findings(doc, rows, getdate(now)) if not _resolved_since_signal(f)]
		out.extend(raise_suggestions(found, agent="foames-pfmea"))
	return out
