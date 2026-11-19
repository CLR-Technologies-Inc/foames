# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""The versioned request/response contract between FoaMES and the FreeCAD bridge.

One JSON envelope per call, versioned so both sides can refuse a peer they do
not understand:

    request : {"protocol": 1, "action": "health"|"capabilities"|"inspect", "params": {...}}
    response: {"protocol": 1, "ok": true,  "result": {...}}
               {"protocol": 1, "ok": false, "error": {"code": "...", "message": "..."}}

Error codes are stable strings; `BridgeError` carries one plus a message. This
module imports nothing outside the standard library and nothing from Frappe or
FreeCAD.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

PROTOCOL_VERSION = 1

ACTIONS = ("health", "capabilities", "inspect")

# Stable error codes. Add new ones, never rename.
ERR_UNKNOWN_ACTION = "unknown_action"
ERR_BAD_REQUEST = "bad_request"
ERR_UNSUPPORTED_PROTOCOL = "unsupported_protocol"
ERR_FREECAD_MISSING = "freecad_missing"
ERR_DOCUMENT_UNREADABLE = "document_unreadable"
ERR_UNSUPPORTED_DOCUMENT = "unsupported_document"
ERR_TIMEOUT = "timeout"
ERR_PATH_REJECTED = "path_rejected"
ERR_TOO_LARGE = "too_large"
ERR_INTERNAL = "internal"


class BridgeError(Exception):
	"""A bridge failure carrying a stable protocol error code."""

	def __init__(self, code: str, message: str):
		super().__init__(message)
		self.code = code
		self.message = message


@dataclass
class Request:
	action: str
	params: dict = field(default_factory=dict)
	protocol: int = PROTOCOL_VERSION

	def to_dict(self) -> dict:
		return {"protocol": self.protocol, "action": self.action, "params": dict(self.params)}


@dataclass
class Response:
	ok: bool
	result: dict | None = None
	error_code: str = ""
	error_message: str = ""
	protocol: int = PROTOCOL_VERSION

	def to_dict(self) -> dict:
		out = {"protocol": self.protocol, "ok": self.ok}
		if self.ok:
			out["result"] = self.result or {}
		else:
			out["error"] = {"code": self.error_code, "message": self.error_message}
		return out

	@classmethod
	def success(cls, result: dict | None = None) -> "Response":
		return cls(ok=True, result=result or {})

	@classmethod
	def failure(cls, error: BridgeError) -> "Response":
		return cls(ok=False, error_code=error.code, error_message=error.message)


def encode(response: Response) -> str:
	return json.dumps(response.to_dict(), indent=1, sort_keys=True)


def decode_request(text: str) -> Request:
	"""Parse and validate a request envelope. Raises BridgeError on any defect."""
	try:
		data = json.loads(text)
	except ValueError as e:
		raise BridgeError(ERR_BAD_REQUEST, "request is not valid JSON: {0}".format(e)) from e
	if not isinstance(data, dict):
		raise BridgeError(ERR_BAD_REQUEST, "request must be a JSON object")
	protocol = data.get("protocol", PROTOCOL_VERSION)
	if protocol != PROTOCOL_VERSION:
		raise BridgeError(
			ERR_UNSUPPORTED_PROTOCOL,
			"protocol {0} is not supported; this bridge speaks {1}".format(protocol, PROTOCOL_VERSION),
		)
	action = data.get("action")
	if action not in ACTIONS:
		raise BridgeError(ERR_UNKNOWN_ACTION, "unknown action {0!r}; expected one of {1}".format(action, ", ".join(ACTIONS)))
	params = data.get("params") or {}
	if not isinstance(params, dict):
		raise BridgeError(ERR_BAD_REQUEST, "params must be an object")
	return Request(action=action, params=params, protocol=protocol)


def decode_response(text: str) -> Response:
	"""Parse a response envelope produced by `encode`."""
	data = json.loads(text)
	if not isinstance(data, dict) or "ok" not in data:
		raise BridgeError(ERR_BAD_REQUEST, "response is not a bridge envelope")
	if data.get("protocol", PROTOCOL_VERSION) != PROTOCOL_VERSION:
		raise BridgeError(ERR_UNSUPPORTED_PROTOCOL, "response protocol mismatch")
	if data.get("ok"):
		return Response(ok=True, result=data.get("result") or {}, protocol=data.get("protocol", PROTOCOL_VERSION))
	error = data.get("error") or {}
	return Response(
		ok=False,
		error_code=error.get("code", ERR_INTERNAL),
		error_message=error.get("message", ""),
		protocol=data.get("protocol", PROTOCOL_VERSION),
	)
