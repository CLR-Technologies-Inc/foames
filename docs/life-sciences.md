# Life sciences: NPI, MSAT tech transfer and process development

This module is for biopharma and medical device plants. It covers the work that sits between development and routine production, done in most companies by two groups:

- **New product introduction (NPI):** taking a new drug, biologic, device or combination product from concept through design, development and verification into commercial manufacturing, as a stage-gate program.
- **Manufacturing science and technology (MSAT):** the process engineering that transfers a process to a new site or scale, keeps it in a state of control, and supports GMP production on the floor.

It adds four things, all in the `FoaMES Life Sciences` module (`foames/foames_lifesci`):

| Record | What it holds |
| --- | --- |
| **NPI Program** | Six stages, a gate at the end of each, and the deliverables each gate needs. Gate decisions are recorded by a reviewer, not edited. |
| **Product Requirements Document (PRD)** | User needs and design inputs (devices), or QTPP elements and CQAs (drugs and biologics), with their trace to design outputs, verification and validation. |
| **Tech Transfer Package** and **Comparability Assessment** | The process as the receiving site needs it: CPPs with normal operating and proven acceptable ranges, CQAs with acceptance limits, the transfer deliverables, and a statistical comparability check per CQA. |
| **PD Simulation Study** | Process development (PD) simulation: a designed experiment, response-surface models, a Monte Carlo what-if, a design-space map, and a scale-up calculator. |

"PRD" is read here as the **product requirements document**. If your organisation uses the letters for process research and development, that work lives in the PD Simulation Study and the Tech Transfer Package.

The module records and calculates; people decide. No gate opens, no package is approved and no process setting changes without a person doing it, in line with the invariant that agents suggest and people act ([AGENTS.md](../AGENTS.md)). The inputs to the simulations are the ranges and results people enter. Approvals are an audit trail with separation of duties, not a validated 21 CFR Part 11 electronic signature; a site that needs one adds re-authentication and its own computer system validation on top.

## Regulatory framing

The structure follows the published guidance below. FoaMES does not claim compliance with any of it: a site's quality system, procedures and validation decide that. Use the references to map the records to your own procedures.

| Area | Guidance the records are shaped by |
| --- | --- |
| Device design controls | ISO 13485:2016 section 7.3; 21 CFR 820 (the Quality Management System Regulation, which incorporates ISO 13485 by reference from 2 February 2026); ISO 14971:2019 risk management; IEC 62366-1 usability |
| Pharmaceutical development | ICH Q8(R2) (QTPP, CQAs, CPPs, design space), ICH Q9(R1) quality risk management, ICH Q10 pharmaceutical quality system, ICH Q12 life-cycle management and established conditions |
| GMP for drugs | 21 CFR 210 and 211; EU GMP Part I and Annex 15 (qualification and validation) |
| Process validation | FDA, Process Validation: General Principles and Practices (2011): stage 1 process design, stage 2 qualification (PPQ), stage 3 continued process verification |
| Tech transfer | WHO TRS 1044 Annex 4 (2022), Good practices on technology transfer in pharmaceutical manufacturing; ISPE Good Practice Guide: Technology Transfer (3rd ed.) |
| Comparability | ICH Q5E comparability of biotechnological products; FDA's statistical approaches for comparative analytical assessment (equivalence testing and the quality range approach) |
| Analytical methods | ICH Q2(R2) validation and ICH Q14 development; method transfer as a transfer deliverable |

## NPI programs

Create an NPI Program with a title, the product, its type and a program lead. The product type picks the deliverable template:

- **Medical Device, In Vitro Diagnostic:** design controls: intended use and user needs, the design and development plan, hazard analysis, the PRD (design inputs), design reviews, design outputs, DFM, design and process FMEA, design verification, design validation and usability, the device master record (medical device file), equipment IQ/OQ/PQ, process validation, the design history file, post-market surveillance.
- **Drug Substance, Drug Product, Biologic, Cell and Gene Therapy:** QbD and transfer: the QTPP, CQAs, quality risk assessment, process characterization by DoE, scale-down model qualification, the control strategy, analytical method validation, stability, engineering batches, the tech transfer package, method transfer, PPQ, comparability, batch records, CPV and established conditions.
- **Combination Product:** both lists, in stage order, without duplicates.

The template is a starting point. Add rows, remove them, or mark an item Not Applicable with a note, so the program matches your procedure. Each deliverable can point at the record that is the evidence (a Validation Protocol, a Standard Operating Procedure, a PFMEA, a PRD or any other DocType) through Document Type and Document.

