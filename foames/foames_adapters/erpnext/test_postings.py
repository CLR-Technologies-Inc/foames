# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Pure tests of the ERPNext posting rules. No site needed."""

import importlib.util
import pathlib
import unittest

from foames.foames_adapters.erpnext import postings


class TestOperations(unittest.TestCase):
	def test_every_operation_names_an_erpnext_doctype(self):
		for op in postings.OPERATIONS.values():
			self.assertIn(op.doctype, ("Stock Entry", "Job Card", "Work Order"))
			self.assertTrue(op.required)

	def test_stock_entry_purposes_are_operations(self):
		for purpose in postings.STOCK_ENTRY_PURPOSES:
			self.assertEqual(postings.OPERATIONS[purpose].doctype, "Stock Entry")
			self.assertEqual(postings.OPERATIONS[purpose].reference_type, "Stock Movement")


class TestPrepare(unittest.TestCase):
	def prepare(self, operation, payload):
		return postings.prepare(postings.OPERATIONS[operation], payload)

	def test_missing_required_field(self):
		with self.assertRaisesRegex(ValueError, "needs work_order"):
			self.prepare("Manufacture", {"qty": 5})

	def test_unknown_field_is_rejected(self):
		with self.assertRaisesRegex(ValueError, "does not understand quantity"):
			self.prepare("Manufacture", {"work_order": "MFG-WO-1", "quantity": 5})

	def test_quantities_are_numbers(self):
		prepared = self.prepare("Manufacture", {"work_order": "MFG-WO-1", "qty": "5", "submit": "false"})
		self.assertEqual(prepared["qty"], 5.0)
		self.assertIs(prepared["submit"], False)
		with self.assertRaisesRegex(ValueError, "qty must be a number"):
			self.prepare("Manufacture", {"work_order": "MFG-WO-1", "qty": "five"})
		with self.assertRaisesRegex(ValueError, "cannot be negative"):
			self.prepare("Manufacture", {"work_order": "MFG-WO-1", "qty": -1})

	def test_time_log_needs_a_time(self):
		with self.assertRaisesRegex(ValueError, "start_time, complete_time or both"):
			self.prepare("Job Card Time Log", {"job_card": "PO-JOB-1", "completed_qty": 2})
		prepared = self.prepare(
			"Job Card Time Log",
			{"job_card": "PO-JOB-1", "complete_time": "2026-10-31 08:00:00", "completed_qty": "2"},
		)
		self.assertEqual(prepared["completed_qty"], 2.0)

	def test_work_order_status_is_restricted(self):
		with self.assertRaisesRegex(ValueError, "must be one of"):
			self.prepare("Work Order Status", {"work_order": "MFG-WO-1", "status": "Completed"})
		self.assertEqual(
			self.prepare("Work Order Status", {"work_order": "MFG-WO-1", "status": "Closed"})["status"],
			"Closed",
		)

	def test_payload_must_be_an_object(self):
		with self.assertRaisesRegex(ValueError, "must be an object"):
			self.prepare("Manufacture", ["MFG-WO-1"])

	def test_prepare_does_not_change_the_input(self):
		payload = {"work_order": "MFG-WO-1", "qty": "3"}
		postings.prepare(postings.OPERATIONS["Manufacture"], payload)
		self.assertEqual(payload["qty"], "3")


class TestMarker(unittest.TestCase):
	def test_marker_is_short_stable_and_distinct(self):
		a = postings.marker("MFG-WO-1:OP1:complete")
		self.assertEqual(a, postings.marker("MFG-WO-1:OP1:complete"))
		self.assertNotEqual(a, postings.marker("MFG-WO-1:OP1:start"))
		self.assertTrue(a.startswith("FOAMES-"))
		self.assertEqual(len(a), 23)


class Transient(Exception):
	pass


class QueryDeadlockError(Exception):
	pass


class ValidationError(Exception):
	pass


class TimestampMismatchError(ValidationError):
	pass


class NegativeStockError(ValidationError):
	pass


class TestClassify(unittest.TestCase):
	def test_database_conflicts_are_retried(self):
		self.assertEqual(postings.classify(postings.error_types(QueryDeadlockError())), "Retry")
		# Frappe derives this lock error from ValidationError; the transient name wins.
		self.assertEqual(postings.classify(postings.error_types(TimestampMismatchError())), "Retry")

	def test_rejections_fail(self):
		self.assertEqual(postings.classify(postings.error_types(NegativeStockError())), "Failed")
		self.assertEqual(postings.classify(postings.error_types(ValueError("qty"))), "Failed")
		self.assertEqual(postings.classify(postings.error_types(KeyError("work_order"))), "Failed")

	def test_unknown_errors_are_retried(self):
		self.assertEqual(postings.classify(postings.error_types(Transient())), "Retry")
		self.assertEqual(postings.classify(postings.error_types(RuntimeError())), "Retry")


class TestRetry(unittest.TestCase):
	def test_backoff_doubles_and_caps(self):
		self.assertEqual(postings.retry_delay(1), 60)
		self.assertEqual(postings.retry_delay(2), 120)
		self.assertEqual(postings.retry_delay(3), 240)
		self.assertEqual(postings.retry_delay(50), postings.MAX_DELAY_SECONDS)

	def test_gives_up_after_the_cap(self):
		self.assertFalse(postings.give_up(postings.MAX_ATTEMPTS - 1))
		self.assertTrue(postings.give_up(postings.MAX_ATTEMPTS))


class TestHooksMatchTheAdapter(unittest.TestCase):
	"""hooks.py repeats the ERPNext DocType list as literals; keep it in step with the adapter."""

	def test_doc_events_cover_every_mapped_doctype(self):
		from foames.foames_adapters.erpnext import REFERENCE_TYPES_BY_DOCTYPE
		from foames.foames_adapters.erpnext.sync import DOC_EVENTS

		path = pathlib.Path(__file__).resolve().parents[2] / "hooks.py"
		spec = importlib.util.spec_from_file_location("foames_hooks", path)
		hooks = importlib.util.module_from_spec(spec)
		spec.loader.exec_module(hooks)
		self.assertEqual(set(hooks.doc_events), set(REFERENCE_TYPES_BY_DOCTYPE))
		for doctype, handlers in hooks.doc_events.items():
			self.assertEqual(dict(handlers), DOC_EVENTS[doctype])
		self.assertIn(
			"foames.foames_adapters.erpnext.floor.extend_snapshot", hooks.foames_floor_snapshot_extensions
		)
		self.assertIn(
			"foames.foames_adapters.doctype.erpnext_outbox.erpnext_outbox.process_outbox",
			hooks.scheduler_events["all"],
		)
