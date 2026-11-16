# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""The MCP endpoint inside the site: Streamable HTTP at
`POST /api/method/foames.foames_mcp.api.mcp`.

Authentication is Frappe's: `Authorization: token <api_key>:<api_secret>` of a FoaMES user (or a
desk session). Guests are refused before this code runs. Every tool call then executes the
whitelisted method as that user, so the same role and user permissions apply as on the desk and
the HTTP API.

The server is stateless: no session id is issued, and each POST carries one JSON-RPC message and
gets one JSON response (or 202 Accepted for a notification). A client that asks for the SSE
stream with GET gets 405, which the specification allows.
"""

from __future__ import annotations

import frappe
from werkzeug.wrappers import Response

import foames
from foames.foames_mcp.protocol import LATEST_PROTOCOL_VERSION, Server, Tool, ToolError
from foames.foames_mcp.tools import INSTRUCTIONS, TOOLS

# Exceptions whose message is meant for the caller and is safe to show.
REPORTABLE = (
	frappe.PermissionError,
	frappe.ValidationError,
	frappe.DoesNotExistError,
	frappe.DuplicateEntryError,
	frappe.AuthenticationError,
)


@frappe.whitelist(methods=["POST"])
def mcp():
	"""Handle one MCP message. Returns the JSON-RPC response as the raw body."""
	body = frappe.request.get_data() if frappe.request else b""
	response = get_server().handle_text(body or b"")
	headers = {"MCP-Protocol-Version": LATEST_PROTOCOL_VERSION}
	if response is None:
		return Response(status=202, headers=headers)
	return Response(response, status=200, mimetype="application/json", headers=headers)


def catalogue() -> list[Tool]:
	"""The core tools and those other apps add with the `foames_mcp_tools` hook. A registered tool may
	not take a core tool's name."""
	tools = list(TOOLS)
	names = {tool.name for tool in tools}
	for path in frappe.get_hooks("foames_mcp_tools") or []:
		for tool in frappe.get_attr(path)():
			if tool.name not in names:
				tools.append(tool)
				names.add(tool.name)
	return tools


def get_server() -> Server:
	return Server(
		catalogue(),
		call=execute_tool,
		name="foames",
		version=foames.__version__,
		instructions=INSTRUCTIONS,
		on_error=log_tool_error,
	)


def execute_tool(tool: Tool, arguments: dict):
	"""Run the tool's whitelisted method as the current user; undo its writes if it fails."""
	from foames.foames_kernel.write_gate import ReadOnlyModeError, gate_tool_call

	method = frappe.get_attr(tool.method)
	frappe.is_whitelisted(method)
	frappe.db.savepoint("foames_mcp_tool")
	try:
		# Read-only mode: a write is held for an operator's sign-off (the agent gets the Pending Write)
		# or refused, instead of being made.
		held = gate_tool_call(tool, arguments)
		if held is not None:
			return held
		# The arguments were validated against the tool's schema, whose keys are the method's parameters.
		return method(**arguments)
	except ReadOnlyModeError as e:
		# The refusal was logged; keep the audit entry.
		raise ToolError(_message(e)) from e
	except REPORTABLE as e:
		frappe.db.rollback(save_point="foames_mcp_tool")
		raise ToolError(_message(e)) from e
	except Exception:
		frappe.db.rollback(save_point="foames_mcp_tool")
		raise
	finally:
		# frappe.throw also queued a message for the desk; this response is raw JSON-RPC.
		frappe.clear_messages()


def log_tool_error(tool: Tool, error: BaseException):
	frappe.log_error(title=f"FoaMES MCP tool {tool.name}", message=frappe.get_traceback())


def _message(error: Exception) -> str:
	text = str(error) or type(error).__name__
	if isinstance(error, frappe.PermissionError):
		text = f"Not permitted: {text}" if text and text != "PermissionError" else "Not permitted"
	return frappe.utils.strip_html_tags(text)


def handle(message: dict) -> dict | None:
	"""Dispatch one parsed MCP message in-process (for tests and scripts on the bench)."""
	return get_server().handle(message)


def tool_list() -> list[dict]:
	return [tool.to_mcp() for tool in catalogue()]
