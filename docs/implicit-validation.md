# Implicit validation

Implicit validation checks a configuration or feature-set revision against requirement, metrology and statistical criteria, before and after a change, and stores the result as hashed, reproducible evidence that other gates can check by ID. It extends the [Validation module](validation.md) and reuses its rules: the capability and control checks are the same ones a Validation Execution uses.

**What it is not.** A passing run is engineering evidence that a change behaved as expected. It is not a regulatory qualification, an electronic signature, a production release or an authorisation to write. Formal IQ, OQ, PQ, PPQ and CPV, with their independent approval, stay in Validation Protocol and Validation Execution. Every write to another system still passes the [read-only gate](read-only-mode.md). Statistical checks alone do not establish regulatory compliance.

## Outcomes

| Outcome | Meaning |
| --- | --- |
| Pass | The evidence is there and meets the criterion |
| Fail | The evidence is there and does not meet it |
| Indeterminate | The evidence is missing, too thin or not trustworthy: too few readings, a reading with no time, a time after the evaluation, no calibration record, an undeclared unit, a configuration value that is not set. Never Pass |
| Manual Review | A person has to inspect or decide (a `manual` check, a marginal gauge R&R) |

A run **fails closed**: its outcome is the worst of its blocking checks (Fail, then Indeterminate, then Manual Review, else Pass). A non-blocking check is reported as a warning and never decides the run. A `Critical` check is always blocking, whatever its definition says.

## A definition

```json
{
  "schema": "foames.implicit-validation/1.0",
  "name": "Bore change on line 2",
  "version": "3",
  "checks": [
    {"key": "rpm-limit", "kind": "requirement", "criticality": "Critical",
     "assert": {"path": "spindle.max_rpm", "op": "le", "value": 6000},
     "source": "REQ-114", "owner": "process engineering"},
    {"key": "bore-gauge", "kind": "metrology", "measurement": "bore", "unit": "mm",
     "max_interval_seconds": 120, "tolerance": 0.1, "uncertainty": 0.01, "grr_percent": 8},
    {"key": "bore-cpk", "kind": "statistical", "measurement": "bore", "unit": "mm",
     "check_type": "Capability", "lower_limit": 9.9, "upper_limit": 10.1, "min_points": 25},
    {"key": "bore-control", "kind": "statistical", "measurement": "bore",
     "check_type": "Statistical Control", "rule_set": "Nelson"},
    {"key": "fixture", "kind": "manual", "description": "Inspect the new fixture", "blocking": false}
  ]
}
```

Every check has a unique `key`, a `kind`, `blocking` (default true) and `criticality` (Low, Medium, High, Critical); `owner`, `source` and `requirement` are carried into the evidence.

- **requirement**: an assertion on the configuration under test. `op` is one of `eq`, `ne`, `lt`, `le`, `gt`, `ge`, `in`, `not_in`, `present`, `absent`; `path` is dotted (`gateway.hosts.0`). A path that is not there is Indeterminate (except for `absent`); a non-number against a bound is Fail. The value found is recorded as evidence, except for `absent` and for a check marked `"sensitive": true`, so a secret left in a configuration is never copied into the run. A sensitive check may only use `present` or `absent`: a definition is stored with every run, so it must never hold a secret to compare against.
- **metrology**: whether a measurement can be trusted. Sub-checks: unit (declared and compatible with the check's unit; a different dimension fails), calibration (instrument id and due date; lapsed fails, missing is Indeterminate), traceability (a certificate reference; turn off with `require_traceability: false`), time (every reading stamped, in order, none after the evaluation, no gap above `max_interval_seconds`), freshness (`max_age_seconds`), uncertainty (test uncertainty ratio `tolerance / uncertainty`, at least `min_tur`, default 4), bias (`reference_value` and `bias_limit`, from readings of a reference standard) and gauge R&R (`grr_percent` from an MSA study: below 10 acceptable, 10 to 30 Manual Review, above 30 Fail). Each runs only when its inputs are named.
- **statistical**: `check_type` Numeric Range, Capability (Cp, Cpk, Pp, Ppk against `min_index`, default 1.33) or Statistical Control (run rules on an I-MR chart), with `min_points` (default 25), plus an optional drift check (`baseline_mean`, `max_shift`). Values are converted to the check's `unit` first. Control and capability are separate checks: a process can be in control and not capable, or capable and not in control.
- **manual**: always Manual Review.

## Data

A run reads one of:

- **Site data**: a `machine` and a `since`/`until` window. FoaMES reads that machine's Measurement events itself, with the caller's permissions. Units, instruments and uncertainty, which the events do not carry, come in `measurements` and are recorded as declared. Production runs must use site data: a supplied dataset, or no data at all, is refused. A `since` or `until` with an offset is converted to site time before the read.
- **A supplied dataset**: `{"id", "measurements": {name: {"unit", "instrument", "uncertainty", "points": [{"t", "v"}]}}}`, for sandbox work and frozen datasets. The run records the source as Supplied, and a gate can refuse it.

Times are compared in UTC: a time with an offset is converted, a time without one is taken as UTC, and site data is converted from the system time zone. A site window with more than 20,000 readings is refused rather than judged on part of its data. Non-finite numbers (NaN, Infinity) are refused.

## Evidence

`run_implicit_validation` (POST, `foames.foames_validation.implicit_api`) evaluates and records an **Implicit Validation Run**: the definition, the dataset reference and source, the configuration revision, the environment (Sandbox, Integration, Production Candidate, Production), the trigger (On Demand, Sandbox Change, Configuration Proposal, Pre-production Promotion, Post-change Monitoring, Scheduled CPV), the evaluation time, the requester, every check's result, and two SHA-256 hashes: the **input hash** over everything that went in, and the **result hash** over the bundle. The same inputs at the same evaluation time reproduce both hashes.

A run is created only by evaluating; nobody can create one on the desk, change one after it is stored, or delete one. With `dry_run` (or `dry_run_implicit_validation`), the bundle is returned and nothing is stored.

Starting a run needs the FoaMES Engineer, Quality, Supervisor or Integration role (or System Manager), and read on the machine it names. Reading runs follows the DocType's permissions and the reader's User Permissions on Machine ([authorization.md](authorization.md)). There is no approval on a run, so an agent has nothing to self-approve: the server computes the outcome.

## Gates

A feature that needs passing evidence (Sandbox Mode promotion, agent configuration writes) calls

```python
from foames.foames_validation.implicit_api import require_passed

require_passed(run_id, configuration_revision, environments=("Production Candidate",), site_data=True)
```

It loads the run, recomputes the bundle's hash and compares it with the stored one and the stored outcome, input hash and revision, and raises `ImplicitValidationError` unless the run verifies, passed, is for that revision, and (when asked) ran in one of the environments on site data. A gate never accepts a `passed=true` from a caller. `foames_implicit_validation_completed` hooks receive each stored run.

## For agents

The MCP tools `foames_get_implicit_validation` (a run, whether it still verifies, its checks) and `foames_dry_run_implicit_validation` (evaluate without storing) are read-only. Recording a run is an API call made by a person or an integration with one of the roles above.

## Engineering evidence and formal validation

| | Implicit validation | Validation Protocol and Execution |
| --- | --- | --- |
| Purpose | Show that a change behaves as expected, continuously or on demand | Formal IQ, OQ, PQ, PPQ, CPV |
| Approval | None; the server computes the outcome | Approval by someone other than the executor |
| Regulatory standing | Engineering evidence that feeds a change record | The qualification record |
| Manual items | Reported as Manual Review for a person to take into a formal execution | Recorded and approved in the execution |
