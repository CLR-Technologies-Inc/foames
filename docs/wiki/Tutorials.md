Tutorials are lessons. Each one takes you from nothing to a working result, one step at a time, on a site where nothing can go wrong. Do them in order; each builds on the one before.

| # | Tutorial | You will end with | Time |
| --- | --- | --- | --- |
| 1 | [Install FoaMES on a development site](Tutorial-1-Install-FoaMES) | A Frappe bench with FoaMES installed, the scheduler on and your user holding the FoaMES roles | 30 to 60 minutes |
| 2 | [Your first machine and OEE](Tutorial-2-Your-first-machine-and-OEE) | A machine on the Floor View, a downtime with a reason, and an OEE figure you can check by hand | 30 minutes |
| 3 | [Your first agent over MCP](Tutorial-3-Your-first-agent-over-MCP) | An AI agent that reads your floor and raises a suggestion, which you then accept | 20 minutes |
| 4 | [Your first agent benchmark run](Tutorial-4-Your-first-agent-benchmark-run) | A scored, sandboxed test of your own coding agent (any CLI or harness) on a FoaMES task. Needs no site | 30 minutes |

Use a throwaway development site for tutorials 1 to 3. Nothing here needs an ERP, a PLC or a real machine: the tutorials send machine events by hand with `curl`. Tutorial 4 needs no site at all, only Python and Docker, and can be done first if you are here to test agents.

When you have finished, the [How-to guides](How-to-guides) cover real jobs on real sites, and [Explanation](Explanation) covers the ideas behind what you saw.
