# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Operator recognition as pure logic: the checks on a recognition, milestones, team highlights
and what the floor may show. No Frappe dependency.

Recognition is positive by design. People give each other kudos; FoaMES adds milestones for a
person's own contributions (andon calls answered, suggestions carried out, ideas credited to them)
and highlights for a team (a line) when its week went well. Nothing here ranks people against each
other, compares one person with another, or produces anything from a bad result: a week that went
badly simply produces no highlight. Team highlights are computed per line, never per person.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

KINDS = ("Kudos", "Helping Hand", "Improvement", "Safety", "Quality", "Milestone", "Team Highlight")
PEOPLE_KINDS = ("Kudos", "Helping Hand", "Improvement", "Safety", "Quality")
SYSTEM_KINDS = ("Milestone", "Team Highlight")

DEFAULT_THRESHOLDS = (1, 10, 25, 50, 100, 250, 500, 1000)

# What a person's milestones count, and how the message reads.
MILESTONE_METRICS = {
	"andon_answered": ("andon call answered", "andon calls answered"),
	"suggestions_done": ("suggestion carried out", "suggestions carried out"),
	"ideas_credited": ("idea put into practice", "ideas put into practice"),
}

MIN_MESSAGE_LENGTH = 3


def check_recognition(
	kind: str,
	recipient_type: str,
	recipient: str | None,
	team: str | None,
	message: str | None,
	given_by: str | None,
	system: bool = False,
) -> list[str]:
	"""The problems with a recognition, as plain sentences; an empty list means it can be saved.

	People give the people kinds only; Milestone and Team Highlight come from FoaMES itself. Nobody
	recognizes themselves."""
	problems = []
	if kind not in KINDS:
		problems.append(f"Unknown kind {kind!r}")
	elif not system and kind in SYSTEM_KINDS:
		problems.append(f"{kind} recognitions are given by FoaMES, not by people")
	if recipient_type == "Person":
		if not recipient:
			problems.append("Choose the person to recognize")
		elif not system and given_by and recipient == given_by:
			problems.append("You cannot recognize yourself; ask a teammate to")
	elif recipient_type == "Team":
		if not (team or "").strip():
			problems.append("Name the team, line or crew to recognize")
	else:
		problems.append(f"Unknown recipient type {recipient_type!r}")
	if len((message or "").strip()) < MIN_MESSAGE_LENGTH:
		problems.append("Say what you are recognizing")
	return problems


def parse_thresholds(text: str | None) -> tuple[int, ...]:
	"""Milestone thresholds from a comma-separated setting, ascending and positive; the default list
	when the setting is empty or holds no number."""
	values = set()
	for part in (text or "").replace(";", ",").split(","):
		part = part.strip()
		if part.isdigit() and int(part) > 0:
			values.add(int(part))
	return tuple(sorted(values)) or DEFAULT_THRESHOLDS


def milestone_key(user: str, metric: str, threshold: int) -> str:
	return f"milestone:{user}:{metric}:{threshold}"


def due_milestones(
	counts: dict[str, dict[str, int]],
	already: set[str],
	thresholds: tuple[int, ...] = DEFAULT_THRESHOLDS,
	skip_users: set[str] | frozenset = frozenset(),
) -> list[dict]:
	"""Milestones people have reached and not yet been recognized for.

	`counts` maps user -> metric -> running total; `already` holds the keys of milestones already
	given. Only the highest new threshold per person and metric is returned, so a site that turns
	milestones on after a year of use does not send a burst of ten at once, and a lower threshold
	is never given after a higher one. Users in `skip_users` (who opted
	out of automatic recognition) get none."""
	out = []
	for user in sorted(counts):
		if user in skip_users:
			continue
		for metric in sorted(counts[user]):
			if metric not in MILESTONE_METRICS:
				continue
			total = counts[user][metric] or 0
			reached = [t for t in thresholds if t <= total]
			new = [t for t in reached if milestone_key(user, metric, t) not in already]
			if not new:
				continue
			top = max(new)
			if any(t > top for t in reached):
				# A higher threshold was already given; a lower one turning up now (a threshold
				# added to the settings later) is not worth a message.
				continue
			singular, plural = MILESTONE_METRICS[metric]
			out.append(
				{
					"key": milestone_key(user, metric, top),
					"recipient": user,
					"metric": metric,
					"threshold": top,
					"total": total,
					"message": f"First {singular}" if top == 1 else f"{top} {plural}",
				}
			)
	return out


def week_start(day: date | datetime) -> date:
	"""The Monday of the week holding `day`."""
	if isinstance(day, datetime):
		day = day.date()
	return day - timedelta(days=day.weekday())


def last_complete_week(today: date | datetime) -> tuple[date, date]:
	"""(Monday, next Monday) of the last week that has fully ended before `today`."""
	start = week_start(today) - timedelta(days=7)
	return start, start + timedelta(days=7)


