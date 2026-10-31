# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The built-in suggestion rules against plain snapshots: thresholds, keys and wording. No Frappe site needed."""

import unittest

from foames.foames_mes.suggestions import (
	SILENT_AFTER_MINUTES,
	TOP_DOWNTIME_SHARE,
	all_rules,
	dominant_downtime_reason,
	silent_machines,
	unresolved_erp_references,
)


def machine(name, status, minutes, last_seen="2026-10-30 08:00:00"):
	return {"name": name, "status": status, "minutes_since_count": minutes, "last_seen": last_seen}


class TestSilentMachines(unittest.TestCase):
	def test_threshold_is_inclusive(self):
		snap = {"machines": [machine("M1", "Unknown", SILENT_AFTER_MINUTES)]}
		self.assertEqual(len(silent_machines(snap)), 1)
		snap = {"machines": [machine("M1", "Unknown", SILENT_AFTER_MINUTES - 0.01)]}
		self.assertEqual(silent_machines(snap), [])

	def test_only_unknown_and_running_machines_are_reported(self):
		snap = {
			"machines": [
				machine("IDLE", "Idle", 500),
				machine("DOWN", "Down", 500),
				machine("SETUP", "Setup", 500),
			]
		}
		self.assertEqual(silent_machines(snap), [])

	def test_machine_that_never_counted_is_left_alone(self):
		self.assertEqual(silent_machines({"machines": [machine("M1", "Unknown", None)]}), [])

	def test_silent_finding_fields(self):
		[finding] = silent_machines({"machines": [machine("M1", "Unknown", 45.6, "2026-10-30 07:00:00")]})
		self.assertEqual(finding["category"], "Machine Data")
		self.assertEqual(finding["severity"], "Warning")
		self.assertEqual((finding["reference_doctype"], finding["reference_name"]), ("Machine", "M1"))
		self.assertEqual(
			finding["evidence"], {"last_seen": "2026-10-30 07:00:00", "minutes_since_count": 45.6}
		)
		self.assertIn("46 minutes", finding["suggestion"])
		self.assertEqual(finding["rule_key"], "silent:M1:2026-10-30 07:00:00")

	def test_stalled_finding_fields(self):
		[finding] = silent_machines({"machines": [machine("M2", "Running", 90)]})
		self.assertEqual(finding["category"], "Downtime")
		self.assertIn("90 minutes", finding["title"])
		self.assertEqual(finding["evidence"]["status"], "Running")
		self.assertTrue(finding["rule_key"].startswith("stalled:M2:"))

	def test_rule_key_changes_with_last_seen_so_a_new_silence_is_a_new_finding(self):
		first = silent_machines({"machines": [machine("M1", "Unknown", 40, "a")]})[0]["rule_key"]
		second = silent_machines({"machines": [machine("M1", "Unknown", 40, "b")]})[0]["rule_key"]
		self.assertNotEqual(first, second)

	def test_missing_machines_key(self):
		self.assertEqual(silent_machines({}), [])


class TestDominantDowntime(unittest.TestCase):
	def row(self, total=100, top_minutes=50, top_reason="JAM", machine="M1", period="last 1 day(s)"):
		return {
			"machine": machine,
			"period": period,
			"total_minutes": total,
			"top_reason": top_reason,
			"top_minutes": top_minutes,
		}

	def test_share_threshold_is_inclusive(self):
		exactly = self.row(total=100, top_minutes=100 * TOP_DOWNTIME_SHARE)
		self.assertEqual(len(dominant_downtime_reason({"downtime_by_machine": [exactly]})), 1)
		below = self.row(total=100, top_minutes=100 * TOP_DOWNTIME_SHARE - 1)
		self.assertEqual(dominant_downtime_reason({"downtime_by_machine": [below]}), [])

	def test_no_downtime_or_no_reason_gives_nothing(self):
		rows = [self.row(total=0, top_minutes=0), self.row(top_reason=None), self.row(total=None)]
		self.assertEqual(dominant_downtime_reason({"downtime_by_machine": rows}), [])

	def test_finding_fields(self):
		[finding] = dominant_downtime_reason({"downtime_by_machine": [self.row(total=120, top_minutes=90)]})
		self.assertEqual(finding["rule_key"], "downtime:M1:JAM:last 1 day(s)")
		self.assertEqual(finding["severity"], "Info")
		self.assertEqual(finding["title"], "JAM is 75% of downtime on M1")
		self.assertIn("90 of 120 downtime minutes", finding["suggestion"])
		self.assertEqual(finding["evidence"]["top_reason"], "JAM")
		self.assertEqual((finding["reference_doctype"], finding["reference_name"]), ("Machine", "M1"))

	def test_one_finding_per_machine(self):
		rows = [self.row(machine="A", top_minutes=100), self.row(machine="B", top_minutes=10)]
		found = dominant_downtime_reason({"downtime_by_machine": rows})
		self.assertEqual([f["reference_name"] for f in found], ["A"])


