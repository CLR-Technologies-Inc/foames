Connection details for the FoaMES MCP server. The tools themselves are on [MCP tools](Reference-MCP-tools); step-by-step client setup is in [Connect an agent CLI or harness](How-to-Connect-an-agent-CLI-or-harness).

## Endpoints

| Transport | Endpoint or command | For |
| --- | --- | --- |
| Streamable HTTP | `POST https://<site>/api/method/foames.foames_mcp.api.mcp` | Clients that can send a custom header |
| stdio bridge | `python3 bridge.py` (from `foames/foames_mcp/bridge.py`), or `python -m foames.foames_mcp` where the package is importable | Clients that start a local process |

Both carry the same tools; the bridge forwards each message unchanged. It is standard-library Python and needs neither Frappe nor FoaMES installed.

## Authentication

| Item | Value |
| --- | --- |
| Header | `Authorization: token <api_key>:<api_secret>` (Frappe token scheme, not Bearer) |
| Key from | User form, Settings, API Access, Generate Keys |
| Also accepted | A logged-in desk session |
| Not supported | OAuth; guests are refused before the server runs |

Permissions are those of the key's user. See [Roles and permissions](Reference-Roles-and-permissions).

## Bridge settings

| Variable | Flag | Default | Meaning |
| --- | --- | --- | --- |
| `FOAMES_URL` | `--url` | required | The site's base URL |
| `FOAMES_API_KEY` | `--api-key` | required | API key |
| `FOAMES_API_SECRET` | `--api-secret` | required | API secret |
| `FOAMES_TIMEOUT_SECONDS` | | 120 | Request timeout |
| `FOAMES_CA_BUNDLE` | | system | PEM file for a private certificate authority |
| `FOAMES_MCP_PATH` | | the standard method path | When the endpoint is behind a path prefix |

## Client configuration at a glance

| Client | Where | Transport |
| --- | --- | --- |
| Claude Code | `claude mcp add --transport http foames <endpoint> --header "Authorization: token ..."` | HTTP |
| Google Antigravity (CLI `agy`, IDE, app) | `~/.gemini/config/mcp_config.json` or `.agents/mcp_config.json`, `mcpServers.foames.serverUrl` and `headers` | HTTP |
| Gemini CLI (legacy) | `~/.gemini/settings.json`, `mcpServers.foames.httpUrl` and `headers` | HTTP |
| Codex CLI | `~/.codex/config.toml`, `[mcp_servers.foames]` with `command`, `args`, `env` | stdio bridge |
| Claude Desktop | `claude_desktop_config.json`, `mcpServers.foames` with `command`, `args`, `env` | stdio bridge |
| Cursor | `~/.cursor/mcp.json`, same shape as Claude Desktop | stdio bridge |
| Custom harness | JSON-RPC 2.0 POSTs to the endpoint, or an MCP SDK client | HTTP |

Client file formats change between releases; check your client's documentation if a snippet is refused.

## Protocol

| Item | Value |
| --- | --- |
| Revisions | 2024-11-05, 2025-03-26, 2025-06-18, 2025-11-25 (others get 2025-11-25) |
| Sessions | None; stateless, one JSON-RPC message per POST, no batches |
| GET stream | Refused (POST only); clients treat it as non-fatal |
| Notifications | Answered `202 Accepted` |
| `initialize` | Includes short agent instructions for the system prompt |
| Errors | Permission or validation failure: tool result with `isError`; anything else logged in the site's Error Log and reported by type only |
| Datetimes | Site-local `YYYY-MM-DD HH:MM:SS`; ISO 8601 accepted |
