# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

import json
import os
import tempfile
import unittest

from foames_openfoam.cases import BUILTIN_CASES
from foames_openfoam.lifecycle import (
	Run,
	RunStore,
	TransitionError,
	idempotency_key,
	new_run_id,
	transition,
)
from foames_openfoam.manifest import ManifestError, config_hash, validate_manifest
from foames_openfoam.runner import residual_summary


class LifecycleTests(unittest.TestCase):
	def test_happy_path(self):
		self.assertEqual(transition("draft", "queued"), "queued")
		self.assertEqual(transition("queued", "running"), "running")
		self.assertEqual(transition("running", "succeeded"), "succeeded")

	def test_terminal_states_are_final(self):
		for terminal in ("succeeded", "failed", "cancelled", "timed_out"):
			with self.assertRaises(TransitionError):
				transition(terminal, "running")

	def test_illegal_skips_rejected(self):
		with self.assertRaises(TransitionError):
			transition("draft", "running")
		with self.assertRaises(TransitionError):
			transition("queued", "succeeded")
		with self.assertRaises(TransitionError):
			transition("running", "queued")

	def test_run_set_status_timestamps(self):
		run = Run(run_id=new_run_id(), case="pitzdaily", idempotency_key="k")
		run.set_status("running")
		self.assertIsNotNone(run.started_at)
		run.set_status("succeeded")
		self.assertIsNotNone(run.finished_at)
		with self.assertRaises(TransitionError):
			run.set_status("failed")

	def test_idempotency_key_stable_and_sensitive(self):
		manifest = {"case": "pitzdaily", "params": {"end_time": 100.0}}
		self.assertEqual(idempotency_key(manifest, "eng"), idempotency_key(manifest, "eng"))
		self.assertNotEqual(idempotency_key(manifest, "eng"), idempotency_key(manifest, "qa"))
		self.assertNotEqual(
			idempotency_key(manifest), idempotency_key({"case": "pitzdaily", "params": {"end_time": 200.0}})
		)


class ManifestTests(unittest.TestCase):
	def test_valid_manifest_normalised(self):
		clean = validate_manifest({"case": "pitzdaily", "params": {"end_time": 100}}, known_cases=tuple(BUILTIN_CASES))
		self.assertEqual(clean["params"]["end_time"], 100.0)

	def test_unknown_case_rejected(self):
		with self.assertRaises(ManifestError):
			validate_manifest({"case": "my_solver"}, known_cases=tuple(BUILTIN_CASES))

	def test_unsafe_names_rejected(self):
		for bad in ("../etc", "PitzDaily", "a b", ""):
			with self.assertRaises(ManifestError):
				validate_manifest({"case": bad})

	def test_non_numeric_and_extra_params_rejected(self):
		with self.assertRaises(ManifestError):
			validate_manifest({"case": "pitzdaily", "params": {"end_time": "soon"}})
		with self.assertRaises(ManifestError):
			validate_manifest({"case": "pitzdaily", "params": {f"p{i}": i for i in range(40)}})

	def test_config_hash_covers_solver_version(self):
		manifest = validate_manifest({"case": "pitzdaily"}, known_cases=tuple(BUILTIN_CASES))
		self.assertNotEqual(config_hash(manifest, "2606"), config_hash(manifest, "2607"))


class RunStoreTests(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.TemporaryDirectory()
		self.addCleanup(self.tmp.cleanup)
		self.store = RunStore(self.tmp.name)

	def test_submit_idempotency_via_store(self):
		manifest = {"case": "pitzdaily", "params": {}}
		key = idempotency_key(manifest, "eng")
		run = Run(run_id=new_run_id(), case="pitzdaily", idempotency_key=key)
		self.store.save(run)
		found = self.store.find_by_key(key)
		self.assertIsNotNone(found)
		self.assertEqual(found.run_id, run.run_id)
		self.assertIsNone(self.store.find_by_key("other"))

	def test_load_missing_returns_none(self):
		self.assertIsNone(self.store.load("run-nope"))


class ResidualTests(unittest.TestCase):
	def test_extracts_final_residuals_per_field(self):
		log = (
			"Solving for p, Initial residual = 0.5, Final residual = 0.01, No Iterations 5\n"
			"Solving for Ux, Initial residual = 0.4, Final residual = 0.02, No Iterations 3\n"
			"Solving for p, Initial residual = 0.01, Final residual = 0.001, No Iterations 2\n"
		)
		# The regex pairs 'Solving for X' with a following 'Final residual' line.
		summary = residual_summary(log)
		self.assertIn("p", summary)
		self.assertEqual(summary["p"], 0.001)

	def test_empty_log(self):
		self.assertEqual(residual_summary("nothing here"), {})


if __name__ == "__main__":
	unittest.main()
