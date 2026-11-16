# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Implicit validation on a site: runs from site and supplied data, immutable evidence, tamper
detection, and what a gate may rely on.

bench --site <site> run-tests --app foames --module foames.foames_validation.test_implicit_validation
"""

import frappe
from frappe.permissions import add_user_permission
from frappe.utils import add_to_date

from foames.foames_validation import implicit as iv
from foames.foames_validation import implicit_api as api
from foames.foames_validation.test_implicit_logic import INSTRUMENT, capability, dataset, definition, stable
from foames.foames_validation.test_validation import START, measure
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import as_user, enforcing_roles, extra_hooks, make_machine, make_user

MACHINE = "T-IVR-1"
OPERATOR = "ivr-operator@example.com"
ENGINEER = "ivr-engineer@example.com"
OTHER_AREA = "T-IVR-2"


def run(environment="Sandbox", revision="rev-1", data=None, **kwargs):
	return api.run_implicit_validation(
		definition(capability()),
		revision,
		environment,
		dataset=dataset() if data is None else data,
		**kwargs,
	)


class TestImplicitValidationRun(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		make_machine(MACHINE)
		make_machine(OTHER_AREA)
		make_user(OPERATOR, "FoaMES Operator")
		make_user(ENGINEER, "FoaMES Engineer")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete(api.RUN)
		frappe.db.delete("User Permission", {"user": ENGINEER})
		super().tearDown()

	def test_a_recorded_run_passes_a_gate_for_its_revision_only(self):
		name = run()["name"]
		self.assertEqual(frappe.db.get_value(api.RUN, name, "outcome"), iv.PASS)
		self.assertEqual(frappe.db.get_value(api.RUN, name, "dataset_source"), "Supplied")
		api.require_passed(name, "rev-1")
		with self.assertRaises(api.ImplicitValidationError):
			api.require_passed(name, "rev-2")
		with self.assertRaises(api.ImplicitValidationError):
			api.require_passed(name, "rev-1", site_data=True)
		with self.assertRaises(api.ImplicitValidationError):
			api.require_passed(name, "rev-1", environments=("Production Candidate",))

	def test_the_same_criteria_run_on_sandbox_and_candidate_production(self):
		sandbox = run("Sandbox")
		candidate = run("Production Candidate")
		self.assertEqual(sandbox["definition"]["hash"], candidate["definition"]["hash"])
		self.assertEqual(sandbox["outcome"], candidate["outcome"])
		api.require_passed(candidate["name"], "rev-1", environments=("Production Candidate",))

	def test_a_failing_or_indeterminate_run_blocks_the_gate(self):
		failing = run(data=dataset(stable(sd=0.06)))["name"]
		thin = run(data=dataset(stable(n=5)))["name"]
		for name in (failing, thin):
			with self.assertRaises(api.ImplicitValidationError):
				api.require_passed(name, "rev-1")

	def test_changed_evidence_is_detected(self):
		name = run(data=dataset(stable(sd=0.06)))["name"]
		frappe.db.set_value(api.RUN, name, "outcome", iv.PASS)  # behind the controller's back
		self.assertFalse(api.get_implicit_validation(name)["verified"])
		with self.assertRaises(api.ImplicitValidationError):
			api.require_passed(name, "rev-1")

	def test_a_changed_environment_or_source_is_detected(self):
		for field, value in (("environment", "Production"), ("dataset_source", "Site")):
			name = run()["name"]
			frappe.db.set_value(api.RUN, name, field, value)
			self.assertFalse(api.get_implicit_validation(name)["verified"])
			with self.assertRaises(api.ImplicitValidationError):
				api.require_passed(name, "rev-1")

	def test_evidence_cannot_be_created_changed_or_deleted_on_the_desk(self):
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc(
				{"doctype": api.RUN, "configuration_revision": "rev-1", "outcome": iv.PASS}
			).insert(ignore_permissions=True)
		name = run()["name"]
		doc = frappe.get_doc(api.RUN, name)
		doc.outcome = iv.FAIL
		with self.assertRaises(frappe.PermissionError):
			doc.save(ignore_permissions=True)
		with self.assertRaises(frappe.PermissionError):
			frappe.delete_doc(api.RUN, name, ignore_permissions=True)

	def test_production_reads_site_data(self):
		with self.assertRaises(frappe.ValidationError):
			run("Production")
		measure([round(v, 4) for v in stable(n=30)], name="bore", machine=MACHINE)
		result = api.run_implicit_validation(
			definition(
				capability(), {"key": "msa", "kind": "metrology", "measurement": "bore", "unit": "mm"}
			),
			"rev-1",
			"Production",
			machine=MACHINE,
			since=START,
			until=add_to_date(START, hours=2),
			# Far-off due date: this run is judged at the real time of the test run.
			measurements={
				"bore": {"unit": "mm", "instrument": {**INSTRUMENT, "calibration_due": "2099-12-31"}}
			},
		)
		self.assertEqual(result["dataset"]["source"], "Site")
		self.assertEqual(frappe.db.get_value(api.RUN, result["name"], "outcome"), iv.PASS)
		api.require_passed(result["name"], "rev-1", site_data=True)

	def test_a_dry_run_stores_nothing(self):
		result = api.dry_run_implicit_validation(
			definition(capability()), "rev-1", "Sandbox", dataset=dataset()
		)
		self.assertTrue(result["dry_run"])
		self.assertFalse(frappe.db.count(api.RUN))

	def test_only_authorised_roles_start_a_run_and_within_their_area(self):
		with enforcing_roles(), as_user(OPERATOR):
			with self.assertRaises(frappe.PermissionError):
				run()
		add_user_permission("Machine", MACHINE, ENGINEER)
		with as_user(ENGINEER):
			with self.assertRaises(frappe.PermissionError):
				run(machine=OTHER_AREA)
			name = run(machine=MACHINE)["name"]
			self.assertEqual(api.get_implicit_validation(name)["outcome"], iv.PASS)

	def test_a_completed_run_calls_the_hook(self):
		seen.clear()
		with extra_hooks(foames_implicit_validation_completed=[f"{__name__}.remember"]):
			name = run()["name"]
		self.assertEqual(seen, [name])


seen = []


def remember(doc):
	seen.append(doc.name)
