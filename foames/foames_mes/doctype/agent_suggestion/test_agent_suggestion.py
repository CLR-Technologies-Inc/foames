# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import json

import frappe

from foames.foames_mes.api import post_suggestion
from foames.foames_mes.doctype.agent_suggestion.agent_suggestion import raise_suggestions
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import as_user, make_machine, make_user


def finding(rule_key="t-sug:one", **overrides):
	values = {
		"rule_key": rule_key,
		"category": "Other",
		"severity": "Info",
		"title": "Something to look at",
		"suggestion": "Look at it.",
		"evidence": {"seen": 1},
	}
	values.update(overrides)
	return values


class TestAgentSuggestion(IntegrationTestCase):
	def make(self, **overrides):
		values = {"doctype": "Agent Suggestion", "title": "T", "category": "Other", "suggestion": "S"}
		values.update(overrides)
		return frappe.get_doc(values).insert()

	def test_defaults(self):
		doc = self.make()
		self.assertEqual((doc.status, doc.severity), ("Open", "Warning"))
		self.assertIsNone(doc.resolved_on)
		self.assertTrue(doc.name.startswith("SUG-"))

	def test_rule_key_default_shapes(self):
		named = self.make(agent="plant-agent")
		self.assertTrue(named.rule_key.startswith("plant-agent:"))
		manual = self.make()
		self.assertTrue(manual.rule_key.startswith("manual:"))
		self.assertNotEqual(named.rule_key, manual.rule_key)
		self.assertEqual(self.make(rule_key="given").rule_key, "given")

	def test_resolving_records_who_and_when(self):
		for status in ("Accepted", "Dismissed", "Done"):
			doc = self.make()
			doc.status = status
			doc.save()
			self.assertTrue(doc.resolved_on, status)
			self.assertEqual(doc.resolved_by, "Administrator")

	def test_reopening_clears_the_resolution_time(self):
		doc = self.make()
		doc.status = "Done"
		doc.save()
		doc.status = "Open"
		doc.save()
		self.assertIsNone(doc.resolved_on)
		self.assertIsNone(doc.resolved_by)

	def test_reference_must_exist(self):
		make_machine("T-SUG-REF")
		doc = self.make(reference_doctype="Machine", reference_name="T-SUG-REF")
		self.assertEqual(doc.reference_name, "T-SUG-REF")
		with self.assertRaises(frappe.ValidationError):
			self.make(reference_doctype="Machine", reference_name="T-SUG-NO-SUCH-MACHINE")


class TestRaiseSuggestions(IntegrationTestCase):
	def test_creates_once_per_open_rule_key(self):
		[name] = raise_suggestions([finding()])
		self.assertEqual(raise_suggestions([finding()]), [])
		doc = frappe.get_doc("Agent Suggestion", name)
		self.assertEqual((doc.agent, doc.status, doc.rule_key), ("foames-rules", "Open", "t-sug:one"))
		self.assertEqual(json.loads(doc.evidence), {"seen": 1})

	def test_resolved_suggestion_is_reopened_with_new_evidence(self):
		[name] = raise_suggestions([finding()])
		doc = frappe.get_doc("Agent Suggestion", name)
		doc.status = "Dismissed"
		doc.resolution = "Not relevant"
		doc.save()
		self.assertEqual(raise_suggestions([finding(evidence={"seen": 2}, suggestion="Again.")]), [name])
		doc.reload()
		self.assertEqual((doc.status, doc.resolution, doc.suggestion), ("Open", None, "Again."))
		self.assertEqual(json.loads(doc.evidence), {"seen": 2})
		self.assertIsNone(doc.resolved_on)

	def test_several_findings_and_a_custom_agent(self):
		created = raise_suggestions([finding("t-sug:a"), finding("t-sug:b")], agent="my-agent")
		self.assertEqual(len(created), 2)
		agents = frappe.get_all("Agent Suggestion", {"name": ("in", created)}, pluck="agent")
		self.assertEqual(set(agents), {"my-agent"})

	def test_list_evidence_is_stored_as_json(self):
		[name] = raise_suggestions([finding("t-sug:list", evidence=[1, 2, 3])])
		self.assertEqual(json.loads(frappe.db.get_value("Agent Suggestion", name, "evidence")), [1, 2, 3])


class TestPostSuggestion(IntegrationTestCase):
	def test_evidence_may_arrive_as_a_json_string(self):
		name = post_suggestion(
			"Chiller", "Downtime", "Check it.", agent="ext", evidence='{"trips": 3}', rule_key="ext:chiller:1"
		)
		doc = frappe.get_doc("Agent Suggestion", name)
		self.assertEqual(json.loads(doc.evidence), {"trips": 3})
		self.assertEqual((doc.agent, doc.severity), ("ext", "Warning"))

	def test_without_a_rule_key_every_post_is_new(self):
		first = post_suggestion("A", "Other", "x", agent="ext")
		second = post_suggestion("A", "Other", "x", agent="ext")
		self.assertNotEqual(first, second)
		self.assertTrue(frappe.db.get_value("Agent Suggestion", first, "rule_key").startswith("ext:"))

	def test_repeated_rule_key_returns_the_open_suggestion(self):
		first = post_suggestion("A", "Other", "x", agent="ext", rule_key="ext:same")
		self.assertEqual(post_suggestion("A", "Other", "y", agent="ext", rule_key="ext:same"), first)
		self.assertEqual(frappe.db.get_value("Agent Suggestion", first, "suggestion"), "x")

	def test_needs_create_permission(self):
		make_user("foames-sug-quality@example.com", "FoaMES Quality")
		make_user("foames-sug-operator@example.com", "FoaMES Operator")
		with as_user("foames-sug-quality@example.com"), self.assertRaises(frappe.PermissionError):
			post_suggestion("A", "Other", "x", agent="ext")
		with as_user("foames-sug-operator@example.com"):
			name = post_suggestion("A", "Other", "x", agent="ext")
		self.assertEqual(
			frappe.db.get_value("Agent Suggestion", name, "owner"), "foames-sug-operator@example.com"
		)
