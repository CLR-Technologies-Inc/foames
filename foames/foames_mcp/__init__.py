# Copyright 2026 CLR Technologies Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""FoaMES as an MCP server.

The Model Context Protocol (MCP) is how coding and operations agents call tools. This package
exposes the public FoaMES API as MCP tools in two transports that share one tool catalogue:

- `api.mcp`: a Streamable HTTP endpoint inside the site at
  `/api/method/foames.foames_mcp.api.mcp`, authenticated with a Frappe API key and secret.
- `bridge`: a stdio server for agents that only speak stdio (Claude Desktop, Claude Code, Cursor),
  which forwards each message to that endpoint. It needs nothing but Python.

`protocol.py` (the JSON-RPC dispatcher) and `tools.py` (the catalogue) import nothing from Frappe,
so they are unit-tested without a site. Permissions are Frappe's own: every tool runs as the user
the API key belongs to and goes through the same `frappe.has_permission` checks as the desk.
"""
