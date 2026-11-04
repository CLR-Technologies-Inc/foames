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
			self.assertIn(
				op.doctype,
				(
					"Stock Entry",
					"Job Card",
					"Work Order",
					"Workstation",
					"Downtime Entry",
					"Quality Inspection",
				),
			)
			self.assertTrue(op.required)

	def test_workstation_status_follows_the_machine_state(self):
		self.assertEqual(postings.workstation_status_for("Running"), "Production")
		self.assertEqual(postings.workstation_status_for("Down"), "Problem")
		self.assertEqual(postings.workstation_status_for("Idle"), "Idle")
		self.assertEqual(postings.workstation_status_for("Setup"), "Setup")
		self.assertEqual(postings.workstation_status_for("Unknown"), "Off")
		self.assertEqual(postings.workstation_status_for(None), "Off")
		for status in postings.WORKSTATION_STATUS_BY_STATE.values():
			self.assertIn(status, postings.WORKSTATION_STATUSES)

	def test_stop_reason_mapping(self):
		# A title that is one of ERPNext's reasons wins, whatever the category says.
		self.assertEqual(postings.stop_reason_for("Electricity down", "Breakdown"), "Electricity down")
		self.assertEqual(postings.stop_reason_for(" Electricity down ", None), "Electricity down")
		# Otherwise the category decides, and the rest is Other.
		self.assertEqual(
			postings.stop_reason_for("Tool change", "Changeover"), "Excessive machine set up time"
		)
		self.assertEqual(postings.stop_reason_for("Spindle", "Breakdown"), "Machine malfunction")
		self.assertEqual(postings.stop_reason_for("PM", "Planned"), "Unplanned machine maintenance")
		self.assertEqual(postings.stop_reason_for("Waiting", "No Material"), "Other")
		self.assertEqual(postings.stop_reason_for(None, None), "Other")
		# An installed ERPNext that lacks a reason never gets it.
		self.assertEqual(postings.stop_reason_for("Spindle", "Breakdown", ("Other",)), "Other")
		self.assertEqual(postings.stop_reason_for("Spindle", "Breakdown", ("Something",)), "Something")
		for reason in postings.STOP_REASON_BY_CATEGORY.values():
			self.assertIn(reason, postings.STOP_REASONS)

	def test_downtime_marker_is_stable_and_distinct_from_the_posting_marker(self):
		self.assertEqual(postings.downtime_marker("DT-2026-00001"), postings.downtime_marker("DT-2026-00001"))
		self.assertNotEqual(postings.downtime_marker("DT-2026-00001"), postings.marker("DT-2026-00001"))
		self.assertNotEqual(
			postings.downtime_marker("DT-2026-00001"), postings.downtime_marker("DT-2026-00002")
		)

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

	def test_workstation_status_is_restricted(self):
		self.assertEqual(
			self.prepare("Workstation Status", {"workstation": "WS-1", "status": "Production"})["status"],
			"Production",
		)
		with self.assertRaises(ValueError):
			self.prepare("Workstation Status", {"workstation": "WS-1", "status": "Running"})
		with self.assertRaises(ValueError):
			self.prepare("Workstation Status", {"workstation": "WS-1"})

	def test_quality_inspection_from_measurements(self):
		from foames.foames_adapters.erpnext import postings

		op = postings.OPERATIONS["Quality Inspection"]
		base = {"reference_type": "Job Card", "reference_name": "JC-1"}
		window = {"machine": "M1", "since": "2026-01-01 08:00:00", "until": "2026-01-01 09:00:00"}
		prepared = postings.prepare(
			op, {**base, "measurements": {**window, "specifications": ["L", "L", " W "]}}
		)
		self.assertEqual(prepared["measurements"], {**window, "specifications": ["L", "W"]})
		self.assertNotIn("readings", prepared)
		self.assertEqual(postings.prepare(op, {**base, "measurements": window})["measurements"], window)
		readings = [{"specification": "L", "values": [1.0]}]
		for bad in (
			{},
			{"measurements": window, "readings": readings},
			{"measurements": "M1"},
			{"measurements": {**window, "colour": "Blue"}},
			{"measurements": {"machine": "M1", "since": "2026-01-01 08:00:00"}},
			{"measurements": {**window, "until": window["since"]}},
			{"measurements": {**window, "specifications": "L"}},
			{"measurements": {**window, "specifications": ["L", ""]}},
		):
			with self.assertRaises(ValueError, msg=bad):
				postings.prepare(op, {**base, **bad})

	def test_quality_inspection_readings(self):
		base = {"reference_type": "Job Card", "reference_name": "PO-JOB00001"}
		prepared = self.prepare(
			"Quality Inspection",
			{
				**base,
				"readings": [
					{"specification": " Length ", "values": [10.1, "9.9", 10]},
					{"specification": "Colour", "value": "Blue"},
					{"specification": "Weight", "value": 250, "min_value": "240", "max_value": 260},
					{"specification": "Finish", "value": "Matt", "status": "Rejected"},
				],
			},
		)
		self.assertEqual(prepared["inspection_type"], "In Process")
		self.assertEqual(
			prepared["readings"],
			[
				{"specification": "Length", "values": [10.1, 9.9, 10.0]},
				{"specification": "Colour", "value": "Blue"},
				{"specification": "Weight", "values": [250.0], "min_value": 240.0, "max_value": 260.0},
				{"specification": "Finish", "value": "Matt", "status": "Rejected"},
			],
		)
		# A Stock Entry is inspected as the finished good comes in, unless told otherwise.
		stock = {**base, "reference_type": "Stock Entry", "readings": [{"specification": "L", "values": [1]}]}
		self.assertEqual(self.prepare("Quality Inspection", stock)["inspection_type"], "Incoming")
		self.assertEqual(
			self.prepare("Quality Inspection", {**stock, "inspection_type": "Outgoing"})["inspection_type"],
			"Outgoing",
		)
		self.assertEqual(
			self.prepare("Quality Inspection", {**stock, "sample_size": "3"})["sample_size"], 3.0
		)
		bad = [
			{**base, "readings": []},
			{**base, "readings": [{"values": [1]}]},
			{**base, "readings": [{"specification": "L"}]},
			{**base, "readings": [{"specification": "L", "values": []}]},
			{**base, "readings": [{"specification": "L", "values": ["ten"]}]},
			{**base, "readings": [{"specification": "L", "values": [1, None]}]},
			{**base, "readings": [{"specification": "L", "values": list(range(11))}]},
			{**base, "readings": [{"specification": "L", "values": [1], "min_value": 5, "max_value": 4}]},
			{**base, "readings": [{"specification": "L", "values": [1], "status": "Maybe"}]},
			{**base, "readings": [{"specification": "L", "values": [1], "note": "x"}]},
			{**base, "readings": [{"specification": "L", "values": [1]}], "inspection_type": "Final"},
			{**base, "readings": [{"specification": "L", "values": [1]}], "sample_size": 0},
			{
				**base,
				"reference_type": "Purchase Receipt",
				"readings": [{"specification": "L", "values": [1]}],
			},
		]
		for payload in bad:
			with self.assertRaises(ValueError, msg=payload):
				self.prepare("Quality Inspection", payload)

	def test_downtime_entry_needs_a_window(self):
		base = {"workstation": "WS-1", "from_time": "2026-10-31 08:00:00", "to_time": "2026-10-31 08:30:00"}
		self.assertEqual(self.prepare("Downtime Entry", base), base)
		with self.assertRaises(ValueError):
			self.prepare("Downtime Entry", {**base, "to_time": base["from_time"]})
		with self.assertRaises(ValueError):
			self.prepare("Downtime Entry", {**base, "machine": "M-1"})
		full = {
			**base,
			"operator": "HR-EMP-00001",
			"stop_reason": "Other",
			"remarks": "x",
			"downtime_record": "DT-1",
		}
		self.assertEqual(self.prepare("Downtime Entry", full), full)


