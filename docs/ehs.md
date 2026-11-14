# Environmental health and safety

The FoaMES EHS module keeps safety records next to the machines and data they are about: incidents and near misses, permits to work with their lockout points, hazard assessments, and exposure monitoring. Because they share a site with machine states and downtime, FoaMES can see things a stand-alone safety system cannot, such as a machine that reports Running while it is locked out. It follows the rule every FoaMES module keeps: it raises **Agent Suggestions** (category **Safety**) for people to act on and never stops, starts or isolates anything itself.

Everything here is established public practice: US OSHA 29 CFR 1904 for recordkeeping, 1910.147 for lockout/tagout, 1910.95 and 1910.1000 for noise and air contaminants, BLS incidence rates per 200,000 hours, the 5 x 5 risk matrix and the NIOSH hierarchy of controls (the order ISO 45001 clause 8.1.2 also uses). FoaMES is a recordkeeping and early-warning tool. It does not replace your competent person, your legal reporting duties or your local regulations. Check the limits and rules that apply where you operate.

The module adds a **FoaMES Safety** role and a **FoaMES Safety** workspace (open incidents, active permits, high residual risks, exposures above the action level, the rates report, open safety suggestions).

## Safety Incident

One record per event: **Near Miss**, **Unsafe Condition**, **Unsafe Act**, **First Aid**, **Injury or Illness**, **Property Damage** or **Environmental Release**. Operators can create incidents (but not edit them afterwards), so reporting a near miss takes no special rights. From a floor tablet, an andon station or an agent, the whitelisted method `foames.foames_ehs.doctype.safety_incident.safety_incident.report_near_miss` takes a title, a description and optionally a machine, a location and a potential severity.

- **Potential Severity (1-5)** is how bad the event could reasonably have been. A near miss with a potential of 4 or 5 is treated as a serious event, because serious-injury precursors deserve the same attention as injuries.
- **Recordability is calculated, never typed in.** For a work-related Injury or Illness, FoaMES applies the general recording criteria of 29 CFR 1904.7: death, days away, restricted work or transfer, medical treatment beyond first aid, loss of consciousness, or a significant diagnosis. It stores **Recordable**, the most serious **Outcome** (the Form 300 columns G to J) and the day counts capped at 180. A First Aid record is never recordable. If the case needed more than first aid, change its type to Injury or Illness.
- **Privacy Case** keeps the name off the log, as 1904.29(b)(7) asks.
- **Environmental Release** records the substance, quantity, where it went, and whether and when an authority was told.
- **Downtime Record** links the stop the incident caused, so OEE and safety tell the same story. **Hazard Assessment** links the hazard the incident exposed, so its risk can be reviewed.
- **Actions** are corrective and preventive actions, each with a control level on the hierarchy, an owner, a due date and a status.

Saving a recordable case, a release reportable to an authority, or anything with a potential severity of 4 or 5 raises a **Critical** suggestion at once. To close an incident it needs a **Root Cause**, and every action must be Done or Cancelled. Closing it resolves the incident's open safety suggestions. A new report that already has open actions moves to **Actions Open** on its own.

## Safety Permit (permit to work)

Permit types are **Lockout Tagout**, **Hot Work**, **Confined Space**, **Working at Height**, **Electrical**, **Line Break**, **Excavation** and **General**. A permit is **Draft** while it is prepared, **Active** while the work may go on, and **Suspended** when the work stops for a while. It ends **Closed**, **Cancelled** or **Expired**. An ended permit is never reopened: the next piece of work gets a new one.

Rules for an **Active** permit:

- Start and end set, the end after the start, and valid for at most 12 hours. A longer job gets a new permit for the next shift.
- An issuer and a performer, who must be different people.
- Lockout Tagout, Confined Space, Line Break and Electrical permits need at least one **Isolation Point**. Every point still in place needs a lock or tag ID and **Zero Energy Verified** ticked. FoaMES fills in who locked and who verified.

A permit can only be **Closed** when every lock has a **Lock Removed On** time. It can link a **Maintenance Work Order** and a **Hazard Assessment**.

**Running under lockout.** When a machine with an active or suspended permit that still holds locks reports **Running**, FoaMES raises a **Critical** suggestion right away, from the machine-state hook. The same rule runs on the floor snapshot with the other suggestion rules. Either the isolation is not effective, the state signal is wrong, or the permit should have been closed. Closing the permit resolves the suggestion.

## Hazard Assessment

A hazard on a machine, a location or a task (a job hazard analysis). **Likelihood** and **Severity** are rated from 1 to 5, and their product is the risk score: 1 to 4 is Low, 5 to 9 Medium, 10 to 16 High, and 20 to 25 Very High. **Controls** each have a level on the hierarchy (Elimination, Substitution, Engineering, Administrative, PPE) and an **In Place** box. **Residual Likelihood** and **Residual Severity** rate the risk with the controls in place. A residual risk higher than the original is refused. **Strongest Control** shows the most effective control in place. The assessment is due for review a set number of days after **Reviewed On** (365 by default).

## Exposure Record

Industrial hygiene monitoring for one agent and one person or similar exposure group.

- **Concentration**: the time-weighted average of the samples over the shift (480 minutes by default). Unsampled time counts as zero, as 1910.1000(d) does.
- **Noise**: the dose on the OSHA 5 dB exchange rate. The reference duration is T = 8 / 2^((L - 90) / 5) hours, the dose is D = 100 x sum(C / T), and the result is the equivalent 8-hour TWA, 16.61 x log10(D / 100) + 90 dBA. Levels below 80 dBA count as zero. The limit defaults to 90 dBA and the action level to 85 dBA.

Enter the **Exposure Limit** and **Action Level** that apply, and note where they come from (PEL, OEL, TLV). **Status** is Below Action Level, At or Above Action Level, or Above Limit. A result at or above the action level raises a suggestion: Warning at the action level, Critical above the limit.

## The hourly check

`foames.foames_ehs.tasks.check_ehs` runs hourly. It:

- sets permits past their end to **Expired** and raises a suggestion for each one. The suggestion is Critical if locks are still applied, otherwise Warning.
- raises a suggestion for each open incident with no root cause more than 7 days after the event. It is Critical for recordable cases.
- raises a suggestion for each open corrective action past its due date. It becomes Critical after 30 days.
- raises a suggestion for each active hazard assessment past its review date, and for each High or Very High residual risk that relies only on administrative controls or PPE, or has no controls in place.

Each condition raises one suggestion, keyed so that it is never repeated every hour.

## Safety Incident Rates report

The report shows incidents by month and type, with recordable, DART and lost-time cases and days away and restricted. Enter **Hours Worked** for the period to get the TRIR, DART rate, lost-time rate and severity rate, all per 200,000 hours. FoaMES does not know payroll hours. The report also shows leading events (near misses, unsafe conditions and acts) and their ratio to recordable cases, which needs no hours.

## What it does not do

- It does not file OSHA forms or send reports to authorities. The records hold what those forms need.
- It does not hold medical records beyond what the log needs.
- It does not control equipment. Isolation is done and verified by people, and FoaMES records it.