def summarize_periods(periods: list[dict]) -> dict:
	"""One team-week from OEE periods: planned minutes, OEE weighted by planned minutes, good and
	scrap counts and the quality rate. Periods with no planned time carry no weight."""
	planned = sum(p.get("planned_minutes") or 0 for p in periods)
	weighted = sum((p.get("oee") or 0) * (p.get("planned_minutes") or 0) for p in periods)
	good = sum(p.get("good_count") or 0 for p in periods)
	scrap = sum(p.get("scrap_count") or 0 for p in periods)
	return {
		"planned_minutes": planned,
		"oee": (weighted / planned) if planned else None,
		"good": good,
		"scrap": scrap,
		"quality": (100.0 * good / (good + scrap)) if (good + scrap) else None,
	}


def team_highlights(
	team: str,
	week: date,
	this_week: dict,
	history: list[dict],
	andon: dict | None = None,
	oee_gain_points: float = 5.0,
	min_planned_minutes: float = 480.0,
	min_history_weeks: int = 4,
	min_andon_calls: int = 3,
) -> list[dict]:
	"""Positive highlights for one team (a line) for one week. Never anything negative.

	`this_week` and each entry of `history` (the weeks before it, most recent first) are
	summarize_periods() results; `andon` is {"calls": n, "on_target": m} for calls raised on the
	team's machines that week. A week with less than `min_planned_minutes` of planned time is too
	thin to say anything about and gets no OEE or quality highlight.

	- OEE up: OEE at least `oee_gain_points` above the week before.
	- Best week: the highest OEE of the last `min_history_weeks` weeks or more.
	- Zero scrap: good output and no scrap all week.
	- Quality up: quality rate at least one point above the week before, when it was not already 100.
	- Andon on target: at least `min_andon_calls` calls, every one acknowledged within its target.
	"""
	out = []

	def add(code, title, message, evidence):
		out.append(
			{
				"key": f"team:{team}:{week.isoformat()}:{code}",
				"team": team,
				"week": week.isoformat(),
				"code": code,
				"title": title,
				"message": message,
				"evidence": evidence,
			}
		)

	enough = (this_week.get("planned_minutes") or 0) >= min_planned_minutes
	oee = this_week.get("oee")
	previous = next((h for h in history if (h.get("planned_minutes") or 0) >= min_planned_minutes), None)
	if enough and oee is not None:
		if previous and previous.get("oee") is not None and oee - previous["oee"] >= oee_gain_points:
			add(
				"oee-up",
				"OEE up",
				f"OEE up {oee - previous['oee']:.1f} points to {oee:.1f}%",
				{"oee": round(oee, 1), "previous_oee": round(previous["oee"], 1)},
			)
		comparable = [
			h["oee"]
			for h in history
			if h.get("oee") is not None and (h.get("planned_minutes") or 0) >= min_planned_minutes
		]
		if len(comparable) >= min_history_weeks and oee > max(comparable):
			add(
				"best-week",
				"Best week",
				f"Best OEE in {len(comparable) + 1} weeks: {oee:.1f}%",
				{"oee": round(oee, 1), "weeks_compared": len(comparable) + 1},
			)
	if enough and (this_week.get("good") or 0) > 0 and not this_week.get("scrap"):
		add(
			"zero-scrap",
			"Zero scrap",
			f"{this_week['good']} good and no scrap all week",
			{"good": this_week["good"], "scrap": 0},
		)
	quality = this_week.get("quality")
	if (
		enough
		and quality is not None
		and previous
		and previous.get("quality") is not None
		and previous["quality"] < 100
		and quality - previous["quality"] >= 1
	):
		add(
			"quality-up",
			"Quality up",
			f"Quality rate up {quality - previous['quality']:.1f} points to {quality:.1f}%",
			{"quality": round(quality, 1), "previous_quality": round(previous["quality"], 1)},
		)
	if andon and (andon.get("calls") or 0) >= min_andon_calls and andon.get("on_target") == andon["calls"]:
		add(
			"andon-on-target",
			"Help on time",
			f"All {andon['calls']} calls for help answered within target",
			dict(andon),
		)
	return out


def floor_items(
	recognitions: list[dict],
	opted_out: set[str] | frozenset = frozenset(),
	show_names: bool = True,
	full_names: dict[str, str] | None = None,
) -> list[dict]:
	"""What the floor may show of recent recognitions.

	Private recognitions and withdrawn ones never reach the floor. A recognition of a person who
	opted out of the floor is left out entirely (they still see it themselves). With names turned
	off, a person is shown as their team when the recognition names one, else as "A teammate". The
	giver's name is shown only when names are shown."""
	full_names = full_names or {}
	out = []
	for r in recognitions:
		if r.get("private") or r.get("status") == "Withdrawn":
			continue
		person = r.get("recipient") if r.get("recipient_type") == "Person" else None
		if person and person in opted_out:
			continue
		if person:
			shown = (full_names.get(person) or person) if show_names else (r.get("team") or "A teammate")
		else:
			shown = r.get("team") or ""
		giver = r.get("given_by")
		out.append(
			{
				"name": r.get("name"),
				"kind": r.get("kind"),
				"recipient": shown,
				"team": r.get("team"),
				"machine": r.get("machine"),
				"message": r.get("message"),
				"recognized_at": r.get("recognized_at"),
				"from": (full_names.get(giver) or giver) if (giver and show_names) else None,
			}
		)
	return out
