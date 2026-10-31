# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Tests for the MCP server core, the tool catalogue and the stdio bridge. No site is needed:

    python -m unittest foames.foames_mcp.test_mcp_protocol

The last class drives the real bridge with the official MCP Python SDK against a local stand-in
for the site, and is skipped when the `mcp` package is not installed.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from foames.foames_mcp import bridge
from foames.foames_mcp.protocol import (
	INVALID_PARAMS,
	INVALID_REQUEST,
	LATEST_PROTOCOL_VERSION,
	METHOD_NOT_FOUND,
	PARSE_ERROR,
	SUPPORTED_PROTOCOL_VERSIONS,
	InvalidParams,
	Server,
	Tool,
	ToolError,
	validate_arguments,
)
from foames.foames_mcp.tools import ALLOWED_METHOD_PREFIXES, TOOLS, TOOLS_BY_NAME

TOOL_NAME = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def request(method, params=None, request_id=1):
	message = {"jsonrpc": "2.0", "id": request_id, "method": method}
	if params is not None:
		message["params"] = params
	return message


class FakeCalls:
	"""Stands in for the site: records calls and returns canned values per tool."""

	def __init__(self, results=None):
		self.results = results or {}
		self.calls = []

	def __call__(self, tool, arguments):
		self.calls.append((tool.name, arguments))
		result = self.results.get(tool.name, {"ok": True})
		if isinstance(result, Exception):
			raise result
		return result


def make_server(results=None, **kwargs):
	calls = FakeCalls(results)
	return Server(TOOLS, calls, name="foames", version="test", instructions="be kind", **kwargs), calls


class TestCatalogue(unittest.TestCase):
	def test_names_are_unique_and_valid(self):
		names = [tool.name for tool in TOOLS]
		self.assertEqual(len(names), len(set(names)))
		for name in names:
			self.assertRegex(name, TOOL_NAME)
			self.assertTrue(name.startswith("foames_"), name)

	def test_every_tool_binds_a_public_method(self):
		for tool in TOOLS:
			self.assertTrue(
				tool.method.startswith(ALLOWED_METHOD_PREFIXES), f"{tool.name} reaches outside the public API"
			)
			self.assertTrue(tool.description)

	def test_schemas_are_closed_objects(self):
		for tool in TOOLS:
			mcp = tool.to_mcp()
			schema = mcp["inputSchema"]
			self.assertEqual(schema["type"], "object")
			self.assertIs(schema["additionalProperties"], False, tool.name)
			for key in schema.get("required", []):
				self.assertIn(key, schema["properties"], f"{tool.name} requires unknown {key}")
			for key, spec in schema["properties"].items():
				self.assertIn("type", spec, f"{tool.name}.{key} has no type")
				self.assertIn("description", spec, f"{tool.name}.{key} has no description")
			self.assertIn("readOnlyHint", mcp["annotations"])

	def test_only_three_tools_write(self):
		writers = sorted(tool.name for tool in TOOLS if not tool.read_only)
		self.assertEqual(
			writers, ["foames_post_suggestion", "foames_run_suggestion_rules", "foames_set_current_job"]
		)
		self.assertFalse(any(tool.destructive for tool in TOOLS))

	def test_floor_agent_playbook_names_exist(self):
		for name in ("foames_get_floor_snapshot", "foames_post_suggestion", "foames_get_oee"):
			self.assertIn(name, TOOLS_BY_NAME)


