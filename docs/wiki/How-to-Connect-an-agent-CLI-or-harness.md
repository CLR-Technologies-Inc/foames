**Goal:** give an agent in any CLI or harness access to a FoaMES site through MCP, so it can read the floor and raise suggestions.

**You need:** a FoaMES site you can reach from where the agent runs (a dev site from [Tutorial 1](Tutorial-1-Install-FoaMES) is ideal for testing), and System Manager on it to create a user.

## 1. Create the agent's user and key (every client)

1. Create a user for the agent, for example `agent-test@example.com`, with **FoaMES Operator** only. Add **FoaMES Quality** or **Supervisor** if it must read more; never System Manager unless it must read External References.
2. On that user, **Settings**, **API Access**, **Generate Keys**. Copy the key and secret.
3. Note the two values every client needs:

| Value | Example |
| --- | --- |
| HTTP endpoint | `https://mes.example.com/api/method/foames.foames_mcp.api.mcp` (dev: `http://foames.localhost:8000/api/method/foames.foames_mcp.api.mcp`) |
| Authorization header | `Authorization: token <api_key>:<api_secret>` |

FoaMES uses Frappe's `token` scheme, not `Bearer`, and has no OAuth flow. A client that can send a custom header connects over HTTP directly. A client that cannot, or that only starts local processes, uses the **stdio bridge**: one file of standard-library Python, `foames/foames_mcp/bridge.py`, which you can copy to any machine without installing FoaMES.

```bash
curl -O https://raw.githubusercontent.com/CLR-Technologies-Inc/foames/main/foames/foames_mcp/bridge.py
```

## 2. Connect your client

Configuration formats change between client releases; if a snippet is refused, check your client's current MCP documentation and keep the same endpoint, header or bridge command.

### Claude Code

```bash
claude mcp add --transport http foames https://mes.example.com/api/method/foames.foames_mcp.api.mcp \
  --header "Authorization: token <api_key>:<api_secret>"
claude mcp list
```

### Codex CLI

Use the bridge, in `~/.codex/config.toml`:

```toml
[mcp_servers.foames]
command = "python3"
args = ["/path/to/bridge.py"]
env = { FOAMES_URL = "https://mes.example.com", FOAMES_API_KEY = "<api_key>", FOAMES_API_SECRET = "<api_secret>" }
```

### Google Antigravity (the `agy` CLI, the IDE and the app)

Google's [Antigravity CLI migration guide](https://antigravity.google/docs/cli/gcli-migration/) presents the Antigravity CLI, command `agy`, as the successor to Gemini CLI. It keeps Gemini CLI's conventions, such as `GEMINI.md`, and offers to migrate a Gemini CLI setup the first time `agy` runs (or with `agy plugin import gemini`). The Antigravity CLI, IDE and app all read MCP servers from the same file ([Antigravity MCP docs](https://antigravity.google/docs/mcp/)):

| Scope | File |
| --- | --- |
| All projects | `~/.gemini/config/mcp_config.json` |
| One workspace | `<workspace>/.agents/mcp_config.json` |

Antigravity talks to remote servers over Streamable HTTP and accepts custom headers, so connect over HTTP directly:

```json
{
  "mcpServers": {
    "foames": {
      "serverUrl": "https://mes.example.com/api/method/foames.foames_mcp.api.mcp",
      "headers": { "Authorization": "token <api_key>:<api_secret>" }
    }
  }
}
```

Note the key is `serverUrl` (or `url`). Gemini CLI's `httpUrl` is not accepted. In the CLI, `/mcp` opens the server manager. In the IDE, open the agent panel's **…** menu, then **MCP Servers**, **Manage MCP Servers**, **View raw config**. In the app, go to **Customizations**, **Installed**, **MCP Servers**.

### Gemini CLI (legacy)

If you still run Gemini CLI, it reads `~/.gemini/settings.json` (or `.gemini/settings.json` in a project):

```json
{
  "mcpServers": {
    "foames": {
      "httpUrl": "https://mes.example.com/api/method/foames.foames_mcp.api.mcp",
      "headers": { "Authorization": "token <api_key>:<api_secret>" }
    }
  }
}
```

When you move to Antigravity, its migration writes this entry into `mcp_config.json` and renames `httpUrl` to `serverUrl`. Google's Antigravity pages that we checked (November 2026) do not give an end-of-support date for Gemini CLI. Several third-party migration guides report that it has been retired in favour of Antigravity. Prefer Antigravity for new setups.

### Cursor, Claude Desktop, VS Code and other desktop clients

Use the bridge. In Cursor's `~/.cursor/mcp.json`, Claude Desktop's `claude_desktop_config.json`, or your editor's MCP file:

```json
{
  "mcpServers": {
    "foames": {
      "command": "python3",
      "args": ["/path/to/bridge.py"],
      "env": {
        "FOAMES_URL": "https://mes.example.com",
        "FOAMES_API_KEY": "<api_key>",
        "FOAMES_API_SECRET": "<api_secret>"
      }
    }
  }
}
```

### Any other MCP client

- **HTTP-capable:** point it at the endpoint with the `Authorization` header. The server is stateless and answers one JSON-RPC message per POST.
- **stdio-only:** run `python3 bridge.py --url https://mes.example.com --api-key <key> --api-secret <secret>` as the server command.

### A custom harness

Speak JSON-RPC to the endpoint yourself, or use an MCP SDK client:

```python
import json, urllib.request

URL = "https://mes.example.com/api/method/foames.foames_mcp.api.mcp"
HEADERS = {"Authorization": "token <api_key>:<api_secret>", "Content-Type": "application/json"}

def call(method, params=None, id_=1):
    body = json.dumps({"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}}).encode()
    with urllib.request.urlopen(urllib.request.Request(URL, data=body, headers=HEADERS)) as r:
        return json.load(r)

call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "my-harness", "version": "0"}})
tools = call("tools/list")["result"]["tools"]
snapshot = call("tools/call", {"name": "foames_get_floor_snapshot", "arguments": {"days": 1}})
```

Hand `tools` to your model as its tool definitions and forward its tool calls with `tools/call`. The `initialize` response carries short agent instructions you can put in the system prompt.

## 3. Check it

Ask the agent to list the machines, or run:

```bash
curl -s https://mes.example.com/api/method/foames.foames_mcp.api.mcp \
  -H "Authorization: token <api_key>:<api_secret>" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python3 -m json.tool | head
```

A tool the user may not run comes back with `isError` and "Not permitted"; give the user the role it needs rather than a broader one. Bridge options (`FOAMES_TIMEOUT_SECONDS`, `FOAMES_CA_BUNDLE`, `FOAMES_MCP_PATH`) are on [MCP setup](Reference-MCP-setup).

For something for the agent to read, seed the site: [Seed a dev site for agent tests](How-to-Seed-a-dev-site-for-agent-tests).