The stages are Concept, Feasibility, Development, Verification & Validation, Transfer and Launch. Set each gate's target date in the Gates table. The current stage and the program status are read-only; they move only through **Record Gate Decision** on the form (or `record_gate_decision` on the document), which:

- is recorded by FoaMES Quality or FoaMES Supervisor, and never by the program lead;
- refuses Go and Conditional Go while a required deliverable of the stage is neither Complete nor Not Applicable, listing what is open;
- needs written conditions and a due date for a Conditional Go, and a rationale for Recycle, Hold and Kill.

| Decision | Effect |
| --- | --- |
| Go | The program moves to the next stage; after the Launch gate it is Launched |
| Conditional Go | As Go; the conditions stay open until someone closes them with **Close Conditions** |
| Recycle | The program stays in the stage to redo work; the gate can be decided again |
| Hold | The program is On Hold in the stage; a later decision on the same gate resumes it |
| Kill | The program is Cancelled |

Every decision keeps who made it and when, and the version history keeps earlier decisions on a recycled gate. A daily job (`foames.foames_lifesci.tasks.check_npi_gates`) raises an Agent Suggestion when the current gate is overdue, or due within 14 days with required deliverables still open, and when the conditions of a Conditional Go are past their due date.

## Product requirements and the trace matrix

A Product Requirements Document lists requirements with an ID (for example `UN-001`, `DI-004`, `CQA-2`), a level and, for a refining requirement, the ID it refines:

| Level | Refines | Typical verification |
| --- | --- | --- |
| User Need, QTPP Element | (top level) | Design validation for a user need |
| Design Input | a user need, QTPP element, regulatory or business requirement | Test, inspection, analysis or demonstration against the acceptance criteria |
| CQA | a QTPP element (or another top-level requirement) | The analytical method and its acceptance criteria |
| Regulatory, Business | (top level) | As stated |

Saving refuses duplicate IDs, a parent that is not in the document and a refinement at the wrong level. Submitting is approval and must be done by someone other than the person who prepared the PRD. After approval only the trace columns change as the work is done (design output, verification reference and status, validation reference); a change to a requirement is an amendment, which makes the next revision.

**Trace Matrix** on the form, and `get_requirements_trace`, show every requirement with what it refines, its children, design output, verification and validation, and its gaps: a user need or QTPP element that nothing refines, a user need with no validation, a design input or CQA without acceptance criteria, verification method or design output, and anything not yet verified or failed. The form keeps the percentage verified, the percentage refined and the count of requirements with gaps current.

## Tech transfer packages

A Tech Transfer Package describes one process for one transfer (site to site, scale-up or scale-down, development to commercial, to or from a contract manufacturer, line transfer):

- **Process parameters**, each with its step, unit, criticality (CPP, KPP or non-critical), set point, normal operating range (NOR) and proven acceptable range (PAR), and, when it depends on scale, its scale rule. Set Ranges to say which sides are set; a CPP or KPP needs them. For a rule that depends on volume alone (scale independent, linear with volume, constant vvm or residence time) the receiving set point is computed from the scale ratio; the geometry-dependent rules (constant P/V, tip speed, kLa, gas velocity) are worked out with the scale-up calculator below.
- **Quality attributes**, each with its unit, criticality (CQA or not), acceptance limits, the analytical method, the PRD requirement it carries and the comparability approach (equivalence by TOST with a margin, quality range with k and coverage, min-max, or descriptive).
- **Deliverables**, filled with the usual transfer list (plan and protocol, gap analysis of equipment, facility, materials and utilities, risk assessment, analytical method transfer, training, engineering batch, PPQ, comparability, transfer report) and tracked after approval.

A draft shows what still blocks approval each time it is saved. Submitting is approval by FoaMES Quality, and is refused while a NOR lies outside its PAR, a set point outside its NOR, a CPP has no ranges, a scale-dependent parameter has no rule, a CQA has no limits, method or approach, an equivalence test has no margin, a parameter or attribute is listed twice, or a CQA names a requirement the linked PRD does not have. The approver must not be the person who prepared the package.

## Comparability

A Comparability Assessment judges one attribute of an approved package from batch results of the sending and the receiving site. The approach and its settings are copied from the package, so the rule is fixed before the data comes in.

| Approach | Comparable when |
| --- | --- |
| Equivalence (TOST) | The 90 % confidence interval of the difference in means (receiving minus sending, Welch with Satterthwaite degrees of freedom) lies within plus or minus the margin; two one-sided tests at alpha 0.05 |
| Quality Range | At least the required share (90 % by default) of receiving batches lie within the sending mean plus or minus k standard deviations (k = 3 by default) |
| Min-Max | Every receiving batch lies within the range the sending site has shown |
| Descriptive | No verdict; summaries for the reviewer |