class TestValidateArguments(unittest.TestCase):
	schema = TOOLS_BY_NAME["foames_get_oee"].input_schema

	def test_accepts_valid_arguments(self):
		args = {"machine": "M-01", "from_time": "2026-10-01 06:00:00", "to_time": "2026-10-01 14:00:00"}
		self.assertEqual(validate_arguments(self.schema, args), args)
		self.assertEqual(
			validate_arguments(self.schema, {**args, "planned_minutes": 450}),
			{**args, "planned_minutes": 450},
		)

	def test_rejects_missing_unknown_and_mistyped(self):
		with self.assertRaisesRegex(InvalidParams, "missing required"):
			validate_arguments(self.schema, {"machine": "M-01"})
		with self.assertRaisesRegex(InvalidParams, "unknown argument"):
			validate_arguments(self.schema, {"machine": "M-01", "from_time": "a", "to_time": "b", "extra": 1})
		with self.assertRaisesRegex(InvalidParams, "type"):
			validate_arguments(self.schema, {"machine": 7, "from_time": "a", "to_time": "b"})
		with self.assertRaisesRegex(InvalidParams, "must be an object"):
			validate_arguments(self.schema, ["M-01"])

	def test_enum_and_bool_rules(self):
		schema = TOOLS_BY_NAME["foames_list_machines"].input_schema
		with self.assertRaisesRegex(InvalidParams, "one of"):
			validate_arguments(schema, {"status": "Broken"})
		with self.assertRaisesRegex(InvalidParams, "type"):
			validate_arguments(schema, {"limit": True})
		self.assertEqual(
			validate_arguments(schema, {"status": "Down", "limit": 5}), {"status": "Down", "limit": 5}
		)
		self.assertEqual(validate_arguments(schema, None), {})

	def test_numeric_bounds(self):
		schema = TOOLS_BY_NAME["foames_get_floor_snapshot"].input_schema
		self.assertEqual(validate_arguments(schema, {"days": 90}), {"days": 90})
		with self.assertRaisesRegex(InvalidParams, "at most 90"):
			validate_arguments(schema, {"days": 1000000})
		with self.assertRaisesRegex(InvalidParams, "at least 1"):
			validate_arguments(schema, {"days": 0})
		with self.assertRaisesRegex(InvalidParams, "at least 1"):
			validate_arguments(TOOLS_BY_NAME["foames_list_machines"].input_schema, {"limit": -5})

	def test_union_types(self):
		schema = TOOLS_BY_NAME["foames_mining_conformance"].input_schema
		for model in ({"edges": []}, ["Setup", "Running"], "PEL-2026-00001"):
			validate_arguments(schema, {"model": model})
		with self.assertRaises(InvalidParams):
			validate_arguments(schema, {"model": 3})


class TestServer(unittest.TestCase):
	def test_initialize_negotiates_a_version(self):
		server, _ = make_server()
		for version in SUPPORTED_PROTOCOL_VERSIONS:
			result = server.handle(request("initialize", {"protocolVersion": version}))["result"]
			self.assertEqual(result["protocolVersion"], version)
		result = server.handle(request("initialize", {"protocolVersion": "1999-01-01"}))["result"]
		self.assertEqual(result["protocolVersion"], LATEST_PROTOCOL_VERSION)
		self.assertEqual(result["serverInfo"]["name"], "foames")
		self.assertEqual(result["instructions"], "be kind")
		self.assertIn("tools", result["capabilities"])

	def test_notifications_and_ping(self):
		server, _ = make_server()
		self.assertIsNone(server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}))
		self.assertEqual(server.handle(request("ping"))["result"], {})

	def test_tools_list(self):
		server, _ = make_server()
		tools = server.handle(request("tools/list"))["result"]["tools"]
		self.assertEqual([t["name"] for t in tools], [t.name for t in TOOLS])
		self.assertTrue(all("inputSchema" in t for t in tools))

	def test_tools_call_returns_structured_content(self):
		server, calls = make_server({"foames_get_floor_snapshot": {"machines": [], "as_of": "now"}})
		response = server.handle(
			request("tools/call", {"name": "foames_get_floor_snapshot", "arguments": {"days": 2}})
		)
		result = response["result"]
		self.assertFalse(result["isError"])
		self.assertEqual(result["structuredContent"], {"machines": [], "as_of": "now"})
		self.assertEqual(json.loads(result["content"][0]["text"]), {"machines": [], "as_of": "now"})
		self.assertEqual(calls.calls, [("foames_get_floor_snapshot", {"days": 2})])

	def test_string_and_list_results(self):
		server, _ = make_server(
			{"foames_mining_export": "<log/>", "foames_list_machines": [{"name": "M-01"}]}
		)
		text = server.handle(request("tools/call", {"name": "foames_mining_export"}))["result"]
		self.assertEqual(text["content"][0]["text"], "<log/>")
		self.assertNotIn("structuredContent", text)
		rows = server.handle(request("tools/call", {"name": "foames_list_machines"}))["result"]
		self.assertEqual(json.loads(rows["content"][0]["text"]), [{"name": "M-01"}])

	def test_tool_error_is_a_result_not_a_protocol_error(self):
		server, _ = make_server({"foames_list_machines": ToolError("Not permitted: read on Machine")})
		result = server.handle(request("tools/call", {"name": "foames_list_machines"}))["result"]
		self.assertTrue(result["isError"])
		self.assertIn("Not permitted", result["content"][0]["text"])

	def test_unexpected_exception_is_logged_and_hidden(self):
		logged = []
		server, _ = make_server(
			{"foames_list_machines": RuntimeError("database password is hunter2")},
			on_error=lambda tool, e: logged.append((tool.name, str(e))),
		)
		result = server.handle(request("tools/call", {"name": "foames_list_machines"}))["result"]
		self.assertTrue(result["isError"])
		self.assertNotIn("hunter2", result["content"][0]["text"])
		self.assertIn("RuntimeError", result["content"][0]["text"])
		self.assertEqual(logged, [("foames_list_machines", "database password is hunter2")])

	def test_protocol_errors(self):
		server, calls = make_server()
		self.assertEqual(
			server.handle(request("tools/call", {"name": "nope"}))["error"]["code"], INVALID_PARAMS
		)
		bad_args = request("tools/call", {"name": "foames_get_oee", "arguments": {"machine": "M-01"}})
		self.assertEqual(server.handle(bad_args)["error"]["code"], INVALID_PARAMS)
		self.assertEqual(server.handle(request("resources/read"))["error"]["code"], METHOD_NOT_FOUND)
		self.assertEqual(server.handle([request("ping")])["error"]["code"], INVALID_REQUEST)
		self.assertEqual(server.handle({"id": 1, "method": "ping"})["error"]["code"], INVALID_REQUEST)
		self.assertEqual(json.loads(server.handle_text("{not json"))["error"]["code"], PARSE_ERROR)
		self.assertIsNone(server.handle({"jsonrpc": "2.0", "id": 9, "result": {}}))
		self.assertEqual(calls.calls, [])

	def test_handle_text_round_trip(self):
		server, _ = make_server()
		self.assertEqual(json.loads(server.handle_text(json.dumps(request("ping"))))["result"], {})
		self.assertIsNone(
			server.handle_text(json.dumps({"jsonrpc": "2.0", "method": "notifications/cancelled"}))
		)

	def test_empty_catalogue_lists_nothing_else(self):
		server, _ = make_server()
		self.assertEqual(server.handle(request("resources/list"))["result"], {"resources": []})
		self.assertEqual(server.handle(request("prompts/list"))["result"], {"prompts": []})


