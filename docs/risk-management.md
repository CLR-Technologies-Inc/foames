# Enterprise risk management

The FoaMES Risk module keeps one risk register for the whole site: safety and environmental risks, and also quality, equipment, supply chain, cybersecurity, compliance, financial, people and strategic risks. Each risk is rated before and after its response, compared with the tolerance set for its category, given owners and controls, and watched until it is closed. Like every FoaMES module it raises **Agent Suggestions** for people to act on and changes nothing on its own.

The module does not replace the detailed assessments FoaMES already has or is adding. A hazard assessment (EHS) keeps the detail of one hazard on one machine or task; a PFMEA keeps the failure chains of one process; an SOP or work instruction says how the work is done; a maintenance plan keeps equipment fit. The register sits above them: a risk links to those records instead of copying them, and FoaMES tells you when one of them no longer supports the risk.

## Sources

The method is established public practice:

- **US Office of Management and Budget, Circular A-123**, *Management's Responsibility for Enterprise Risk Management and Internal Control* (2016), which sets out risk appetite, risk tolerance and a portfolio view of risk, and the ERM steps: establish the context, identify risks, analyse and evaluate them, develop responses, respond, monitor, and keep identifying.
- **US Department of Energy, *Enterprise Risk Management, Fiscal Year 2024 Guidance*** (Office of Finance and Accounting, December 2023), a public US government document that applies Circular A-123. FoaMES follows its risk profile structure: the "If ..., then ..." risk statement, one risk category and one objective per risk, impact and likelihood each rated 1 to 5 with their product as the score, inherent and residual ratings, the Accept, Avoid, Reduce, Transfer and Share responses, a named organization for transfers and shares, a proposed response for the residual risk, a risk owner, and tolerance by category. The rules FoaMES enforces (residual never above inherent, residual equal to inherent when nothing is done, a counterparty for a transfer or share) are the checks that guidance lists for its template.
- **US GAO, *Standards for Internal Control in the Federal Government*** (the Green Book), for the definition of risk tolerance as the acceptable level of variation in performance.
- **The hierarchy of controls** as published by the US National Institute for Occupational Safety and Health (NIOSH), and used in ISO 45001 clause 8.1.2: elimination, substitution, engineering controls, administrative controls, personal protective equipment. Work practice controls are listed on their own because many standards name them separately ("engineering and work practice controls").

Nothing here is specific to a government agency. The DOE categories and strategic objectives are not reproduced; FoaMES ships general manufacturing categories that each site edits. FoaMES is a recordkeeping and early-warning tool: it does not replace the judgement of your risk owners, your competent persons or your legal duties.

## Setting up

**Risk Settings** (FoaMES Risk workspace, Setup card):

| Field | Default | Meaning |
| --- | --- | --- |
| Risk Appetite Statement | empty | How much risk the organization is willing to take on in pursuit of its objectives. Shown on every risk |
| Default Tolerance | Moderate | The highest residual rating accepted without management's acceptance, for a category with no tolerance of its own |
| Rating bands | Very Low up to 3, Low up to 6, Moderate up to 12, High up to 16, Very High above | How a 1 to 25 score maps to a rating |
| Review Every | 365 days | For risks rated Moderate or lower |
| High Risk Review Every | 90 days | For risks with a High or Very High residual rating |
| Verify Controls Every | 180 days | For controls in place that set no interval of their own |

**Risk Category** holds the categories and each one's **Risk Tolerance**. **Hazard Category** marks the categories whose risks are physical hazards, where the hierarchy of controls applies strictly (see below). FoaMES installs sixteen starting categories: Safety and Health, Environmental, Product Quality, Process and Equipment, Supply Chain, Cybersecurity and OT, IT Infrastructure, Regulatory Compliance, Financial, Fraud, Human Capital, Physical Infrastructure, Continuity of Operations, Reputational, Strategic and Other. Their tolerances are examples; set your own.

**Risk Template** is a starting point for a common risk: a statement, typical inherent ratings and typical controls on the hierarchy. FoaMES installs thirteen, among them chemical exposure in a process area, contact with moving machine parts, release of a stored liquid, loss of a critical utility, critical equipment failure, a single source for a critical material, ransomware on the plant network, an unapproved write from FoaMES into another system, product contamination, loss of key knowledge, a lapsed permit, unreliable records and change without risk review. Edit, disable or add your own. Installing again never overwrites a category or template that exists.

Roles: FoaMES Supervisors manage settings, categories and the register and are the ones who accept residual risk. FoaMES Engineers, Quality and Maintenance create and edit risks and templates. FoaMES Operators can read the register.

## An Enterprise Risk

| Section | Fields |
| --- | --- |
| Header | Risk Name, Category, Objective (Strategic, Operations, Reporting, Compliance), Fraud Impact, Risk Owner, Status, Identified On, Machine, Location or Process Area |
| Risk Statement | "If <event>, then <all the impacts>", and the causes and context. A risk is a potential event; something that already happened is an incident |
| Inherent Risk | Impact and Likelihood, 1 to 5, before any action; the score and rating are calculated |
| Current Response | Accept, Avoid, Reduce, Transfer or Share; who the risk is transferred to or shared with; the current actions |
| Controls | One row per control (below); the strongest control in place is shown |
| Residual Risk | Impact and Likelihood after the current response; empty means no reduction |
| Tolerance and Acceptance | The category's tolerance, whether the residual rating is within it, the risk appetite, and management's acceptance |
| Proposed Response | A further response, the actions, a target date and the target impact and likelihood |
| Monitoring | Key risk indicators, the review interval, the next review and the review history |
| Linked Records | Records the risk draws on, with their relation |

