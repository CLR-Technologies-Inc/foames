# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Implicit validation on a site: run the checks, store the evidence, and let gates read it by ID.

The rules are pure, in `implicit.py`. This module reads machine data, records an Implicit
Validation Run, and gives other features (Sandbox Mode promotion, agent configuration writes, the
write gate) one way to rely on a result: `require_passed(run, configuration_revision)`. It loads
the run, recomputes the hash of its bundle, and checks the outcome and the revision. A caller can
never hand a gate `passed=True`; it hands the run's ID.

Running the checks is not approving anything: a run has no sign-off, changes no manufacturing
record, and a Pass is engineering evidence only.
"""

from __future__ import annotations

import json
from datetime import timezone
from zoneinfo import ZoneInfo

import frappe
from frappe import _
from frappe.utils import get_datetime, get_system_timezone, now_datetime

from foames.foames_kernel.access import require_read
from foames.foames_validation import implicit as iv

RUN = "Implicit Validation Run"
# Who may start a run. Reading runs follows the DocType's permissions.
INITIATOR_ROLES = (
	"FoaMES Engineer",
	"FoaMES Quality",
	"FoaMES Supervisor",
	"FoaMES Integration",
	"System Manager",
)
# Environments where the data must come from the site, not from the caller.
SITE_DATA_ONLY = ("Production",)
MAX_POINTS = 20000


class ImplicitValidationError(frappe.ValidationError):
	"""A gate asked for a passing implicit validation and the run does not provide one."""


def _json(value, what: str):
	if value in (None, ""):
		return None
	if isinstance(value, (dict, list)):
		return value
	try:
		return json.loads(value)
	except ValueError:
		frappe.throw(_("{0} is not valid JSON").format(what))


def _utc(value):
	"""A site datetime (naive, in the system time zone) as an aware UTC datetime. The evaluator
	compares every time in UTC, so supplied data may carry any offset."""
	value = get_datetime(value)
	if value.tzinfo is None:
		value = value.replace(tzinfo=ZoneInfo(get_system_timezone()))
	return value.astimezone(timezone.utc)


def _site_local(value):
	"""A datetime as naive site time, which is how the database stores and compares timestamps."""
	value = get_datetime(value)
	if value is not None and value.tzinfo is not None:
		value = value.astimezone(ZoneInfo(get_system_timezone())).replace(tzinfo=None)
	return value


def site_dataset(machine: str, definition: dict, since, until, measurements: dict | None = None) -> dict:
	"""The Measurement events of `machine` in [since, until] for every measurement the definition
	names, read with the caller's permissions. `measurements` adds what the events do not carry:
	{name: {"unit", "instrument", "uncertainty"}}, recorded as declared."""
	names = sorted({c.get("measurement") for c in definition.get("checks") or [] if c.get("measurement")})
	since, until = _site_local(since), _site_local(until)
	if not since or not until or until <= since:
		frappe.throw(_("Give the window of machine data to read: since before until"))
	rows = (
		frappe.get_list(
			"Machine Event",
			filters=[
				["machine", "=", machine],
				["event_type", "=", "Measurement"],
				["measurement_name", "in", names],
				["timestamp", ">=", since],
				["timestamp", "<=", until],
			],
			fields=["measurement_name", "value", "timestamp"],
			order_by="timestamp asc, creation asc",
			limit_page_length=MAX_POINTS + 1,
		)
		if names
		else []
	)
	if len(rows) > MAX_POINTS:
		# A cut window would be judged on part of its data; refuse it instead.
		frappe.throw(_("The window holds more than {0} readings; narrow since and until").format(MAX_POINTS))
	meta = measurements or {}
	out = {}
	for name in names:
		declared = meta.get(name) or {}
		out[name] = {
			**{k: declared[k] for k in ("unit", "instrument", "uncertainty") if k in declared},
			"points": [
				{"t": _utc(r.timestamp).isoformat(), "v": r.value} for r in rows if r.measurement_name == name
			],
		}
	return {"id": f"site:{machine}:{since.isoformat()}..{until.isoformat()}", "measurements": out}


@frappe.whitelist(methods=["POST"])
def run_implicit_validation(
	definition: str | dict,
	configuration_revision: str,
	environment: str,
	trigger: str = "On Demand",
	machine: str | None = None,
	since: str | None = None,
	until: str | None = None,
	dataset: str | dict | None = None,
	configuration: str | dict | None = None,
	measurements: str | dict | None = None,
	dry_run: int | bool = 0,
) -> dict:
	"""Evaluate a definition against a configuration and data, and record the evidence.

	Data comes from the site (a `machine` and a `since`/`until` window of its Measurement events) or
	from the caller (`dataset`, for sandbox work and frozen datasets; refused for Production). With
	`dry_run` the bundle is returned and nothing is stored."""
	frappe.only_for(INITIATOR_ROLES)
	definition = _json(definition, "definition")
	configuration = _json(configuration, "configuration")
	supplied = _json(dataset, "dataset")
	configuration_revision = (configuration_revision or "").strip()
	if not configuration_revision:
		frappe.throw(_("Name the configuration or feature-set revision the evidence is for"))
	if environment not in iv.ENVIRONMENTS:
		frappe.throw(_("Environment must be one of {0}").format(", ".join(iv.ENVIRONMENTS)))
	if trigger not in iv.TRIGGERS:
		frappe.throw(_("Trigger must be one of {0}").format(", ".join(iv.TRIGGERS)))
	if machine:
		require_read("Machine", machine)
	try:
		checked = iv.validate_definition(definition)
	except iv.DefinitionError as error:
		frappe.throw(str(error))
	if supplied is not None:
		if environment in SITE_DATA_ONLY:
			frappe.throw(
				_("A {0} run reads its data from the site; a supplied dataset is refused").format(environment)
			)
		data, source = supplied, "Supplied"
	elif machine and since and until:
		data, source = (
			site_dataset(machine, checked, since, until, _json(measurements, "measurements")),
			"Site",
		)
	elif environment in SITE_DATA_ONLY:
		frappe.throw(
			_("A {0} run reads its data from the site: give a machine, since and until").format(environment)
		)
	else:
		data, source = None, ""
	try:
		bundle = iv.evaluate(
			checked, data, configuration, _utc(now_datetime()), configuration_revision, environment
		)
	except ValueError as error:  # a malformed definition, or a non-finite number in the inputs
		frappe.throw(str(error))
	bundle["dataset"]["source"] = source
	bundle["result_hash"] = iv.result_hash(bundle)
	if frappe.utils.cint(dry_run):
		return {"dry_run": True, **bundle}
	doc = frappe.get_doc(
		{
			"doctype": RUN,
			"definition_name": checked["name"],
			"definition_version": checked["version"],
			"outcome": bundle["outcome"],
			"trigger": trigger,
			"environment": environment,
			"machine": machine,
			"configuration_revision": configuration_revision,
			"as_of": now_datetime(),
			"requested_by": frappe.session.user,
			"dataset_reference": bundle["dataset"]["id"],
			"dataset_source": source,
			"input_hash": bundle["input_hash"],
			"result_hash": bundle["result_hash"],
			"summary": _summary(bundle),
			"definition": iv.canonical(checked),
			"result": iv.canonical(bundle),
		}
	)
	doc.flags.from_evaluator = True
	doc.insert(ignore_permissions=True)
	for hook in frappe.get_hooks("foames_implicit_validation_completed") or []:
		frappe.get_attr(hook)(doc)
	return {"name": doc.name, **bundle}


@frappe.whitelist()
def dry_run_implicit_validation(
	definition: str | dict,
	configuration_revision: str,
	environment: str,
	machine: str | None = None,
	since: str | None = None,
	until: str | None = None,
	dataset: str | dict | None = None,
	configuration: str | dict | None = None,
	measurements: str | dict | None = None,
) -> dict:
	"""Evaluate without storing anything: for an agent to see what a change would show."""
	return run_implicit_validation(
		definition,
		configuration_revision,
		environment,
		machine=machine,
		since=since,
		until=until,
		dataset=dataset,
		configuration=configuration,
		measurements=measurements,
		dry_run=1,
	)


def _summary(bundle: dict) -> str:
	counts = ", ".join(f"{n} {o}" for o, n in bundle["counts"].items() if n)
	return f"{bundle['outcome']}: {counts}"


def verified(doc) -> bool:
	"""True when the stored bundle still hashes to the stored result hash and matches the record."""
	try:
		bundle = json.loads(doc.result or "")
	except ValueError:
		return False
	return (
		iv.verify_bundle(bundle)
		and bundle.get("result_hash") == doc.result_hash
		and bundle.get("outcome") == doc.outcome
		and bundle.get("input_hash") == doc.input_hash
		and (bundle.get("configuration") or {}).get("revision") == doc.configuration_revision
		and (bundle.get("environment") or "") == (doc.environment or "")
		and ((bundle.get("dataset") or {}).get("source") or "") == (doc.dataset_source or "")
	)


@frappe.whitelist()
def get_implicit_validation(name: str, include_checks: int | bool = 1) -> dict:
	"""One run: outcome, revision, hashes, whether the evidence still verifies, and its checks."""
	require_read(RUN, name)
	doc = frappe.get_doc(RUN, name)
	out = {
		"name": doc.name,
		"outcome": doc.outcome,
		"verified": verified(doc),
		"environment": doc.environment,
		"trigger": doc.trigger,
		"machine": doc.machine,
		"configuration_revision": doc.configuration_revision,
		"definition": {"name": doc.definition_name, "version": doc.definition_version},
		"dataset": {"reference": doc.dataset_reference, "source": doc.dataset_source},
		"as_of": str(doc.as_of),
		"requested_by": doc.requested_by,
		"input_hash": doc.input_hash,
		"result_hash": doc.result_hash,
		"summary": doc.summary,
	}
	if frappe.utils.cint(include_checks):
		try:
			out["checks"] = json.loads(doc.result or "{}").get("checks", [])
		except ValueError:
			out["checks"] = []
	return out


def require_passed(
	name: str,
	configuration_revision: str,
	environments: tuple[str, ...] | None = None,
	site_data: bool = False,
) -> frappe._dict:
	"""For gates: the run, when it verifies, passed, is pinned to `configuration_revision` and (when
	given) ran in one of `environments` on site data. Raises ImplicitValidationError otherwise.
	Reads as the system, so a gate can check a run the caller may not open."""
	doc = frappe.get_doc(RUN, name) if name and frappe.db.exists(RUN, name) else None
	if doc is None:
		raise ImplicitValidationError(_("Implicit validation {0} does not exist").format(name))
	if not verified(doc):
		raise ImplicitValidationError(
			_("Implicit validation {0} does not verify; its evidence was changed").format(name)
		)
	if doc.configuration_revision != configuration_revision:
		raise ImplicitValidationError(
			_("Implicit validation {0} is for revision {1}, not {2}").format(
				name, doc.configuration_revision, configuration_revision
			)
		)
	if environments and doc.environment not in environments:
		raise ImplicitValidationError(
			_("Implicit validation {0} ran in {1}, not in {2}").format(
				name, doc.environment, ", ".join(environments)
			)
		)
	if site_data and doc.dataset_source != "Site":
		raise ImplicitValidationError(
			_("Implicit validation {0} did not read its data from the site").format(name)
		)
	if doc.outcome != iv.PASS:
		raise ImplicitValidationError(
			_("Implicit validation {0} did not pass: {1}").format(name, doc.summary)
		)
	return frappe._dict(doc.as_dict())