# A stand-in for the site: the same Server behind a plain HTTP endpoint with token auth ---------


class SiteStandIn:
	def __init__(self, results=None, status=None):
		self.server, self.calls = make_server(results)
		self.requests = []
		self.forced_status = status
		stand_in = self

		class Handler(BaseHTTPRequestHandler):
			def log_message(self, *args):
				pass

			def do_POST(self):
				body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
				stand_in.requests.append((self.path, dict(self.headers), body))
				if stand_in.forced_status:
					self.send_response(stand_in.forced_status)
					self.send_header("Content-Type", "application/json")
					self.end_headers()
					self.wfile.write(b'{"message": "Invalid API Key", "exc_type": "AuthenticationError"}')
					return
				if self.headers.get("Authorization") != "token key:secret":
					self.send_response(403)
					self.end_headers()
					return
				response = stand_in.server.handle_text(body)
				if response is None:
					self.send_response(202)
					self.end_headers()
					return
				data = response.encode()
				self.send_response(200)
				self.send_header("Content-Type", "application/json")
				self.send_header("Content-Length", str(len(data)))
				self.end_headers()
				self.wfile.write(data)

		self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
		self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
		self.thread.start()

	@property
	def url(self):
		return f"http://127.0.0.1:{self.httpd.server_port}"

	def close(self):
		self.httpd.shutdown()
		self.httpd.server_close()


