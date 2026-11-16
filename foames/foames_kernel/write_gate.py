# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""The write gate: the one place every connector write passes through.

Read-only mode (RO mode) lets a plant connect FoaMES to its ERP, MES, SCADA and historians reading
only, and approve each write path when it is ready. While a connector is read-only, a write it
would make is either held as a **Pending Write** until an authorised person signs it off with an
electronic signature (meaning, reason, user, time, re-entered password), or refused. Every step is
recorded in the append-only, hash-chained **Write Audit Log**, against the work order, Job Card,
process run and machine the write belongs to.

What passes the gate:

- **Outbox postings.** Each adapter outbox listed in the `foames_write_gated_outboxes` hook is
  checked when a posting is queued (`outbox_queued`) and again when the outbox is about to send it
  (`outbox_may_send`, called from the outbox's `claim`). A held posting keeps its place in its
  sequence group, so later postings of the same work order wait behind it.
- **MCP tool calls** that write (`gate_tool_call`, from `foames_mcp.api.execute_tool`).
- **Registered actions** (`request_write`): any adapter, bridge or app that writes directly rather
  than through an outbox registers the action in the `foames_write_actions` hook and calls
  `request_write` instead of performing it.

The rules themselves are pure and live in `write_policy.py`. The idea of shipping connectors
read-only first, with writes signed off by an operator and logged against the work order, was
suggested by Ramakrishna Gampa.
"""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import get_fullname, now_datetime

from foames.foames_kernel import write_policy as policy

SETTINGS = "FoaMES Settings"
POLICY = "Connector Write Policy"
PENDING = "Pending Write"
AUDIT = "Write Audit Log"

MCP_CONNECTOR = "mcp"
OUTBOX_PENDING_STATUSES = ("Queued", "Retry", "Unknown")
AUDIT_FIELDS = (
	"event",
	"timestamp",
	"user",
	"full_name",
	"connector",
	"action",
	"pending_write",
	"reference_doctype",
	"reference_name",
	"work_order",
	"job_card",
	"process_run",
	"machine",
	"reason",
	"details",
)
SETTINGS_FIELDS = (
	"read_only_mode",
	"read_only_action",
	"new_connectors_read_only",
	"sign_off_role",
	"require_second_person",
	"gate_agent_suggestions",
)
POLICY_FIELDS = (
	"connector",
	"connector_label",
	"connector_kind",
	"read_only",
	"when_read_only",
	"sign_off_role",
)


class ReadOnlyModeError(frappe.ValidationError):
	"""A write was refused because its connector is read-only and set to block."""


# Settings and policies ---------------------------------------------------------------------------


def site_settings() -> frappe._dict:
	values = frappe._dict()
	for field in SETTINGS_FIELDS:
		values[field] = frappe.db.get_single_value(SETTINGS, field)
	values.read_only_action = values.read_only_action or policy.QUEUE
	values.sign_off_role = values.sign_off_role or ""
	return values


def connector_policy(connector: str, label: str = "", kind: str = "") -> frappe._dict:
	"""The connector's policy, created on first sight: read-only when the site says new connectors
	start read-only (the default)."""
	row = frappe.db.get_value(POLICY, connector, POLICY_FIELDS, as_dict=True)
	if row:
		return row
	read_only = 1 if frappe.db.get_single_value(SETTINGS, "new_connectors_read_only") else 0
	doc = frappe.get_doc(
		{
			"doctype": POLICY,
			"connector": connector,
			"connector_label": label or connector,
			"connector_kind": kind or "",
			"read_only": read_only,
			"when_read_only": policy.SITE_DEFAULT,
		}
	)
	doc.flags.created_by_gate = True
	frappe.db.savepoint("foames_write_policy")
	try:
		doc.insert(ignore_permissions=True)
	except (frappe.DuplicateEntryError, frappe.UniqueValidationError):
		frappe.db.rollback(save_point="foames_write_policy")
	return frappe.db.get_value(POLICY, connector, POLICY_FIELDS, as_dict=True)


def decision_for(connector: str, label: str = "", kind: str = "") -> tuple[str, frappe._dict, frappe._dict]:
	"""`(decision, policy, settings)` for a write by `connector` now."""
	settings = site_settings()
	row = connector_policy(connector, label, kind)
	decision = policy.decide(
		bool(settings.read_only_mode),
		bool(row.read_only),
		row.when_read_only,
		settings.read_only_action,
	)
	return decision, row, settings


def is_read_only(connector: str) -> bool:
	"""Whether a write by this connector would be held or refused now."""
	return decision_for(connector)[0] != policy.ALLOW


def sign_off_role(connector: str) -> str:
	row = frappe.db.get_value(POLICY, connector, "sign_off_role") if connector else None
	return row or site_settings().sign_off_role


# Audit log ---------------------------------------------------------------------------------------


def audit(
	event: str,
	connector: str = "",
	*,
	action: str = "",
	pending_write: str = "",
	reference_doctype: str = "",
	reference_name: str = "",
	context: dict | None = None,
	reason: str = "",
	details=None,
	user: str = "",
) -> str:
	"""Append one entry to the Write Audit Log, chained to the entry before it."""
	user = user or frappe.session.user
	context = context or {}
	values = {
		"event": event,
		"timestamp": now_datetime(),
		"user": user,
		"full_name": get_fullname(user),
		"connector": connector or "",
		"action": action or "",
		"pending_write": pending_write or "",
		"reference_doctype": reference_doctype or "",
		"reference_name": reference_name or "",
		"work_order": context.get("work_order") or "",
		"job_card": context.get("job_card") or "",
		"process_run": context.get("process_run") or "",
		"machine": _machine(context.get("machine")),
		"reason": (reason or "")[:2000],
		"details": json.dumps(details, indent=1, sort_keys=True, default=str) if details is not None else "",
	}
	# Lock the newest entry so that two writers cannot both chain to it.
	last = frappe.db.sql(
		"select entry_hash from `tabWrite Audit Log` order by creation desc, name desc limit 1 for update"
	)
	previous = (last[0][0] or "") if last else ""
	doc = frappe.get_doc({"doctype": AUDIT, **values, "previous_hash": previous})
	doc.entry_hash = policy.entry_hash(previous, audit_content(doc))
	doc.flags.foames_audit = True
	doc.insert(ignore_permissions=True)
	return doc.name


def audit_content(doc) -> dict:
	"""What an entry's hash covers, as text, so the hash can be recomputed from the stored record."""
	return {field: _text(doc.get(field)) for field in AUDIT_FIELDS}


def _text(value) -> str:
	return "" if value is None else str(value)


def _machine(value) -> str:
	if value and frappe.db.exists("Machine", value):
		return value
	return ""


# Holding a write ---------------------------------------------------------------------------------


def _normalised(arguments):
	return json.loads(json.dumps(arguments if arguments is not None else {}, default=str))


def hold(
	connector: str,
	kind: str,
	action: str,
	arguments,
	*,
	requested_by: str = "",
	source: str = "",
	reference_doctype: str = "",
	reference_name: str = "",
	context: dict | None = None,
	summary: str = "",
	sequence_group: str = "",
) -> str:
	"""Record a write that waits for sign-off and return the Pending Write's name."""
	arguments = _normalised(arguments)
	context = policy.context_of(arguments, context)
	requested_by = requested_by or frappe.session.user
	doc = frappe.get_doc(
		{
			"doctype": PENDING,
			"status": policy.AWAITING,
			"connector": connector,
			"kind": kind,
			"action": action,
			"requested_by": requested_by,
			"requested_at": now_datetime(),
			"request_source": source,
			"reference_doctype": reference_doctype or None,
			"reference_name": reference_name or None,
			"work_order": context["work_order"],
			"job_card": context["job_card"],
			"process_run": context["process_run"],
			"machine": _machine(context["machine"]) or None,
			"sequence_group": sequence_group or "",
			"summary": summary or f"{action} on {connector}",
			"arguments": json.dumps(arguments, indent=1, sort_keys=True),
			"payload_hash": policy.payload_hash(connector, kind, action, arguments),
		}
	)
	doc.insert(ignore_permissions=True)
	audit(
		policy.EVENT_HELD,
		connector,
		action=action,
		pending_write=doc.name,
		reference_doctype=reference_doctype,
		reference_name=reference_name,
		context=context,
		user=requested_by,
		reason=_("Read-only mode: waiting for an operator's sign-off"),
		details={"payload_hash": doc.payload_hash, "source": source},
	)
	frappe.publish_realtime(
		"foames_pending_write",
		{"name": doc.name, "connector": connector, "action": action},
		doctype=PENDING,
		after_commit=True,
	)
	return doc.name


def refuse(
	connector: str, action: str, arguments, *, context=None, user="", reference_doctype="", reference_name=""
):
	"""Log a write refused because its connector blocks writes."""
	arguments = _normalised(arguments)
	audit(
		policy.EVENT_BLOCKED,
		connector,
		action=action,
		reference_doctype=reference_doctype,
		reference_name=reference_name,
		context=policy.context_of(arguments, context),
		user=user,
		reason=_("Read-only mode: {0} blocks writes").format(connector),
		details={"payload_hash": policy.payload_hash(connector, "", action, arguments)},
	)


# Outboxes ----------------------------------------------------------------------------------------


def gated_outboxes() -> dict[str, str]:
	"""Outbox DocType -> how its connector is found: a connector key, or `field:<fieldname>`."""
	out = {}
	for doctype, values in (frappe.get_hooks("foames_write_gated_outboxes") or {}).items():
		values = values if isinstance(values, list | tuple) else [values]
		if values:
			out[doctype] = values[-1]
	return out


def outbox_connector(doc) -> str:
	spec = gated_outboxes().get(doc.doctype)
	if not spec:
		return ""
	if spec.startswith("field:"):
		return str(doc.get(spec.split(":", 1)[1]) or "")
	return spec


def _outbox_payload(doc) -> dict:
	try:
		payload = json.loads(doc.payload or "{}")
	except ValueError:
		return {}
	return payload if isinstance(payload, dict) else {}


def _pending_for(doctype: str, name: str):
	return frappe.db.get_value(
		PENDING,
		{"kind": policy.KIND_OUTBOX, "reference_doctype": doctype, "reference_name": name},
		["name", "status", "payload_hash", "connector", "action"],
		as_dict=True,
		order_by="creation desc",
	)


def _hold_outbox(doc, connector: str, decision: str):
	payload = _outbox_payload(doc)
	# The sequence group is usually the work order; a work order named in the payload wins.
	context = {"work_order": doc.get("sequence_group") or ""}
	if decision == policy.BLOCK:
		refuse(
			connector,
			doc.operation,
			payload,
			context=context,
			user=doc.owner,
			reference_doctype=doc.doctype,
			reference_name=doc.name,
		)
		_cancel_outbox_row(
			doc.doctype, doc.name, _("Blocked by read-only mode: {0} does not write").format(connector)
		)
		return None
	if policy.context_of(payload).get("work_order"):
		context = {}
	return hold(
		connector,
		policy.KIND_OUTBOX,
		doc.operation,
		payload,
		requested_by=doc.owner,
		source=doc.doctype,
		reference_doctype=doc.doctype,
		reference_name=doc.name,
		context=context,
		summary=_("{0} to {1}").format(doc.operation, connector),
		sequence_group=doc.get("sequence_group") or "",
	)


def _cancel_outbox_row(doctype: str, name: str, message: str):
	frappe.db.set_value(
		doctype,
		name,
		{"status": "Cancelled", "next_attempt_at": None, "last_error": message[:1000]},
		update_modified=False,
	)


def outbox_queued(doc, method=None):
	"""`after_insert` of a gated outbox: hold or refuse the posting at once when its connector is
	read-only, so the operator sees it before the outbox runs."""
	connector = outbox_connector(doc)
	if not connector:
		return
	decision = decision_for(connector)[0]
	if decision != policy.ALLOW:
		_hold_outbox(doc, connector, decision)


def outbox_may_send(doc) -> bool:
	"""Called by an outbox's `claim` before it sends a posting. True when the posting may go: its
	connector writes, or the posting was signed off. Otherwise the posting is held (or refused) and
	stays where it is, holding back the rest of its sequence group."""
	connector = outbox_connector(doc)
	if not connector:
		return True
	pending = _pending_for(doc.doctype, doc.name)
	if pending:
		if pending.status in policy.SENDABLE:
			if pending.status == policy.APPROVED:
				if (
					policy.payload_hash(
						connector, policy.KIND_OUTBOX, pending.action, _normalised(_outbox_payload(doc))
					)
					!= pending.payload_hash
				):
					_withdraw(pending.name, _("The posting's payload changed after it was signed"))
					return False
				frappe.db.set_value(PENDING, pending.name, "status", policy.RELEASED, update_modified=False)
				audit(
					policy.EVENT_RELEASED,
					connector,
					action=pending.action,
					pending_write=pending.name,
					reference_doctype=doc.doctype,
					reference_name=doc.name,
					context={"work_order": doc.get("sequence_group") or ""},
				)
			return True
		if pending.status == policy.AWAITING:
			return False
	# Nothing is held for it, or what was held went away: decide now.
	decision = decision_for(connector)[0]
	if decision == policy.ALLOW:
		return True
	_hold_outbox(doc, connector, decision)
	return False


def outbox_updated(doc, method=None):
	"""`on_update` of a gated outbox: a posting cancelled while it waited withdraws its Pending Write."""
	if doc.status != "Cancelled":
		return
	pending = _pending_for(doc.doctype, doc.name)
	if pending and pending.status == policy.AWAITING:
		_withdraw(pending.name, _("The posting was cancelled in its outbox"))


def _withdraw(name: str, reason: str):
	row = frappe.db.get_value(
		PENDING, name, ["connector", "action", "reference_doctype", "reference_name"], as_dict=True
	)
	frappe.db.set_value(PENDING, name, {"status": policy.WITHDRAWN, "error": reason}, update_modified=False)
	audit(
		policy.EVENT_WITHDRAWN,
		row.connector,
		action=row.action,
		pending_write=name,
		reference_doctype=row.reference_doctype,
		reference_name=row.reference_name,
		reason=reason,
	)


# MCP tool calls ----------------------------------------------------------------------------------


def gate_tool_call(tool, arguments: dict) -> dict | None:
	"""None when the tool may run now. Otherwise the result the agent gets instead: the Pending Write
	that waits for sign-off. Raises ReadOnlyModeError when the MCP connector blocks writes."""
	if tool.read_only:
		return None
	settings = site_settings()
	if getattr(tool, "suggests", False) and not settings.gate_agent_suggestions:
		return None
	decision = decision_for(MCP_CONNECTOR, _("FoaMES MCP server"), "Agent")[0]
	if decision == policy.ALLOW:
		return None
	context = _tool_context(arguments)
	if decision == policy.BLOCK:
		refuse(MCP_CONNECTOR, tool.name, arguments, context=context)
		raise ReadOnlyModeError(
			_("FoaMES is in read-only mode and {0} is blocked. Ask a person to make the change.").format(
				tool.name
			)
		)
	name = hold(
		MCP_CONNECTOR,
		policy.KIND_TOOL,
		tool.name,
		arguments,
		source="MCP",
		reference_doctype="Machine" if context.get("machine") else "",
		reference_name=context.get("machine") or "",
		context=context,
		summary=_("{0} asked by an agent").format(tool.title or tool.name),
	)
	return {
		"status": policy.AWAITING,
		"pending_write": name,
		"message": _(
			"FoaMES is in read-only mode. Nothing was written yet: the call waits as Pending Write {0} for "
			"an authorised person's electronic sign-off. Do not call the tool again for the same change."
		).format(name),
	}


def _tool_context(arguments: dict) -> dict:
	context = policy.context_of(arguments)
	reference = arguments.get("reference")
	if reference:
		row = frappe.db.get_value(
			"External Reference", reference, ["reference_type", "external_id"], as_dict=True
		)
		if row and row.reference_type == "Job Card":
			context["job_card"] = row.external_id
		elif row and row.reference_type == "Work Order":
			context["work_order"] = row.external_id
	return context


# Registered actions ------------------------------------------------------------------------------


def registered_actions() -> dict[str, str]:
	"""Action key -> dotted path, from the `foames_write_actions` hook."""
	out = {}
	for key, values in (frappe.get_hooks("foames_write_actions") or {}).items():
		values = values if isinstance(values, list | tuple) else [values]
		if values:
			out[key] = values[-1]
	return out


def request_write(
	connector: str,
	action: str,
	arguments: dict,
	*,
	label: str = "",
	kind: str = "",
	context: dict | None = None,
	reference_doctype: str = "",
	reference_name: str = "",
	summary: str = "",
) -> dict:
	"""Perform a registered write action, or hold it for sign-off, as the connector's mode says.

	Use this for any write that does not go through an outbox: a SCADA or historian write, a write
	to another system a bridge makes, a change to FoaMES that a connector asks for. `action` must be
	registered in the `foames_write_actions` hook, and is called with `**arguments` when it runs.
	Returns `{"status": "Executed", "result": ...}` or `{"status": "Awaiting Sign-off",
	"pending_write": ...}`; raises ReadOnlyModeError when the connector blocks writes.
	"""
	if action not in registered_actions():
		frappe.throw(_("{0} is not a registered write action").format(action))
	decision = decision_for(connector, label, kind)[0]
	if decision == policy.ALLOW:
		return {
			"status": policy.EXECUTED,
			"result": frappe.get_attr(registered_actions()[action])(**arguments),
		}
	if decision == policy.BLOCK:
		refuse(
			connector,
			action,
			arguments,
			context=context,
			reference_doctype=reference_doctype,
			reference_name=reference_name,
		)
		raise ReadOnlyModeError(_("{0} is read-only and blocks writes").format(connector))
	name = hold(
		connector,
		policy.KIND_ACTION,
		action,
		arguments,
		source="request_write",
		reference_doctype=reference_doctype,
		reference_name=reference_name,
		context=context,
		summary=summary,
	)
	return {"status": policy.AWAITING, "pending_write": name}


# Sign-off ----------------------------------------------------------------------------------------


@frappe.whitelist(methods=["POST"])
def sign_pending_write(pending_write: str, meaning: str, reason: str, password: str) -> dict:
	"""Sign a Pending Write off: approve it (it is performed, or released to its outbox) or reject it.

	An electronic signature in the sense of 21 CFR Part 11: the signer is the logged-in user, who
	re-enters their password; the signature carries the signer's name, the time and its meaning,
	and is sealed with a hash over the exact payload. Every attempt, failed ones included, is logged.
	"""
	user = frappe.session.user
	if user == "Guest":
		raise frappe.PermissionError
	frappe.has_permission(PENDING, "read", pending_write, throw=True)
	frappe.db.sql("select name from `tabPending Write` where name=%s for update", (pending_write,))
	doc = frappe.get_doc(PENDING, pending_write)
	settings = site_settings()
	failure = None
	try:
		from frappe.utils.password import check_password

		check_password(user, password or "")
	except frappe.AuthenticationError:
		failure = _("The password did not match")
	if not failure:
		try:
			policy.check_signature(
				signer=user,
				requester=doc.requested_by or "",
				meaning=meaning,
				reason=reason,
				signer_roles=frappe.get_roles(user),
				required_role=sign_off_role(doc.connector),
				require_second_person=bool(settings.require_second_person),
				status=doc.status,
			)
		except policy.SignatureError as e:
			failure = str(e)
	if not failure:
		failure = _integrity_problem(doc)
	if failure:
		audit(
			policy.EVENT_SIGNATURE_FAILED,
			doc.connector,
			action=doc.action,
			pending_write=doc.name,
			reference_doctype=doc.reference_doctype,
			reference_name=doc.reference_name,
			context=_doc_context(doc),
			reason=failure,
			details={"meaning": meaning},
		)
		# The failed attempt stays on record even though the request fails.
		frappe.db.commit()  # nosemgrep
		frappe.throw(failure, frappe.ValidationError, title=_("Not signed"))

	signed_at = now_datetime()
	reason = reason.strip()
	seal = policy.signature_hash(doc.name, doc.payload_hash, user, meaning, reason, str(signed_at))
	doc.db_set(
		{
			"signed_by": user,
			"signed_by_name": get_fullname(user),
			"signed_at": signed_at,
			"signature_meaning": meaning,
			"signature_reason": reason,
			"signature_hash": seal,
			"status": policy.APPROVED if meaning == policy.APPROVE else policy.REJECTED,
		}
	)
	audit(
		policy.EVENT_SIGNED if meaning == policy.APPROVE else policy.EVENT_REJECTED,
		doc.connector,
		action=doc.action,
		pending_write=doc.name,
		reference_doctype=doc.reference_doctype,
		reference_name=doc.reference_name,
		context=_doc_context(doc),
		reason=reason,
		details={"meaning": meaning, "signature_hash": seal, "payload_hash": doc.payload_hash},
	)
	if meaning == policy.REJECT:
		if doc.kind == policy.KIND_OUTBOX and doc.reference_doctype and doc.reference_name:
			_cancel_outbox_row(
				doc.reference_doctype,
				doc.reference_name,
				_("Rejected at sign-off by {0}: {1}").format(get_fullname(user), reason),
			)
	elif doc.kind != policy.KIND_OUTBOX:
		_execute(doc)
	doc.reload()
	return {
		"pending_write": doc.name,
		"status": doc.status,
		"signed_by": doc.signed_by,
		"signed_at": doc.signed_at,
		"signature_hash": doc.signature_hash,
		"error": doc.error,
	}


def _doc_context(doc) -> dict:
	return {field: doc.get(field) for field in policy.CONTEXT_FIELDS}


def _integrity_problem(doc) -> str | None:
	"""Why the write cannot be signed as it stands, if anything has changed since it was held."""
	try:
		arguments = json.loads(doc.arguments or "{}")
	except ValueError:
		return _("The stored payload is not valid JSON")
	if policy.payload_hash(doc.connector, doc.kind, doc.action, arguments) != doc.payload_hash:
		return _("The stored payload does not match its hash; it was changed after it was requested")
	if doc.kind == policy.KIND_OUTBOX:
		if not (
			doc.reference_doctype
			and doc.reference_name
			and frappe.db.exists(doc.reference_doctype, doc.reference_name)
		):
			return _("The outbox posting no longer exists")
		row = frappe.get_doc(doc.reference_doctype, doc.reference_name)
		if row.status not in OUTBOX_PENDING_STATUSES:
			return _("The outbox posting is {0} and can no longer be signed").format(row.status)
		current = policy.payload_hash(doc.connector, doc.kind, doc.action, _normalised(_outbox_payload(row)))
		if current != doc.payload_hash:
			return _("The outbox posting's payload changed after it was held")
	return None


def _resolve(doc):
	if doc.kind == policy.KIND_TOOL:
		from foames.foames_mcp.api import catalogue

		tool = next((t for t in catalogue() if t.name == doc.action), None)
		if not tool:
			frappe.throw(_("{0} is not an MCP tool").format(doc.action))
		method = frappe.get_attr(tool.method)
		frappe.is_whitelisted(method)
		return method
	path = registered_actions().get(doc.action)
	if not path:
		frappe.throw(_("{0} is not a registered write action").format(doc.action))
	return frappe.get_attr(path)


def _execute(doc):
	"""Run an approved tool call or action as the user who asked for it, and record what happened."""
	arguments = json.loads(doc.arguments or "{}")
	signer = frappe.session.user
	frappe.db.savepoint("foames_write_gate_execute")
	try:
		method = _resolve(doc)
		frappe.set_user(doc.requested_by or signer)  # nosemgrep
		result = method(**arguments)
		status, error = policy.EXECUTED, None
	except Exception as e:
		frappe.db.rollback(save_point="foames_write_gate_execute")
		result, status, error = (
			None,
			policy.FAILED,
			frappe.utils.strip_html(str(e) or type(e).__name__)[:1000],
		)
	finally:
		frappe.set_user(signer)  # nosemgrep
		frappe.clear_messages()
	doc.db_set(
		{
			"status": status,
			"result": json.dumps(result, indent=1, default=str) if result is not None else None,
			"error": error,
		}
	)
	audit(
		policy.EVENT_EXECUTED if status == policy.EXECUTED else policy.EVENT_EXECUTION_FAILED,
		doc.connector,
		action=doc.action,
		pending_write=doc.name,
		reference_doctype=doc.reference_doctype,
		reference_name=doc.reference_name,
		context=_doc_context(doc),
		reason=error or "",
		user=signer,
	)


# Reads for people and agents ---------------------------------------------------------------------


@frappe.whitelist()
def get_write_mode() -> dict:
	"""The site's read-only mode, every connector's policy and what it means now, and how many writes
	wait for sign-off."""
	frappe.has_permission(POLICY, "read", throw=True)
	settings = site_settings()
	connectors = []
	for row in frappe.get_all(POLICY, fields=list(POLICY_FIELDS), order_by="connector asc"):
		row["effective"] = policy.decide(
			bool(settings.read_only_mode), bool(row.read_only), row.when_read_only, settings.read_only_action
		)
		connectors.append(row)
	return {
		"site_read_only": bool(settings.read_only_mode),
		"read_only_action": settings.read_only_action,
		"new_connectors_read_only": bool(settings.new_connectors_read_only),
		"sign_off_role": settings.sign_off_role,
		"require_second_person": bool(settings.require_second_person),
		"gate_agent_suggestions": bool(settings.gate_agent_suggestions),
		"connectors": connectors,
		"awaiting_sign_off": frappe.db.count(PENDING, {"status": policy.AWAITING}),
	}


def _limit(limit) -> int:
	return max(1, min(int(limit or 100), 1000))


@frappe.whitelist()
def list_pending_writes(
	status: str | None = None,
	connector: str | None = None,
	work_order: str | None = None,
	job_card: str | None = None,
	process_run: str | None = None,
	machine: str | None = None,
	limit: int = 100,
) -> list[dict]:
	"""Pending Writes, newest first, with who asked, what for, and who signed."""
	filters = {
		key: value
		for key, value in {
			"status": status,
			"connector": connector,
			"work_order": work_order,
			"job_card": job_card,
			"process_run": process_run,
			"machine": machine,
		}.items()
		if value
	}
	return frappe.get_list(
		PENDING,
		filters=filters,
		fields=[
			"name",
			"status",
			"connector",
			"kind",
			"action",
			"summary",
			"requested_by",
			"requested_at",
			"work_order",
			"job_card",
			"process_run",
			"machine",
			"reference_doctype",
			"reference_name",
			"signed_by_name",
			"signed_at",
			"signature_meaning",
			"signature_reason",
		],
		order_by="creation desc",
		limit_page_length=_limit(limit),
	)


@frappe.whitelist()
def get_write_audit_trail(
	work_order: str | None = None,
	job_card: str | None = None,
	process_run: str | None = None,
	machine: str | None = None,
	pending_write: str | None = None,
	connector: str | None = None,
	limit: int = 200,
) -> list[dict]:
	"""The Write Audit Log for a work order, Job Card, process run, machine, Pending Write or
	connector, oldest first."""
	filters = {
		key: value
		for key, value in {
			"work_order": work_order,
			"job_card": job_card,
			"process_run": process_run,
			"machine": machine,
			"pending_write": pending_write,
			"connector": connector,
		}.items()
		if value
	}
	return frappe.get_list(
		AUDIT,
		filters=filters,
		fields=["name", *AUDIT_FIELDS],
		order_by="creation asc, name asc",
		limit_page_length=_limit(limit),
	)


@frappe.whitelist()
def verify_audit_trail() -> dict:
	"""Recompute the hash chain of the whole Write Audit Log and list the entries that do not match."""
	frappe.only_for(("System Manager", "FoaMES Quality"))
	rows = frappe.get_all(
		AUDIT,
		fields=["name", "previous_hash", "entry_hash", *AUDIT_FIELDS],
		order_by="creation asc, name asc",
	)
	entries = [
		{
			"name": row.name,
			"previous_hash": row.previous_hash or "",
			"entry_hash": row.entry_hash,
			"content": {field: _text(row.get(field)) for field in AUDIT_FIELDS},
		}
		for row in rows
	]
	broken = policy.verify_chain(entries)
	return {"entries": len(entries), "broken": broken, "intact": not broken}


@frappe.whitelist()
def verify_pending_write(pending_write: str) -> dict:
	"""Whether a Pending Write's payload and signature still match their hashes."""
	frappe.has_permission(PENDING, "read", pending_write, throw=True)
	doc = frappe.get_doc(PENDING, pending_write)
	arguments = json.loads(doc.arguments or "{}")
	payload_ok = policy.payload_hash(doc.connector, doc.kind, doc.action, arguments) == doc.payload_hash
	signature_ok = None
	if doc.signed_by:
		signature_ok = (
			policy.signature_hash(
				doc.name,
				doc.payload_hash,
				doc.signed_by,
				doc.signature_meaning,
				doc.signature_reason or "",
				str(doc.signed_at),
			)
			== doc.signature_hash
		)
	return {"pending_write": doc.name, "payload_ok": payload_ok, "signature_ok": signature_ok}


# Changes to the mode itself ---------------------------------------------------------------------


def log_settings_change(doc):
	"""FoaMES Settings `on_update`: record every change to read-only mode."""
	before = doc.get_doc_before_save()
	changes = {
		field: {"from": before.get(field) if before else None, "to": doc.get(field)}
		for field in SETTINGS_FIELDS
		if not before or before.get(field) != doc.get(field)
	}
	if changes:
		audit(policy.EVENT_SETTINGS_CHANGED, reason=_("FoaMES Settings changed"), details=changes)


def log_policy_change(doc, event_reason: str = ""):
	before = doc.get_doc_before_save()
	fields = (*POLICY_FIELDS, "approval_reference")
	changes = {
		field: {"from": before.get(field) if before else None, "to": doc.get(field)}
		for field in fields
		if not before or before.get(field) != doc.get(field)
	}
	if changes:
		audit(
			policy.EVENT_POLICY_CHANGED,
			doc.connector,
			reason=event_reason or doc.get("approval_reference") or "",
			details=changes,
		)