Whatever the approach, a receiving batch outside the attribute's acceptance limits makes the outcome Not Comparable. Too few results give Insufficient Data (TOST needs at least two batches per site). Submitting records the review: it needs an approved package and a decisive outcome, and is done by someone other than the person who entered the results.

## PD simulation

A PD Simulation Study holds one designed experiment and what is learned from it.

1. **Factors and responses.** Up to six factors with the studied low and high, and for the what-if how each varies in operation (fixed, normal with a standard deviation, uniform or triangular around the nominal). Up to four responses with their limits; tick CQA for those that are. Factors map to columns x1 to x6 of the runs and responses to y1 to y4, in row order.
2. **Generate Design.** Full factorial (2 or more levels), two-level fractional factorial (the standard minimum-aberration generators for 3 to 6 factors), or central composite, face-centred or rotatable, with centre points, replicates and a seeded random run order. The summary says the run count, the resolution of a fraction, and warns when rotatable axial points lie outside the low-high range.
3. **Run the experiments** and enter each result in y1 to y4. Edit x1 to x6 when a run's actual settings differed from the plan, or tick Exclude (and say why in the note) to leave a run out.
4. **Fit Models.** Least squares, per response, of a linear, linear with interactions, or full quadratic model in coded units, with coefficients, standard errors and p-values, R squared, adjusted R squared and RMSE. A design that cannot estimate the model (too few runs, aliased terms) is reported per response.
5. **Run What-If.** A seeded Monte Carlo around the nominal settings through the fitted models, with the residual error added: for each response the mean, the 5th, 50th and 95th percentiles, the probability of meeting its limits and the predicted Ppk, and the probability that every response is within limits at once. The share of draws outside the studied range is reported, since the model extrapolates there.
6. **Design Space.** A grid over any two factors with the others at nominal, marking where every response with limits is predicted within them. This is the ICH Q8 picture of a design space from the models; it is evidence for the people who set the ranges, not an approved design space.

### Scale-up calculator

`foames.foames_lifesci.api.scale_up` (MCP tool `foames_scale_up`) works out a stirred, aerated vessel at a larger volume under geometric similarity. For constant P/V, constant tip speed, constant Reynolds number and constant mixing time it gives the large-scale impeller speed and what the other criteria become (power, P/V, tip speed, Re, vvm, superficial gas velocity and kLa), with ratios to the small scale, so the trade-off is visible. Gas flow follows constant vvm or constant superficial velocity; kLa uses van 't Riet's correlations (Ind. Eng. Chem. Process Des. Dev. 18 (1979) 357) for coalescing or non-coalescing broths. Inputs are in litres, metres, rpm, kg/m3, Pa s and L/min. The results are estimates for engineering judgment, not a validated scale-up; check the regime (Re above 10,000 for a constant power number) and heat removal, since jacket area per volume falls with scale.

## Roles

| Role | NPI Program | PRD, Tech Transfer Package, Comparability | PD Simulation Study |
| --- | --- | --- | --- |
| FoaMES Engineer | create, edit | create, edit drafts | create, edit, run |
| FoaMES Quality | create, edit, gate decisions | create, edit, approve (submit) | create, edit, run |
| FoaMES Supervisor | create, edit, gate decisions | read | read |
| FoaMES Operator, Maintenance | read | read the tech transfer package (Operator) | none |

## API and MCP

| Method (`foames.foames_lifesci.api.*`) | MCP tool | Returns |
| --- | --- | --- |
| `get_npi_status(program, include_closed)` | `foames_get_npi_status` | Stage, status, next gate, required deliverables open, open conditions, decisions |
| `get_requirements_trace(document)` | `foames_get_requirements_trace` | The trace matrix, gaps and coverage |
| `get_tech_transfer_package(package)` | `foames_get_tech_transfer_package` | Parameters, attributes with comparability outcomes, deliverables, open problems |
| `get_pd_study(study)` | `foames_get_pd_study` | Factors, responses, runs, models and the last what-if |
| `scale_up(...)` | `foames_scale_up` | The scale-up table |

All of them read. The actions that change records (gate decisions, generating a design, fitting, the what-if) are document methods called from the form or the REST API by a person with the role.

## Code

The rules and the arithmetic import nothing from Frappe and are tested without a site: `npi.py` (stages, templates, gate rules, findings), `requirements.py` (structure and the trace matrix), `transfer.py` (package checks, comparability), `stats.py` (t distribution, summaries, a linear solver), `doe.py` (designs, fits, what-if, design space) and `scaleup.py`. `python -m unittest foames.foames_lifesci.test_lifesci_logic` runs them; `test_lifesci.py` covers the DocTypes on a site.