class TestBridge(unittest.TestCase):
	def setUp(self):
		self.site = SiteStandIn({"foames_list_machines": [{"name": "M-01", "status": "Running"}]})
		self.addCleanup(self.site.close)

	def make_bridge(self, key="key", secret="secret"):
		return bridge.build(["--url", self.site.url, "--api-key", key, "--api-secret", secret])

	def test_forwards_requests_with_token_auth(self):
		b = self.make_bridge()
		line = json.dumps(request("tools/call", {"name": "foames_list_machines", "arguments": {}}))
		response = json.loads(b.forward(line))
		self.assertEqual(
			json.loads(response["result"]["content"][0]["text"]), [{"name": "M-01", "status": "Running"}]
		)
		path, headers, _ = self.site.requests[-1]
		self.assertEqual(path, bridge.DEFAULT_PATH)
		self.assertEqual(headers["Authorization"], "token key:secret")

	def test_errors_with_a_null_id_are_forwarded(self):
		b = self.make_bridge()
		response = json.loads(b.forward("[]"))
		self.assertEqual(response["error"]["code"], INVALID_REQUEST)
		self.assertIsNone(response["id"])

	def test_notifications_get_no_reply(self):
		b = self.make_bridge()
		self.assertIsNone(b.forward(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})))
		self.assertEqual(len(self.site.requests), 1)

	def test_bad_credentials_become_a_jsonrpc_error(self):
		b = self.make_bridge(secret="wrong")
		with contextlib.redirect_stderr(io.StringIO()) as stderr:
			response = json.loads(b.forward(json.dumps(request("ping"))))
		self.assertIn("HTTP 403", stderr.getvalue())
		self.assertEqual(response["error"]["code"], bridge.AUTH_ERROR)
		self.assertEqual(response["id"], 1)

	def test_unreachable_site(self):
		b = bridge.build(
			["--url", "http://127.0.0.1:9", "--api-key", "k", "--api-secret", "s", "--timeout", "2"]
		)
		with contextlib.redirect_stderr(io.StringIO()):
			response = json.loads(b.forward(json.dumps(request("ping"))))
		self.assertEqual(response["error"]["code"], bridge.UPSTREAM_ERROR)

	def test_build_requires_credentials(self):
		with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
			bridge.build(["--url", self.site.url])

	def test_serve_streams_lines(self):
		b = self.make_bridge()
		stdin = io.StringIO(
			json.dumps(request("ping")) + "\n\n" + json.dumps(request("tools/list", request_id=2)) + "\n"
		)
		stdout = io.StringIO()
		b.serve(stdin, stdout)
		lines = [json.loads(l) for l in stdout.getvalue().splitlines()]
		self.assertEqual([l["id"] for l in lines], [1, 2])
		self.assertEqual(len(lines[1]["result"]["tools"]), len(TOOLS))


try:
	import anyio
	from mcp import ClientSession, StdioServerParameters
	from mcp.client.stdio import stdio_client
	from mcp.client.streamable_http import streamable_http_client
except ImportError:  # the SDK is only a test aid; the bridge itself needs nothing
	ClientSession = None


@unittest.skipIf(ClientSession is None, "the mcp SDK is not installed")
class TestWithTheOfficialClient(unittest.TestCase):
	"""The real bridge process, driven by the official MCP client SDK over stdio."""

	def setUp(self):
		self.site = SiteStandIn({"foames_get_floor_snapshot": {"machines": [{"name": "M-01"}]}})
		self.addCleanup(self.site.close)

	def run_session(self, scenario):
		params = StdioServerParameters(
			command=sys.executable,
			args=[os.path.abspath(bridge.__file__)],
			env={
				**os.environ,
				"FOAMES_URL": self.site.url,
				"FOAMES_API_KEY": "key",
				"FOAMES_API_SECRET": "secret",
			},
		)

		async def main():
			async with stdio_client(params) as (read, write):
				async with ClientSession(read, write) as session:
					with anyio.fail_after(30):
						return await scenario(session)

		return anyio.run(main)

	def test_initialize_list_and_call(self):
		async def scenario(session):
			init = await session.initialize()
			tools = await session.list_tools()
			result = await session.call_tool("foames_get_floor_snapshot", {"days": 1})
			return init, tools, result

		init, tools, result = self.run_session(scenario)
		self.assertEqual(init.server_info.name, "foames")
		self.assertIn(init.protocol_version, SUPPORTED_PROTOCOL_VERSIONS)
		self.assertEqual({t.name for t in tools.tools}, {t.name for t in TOOLS})
		self.assertFalse(result.is_error)
		self.assertEqual(result.structured_content, {"machines": [{"name": "M-01"}]})
		self.assertEqual(self.site.calls.calls, [("foames_get_floor_snapshot", {"days": 1})])
		self.assertTrue(all(h["Authorization"] == "token key:secret" for _, h, _ in self.site.requests))

	def test_streamable_http_client_against_the_endpoint(self):
		"""The SDK's HTTP transport straight at the endpoint, as Claude Code's `--transport http` does."""
		import httpx2

		url = self.site.url + bridge.DEFAULT_PATH

		async def main():
			client = httpx2.AsyncClient(headers={"Authorization": "token key:secret"})
			async with (
				client,
				streamable_http_client(url, http_client=client, terminate_on_close=False) as (
					read,
					write,
					*_,
				),
			):
				async with ClientSession(read, write) as session:
					with anyio.fail_after(30):
						await session.initialize()
						tools = await session.list_tools()
						result = await session.call_tool("foames_get_floor_snapshot", {})
						return tools, result

		tools, result = anyio.run(main)
		self.assertEqual(len(tools.tools), len(TOOLS))
		self.assertEqual(result.structured_content, {"machines": [{"name": "M-01"}]})


if __name__ == "__main__":
	unittest.main()
