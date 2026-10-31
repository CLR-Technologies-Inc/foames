# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""A small MCP server core: JSON-RPC 2.0 dispatch for `initialize`, `ping`, `tools/list` and
`tools/call`, with argument validation against each tool's input schema.

No Frappe and no MCP SDK: the transports (`api.py` in the site, `bridge.py` over stdio) hand
every message to `Server.handle` and send back whatever it returns. The MCP protocol revisions
in SUPPORTED_PROTOCOL_VERSIONS are the ones that negotiate through `initialize`; a client that
offers one of them gets it back, any other offer gets the newest we speak.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

SUPPORTED_PROTOCOL_VERSIONS = ("2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25")
LATEST_PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[-1]

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class ToolError(Exception):
	"""A tool failed for a reason the agent should see (permission denied, validation, not found).
	It becomes a tool result with `isError`, not a JSON-RPC error, so the agent can recover."""


class InvalidParams(Exception):
	"""The request's params are malformed; becomes JSON-RPC error -32602."""


@dataclass(frozen=True)
class Tool:
	"""One MCP tool bound to a whitelisted FoaMES method."""

	name: str
	description: str
	method: str
	input_schema: dict = field(default_factory=lambda: {"type": "object", "properties": {}})
	title: str = ""
	read_only: bool = True
	destructive: bool = False
	idempotent: bool = True

	def to_mcp(self) -> dict:
		schema = dict(self.input_schema)
		schema.setdefault("type", "object")
		schema.setdefault("properties", {})
		schema.setdefault("additionalProperties", False)
		out = {
			"name": self.name,
			"description": self.description,
			"inputSchema": schema,
			"annotations": {
				"title": self.title or self.name,
				"readOnlyHint": self.read_only,
				"destructiveHint": self.destructive,
				"idempotentHint": self.idempotent,
				"openWorldHint": False,
			},
		}
		if self.title:
			out["title"] = self.title
		return out


JSON_TYPES = {
	"string": (str,),
	"integer": (int,),
	"number": (int, float),
	"boolean": (bool,),
	"array": (list,),
	"object": (dict,),
	"null": (type(None),),
}


def validate_arguments(schema: dict, arguments: Any) -> dict:
	"""Check `arguments` against a tool's (deliberately simple) JSON schema: required keys, no
	unknown keys, the declared `type` of each property, its `enum` and its numeric `minimum` and
	`maximum`. Returns the arguments."""
	if arguments is None:
		arguments = {}
	if not isinstance(arguments, dict):
		raise InvalidParams("arguments must be an object")
	properties = schema.get("properties") or {}
	if schema.get("additionalProperties", False) is False:
		unknown = sorted(set(arguments) - set(properties))
		if unknown:
			raise InvalidParams(f"unknown argument(s): {', '.join(unknown)}")
	missing = [key for key in schema.get("required") or [] if arguments.get(key) is None]
	if missing:
		raise InvalidParams(f"missing required argument(s): {', '.join(missing)}")
	for key, value in arguments.items():
		if value is None:
			continue
		spec = properties.get(key) or {}
		_check_type(key, value, spec)
	return arguments


def _check_type(key: str, value: Any, spec: dict):
	types = spec.get("type")
	if types:
		allowed = tuple(
			t for name in ([types] if isinstance(types, str) else types) for t in JSON_TYPES[name]
		)
		ok = isinstance(value, allowed)
		# bool is an int in Python; JSON keeps them apart.
		if isinstance(value, bool) and bool not in allowed:
			ok = False
		if not ok:
			raise InvalidParams(f"argument {key} must be of type {types}")
	if "enum" in spec and value not in spec["enum"]:
		raise InvalidParams(f"argument {key} must be one of {', '.join(map(str, spec['enum']))}")
	if isinstance(value, int | float) and not isinstance(value, bool):
		if "minimum" in spec and value < spec["minimum"]:
			raise InvalidParams(f"argument {key} must be at least {spec['minimum']}")
		if "maximum" in spec and value > spec["maximum"]:
			raise InvalidParams(f"argument {key} must be at most {spec['maximum']}")


def format_result(value: Any) -> dict:
	"""A tool's return value as an MCP tool result: text (the JSON) and, for a dict, the same dict
	as structuredContent."""
	if isinstance(value, str):
		return {"content": [{"type": "text", "text": value}], "isError": False}
	text = json.dumps(value, default=str, ensure_ascii=False)
	result = {"content": [{"type": "text", "text": text}], "isError": False}
	if isinstance(value, dict):
		result["structuredContent"] = json.loads(text)
	return result