class TestFinishedGoodIdentity(unittest.TestCase):
	def prepare(self, operation, payload):
		return postings.prepare(postings.OPERATIONS[operation], payload)

	def test_time_log_operators_take_any_shape(self):
		base = {"job_card": "PO-JOB00001", "start_time": "2026-10-31 08:00:00"}
		rows = [{"employee": "HR-EMP-00001"}, {"employee": "HR-EMP-00002"}]
		self.assertEqual(self.prepare("Job Card Time Log", {**base, "employees": rows})["employees"], rows)
		self.assertEqual(
			self.prepare("Job Card Time Log", {**base, "employees": ["HR-EMP-00001", "HR-EMP-00002"]})[
				"employees"
			],
			rows,
		)
		self.assertEqual(
			self.prepare("Job Card Time Log", {**base, "employees": "HR-EMP-00001, HR-EMP-00002"})[
				"employees"
			],
			rows,
		)
		self.assertNotIn("employees", self.prepare("Job Card Time Log", {**base, "employees": None}))
		with self.assertRaises(ValueError):
			self.prepare("Job Card Time Log", {**base, "employees": [{"name": "x"}]})
		with self.assertRaises(ValueError):
			self.prepare("Job Card Time Log", {**base, "employees": 7})

	def test_manufacture_batch_and_serial_numbers(self):
		base = {"work_order": "MFG-WO-1"}
		self.assertEqual(
			self.prepare("Manufacture", {**base, "serial_nos": "SN-1, SN-2\nSN-3 "})["serial_nos"],
			["SN-1", "SN-2", "SN-3"],
		)
		self.assertEqual(
			self.prepare("Manufacture", {**base, "qty": 2, "serial_nos": ["SN-1", "SN-2"]})["serial_nos"],
			["SN-1", "SN-2"],
		)
		self.assertEqual(self.prepare("Manufacture", {**base, "batch_no": " B-1 "})["batch_no"], "B-1")
		# Empty values are dropped rather than sent.
		self.assertNotIn("batch_no", self.prepare("Manufacture", {**base, "batch_no": ""}))
		self.assertNotIn("serial_nos", self.prepare("Manufacture", {**base, "serial_nos": None}))
		with self.assertRaises(ValueError):
			self.prepare("Manufacture", {**base, "qty": 3, "serial_nos": ["SN-1", "SN-2"]})
		with self.assertRaises(ValueError):
			self.prepare("Manufacture", {**base, "serial_nos": ["SN-1", "SN-1"]})
		with self.assertRaises(ValueError):
			self.prepare("Manufacture", {**base, "serial_nos": ", ,"})
		with self.assertRaises(ValueError):
			self.prepare("Manufacture", {**base, "serial_nos": 5})
		# A null in the list is malformed, not the serial number "None".
		with self.assertRaises(ValueError):
			self.prepare("Manufacture", {**base, "qty": 2, "serial_nos": ["SN-1", None]})
		# Serial numbers count units, so the quantity has to be whole.
		with self.assertRaises(ValueError):
			self.prepare("Manufacture", {**base, "qty": 1.5, "serial_nos": ["SN-1"]})
		# Only the Manufacture entry names the finished good.
		with self.assertRaises(ValueError):
			self.prepare("Material Transfer for Manufacture", {**base, "batch_no": "B-1"})


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
		self.assertEqual(set(hooks.doc_events), set(REFERENCE_TYPES_BY_DOCTYPE) | {"Downtime Record"})
		for doctype in REFERENCE_TYPES_BY_DOCTYPE:
			self.assertEqual(dict(hooks.doc_events[doctype]), DOC_EVENTS[doctype])
		self.assertEqual(
			hooks.doc_events["Downtime Record"],
			{"on_update": "foames.foames_adapters.erpnext.downtime.on_update"},
		)
		self.assertEqual(
			hooks.foames_machine_state_changed,
			["foames.foames_adapters.erpnext.workstation.on_state_changed"],
		)
		self.assertIn(
			"foames.foames_adapters.erpnext.floor.extend_snapshot", hooks.foames_floor_snapshot_extensions
		)
		self.assertIn(
			"foames.foames_adapters.doctype.erpnext_outbox.erpnext_outbox.process_outbox",
			hooks.scheduler_events["all"],
		)
