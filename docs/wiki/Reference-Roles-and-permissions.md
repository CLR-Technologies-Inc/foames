Installing FoaMES creates six roles. System Manager keeps full access to everything, including FoaMES Settings, adapter settings and External References. Each role also opens its own workspace ([Reports and workspaces](Reference-Reports-and-workspaces)).

| Role | Meant for | May do |
| --- | --- | --- |
| FoaMES Engineer | Process and manufacturing engineers | Full access to Machines, Downtime Reasons, Machine Data Settings, OEE Periods and Agent Suggestions; post machine events; sees the Supervisor, Maintenance, Quality and Integration workspaces |
| FoaMES Operator | Shop-floor users | Create and edit Machines, Downtime Records and Agent Suggestions; create Machine Events (manual entry or unsigned test posts); read Downtime Reasons and OEE Periods; raise and close andon calls; acknowledge SOPs |
| FoaMES Quality | Quality staff | Edit (not create) Machines, Downtime Records and Agent Suggestions; read Machine Events, Downtime Reasons and OEE Periods; write SOPs and record training |
| FoaMES Supervisor | Shift and production supervisors | Read and report on everything in the MES module; edit Machines; create and edit Downtime Records, Downtime Reasons, Agent Suggestions and Process Event Logs; edit andon call types |
| FoaMES Maintenance | Maintenance technicians and planners | Read Machines, Machine Events and OEE Periods; create and edit Downtime Records, Downtime Reasons and Agent Suggestions; create Machine Events; create, edit and delete Maintenance Plans and Work Orders |
| FoaMES Integration | Service users for other systems | Create the inbound-message and outbox records an adapter receives from another system. Give it to the user whose API key that system uses |

Operators and Quality staff can change a Machine's Source ID, OEE parameters and Disabled flag. To reserve that to engineers, tighten Machine permissions in Role Permissions Manager.

## By task

| Task | Roles |
| --- | --- |
| Watch the Floor View | Operator, Engineer, Quality, Supervisor |
| Assign a downtime reason, add a manual Downtime Record | Operator, Engineer, Quality, Supervisor, Maintenance |
| Create Machines and Downtime Reasons, change Machine Data Settings | Engineer |
| Accept, dismiss or complete a suggestion | Operator, Engineer, Quality, Supervisor, Maintenance |
| Post machine events by hand | Operator, Engineer, Maintenance |
| Maintenance plans and work orders | Maintenance, Engineer (Supervisor creates and edits work orders) |
| Write and revise SOPs | Engineer, Quality |
| Sign an SOP | Anyone holding a sign-off role named on it, except its author |
| Read External References | System Manager by default |

## Agents

An MCP agent runs as the user whose API key it holds, with that user's permissions. Give it the narrowest role its job needs; FoaMES Operator is enough to read the floor and post suggestions. See [MCP tools](Reference-MCP-tools).
