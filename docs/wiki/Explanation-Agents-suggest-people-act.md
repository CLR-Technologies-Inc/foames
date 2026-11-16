FoaMES is an *agentic* MES: built-in rules, run-rule checks, maintenance meters and external AI agents all watch the floor and find things worth acting on. Yet none of them acts. Every finding ends as an **Agent Suggestion**, a record with a title, a category, a severity, the evidence it rests on, and a status that only a person changes.

## Why not let the agent act?

The shop floor is where software mistakes become scrap, injuries or a lost shift. An agent that stops a machine, writes to a PLC, closes a downtime or posts to the ERP on its own is an agent whose mistakes are physical and immediate. Even a good model misreads context: a machine "running without counting" may be in a planned trial; a "dominant downtime reason" may be a mis-tagged button.

So FoaMES draws a hard line. Agents may read everything their user may read, and they may propose. People decide. In the code this shows up as rules you can check:

- The built-in rules, the SPC check, the maintenance check, andon escalation and SOP review all raise suggestions and nothing else.
- Of the 24 MCP tools, only three write: two create suggestions, and one records which job a machine is on. None writes to an ERP or to a machine.
- An agent runs as an ordinary Frappe user with an API key, under that user's permissions. There is no superuser path for agents.

## What makes a suggestion useful

- **Evidence.** The numbers the finding rests on are stored as JSON on the record, so the reader can check the reasoning instead of trusting it.
- **No repeats.** A rule key identifies the finding. While it is open, the same finding is not raised again; if it recurs after being resolved, the old record is reopened with the new evidence.
- **A decision trail.** Accepted, Done or Dismissed, with a resolution and who resolved it and when. A dismissed finding records why, so the next person does not reopen the question.
- **One place to look.** Suggestions from rules, from SPC, from maintenance and from any external agent sit in the same list and on the Floor View, and the **Suggestion Status** report shows how quickly they are dealt with.

## What this means for automation

This does not rule out automation; it puts it where it belongs. Writes to other systems are explicit, configured postings that a person switched on (for example, rolling machine counts up to Job Cards), sent through an outbox you can pause and inspect. What an agent adds is judgement and attention, presented for a person to accept.
