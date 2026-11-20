# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Simulation run lifecycle helpers. Pure: no Frappe imports.

Mirrors the provider's state machine (`bridges/openfoam/foames_openfoam/
lifecycle.py`) closely enough for the DocType to reject illegal local
transitions; the provider remains the authority on actual run state.
"""

from __future__ import annotations

RUN_STATES = ("draft", "queued", "running", "succeeded", "failed", "cancelled", "timed_out")
TERMINAL_STATES = ("succeeded", "failed", "cancelled", "timed_out")
ACTIVE_STATES = ("queued", "running")

_ALLOWED = {
	"draft": {"queued", "cancelled"},
	"queued": {"running", "cancelled", "failed"},
	"running": {"succeeded", "failed", "cancelled", "timed_out"},
}


class TransitionError(Exception):
	pass


def transition(current: str, target: str) -> str:
	if current not in RUN_STATES:
		raise TransitionError("unknown state {0!r}".format(current))
	if target not in RUN_STATES:
		raise TransitionError("unknown state {0!r}".format(target))
	if current in TERMINAL_STATES:
		raise TransitionError("run is already terminal ({0}); cannot move to {1}".format(current, target))
	if target not in _ALLOWED.get(current, set()):
		raise TransitionError("cannot move a run from {0} to {1}".format(current, target))
	return target


def is_terminal(status: str) -> bool:
	return status in TERMINAL_STATES


def epoch_to_datetime(value):
	"""Provider epoch seconds -> naive datetime for Datetime fields; None passes through."""
	from datetime import datetime

	if value in (None, ""):
		return None
	try:
		return datetime.fromtimestamp(float(value))
	except (TypeError, ValueError, OSError):
		return None


def evidence_status(run_status: str) -> str:
	"""How a finished run may be used as validation evidence.

	Only `succeeded` runs are candidates at all, and even then they stay
	*unapproved*: a person reviews them against the Validation Protocol's
	acceptance criteria. Everything else is not evidence.
	"""
	return "Candidate" if run_status == "succeeded" else "Not evidence"
