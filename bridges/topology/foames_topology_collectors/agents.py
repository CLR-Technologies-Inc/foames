# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""AI agent activity from a JSON Lines event log.

Each line is one event:

	{"time": "2026-11-15T10:00:00Z", "agent": "planner", "task": "T-17", "status": "running",
	 "title": "Re-plan line 2", "host": "gw1", "delegated_by": "orchestrator", "parent_task": "T-10",
	 "target": "machine:CNC-01"}

Only agent and task are required. The latest event per task wins, keeping fields only earlier ones carried. The report holds:

* an Agent asset per agent (data layer), Runs On its host when one is given (host:<name>, the
  same id the network collector uses, so the two graphs join);
* an Agent Task asset per task in the window, with the agent's status mapped to the topology
  statuses (running → Running, done → OK, failed → Down, waiting → Idle);
* Delegates links from the agent that runs a task to the task, from the agent that handed it over
  to that agent, and from a parent task to its sub-task;
* a Write binding from a task to the physical asset it acts on (target), so the view shows which
  equipment an agent's task touches. FoaMES records this; it never acts on it.

This treats an agent's delegated task like a job on a machine, so the same views, findings and
lineage cover agents and equipment alike.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone

from foames_topology_collectors.network import host_id

STATUS = {
	"running": "Running",
	"started": "Running",
	"in_progress": "Running",
	"done": "OK",
	"completed": "OK",
	"succeeded": "OK",
	"ok": "OK",
	"failed": "Down",
	"error": "Down",
	"cancelled": "Idle",
	"waiting": "Idle",
	"queued": "Idle",
	"blocked": "Idle",
}


def _id(prefix, value):
	return f"{prefix}:{re.sub(r'[^A-Za-z0-9._:-]+', '-', str(value)).strip('-')}"


def _parse(value):
	if not value:
		return None
	text = str(value).replace("T", " ").rstrip("Z").split("+")[0]
	for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
		try:
			return datetime.strptime(text, fmt)
		except ValueError:
			continue
	return None


def read_events(lines):
	"""Events from an iterable of JSON lines. Lines that are not objects with agent and task are
	skipped and counted."""
	events, skipped = [], 0
	for line in lines:
		line = line.strip()
		if not line:
			continue
		try:
			event = json.loads(line)
		except ValueError:
			skipped += 1
			continue
		if not isinstance(event, dict) or not event.get("agent") or not event.get("task"):
			skipped += 1
			continue
		events.append(event)
	return events, skipped


def report_from_events(
	events, *, provider: str, tenant: str | None = None, window_hours: float = 24, now: datetime | None = None
) -> dict:
	now = now or datetime.now(timezone.utc).replace(tzinfo=None)
	since = now - timedelta(hours=window_hours) if window_hours else None
	latest = {}
	for event in events:
		at = _parse(event.get("time")) or now
		if since and at < since:
			continue
		key = str(event["task"])
		# The latest event's fields win; fields only an earlier event carried (who delegated the
		# task, its parent) are kept.
		if key not in latest:
			latest[key] = (at, event)
		elif at >= latest[key][0]:
			latest[key] = (at, {**latest[key][1], **event})
		else:
			latest[key] = (latest[key][0], {**event, **latest[key][1]})

	assets, links, bindings = {}, {}, []
	agents_seen = {}

	def agent(name, at, status=None, host=None):
		asset_id = _id("agent", name)
		current = agents_seen.get(asset_id)
		if current is None or at >= current["_at"]:
			agents_seen[asset_id] = {
				"_at": at,
				"status": status or (current or {}).get("status") or "Idle",
				"host": host or (current or {}).get("host"),
			}
		elif host and not current.get("host"):
			current["host"] = host
		return asset_id

	def link(a, link_type, b):
		links[(a, link_type, b)] = {"from_asset": a, "to_asset": b, "link_type": link_type}

	for key, (at, event) in sorted(latest.items()):
		status = STATUS.get(str(event.get("status") or "").lower(), "Unknown")
		task_id = _id("task", key)
		runner = agent(event["agent"], at, "Running" if status == "Running" else None, event.get("host"))
		assets[task_id] = {
			"asset_id": task_id,
			"title": event.get("title") or key,
			"kind": "Agent Task",
			"status": status,
			"last_seen": at.strftime("%Y-%m-%d %H:%M:%S"),
			"attributes": {k: event[k] for k in ("summary", "model", "cost", "tokens") if k in event},
		}
		link(runner, "Delegates", task_id)
		if event.get("delegated_by"):
			link(agent(event["delegated_by"], at), "Delegates", runner)
		if event.get("parent_task"):
			parent = _id("task", event["parent_task"])
			if str(event["parent_task"]) in latest:
				link(parent, "Delegates", task_id)
		if event.get("target"):
			bindings.append({"signal": task_id, "physical_asset": str(event["target"]), "direction": "Write"})

	hosts = {}
	for asset_id, info in agents_seen.items():
		assets[asset_id] = {
			"asset_id": asset_id,
			"title": asset_id.split(":", 1)[1],
			"kind": "Agent",
			"status": info["status"],
			"last_seen": info["_at"].strftime("%Y-%m-%d %H:%M:%S"),
		}
		if info.get("host"):
			host = host_id(info["host"])
			hosts[host] = info["host"]
			link(asset_id, "Runs On", host)

	return {
		"provider": provider,
		"tenant": tenant,
		"assets": [assets[k] for k in sorted(assets)],
		"links": [links[k] for k in sorted(links)],
		"bindings": bindings,
		# Tasks age out of the window, so the provider's assets not reported now are retired.
		"retire_missing": True,
		"hosts_referenced": sorted(hosts),
	}
