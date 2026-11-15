# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Read-only mode: the pure rules behind the write gate.

Every write that leaves FoaMES for another system (an ERP, another MES, SCADA, a historian) or that
an agent or connector makes to FoaMES's own state passes one gate, `foames_kernel/write_gate.py`.
This module holds what that gate decides and how it seals what it records, with no Frappe import,
so the rules can be tested and read on their own:

- `decide` says whether a write goes now, waits for an operator's sign-off, or is refused.
- `context_of` finds the work order, Job Card, process run and machine a write belongs to, so the
  sign-off and the audit entry are logged against them.
- `payload_hash`, `signature_hash` and `entry_hash` bind a signature to exactly what was signed and
  chain the audit entries, so an edited payload or a removed entry shows.
- `check_signature` holds the sign-off rules: a meaning, a reason, an authorised role, and (unless
  the site turns it off) a signer other than the requester.
"""

from __future__ import annotations

import hashlib
import json

ALLOW = "Allow"
QUEUE = "Queue for sign-off"
BLOCK = "Block"
ACTIONS = (QUEUE, BLOCK)
SITE_DEFAULT = "Site default"
POLICY_ACTIONS = (SITE_DEFAULT, QUEUE, BLOCK)

# What a signature means (21 CFR 11.50(a)(3): the meaning of the signature is part of it).
APPROVE = "Approved"
REJECT = "Rejected"
MEANINGS = (APPROVE, REJECT)

# Kinds of write the gate holds.
KIND_OUTBOX = "Outbox Posting"
KIND_TOOL = "MCP Tool Call"
KIND_ACTION = "Registered Action"
KINDS = (KIND_OUTBOX, KIND_TOOL, KIND_ACTION)

# Pending Write statuses.
AWAITING = "Awaiting Sign-off"
APPROVED = "Approved"  # signed; an outbox posting goes with the next outbox run
RELEASED = "Released"  # an approved outbox posting the outbox has picked up
EXECUTED = "Executed"  # an approved tool call or action that ran
REJECTED = "Rejected"
BLOCKED = "Blocked"
FAILED = "Failed"  # approved, then the action raised
WITHDRAWN = "Withdrawn"  # the write went away before anyone signed (outbox row cancelled)
STATUSES = (AWAITING, APPROVED, RELEASED, EXECUTED, REJECTED, BLOCKED, FAILED, WITHDRAWN)
OPEN_STATUSES = (AWAITING,)
# A posting whose Pending Write reached one of these may be sent.
SENDABLE = (APPROVED, RELEASED)

# Audit events.
EVENT_REQUESTED = "Write Requested"
EVENT_HELD = "Held for Sign-off"
EVENT_BLOCKED = "Blocked"
EVENT_ALLOWED = "Allowed (read-write)"
EVENT_SIGNED = "Signed"
EVENT_SIGNATURE_FAILED = "Signature Failed"
EVENT_REJECTED = "Rejected"
EVENT_RELEASED = "Released to Send"
EVENT_EXECUTED = "Executed"
EVENT_EXECUTION_FAILED = "Execution Failed"
EVENT_WITHDRAWN = "Withdrawn"
EVENT_POLICY_CHANGED = "Policy Changed"
EVENT_SETTINGS_CHANGED = "Settings Changed"
EVENTS = (
	EVENT_REQUESTED,
	EVENT_HELD,
	EVENT_BLOCKED,
	EVENT_ALLOWED,
	EVENT_SIGNED,
	EVENT_SIGNATURE_FAILED,
	EVENT_REJECTED,
	EVENT_RELEASED,
	EVENT_EXECUTED,
	EVENT_EXECUTION_FAILED,
	EVENT_WITHDRAWN,
	EVENT_POLICY_CHANGED,
	EVENT_SETTINGS_CHANGED,
)

# Payload keys the context is read from, in order of preference. Adapters name the same things in
# different ways; a caller that knows better passes the context itself.
CONTEXT_KEYS = {
	"work_order": (
		"work_order",
		"workOrder",
		"work_order_id",
		"production_order",
		"productionOrder",
		"manufacturing_order",
		"ManufacturingOrder",
		"order",
		"order_number",
		"OrderNumber",
	),
	"job_card": ("job_card", "jobCard", "job_card_id", "operation_activity", "job", "job_id"),
	"process_run": ("process_run", "processRun", "run", "run_id", "batch_record", "batch"),
	"machine": ("machine", "machine_id", "machineId", "workstation", "resource"),
}
CONTEXT_FIELDS = tuple(CONTEXT_KEYS)


def decide(
	site_read_only: bool,
	policy_read_only: bool,
	policy_action: str | None = None,
	site_action: str | None = None,
) -> str:
	"""What happens to a write: `ALLOW`, `QUEUE` (wait for sign-off) or `BLOCK`.

	The site-wide switch makes every connector read-only, whatever its own policy says; a connector
	is otherwise read-only when its policy is. A read-only connector's writes are queued or blocked
	as its policy says, or as the site says when the policy leaves it to the site.
	"""
	if not (site_read_only or policy_read_only):
		return ALLOW
	if policy_action in ACTIONS:
		return policy_action
	if site_action in ACTIONS:
		return site_action
	return QUEUE


def context_of(payload, explicit: dict | None = None) -> dict:
	"""The work order, Job Card, process run and machine a write belongs to.

	Values passed in `explicit` win; the rest are read from the payload's top level, then from one
	level of nesting. Only scalar values are taken; a value is cut to 140 characters.
	"""
	found = {key: _clean((explicit or {}).get(key)) for key in CONTEXT_FIELDS}
	layers = [payload] if isinstance(payload, dict) else []
	if isinstance(payload, dict):
		layers += [value for value in payload.values() if isinstance(value, dict)]
	for key, names in CONTEXT_KEYS.items():
		if found[key]:
			continue
		for layer in layers:
			value = next((_clean(layer.get(name)) for name in names if _clean(layer.get(name))), "")
			if value:
				found[key] = value
				break
	return found


def _clean(value) -> str:
	if value is None or isinstance(value, dict | list | tuple | set | bool):
		return ""
	return str(value).strip()[:140]


def canonical(value) -> str:
	"""The JSON text a hash is taken over: sorted keys, no whitespace, non-JSON values as strings."""
	return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=False)


def sha256(text: str) -> str:
	return hashlib.sha256(text.encode("utf-8")).hexdigest()


def payload_hash(connector: str, kind: str, action: str, arguments) -> str:
	"""What a signature is bound to: the connector, the kind and name of the write, and its payload."""
	return sha256(canonical({"connector": connector, "kind": kind, "action": action, "arguments": arguments}))


def signature_hash(
	pending_write: str, payload_digest: str, signer: str, meaning: str, reason: str, signed_at: str
) -> str:
	"""The seal of one signature (21 CFR 11.70: a signature linked to its record so that it cannot be
	copied to another one). Recomputing it from the record shows whether anything was changed."""
	return sha256(
		canonical(
			{
				"pending_write": pending_write,
				"payload_hash": payload_digest,
				"signer": signer,
				"meaning": meaning,
				"reason": reason,
				"signed_at": signed_at,
			}
		)
	)


def entry_hash(previous_hash: str, entry: dict) -> str:
	"""The hash of one audit entry, chained to the one before it."""
	return sha256((previous_hash or "") + canonical(entry))


def verify_chain(entries: list[dict]) -> list[str]:
	"""Names of entries, oldest first, whose hash does not follow from the previous entry and their
	own content. Each entry carries `name`, `previous_hash`, `entry_hash` and `content`."""
	broken = []
	previous = ""
	for entry in entries:
		if entry.get("previous_hash", "") != previous or entry.get("entry_hash") != entry_hash(
			previous, entry.get("content") or {}
		):
			broken.append(entry.get("name"))
		previous = entry.get("entry_hash") or ""
	return broken


class SignatureError(ValueError):
	pass


def check_signature(
	*,
	signer: str,
	requester: str,
	meaning: str,
	reason: str,
	signer_roles,
	required_role: str,
	require_second_person: bool,
	status: str,
) -> None:
	"""Raise `SignatureError` when a sign-off may not be given. The password is checked by the caller."""
	if status not in OPEN_STATUSES:
		raise SignatureError(f"This write is {status}; only a write awaiting sign-off can be signed")
	if meaning not in MEANINGS:
		raise SignatureError(f"The meaning of a signature is one of {', '.join(MEANINGS)}")
	if len((reason or "").strip()) < 3:
		raise SignatureError("A signature needs a reason")
	if required_role and required_role not in set(signer_roles or ()):
		raise SignatureError(f"Signing needs the role {required_role}")
	if require_second_person and signer and signer == requester:
		raise SignatureError("The person who asked for a write cannot also sign it off")