class TestUnresolvedERPReferences(unittest.TestCase):
	def ref(self, n, status="Missing"):
		return {"name": f"REF-{n}", "reference_type": "Item", "external_id": f"I-{n}", "status": status}

	def test_nothing_missing(self):
		self.assertEqual(unresolved_erp_references({}), [])
		snap = {"external_references": [self.ref(1, "Resolved"), self.ref(2, "Unverified")]}
		self.assertEqual(unresolved_erp_references(snap), [])

	def test_one_finding_lists_the_missing_records(self):
		snap = {"external_references": [self.ref(1), self.ref(2, "Resolved"), self.ref(3)]}
		[finding] = unresolved_erp_references(snap)
		self.assertEqual(finding["category"], "ERP")
		self.assertEqual(finding["title"], "2 ERP references point to records that do not exist")
		self.assertIn("Item I-1, Item I-3", finding["suggestion"])
		self.assertEqual(finding["evidence"], {"missing": ["REF-1", "REF-3"]})
		self.assertEqual(finding["rule_key"], "erp-missing:2:REF-1")
		self.assertNotIn("reference_doctype", finding)

	def test_wording_lists_at_most_ten_but_evidence_lists_all(self):
		snap = {"external_references": [self.ref(n) for n in range(15)]}
		[finding] = unresolved_erp_references(snap)
		self.assertEqual(finding["suggestion"].count("Item I-"), 10)
		self.assertEqual(len(finding["evidence"]["missing"]), 15)
		self.assertIn("15 ERP references", finding["title"])


class TestAllRules(unittest.TestCase):
	def test_combines_every_rule_in_order(self):
		snap = {
			"machines": [machine("M1", "Unknown", 60)],
			"downtime_by_machine": [
				{"machine": "M1", "period": "p", "total_minutes": 10, "top_reason": "X", "top_minutes": 10}
			],
			"external_references": [
				{"name": "R", "reference_type": "Batch", "external_id": "B", "status": "Missing"}
			],
		}
		keys = [f["rule_key"] for f in all_rules(snap)]
		self.assertEqual(keys, ["silent:M1:2026-10-30 08:00:00", "downtime:M1:X:p", "erp-missing:1:R"])

	def test_every_finding_has_the_fields_the_doctype_needs(self):
		snap = {
			"machines": [machine("M1", "Running", 60)],
			"downtime_by_machine": [
				{"machine": "M1", "period": "p", "total_minutes": 10, "top_reason": "X", "top_minutes": 9}
			],
			"external_references": [
				{"name": "R", "reference_type": "Batch", "external_id": "B", "status": "Missing"}
			],
		}
		for finding in all_rules(snap):
			for key in ("rule_key", "category", "severity", "title", "suggestion", "evidence"):
				self.assertIn(key, finding)
			self.assertIn(
				finding["category"],
				("Yield", "Downtime", "Quality", "Release", "Machine Data", "ERP", "Other"),
			)
			self.assertIn(finding["severity"], ("Info", "Warning", "Critical"))
			self.assertLessEqual(len(finding["title"]), 140)


if __name__ == "__main__":
	unittest.main()