def error_result(message: str) -> dict:
	return {"content": [{"type": "text", "text": message}], "isError": True}


class Server:
	"""Dispatches MCP messages to a catalogue of tools.

	`call(tool, arguments)` is the transport's way to run a tool: in the site it calls the
	whitelisted method as the request's user. It may raise ToolError for failures the agent should
	see; any other exception is reported as an internal error without its details, after `on_error`
	(if given) has had the chance to log it.
	"""

	def __init__(
		self,
		tools: list[Tool],
		call: Callable[[Tool, dict], Any],
		name: str = "foames",
		version: str = "",
		instructions: str = "",
		on_error: Callable[[Tool, BaseException], None] | None = None,
	):
		self.tools = {tool.name: tool for tool in tools}
		self.call = call
		self.name = name
		self.version = version
		self.instructions = instructions
		self.on_error = on_error

	# Transport entry points --------------------------------------------------------------------

	def handle_text(self, text: str | bytes) -> str | None:
		"""Handle one raw JSON message; the response as JSON text, or None when there is none."""
		try:
			message = json.loads(text)
		except ValueError:
			return json.dumps(_error(None, PARSE_ERROR, "Parse error"))
		response = self.handle(message)
		return None if response is None else json.dumps(response, default=str, ensure_ascii=False)

	def handle(self, message: Any) -> dict | None:
		"""Handle one parsed message. Returns the response object, or None for a notification."""
		if not isinstance(message, dict):
			# JSON-RPC batches left the MCP spec in 2025-06-18; Frappe would not pass one anyway.
			return _error(None, INVALID_REQUEST, "Invalid request: expected one JSON-RPC object")
		request_id = message.get("id")
		method = message.get("method")
		if message.get("jsonrpc") != "2.0" or not isinstance(method, str):
			if "result" in message or "error" in message:
				return None  # a response to something we sent; we send nothing, so ignore it
			return _error(request_id, INVALID_REQUEST, "Invalid request")
		params = message.get("params") or {}
		if not isinstance(params, dict):
			return _error(request_id, INVALID_PARAMS, "params must be an object")
		if request_id is None:
			self._notification(method, params)
			return None
		try:
			return {"jsonrpc": "2.0", "id": request_id, "result": self._request(method, params)}
		except InvalidParams as e:
			return _error(request_id, INVALID_PARAMS, str(e))
		except _MethodNotFound as e:
			return _error(request_id, METHOD_NOT_FOUND, str(e))

	# Methods -----------------------------------------------------------------------------------

	def _notification(self, method: str, params: dict):
		# notifications/initialized, notifications/cancelled, notifications/roots/list_changed:
		# nothing to do for a stateless server.
		return None

	def _request(self, method: str, params: dict) -> dict:
		if method == "initialize":
			return self.initialize(params)
		if method == "ping":
			return {}
		if method == "tools/list":
			return {"tools": [tool.to_mcp() for tool in self.tools.values()]}
		if method == "tools/call":
			return self.call_tool(params)
		if method in ("resources/list", "resources/templates/list"):
			return {"resources": []} if method == "resources/list" else {"resourceTemplates": []}
		if method == "prompts/list":
			return {"prompts": []}
		raise _MethodNotFound(f"Method not found: {method}")

	def initialize(self, params: dict) -> dict:
		offered = params.get("protocolVersion")
		version = offered if offered in SUPPORTED_PROTOCOL_VERSIONS else LATEST_PROTOCOL_VERSION
		result = {
			"protocolVersion": version,
			"capabilities": {"tools": {"listChanged": False}},
			"serverInfo": {"name": self.name, "title": "FoaMES", "version": self.version},
		}
		if self.instructions:
			result["instructions"] = self.instructions
		return result

	def call_tool(self, params: dict) -> dict:
		name = params.get("name")
		tool = self.tools.get(name) if isinstance(name, str) else None
		if not tool:
			raise InvalidParams(f"Unknown tool: {name}")
		arguments = validate_arguments(tool.input_schema, params.get("arguments"))
		try:
			return format_result(self.call(tool, arguments))
		except ToolError as e:
			return error_result(str(e))
		except Exception as e:  # every failure must come back as a tool result
			if self.on_error:
				self.on_error(tool, e)
			return error_result(f"{tool.name} failed with {type(e).__name__}; see the site's Error Log")


class _MethodNotFound(Exception):
	pass


def _error(request_id, code: int, message: str) -> dict:
	return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
