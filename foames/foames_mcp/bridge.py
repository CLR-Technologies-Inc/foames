#!/usr/bin/env python3
# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""FoaMES MCP over stdio: a bridge from an agent's stdio transport to a FoaMES site.

Agents such as Claude Desktop, Claude Code or Cursor start this script and speak MCP over its
stdin and stdout (one JSON-RPC message per line). The bridge forwards each message to the site's
MCP endpoint over HTTPS with the API key and secret, and writes the response back. It keeps no
state and interprets no message, so the tool list and behaviour are always the site's.

Only the Python standard library is used, so the file can be copied anywhere on its own:

    python bridge.py --url https://mes.example.com --api-key KEY --api-secret SECRET

or with FOAMES_URL, FOAMES_API_KEY and FOAMES_API_SECRET in the environment:

    python -m foames.foames_mcp

Optional: FOAMES_TIMEOUT_SECONDS (default 120), FOAMES_CA_BUNDLE (a PEM file for a private CA),
FOAMES_MCP_PATH (default /api/method/foames.foames_mcp.api.mcp).
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request

DEFAULT_PATH = "/api/method/foames.foames_mcp.api.mcp"
UPSTREAM_ERROR = -32000
AUTH_ERROR = -32001


class Bridge:
	def __init__(self, url: str, api_key: str, api_secret: str, timeout: float = 120.0, ca_bundle: str = ""):
		self.endpoint = url
		self.headers = {
			"Authorization": f"token {api_key}:{api_secret}",
			"Content-Type": "application/json",
			"Accept": "application/json",
			"User-Agent": "foames-mcp-bridge",
		}
		self.timeout = timeout
		self.context = ssl.create_default_context(cafile=ca_bundle) if ca_bundle else None

	def forward(self, line: str) -> str | None:
		"""Send one raw message to the site; the response line to write back, or None."""
		try:
			message = json.loads(line)
		except ValueError:
			return _dumps(_error(None, -32700, "Parse error"))
		request_id = message.get("id") if isinstance(message, dict) else None
		params = message.get("params") if isinstance(message, dict) else None
		if isinstance(params, dict) and params.get("protocolVersion"):
			# After initialize, the specification wants the negotiated version on every request.
			self.headers["MCP-Protocol-Version"] = str(params["protocolVersion"])
		try:
			status, body = self.post(line.encode("utf-8"))
		except urllib.error.HTTPError as e:
			status, body = e.code, e.read()
		except (urllib.error.URLError, TimeoutError, OSError) as e:
			return self._failure(request_id, UPSTREAM_ERROR, f"FoaMES site unreachable: {e}")
		if status in (401, 403):
			return self._failure(
				request_id,
				AUTH_ERROR,
				f"FoaMES refused the credentials (HTTP {status}): {_frappe_message(body)}",
			)
		if status >= 400:
			return self._failure(
				request_id, UPSTREAM_ERROR, f"FoaMES returned HTTP {status}: {_frappe_message(body)}"
			)
		# The site answers a notification with 202 and no body. Anything else is written back, including
		# an error with a null id for a message the site could not read as a request.
		if status == 202 or not body:
			return None
		return body.decode("utf-8", errors="replace").strip() or None

	def post(self, data: bytes) -> tuple[int, bytes]:
		request = urllib.request.Request(self.endpoint, data=data, headers=self.headers, method="POST")
		with urllib.request.urlopen(request, timeout=self.timeout, context=self.context) as response:
			return response.status, response.read()

	def _failure(self, request_id, code: int, message: str) -> str | None:
		print(message, file=sys.stderr, flush=True)
		if request_id is None:
			return None
		return _dumps(_error(request_id, code, message))

	def serve(self, stdin=None, stdout=None):
		stdin = stdin or sys.stdin
		stdout = stdout or sys.stdout
		for line in stdin:
			line = line.strip()
			if not line:
				continue
			response = self.forward(line)
			if response is not None:
				stdout.write(response + "\n")
				stdout.flush()


def _frappe_message(body: bytes) -> str:
	"""The human-readable part of a Frappe error body, when there is one."""
	try:
		data = json.loads(body)
	except ValueError:
		return body.decode("utf-8", errors="replace")[:200]
	if isinstance(data, dict):
		for key in ("message", "exception", "exc_type"):
			if data.get(key):
				return str(data[key])[:200]
		if data.get("_server_messages"):
			try:
				messages = json.loads(data["_server_messages"])
				return "; ".join(json.loads(m).get("message", "") for m in messages)[:200]
			except ValueError:
				pass
	return str(data)[:200]


def _error(request_id, code: int, message: str) -> dict:
	return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _dumps(value) -> str:
	return json.dumps(value, ensure_ascii=False)


def build(argv: list[str] | None = None) -> Bridge:
	parser = argparse.ArgumentParser(description="FoaMES MCP server over stdio")
	parser.add_argument(
		"--url", default=os.environ.get("FOAMES_URL"), help="Site URL, e.g. https://mes.example.com"
	)
	parser.add_argument("--api-key", default=os.environ.get("FOAMES_API_KEY"))
	parser.add_argument("--api-secret", default=os.environ.get("FOAMES_API_SECRET"))
	parser.add_argument("--path", default=os.environ.get("FOAMES_MCP_PATH", DEFAULT_PATH))
	parser.add_argument(
		"--timeout", type=float, default=float(os.environ.get("FOAMES_TIMEOUT_SECONDS", "120"))
	)
	parser.add_argument("--ca-bundle", default=os.environ.get("FOAMES_CA_BUNDLE", ""))
	args = parser.parse_args(argv)
	missing = [
		name
		for name, value in (
			("--url", args.url),
			("--api-key", args.api_key),
			("--api-secret", args.api_secret),
		)
		if not value
	]
	if missing:
		parser.error(f"missing {', '.join(missing)} (or FOAMES_URL, FOAMES_API_KEY, FOAMES_API_SECRET)")
	url = args.url.rstrip("/") + (args.path if args.path.startswith("/") else "/" + args.path)
	return Bridge(url, args.api_key, args.api_secret, timeout=args.timeout, ca_bundle=args.ca_bundle)


def main(argv: list[str] | None = None):
	build(argv).serve()


if __name__ == "__main__":
	main()