Impact runs from 1 Very Low (insignificant, no effect on objectives) to 5 Very High (will likely prevent the objective). Likelihood uses the guidance's bands: 1 under 5%, 2 from 5% to 25%, 3 from 26% to 49%, 4 from 50% to 74%, 5 at 75% or more.

FoaMES refuses a risk whose residual impact or likelihood is higher than the inherent one, an Accept response with a residual rating below the inherent one, a Reduce response that lowers the rating without at least one control in place that has not failed, a target above the residual rating, and a Transfer or Share without the organization that takes the risk on. A statement not written as "If ..., then ..." gets a warning only.

Statuses run **Identified**, **Assessed**, **Treating**, **Monitoring** and **Closed**. A risk above its tolerance can be in Monitoring only once management has accepted its residual risk. Closing needs a note saying why.

### Controls and the hierarchy

Each control row has:

- **Level**: Elimination, Substitution, Engineering Controls, Administrative Controls, Work Practices, PPE, or Other Management Control for risks that are not physical hazards (a second supplier, a contract, insurance, segregation of duties, a tested backup). Elimination is the most effective, PPE the least; Other Management Control ranks with administrative controls.
- **Function**: Preventive, Detective, Corrective or Contingency.
- **Status**: Planned, In Place or Retired, with the owner and the date it was put in place.
- **Verification**: the method (inspection, test, observation, audit, measurement, document review), the interval, the last verification and its result (Pass or Fail), and the **Effectiveness** found at the last review (Effective, Partially Effective, Ineffective). FoaMES fills in who verified, and the next verification date.
- **Evidence**: the record that carries out or proves the control. A work practice points at its SOP or work instruction, an engineering control at the maintenance plan that keeps it working or at its hazard assessment, a read-only connector at its Connector Write Policy.

A control that failed verification or was found ineffective no longer counts as in place, so it cannot hold a residual rating down and does not count as the strongest control.

### Acceptance and review

**Accept Residual Risk** (FoaMES Supervisor or System Manager) records who accepted the residual risk, when, why, and at which score. A later change to the residual score clears the acceptance. **Record Review** adds a row to the review history with the score and rating at the time and restarts the review interval. Neither can be done by editing the fields directly.

### Linked records

A link has a relation: **Source** (the detailed assessment this risk summarises), **Realized Event** (an incident in which the risk happened) or **Related**. A risk can link to hazard assessments, safety incidents, permits and exposure records (EHS), PFMEAs, work instructions, SOPs, maintenance plans and work orders, machines, downtime records, andon calls, suggestions, connector write policies and pending writes (read-only mode), and other risks, as far as those modules are installed on the site.

On a hazard assessment or a PFMEA, **Create > Enterprise Risk** makes a risk that summarises it and links back to it as its Source. The controls stay on the assessment. FoaMES reads the source's current rating (a hazard assessment's residual level; for a PFMEA, High when any failure chain has action priority High) and raises a suggestion when it is above the risk's residual rating.

## The daily check

`foames.foames_risk.tasks.check_risks` runs daily. For each open risk it raises a suggestion (category Other, pointing at the risk) when:

- the residual rating is above tolerance and not accepted (Critical for Very High);
- the review is overdue;
- a High or Very High risk in a hazard category relies only on administrative controls, work practices or PPE;
- a control in place is overdue for verification, failed it, or was found ineffective;
- a control's evidence no longer holds: the SOP is not Effective, the work instruction not Released, the hazard assessment not Active, the PFMEA not Released, the maintenance plan is Overdue or disabled, the connector write policy no longer keeps its connector read-only, or the record is gone;
- a key risk indicator is above (or below) its threshold;
- the proposed response's target date has passed and the residual score is still above the target;
- a Source now rates higher than the risk.

Each condition is raised once and not repeated until its suggestion is resolved.

## Reports

**Risk Register** lists the risks with the columns of a risk profile: name, category, objective, statement, inherent impact, likelihood, score and rating, response and counterparty, strongest control, residual impact, likelihood, score and rating, tolerance, acceptance, proposed response and target, owner, status, next review, fraud impact. Filters for category, status, rating, objective, owner, machine, above tolerance only and closed risks. It exports to Excel like every Frappe report.

**Risk Heat Map** counts open risks on the 5 x 5 grid, impact down the side and likelihood across, coloured by rating. Switch the basis between Residual and Inherent to see what the controls are doing.

## Extending it

Another app adds to the register through hooks in its own `hooks.py`:

| Hook | Shape | Use it to |
| --- | --- | --- |
| `foames_risk_linkable_doctypes` | list of DocType names | Let a risk link to your records |
| `foames_risk_source_readers` | {doctype: dotted path}, `(doctype, name) -> rating or None` | Report your assessment's current rating on the register's scale, so a risk with it as Source is watched |
| `foames_risk_source_values` | {doctype: dotted path}, `(doctype, name) -> dict` | The fields of a new risk made from your record with `create_from_source` |
| `foames_risk_evidence_checks` | list of dotted paths, `(doctype, name) -> problem or None` | Say when your record no longer supports a control, as a short phrase such as "is suspended" |

The scoring, tolerance, hierarchy and findings rules are pure functions in `foames/foames_risk/risk.py`, with no Frappe dependency.

## What it does not do

- It does not file risk profiles or assurance statements with anyone. The register holds what such a profile needs and exports it.
- It does not test internal controls over financial reporting.
- It does not decide a rating, an acceptance or a closure. People do; FoaMES checks the record is consistent and points at what has gone stale.
