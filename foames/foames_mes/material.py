# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Shop-floor material flow as pure arithmetic: lineside stock, kanban loops, material queues, the
line-dry forecast and Material Processing Complexity (MPC). No Frappe dependency.

The ERP stays the inventory system of record. FoaMES keeps a view of the stock at each point of use
(a Lineside Bin), estimates what the machines have consumed since the ERP was last read, and warns
before a line runs dry. It never posts stock movements itself; people do that in the ERP.

Running dry
    A line runs dry when a machine is starved of material: its lineside bin is empty or its input
    queue has nothing ready to start. The usual industry words are line starvation and material
    shortage. The forecast compares the hours of stock left at the current consumption rate with the
    time a replenishment takes to arrive and be made ready (the replenishment lead time plus the
    material's conditioning time, such as thawing, degassing, baking or acclimatising).

Material queues
    Material waits in front of a machine or work centre. A queue has a dispatch rule (FIFO, priority,
    earliest due date or first expired first out) and a buffer capacity; a full buffer blocks the
    machine upstream. Each entry can carry a minimum wait (cure, degas, cool, thaw) before it is ready
    and a maximum wait: a queue-time limit (Q-time), a hold time, a floor life or an out-time. An
    entry past its maximum wait or its expiry is never dispatched; a person decides what happens to it.

Material Processing Complexity (MPC)
    A 1 to 5 rating of how complex a material is to handle and process on the floor, built from
    attributes that existing standards already define (see FACTORS). The highest factor sets the
    level, and three or more elevated factors raise it one more. The top two levels follow the same
    oversight pattern as the Equipment Complexity Level: MPC 4 recommends a single human expert and
    MPC 5 needs a team of experts.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta

# --------------------------------------------------------------------------------------------------
# Material Processing Complexity
# --------------------------------------------------------------------------------------------------

# Each factor maps an option to a score from 0 to 4. The options use the wording of the standard the
# factor comes from, so a profile reads the same as the safety data sheet or the specification.
FACTORS: dict[str, dict] = {
	"hazard_rating": {
		"label": "Hazard (NFPA 704 highest rating, or GHS)",
		"source": "NFPA 704; GHS (UN Globally Harmonized System)",
		"options": {
			"0 - Minimal": 0,
			"1 - Slight / GHS Warning": 1,
			"2 - Moderate": 2,
			"3 - Serious / GHS Danger": 3,
			"4 - Severe": 4,
		},
	},
	"exposure_band": {
		"label": "Occupational exposure band",
		"source": "OEB 1-5 banding of occupational exposure limits",
		"options": {"None": 0, "OEB 1": 0, "OEB 2": 1, "OEB 3": 2, "OEB 4": 3, "OEB 5": 4},
	},
	"moisture_sensitivity": {
		"label": "Moisture sensitivity level",
		"source": "IPC/JEDEC J-STD-033 (floor life after the dry pack is opened)",
		"options": {
			"Not sensitive": 0,
			"MSL 1": 0,
			"MSL 2": 1,
			"MSL 2a": 1,
			"MSL 3": 2,
			"MSL 4": 3,
			"MSL 5": 3,
			"MSL 5a": 3,
			"MSL 6": 4,
		},
	},
	"storage_temperature": {
		"label": "Storage temperature",
		"source": "USP <659> packaging and storage requirements; cold chain practice",
		"options": {
			"Ambient": 0,
			"Controlled room temperature": 1,
			"Refrigerated (2-8 C)": 2,
			"Frozen": 3,
			"Cryogenic": 4,
		},
	},
	"atmosphere": {
		"label": "Atmosphere (dry process)",
		"source": "Dew point controlled dry rooms; inert gas handling; isolators",
		"options": {
			"Ambient": 0,
			"Low humidity": 1,
			"Dry room": 3,
			"Inert gas": 3,
			"Glovebox or isolator": 4,
		},
	},
	"cleanliness": {
		"label": "Cleanroom class at point of use",
		"source": "ISO 14644-1 cleanroom classes",
		"options": {
			"Not controlled": 0,
			"ISO 8": 1,
			"ISO 7": 2,
			"ISO 6": 2,
			"ISO 5": 3,
			"ISO 4 or cleaner": 4,
		},
	},
	"esd_sensitivity": {
		"label": "Electrostatic discharge sensitivity",
		"source": "ANSI/ESD S20.20; ANSI/ESDA/JEDEC JS-001 HBM classes",
		"options": {"Not sensitive": 0, "ESD sensitive": 2, "HBM Class 0 (under 250 V)": 3},
	},
	"physical_form": {
		"label": "Physical form",
		"source": "Bulk solids flowability (Carr index, Hausner ratio, USP <1174>)",
		"options": {
			"Discrete rigid": 0,
			"Discrete fragile": 1,
			"Free-flowing bulk or liquid": 1,
			"Cohesive powder, paste or viscous liquid": 2,
			"Compressed gas or cryogenic liquid": 3,
		},
	},
}

# Numeric factors, scored by thresholds: (upper bound exclusive, score) in ascending order.
NUMERIC_FACTORS: dict[str, dict] = {
	"shortest_time_limit_hours": {
		"label": "Shortest time limit (shelf life, hold time, Q-time, floor life, out-time or pot life)",
		"source": "ICH Q1A shelf life; hold-time studies; SEMI fab queue-time limits; J-STD-033 floor life",
		# 0 or empty means no limit. Under 1 hour scores 4; under a day 3; under 30 days 2; else 1.
		"bands": ((1, 4), (24, 3), (720, 2)),
		"above": 1,
	},
	"conditioning_steps": {
		"label": "Conditioning steps before use (thaw, degas, bake, acclimatise, premix)",
		"source": "Material preparation steps in the specification or SOP",
		"bands": ((1, 0), (2, 1), (3, 2)),
		"above": 3,
	},
	"critical_attributes": {
		"label": "Critical material attributes checked at receipt or use",
		"source": "ICH Q8 critical material attributes",
		"bands": ((1, 0), (3, 1), (6, 2)),
		"above": 3,
	},
}

MPC_LABELS = {
	1: "Standard",
	2: "Basic controls",
	3: "Controlled",
	4: "Critical: Human Expert Recommended",
	5: "Extreme: Expert Team Required",
}
MPC_OVERSIGHT = {1: "none", 2: "none", 3: "none", 4: "single", 5: "team"}
# How much more buffer a line keeps for a material at each level before it warns of running dry.
MPC_SAFETY_MULTIPLIER = {1: 1.0, 2: 1.1, 3: 1.25, 4: 1.5, 5: 2.0}
COMPOUND_SCORE = 2
COMPOUND_COUNT = 3


def numeric_score(factor: str, value) -> int:
	spec = NUMERIC_FACTORS[factor]
	value = float(value or 0)
	if factor == "shortest_time_limit_hours" and value <= 0:
		return 0
	for bound, score in spec["bands"]:
		if value < bound:
			return score
	return spec["above"]


def factor_scores(profile: dict) -> dict[str, int]:
	"""Score of every factor a profile sets. Unknown options score 0, so a blank profile is MPC 1."""
	scores = {}
	for factor, spec in FACTORS.items():
		scores[factor] = spec["options"].get(profile.get(factor) or "", 0)
	for factor in NUMERIC_FACTORS:
		scores[factor] = numeric_score(factor, profile.get(factor))
	return scores


def mpc(profile: dict) -> dict:
	"""The MPC level of a material handling profile, what drove it and the controls it implies.

	The level is one more than the highest factor score, so a material with any severe factor is
	MPC 5. Three or more factors at score 2 or above compound: the level rises one, up to 5.
	"""
	scores = factor_scores(profile)
	highest = max(scores.values()) if scores else 0
	level = 1 + highest
	elevated = [f for f, s in scores.items() if s >= COMPOUND_SCORE]
	compounded = len(elevated) >= COMPOUND_COUNT and level < 5
	if compounded:
		level += 1
	level = max(1, min(5, level))
	drivers = sorted((f for f, s in scores.items() if s and s == highest), key=_factor_order)
	time_sensitive = scores["shortest_time_limit_hours"] > 0 or scores["moisture_sensitivity"] > 0
	return {
		"level": level,
		"label": MPC_LABELS[level],
		"expert_oversight": MPC_OVERSIGHT[level],
		"scores": scores,
		"drivers": drivers,
		"compounded": compounded,
		"safety_multiplier": MPC_SAFETY_MULTIPLIER[level],
		"default_dispatch": "Earliest Expiry" if time_sensitive else "FIFO",
		"conditioning_minutes": float(profile.get("conditioning_minutes") or 0),
	}


def _factor_order(factor: str) -> int:
	order = list(FACTORS) + list(NUMERIC_FACTORS)
	return order.index(factor)


def factor_label(factor: str) -> str:
	spec = FACTORS.get(factor) or NUMERIC_FACTORS.get(factor) or {}
	return spec.get("label", factor)


# --------------------------------------------------------------------------------------------------
# Lineside stock and kanban
# --------------------------------------------------------------------------------------------------

BIN_STATUSES = ("OK", "Reorder", "Running Dry", "Will Run Dry", "Dry")
BIN_SEVERITY = {"Reorder": "Info", "Running Dry": "Warning", "Will Run Dry": "Critical", "Dry": "Critical"}
DEFAULT_WARN_MARGIN = 0.5
REPLENISHMENT_METHODS = ("Kanban", "Reorder Point", "Min-Max", "Manual")


def estimated_on_hand(read_qty: float, consumed_since_read: float) -> float:
	"""Stock at the bin now: the last stock read less what the machines have used since, never below 0."""
	return max(float(read_qty or 0) - max(float(consumed_since_read or 0), 0.0), 0.0)


def consumption(units_produced: float, quantity_per_unit: float, scrap_allowance_percent: float = 0) -> float:
	"""Material used to produce some units, with a scrap or loss allowance (backflush arithmetic)."""
	units = max(float(units_produced or 0), 0.0)
	per_unit = max(float(quantity_per_unit or 0), 0.0)
	return units * per_unit * (1 + max(float(scrap_allowance_percent or 0), 0.0) / 100.0)


def rate_per_hour(quantity: float, hours: float) -> float:
	return float(quantity or 0) / hours if hours and hours > 0 else 0.0


def hours_to_dry(on_hand: float, per_hour: float) -> float | None:
	"""Hours until the bin is empty at the current rate, or None when nothing is being used."""
	if per_hour <= 0:
		return None
	return max(float(on_hand or 0), 0.0) / per_hour


def kanban_cards(
	demand_per_hour: float, lead_hours: float, container_quantity: float, safety_percent: float = 0
) -> int:
	"""Cards a kanban loop needs: demand over the replenishment lead time, plus safety, in containers
	(N = D x L x (1 + safety) / C, rounded up). At least one card."""
	if not container_quantity or container_quantity <= 0:
		raise ValueError("the container quantity must be positive")
	demand = max(float(demand_per_hour or 0), 0.0) * max(float(lead_hours or 0), 0.0)
	return max(
		1, math.ceil(demand * (1 + max(float(safety_percent or 0), 0.0) / 100.0) / container_quantity - 1e-9)
	)


def replenish_quantity(bin_: dict, on_hand: float) -> float:
	"""How much to call for now, by the bin's replenishment method; 0 when none is due."""
	method = bin_.get("replenishment_method") or "Reorder Point"
	in_transit = max(float(bin_.get("in_transit_qty") or 0), 0.0)
	position = on_hand + in_transit
	reorder = float(bin_.get("reorder_qty") or 0)
	maximum = float(bin_.get("max_qty") or 0)
	container = float(bin_.get("container_qty") or 0)
	if method == "Kanban" and container > 0:
		cards = int(bin_.get("kanban_cards") or 0)
		if not cards:
			return 0.0
		full = math.floor(position / container + 1e-9)
		empty = max(cards - full, 0)
		return empty * container
	if position > reorder:
		return 0.0
	if method == "Min-Max" and maximum > 0:
		return max(maximum - position, 0.0)
	if container > 0:
		return container
	return max(maximum - position, reorder - position, 0.0)


def assess_bin(
	bin_: dict, on_hand: float, per_hour: float, mpc_level: int = 1, conditioning_minutes: float = 0
) -> dict:
	"""Status of one lineside bin and the numbers behind it.

	Dry: nothing left. Will Run Dry: the stock runs out before a replenishment called now can arrive
	and be made ready. Running Dry: the stock runs out inside the warning horizon, which is that lead
	time times the MPC safety multiplier times one plus the warning margin. Reorder: at or below the
	reorder quantity (or kanban cards are waiting) but not yet at risk.
	"""
	lead_minutes = max(float(bin_.get("replenishment_lead_minutes") or 0), 0.0) + max(
		float(conditioning_minutes or 0), 0.0
	)
	lead_hours = lead_minutes / 60.0
	multiplier = MPC_SAFETY_MULTIPLIER.get(int(mpc_level or 1), 1.0)
	margin = bin_.get("warn_margin_percent")
	margin = DEFAULT_WARN_MARGIN if margin in (None, "") else max(float(margin), 0.0) / 100.0
	horizon_hours = lead_hours * multiplier * (1 + margin)
	left = hours_to_dry(on_hand, per_hour)
	in_transit = max(float(bin_.get("in_transit_qty") or 0), 0.0)
	call = replenish_quantity(bin_, on_hand)
	if on_hand <= 0:
		status = "Dry"
	elif left is not None and lead_hours > 0 and left < lead_hours and in_transit <= 0:
		status = "Will Run Dry"
	elif left is not None and horizon_hours > 0 and left < horizon_hours and in_transit <= 0:
		status = "Running Dry"
	elif call > 0:
		status = "Reorder"
	else:
		status = "OK"
	return {
		"status": status,
		"on_hand": on_hand,
		"per_hour": per_hour,
		"hours_to_dry": left,
		"lead_hours": lead_hours,
		"horizon_hours": horizon_hours,
		"replenish_qty": call,
	}


def dry_at(now: datetime, hours_left: float | None) -> datetime | None:
	return now + timedelta(hours=hours_left) if hours_left is not None else None


def bin_findings(bins: list[dict]) -> list[dict]:
	"""Agent Suggestion dicts for bins that need replenishing or are running dry.

	Each dict carries name, title, machine, item, uom, mpc_level and the assess_bin result under
	"assessment", plus dry_at when known.
	"""
	out = []
	for b in bins:
		a = b["assessment"]
		status = a["status"]
		if status not in BIN_SEVERITY:
			continue
		title = b.get("title") or b["name"]
		where = f" at {b['machine']}" if b.get("machine") else ""
		uom = f" {b['uom']}" if b.get("uom") else ""
		left = a["hours_to_dry"]
		when = (
			f" At {a['per_hour']:,.2f}{uom} an hour it runs out around {b['dry_at']}."
			if b.get("dry_at")
			else ""
		)
		call = f" Call for {a['replenish_qty']:,.2f}{uom}." if a["replenish_qty"] > 0 else ""
		if status == "Dry":
			text = f"{title}{where} is empty. The machine is starved of {b.get('item') or 'material'}; record the stop as No Material and replenish.{call}"
		elif status == "Will Run Dry":
			text = (
				f"{title}{where} has {a['on_hand']:,.2f}{uom}, about {left:,.1f} hours, but a replenishment takes "
				f"{a['lead_hours']:,.1f} hours to arrive and be ready.{when} Expedite it now or plan the line to stop.{call}"
			)
		elif status == "Running Dry":
			text = (
				f"{title}{where} has about {left:,.1f} hours of stock left, inside its {a['horizon_hours']:,.1f} hour "
				f"warning horizon.{when} Replenish before the line runs dry.{call}"
			)
		else:
			text = f"{title}{where} is at its reorder point with {a['on_hand']:,.2f}{uom} on hand.{call}"
		level = int(b.get("mpc_level") or 1)
		if level >= 4:
			text += (
				f" The material is MPC {level} ({MPC_LABELS[level]}); its handling needs expert oversight."
			)
		out.append(
			{
				"rule_key": f"material-bin:{b['name']}:{status}:{b.get('cycle') or ''}",
				"category": "Material",
				"severity": BIN_SEVERITY[status],
				"title": f"{title}{where}: {status.lower()}",
				"suggestion": text,
				"reference_doctype": "Lineside Bin",
				"reference_name": b["name"],
				"evidence": {
					"machine": b.get("machine"),
					"item": b.get("item"),
					"mpc_level": level,
					**{k: (round(v, 4) if isinstance(v, float) else v) for k, v in a.items()},
				},
			}
		)
	return out


# --------------------------------------------------------------------------------------------------
# Material queues
# --------------------------------------------------------------------------------------------------

DISPATCH_RULES = ("FIFO", "Priority", "Earliest Due", "Earliest Expiry")
OPEN_ENTRY_STATUSES = ("Waiting", "In Process", "On Hold")
READINESS = ("Conditioning", "Ready", "Q-time Warning", "Q-time Exceeded", "Expired", "On Hold", "In Process")
DEFAULT_QTIME_WARN_PERCENT = 80.0
_FAR = datetime.max


def _dt(value) -> datetime | None:
	if value in (None, ""):
		return None
	if isinstance(value, datetime):
		return value
	return datetime.fromisoformat(str(value))


def readiness(entry: dict, now: datetime, warn_percent: float | None = None) -> dict:
	"""Where one queue entry stands now.

	Conditioning: still inside its minimum wait. Ready: may start. Q-time Warning: past the warning
	share of its maximum wait. Q-time Exceeded: past its maximum wait. Expired: past its expiry. On
	Hold and In Process pass through from the entry's status.
	"""
	status = entry.get("status") or "Waiting"
	arrived = _dt(entry.get("arrived_at")) or now
	waited = max((now - arrived).total_seconds() / 60.0, 0.0)
	min_wait = max(float(entry.get("min_wait_minutes") or 0), 0.0)
	max_wait = max(float(entry.get("max_wait_minutes") or 0), 0.0)
	expires = _dt(entry.get("expires_at"))
	warn = DEFAULT_QTIME_WARN_PERCENT if warn_percent in (None, "") else float(warn_percent)
	ready_at = arrived + timedelta(minutes=min_wait)
	limit_at = arrived + timedelta(minutes=max_wait) if max_wait else None
	if status in ("On Hold", "In Process"):
		state = status
	elif expires and now >= expires:
		state = "Expired"
	elif max_wait and waited >= max_wait:
		state = "Q-time Exceeded"
	elif waited < min_wait:
		state = "Conditioning"
	elif max_wait and waited >= max_wait * warn / 100.0:
		state = "Q-time Warning"
	else:
		state = "Ready"
	return {
		"state": state,
		"waited_minutes": waited,
		"ready_at": ready_at,
		"limit_at": limit_at,
		"expires_at": expires,
		"minutes_to_limit": (limit_at - now).total_seconds() / 60.0 if limit_at else None,
	}


def dispatchable(state: str) -> bool:
	return state in ("Ready", "Q-time Warning")


def dispatch_order(
	entries: list[dict], rule: str, now: datetime, warn_percent: float | None = None
) -> list[dict]:
	"""Entries that may start, in the order the queue's dispatch rule picks them.

	Entries close to their queue-time limit are not jumped ahead by FIFO alone; the rule decides, and
	the suggestions warn about them. Ties always fall back to arrival order, then name.
	"""
	ready = []
	for e in entries:
		r = readiness(e, now, warn_percent)
		if dispatchable(r["state"]):
			ready.append({**e, "readiness": r})

	def arrival(e):
		return (_dt(e.get("arrived_at")) or now, e.get("name") or "")

	if rule == "Priority":
		key = lambda e: (int(e.get("priority") or 0) * -1, *arrival(e))  # noqa: E731
	elif rule == "Earliest Due":
		key = lambda e: (_dt(e.get("due_at")) or _FAR, *arrival(e))  # noqa: E731
	elif rule == "Earliest Expiry":
		key = lambda e: (_earliest_limit(e) or _FAR, *arrival(e))  # noqa: E731
	else:
		key = arrival
	return sorted(ready, key=key)


def _earliest_limit(e: dict) -> datetime | None:
	r = e["readiness"]
	limits = [d for d in (r["limit_at"], r["expires_at"]) if d]
	return min(limits) if limits else None


def queue_summary(queue: dict, entries: list[dict], now: datetime) -> dict:
	"""Counts and quantities for one queue: what is waiting, ready, conditioning, out of time or on hold,
	the oldest wait and whether the buffer is full."""
	states: dict[str, int] = {}
	quantity = 0.0
	oldest = 0.0
	waiting = 0
	for e in entries:
		if (e.get("status") or "Waiting") not in OPEN_ENTRY_STATUSES:
			continue
		r = readiness(e, now, queue.get("qtime_warn_percent"))
		states[r["state"]] = states.get(r["state"], 0) + 1
		if r["state"] != "In Process":
			waiting += 1
			quantity += float(e.get("quantity") or 0)
			oldest = max(oldest, r["waited_minutes"])
	capacity = int(queue.get("capacity") or 0)
	ready = states.get("Ready", 0) + states.get("Q-time Warning", 0)
	return {
		"waiting": waiting,
		"ready": ready,
		"states": states,
		"quantity": quantity,
		"oldest_wait_minutes": oldest,
		"capacity": capacity,
		"full": bool(capacity and waiting >= capacity),
		"starved": ready == 0 and not states.get("In Process"),
	}


QUEUE_SEVERITY = {
	"Q-time Warning": "Warning",
	"Q-time Exceeded": "Critical",
	"Expired": "Critical",
	"Starved": "Warning",
	"Blocked": "Warning",
}


def queue_findings(queues: list[dict], now: datetime) -> list[dict]:
	"""Agent Suggestion dicts for material queues: entries near or past their queue-time limit or
	expiry, a machine starved with nothing ready to start, and a full buffer blocking upstream.

	Each queue dict carries name, title, machine, machine_status, capacity, qtime_warn_percent and its
	open entries (name, item, batch, quantity, uom, arrived_at, status, min_wait_minutes,
	max_wait_minutes, expires_at, mpc_level).
	"""
	out = []
	for q in queues:
		title = q.get("title") or q["name"]
		entries = q.get("entries") or []
		for e in entries:
			if (e.get("status") or "Waiting") != "Waiting":
				continue
			r = readiness(e, now, q.get("qtime_warn_percent"))
			state = r["state"]
			if state not in ("Q-time Warning", "Q-time Exceeded", "Expired"):
				continue
			what = (
				" ".join(str(x) for x in (e.get("quantity"), e.get("uom"), e.get("item")) if x) or e["name"]
			)
			lot = f" (lot {e['batch']})" if e.get("batch") else ""
			if state == "Q-time Warning":
				text = (
					f"{what}{lot} has waited {r['waited_minutes']:,.0f} minutes in {title}; its queue-time limit "
					f"is reached at {r['limit_at']}. Start it next or move it to a free machine."
				)
			elif state == "Q-time Exceeded":
				text = (
					f"{what}{lot} has waited {r['waited_minutes']:,.0f} minutes in {title}, past its queue-time "
					f"limit at {r['limit_at']}. It will not be dispatched; hold it and decide its disposition "
					"(rework, re-condition, requalify or scrap) under your procedure."
				)
			else:
				text = (
					f"{what}{lot} in {title} expired at {r['expires_at']}. It will not be dispatched; hold it and "
					"decide its disposition under your procedure."
				)
			level = int(e.get("mpc_level") or 1)
			if level >= 4:
				text += f" The material is MPC {level} ({MPC_LABELS[level]})."
			out.append(
				{
					"rule_key": f"material-queue:{e['name']}:{state}",
					"category": "Material",
					"severity": QUEUE_SEVERITY[state],
					"title": f"{e.get('item') or e['name']} in {title}: {state.lower()}",
					"suggestion": text,
					"reference_doctype": "Material Queue Entry",
					"reference_name": e["name"],
					"evidence": {
						"queue": q["name"],
						"machine": q.get("machine"),
						"waited_minutes": round(r["waited_minutes"], 1),
						"max_wait_minutes": e.get("max_wait_minutes"),
						"limit_at": str(r["limit_at"]) if r["limit_at"] else None,
						"expires_at": str(r["expires_at"]) if r["expires_at"] else None,
						"mpc_level": level,
					},
				}
			)
		summary = queue_summary(q, entries, now)
		machine = q.get("machine")
		# One suggestion per episode: a starved queue is keyed on its last activity (the latest start or
		# finish), a full one on its oldest waiting entry, so a dismissed finding stays dismissed until
		# the queue moves again.
		oldest = _oldest_waiting(entries)
		if machine and summary["starved"] and q.get("machine_status") in ("Running", "Idle"):
			conditioning = summary["states"].get("Conditioning", 0)
			why = (
				f" {conditioning} entr{'y is' if conditioning == 1 else 'ies are'} still conditioning."
				if conditioning
				else " Nothing is waiting."
			)
			out.append(
				{
					"rule_key": f"material-starved:{q['name']}:{q.get('last_activity') or ''}",
					"category": "Material",
					"severity": QUEUE_SEVERITY["Starved"],
					"title": f"{machine} is starved: nothing ready in {title}",
					"suggestion": (
						f"{machine} is {q.get('machine_status')} and {title} has no material ready to start.{why} "
						"Bring the next job's material forward, or record the idle time as No Material."
					),
					"reference_doctype": "Material Queue",
					"reference_name": q["name"],
					"evidence": {"machine": machine, **summary},
				}
			)
		if summary["full"]:
			out.append(
				{
					"rule_key": f"material-blocked:{q['name']}:{oldest}",
					"category": "Material",
					"severity": QUEUE_SEVERITY["Blocked"],
					"title": f"{title} is full: upstream is blocked",
					"suggestion": (
						f"{title} holds {summary['waiting']} waiting entries against a capacity of {summary['capacity']}. "
						f"The oldest has waited {summary['oldest_wait_minutes']:,.0f} minutes. Upstream machines feeding "
						"it will be blocked; slow the release of work to them or add capacity here."
					),
					"reference_doctype": "Material Queue",
					"reference_name": q["name"],
					"evidence": {"machine": machine, **summary},
				}
			)
	return out


def _oldest_waiting(entries: list[dict]) -> str:
	waiting = [e for e in entries if (e.get("status") or "Waiting") == "Waiting"]
	if not waiting:
		return ""
	return min(waiting, key=lambda e: (_dt(e.get("arrived_at")) or _FAR, e.get("name") or ""))["name"]
