In this tutorial you will connect an AI agent to your FoaMES site through the Model Context Protocol (MCP), ask it about the floor, have it raise an Agent Suggestion, and then decide on that suggestion yourself. You will see that the agent works with an ordinary user's permissions and that its only power is to suggest.

**You need:** the site and the press-1 machine from [Tutorial 2](Tutorial-2-Your-first-machine-and-OEE), and an MCP client. The steps use [Claude Code](https://docs.claude.com/en/docs/claude-code/overview); Claude Desktop, Cursor and other clients work too (see the end of this page).

## 1. Create a user for the agent

An agent should have its own user, so you can see what it did and limit what it may do.

1. Open **User**, choose **New**, and create `floor-agent@example.com` with first name *Floor Agent*.
2. Under **Roles**, tick **FoaMES Operator** only. Do not give an agent System Manager.
3. Save, then under **Settings**, **API Access**, press **Generate Keys** and copy the key and secret.

## 2. Connect the client

```bash
claude mcp add --transport http foames \
  http://foames.localhost:8000/api/method/foames.foames_mcp.api.mcp \
  --header "Authorization: token <agent api key>:<agent api secret>"
```

Check that the server answers, without any client, if you like:

```bash
curl -s http://foames.localhost:8000/api/method/foames.foames_mcp.api.mcp \
  -H "Authorization: token <agent api key>:<agent api secret>" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python3 -m json.tool | head -20
```

## 3. Ask about the floor

Start Claude Code and ask, in plain words:

> Using the foames tools, list the machines and tell me what press-1 did on 5 January 2026 between 06:00 and 08:00, including its OEE and downtime.

The agent calls tools such as `foames_list_machines`, `foames_get_oee` and `foames_list_downtime`. You should recognise the numbers from Tutorial 2. Every call ran as *Floor Agent*, with exactly the permissions of a FoaMES Operator.

## 4. Have the agent raise a suggestion

Ask:

> Post a suggestion that press-1's ideal cycle time should be checked, with the performance figure as evidence.

The agent calls `foames_post_suggestion`. This is one of only three tools that write anything, and what it writes is a proposal, not a change.

## 5. Decide on it yourself

1. Open the **Floor View**. The new suggestion is listed under the tiles, with the agent's name.
2. Open it. Read the **Evidence**, which holds the numbers the agent relied on.
3. Set **Status** to **Accepted** and write in **Resolution** what you will do, or **Dismissed** with the reason.

The machine, its settings and its OEE are unchanged. Nothing changes until a person acts.

## What you learned

- FoaMES is an MCP server. Agents use the same public API as the desk, as a normal user.
- An agent can read the floor and post suggestions. It cannot change machines, close downtime or write to an ERP.
- People own the decision: the suggestion waits for a status and a resolution.

## Other clients

For Claude Desktop, Cursor and other clients that start a local process, use the stdio bridge, which is one file of standard-library Python you can copy anywhere:

```json
{
  "mcpServers": {
    "foames": {
      "command": "python3",
      "args": ["/path/to/foames/foames/foames_mcp/bridge.py"],
      "env": {
        "FOAMES_URL": "http://foames.localhost:8000",
        "FOAMES_API_KEY": "<agent api key>",
        "FOAMES_API_SECRET": "<agent api secret>"
      }
    }
  }
}
```

The full list of tools is on [MCP tools](Reference-MCP-tools). Why agents only suggest is explained in [Agents suggest, people act](Explanation-Agents-suggest-people-act).
