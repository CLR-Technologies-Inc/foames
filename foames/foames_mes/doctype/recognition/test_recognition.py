# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Recognition on a site: giving and withdrawing, privacy, the floor, milestones, credited ideas
and team highlights."""

import frappe
from frappe.utils import add_days, add_to_date, get_datetime, getdate

from foames.foames_mes.doctype.andon_call.andon_call import acknowledge_andon, raise_andon
from foames.foames_mes.doctype.andon_call_type.andon_call_type import create_default_call_types
from foames.foames_mes.doctype.recognition.recognition import (
	floor_recognitions,
	give_recognition,
	recognize_milestones,
	recognize_team_highlights,
	set_my_recognition_preferences,
	withdraw_recognition,
)
from foames.foames_mes.floor import floor_snapshot
from foames.foames_mes.recognition import last_complete_week
from foames.tests_compat import IntegrationTestCase
from foames.tests_helpers import as_user, make_machine, make_user

ANA = "t-rec-ana@example.com"
BO = "t-rec-bo@example.com"
CY = "t-rec-cy@example.com"
SUP = "t-rec-sup@example.com"


class TestRecognition(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		for user in (ANA, BO, CY):
			make_user(user, "FoaMES Operator")
		make_user(SUP, "FoaMES Supervisor")
		settings = frappe.get_single("Recognition Settings")
		settings.set("opt_out", [])
		settings.flags.ignore_permissions = True
		settings.save()

	def give(self, giver, **values):
		with as_user(giver):
			return give_recognition(**{"message": "Thanks for the help", **values})["name"]

	def test_kudos_stamps_giver_and_notifies(self):
		name = self.give(BO, recipient=ANA, team="Line 1")
		doc = frappe.get_doc("Recognition", name)
		self.assertEqual((doc.given_by, doc.recipient_type, doc.status), (BO, "Person", "Active"))
		self.assertTrue(doc.recognized_at)
		self.assertTrue(
			frappe.db.exists(
				"Notification Log", {"for_user": ANA, "document_type": "Recognition", "document_name": name}
			)
		)

	def test_team_recognition_without_a_person(self):
		name = self.give(BO, team="Night crew")
		self.assertEqual(frappe.db.get_value("Recognition", name, "recipient_type"), "Team")

	def test_nobody_recognizes_themselves(self):
		with self.assertRaises(frappe.ValidationError):
			self.give(ANA, recipient=ANA)

	def test_people_cannot_give_milestones(self):
		with self.assertRaises(frappe.ValidationError):
			self.give(BO, recipient=ANA, kind="Milestone")

	def test_fixed_once_given_and_withdrawn_only_by_giver_or_supervisor(self):
		name = self.give(BO, recipient=ANA)
		doc = frappe.get_doc("Recognition", name)
		doc.message = "Something else"
		with as_user(BO), self.assertRaises(frappe.ValidationError):
			doc.save()
		with as_user(CY), self.assertRaises(frappe.PermissionError):
			withdraw_recognition(name)
		with as_user(BO):
			self.assertEqual(withdraw_recognition(name)["status"], "Withdrawn")
		other = self.give(BO, recipient=CY)
		with as_user(SUP):
			self.assertEqual(withdraw_recognition(other)["status"], "Withdrawn")

	def test_private_is_seen_only_by_those_involved(self):
		name = self.give(BO, recipient=ANA, private=1)
		public = self.give(BO, recipient=ANA)
		for user, sees in ((ANA, True), (BO, True), (SUP, True), (CY, False)):
			with as_user(user):
				listed = set(frappe.get_list("Recognition", pluck="name"))
				self.assertEqual(name in listed, sees, user)
				self.assertIn(public, listed)
				self.assertEqual(frappe.has_permission("Recognition", "read", doc=name), sees, user)
		self.assertNotIn(name, [r["name"] for r in floor_recognitions()])

	def test_floor_shows_recent_and_respects_opt_out(self):
		name = self.give(BO, recipient=ANA, machine=make_machine("T-REC-M1").name)
		snapshot = floor_snapshot()
		self.assertIn(name, [r["name"] for r in snapshot["recognitions"]])
		with as_user(ANA):
			prefs = set_my_recognition_preferences(show_on_floor=0, milestones=1)
		self.assertEqual(prefs, {"show_on_floor": False, "milestones": True})
		self.assertNotIn(name, [r["name"] for r in floor_recognitions()])
		with as_user(ANA):
			set_my_recognition_preferences(show_on_floor=1, milestones=1)
		self.assertIn(name, [r["name"] for r in floor_recognitions()])

	def test_old_and_withdrawn_recognitions_leave_the_floor(self):
		old = self.give(BO, recipient=ANA)
		frappe.db.set_value("Recognition", old, "recognized_at", add_days(get_datetime(), -30))
		gone = self.give(BO, recipient=CY)
		with as_user(BO):
			withdraw_recognition(gone)
		shown = [r["name"] for r in floor_recognitions()]
		self.assertNotIn(old, shown)
		self.assertNotIn(gone, shown)

	def test_milestones_once_and_not_for_opted_out(self):
		create_default_call_types()
		machine = make_machine("T-REC-M2").name
		for _ in range(2):
			with as_user(SUP):
				call = raise_andon(machine, "Material")["name"]
			with as_user(ANA):
				acknowledge_andon(call)
			with as_user(CY):
				acknowledge_andon(raise_andon(machine, "Material")["name"])
		with as_user(CY):
			set_my_recognition_preferences(show_on_floor=1, milestones=0)
		created = recognize_milestones()
		mine = frappe.get_all(
			"Recognition", {"name": ("in", created), "recipient": ANA}, ["kind", "message", "given_by"]
		)
		self.assertEqual(len(mine), 1)
		self.assertEqual(
			(mine[0].kind, mine[0].message, mine[0].given_by),
			("Milestone", "First andon call answered", None),
		)
		self.assertFalse(frappe.db.exists("Recognition", {"recipient": CY, "kind": "Milestone"}))
		self.assertEqual(recognize_milestones(), [])

	def test_credited_idea_is_recognized_once_when_done(self):
		suggestion = frappe.get_doc(
			{
				"doctype": "Agent Suggestion",
				"title": "Stage the next coil during the run",
				"category": "Downtime",
				"severity": "Info",
				"suggestion": "Cuts the changeover by staging material early.",
				"credited_to": ANA,
			}
		).insert()
		self.assertFalse(frappe.db.exists("Recognition", {"recognition_key": f"idea:{suggestion.name}"}))
		suggestion.status = "Done"
		suggestion.save()
		suggestion.status = "Open"
		suggestion.save()
		suggestion.status = "Done"
		suggestion.save()
		rows = frappe.get_all(
			"Recognition",
			{"recognition_key": f"idea:{suggestion.name}"},
			["kind", "recipient", "reference_name"],
		)
		self.assertEqual(len(rows), 1)
		self.assertEqual(
			(rows[0].kind, rows[0].recipient, rows[0].reference_name), ("Improvement", ANA, suggestion.name)
		)

	def test_team_highlights_for_a_good_week(self):
		machine = make_machine("T-REC-M3", line="T-REC-LINE").name
		start, _end = last_complete_week(getdate())
		self.period(machine, start, oee=72, good=500, scrap=0)
		self.period(machine, add_days(start, -7), oee=60, good=480, scrap=12)
		created = recognize_team_highlights()
		keys = set(
			frappe.get_all(
				"Recognition", {"name": ("in", created), "team": "T-REC-LINE"}, pluck="recognition_key"
			)
		)
		week = start.isoformat()
		# 72 vs 60 OEE, no scrap, and quality from 97.6% (480 good, 12 scrap) to 100%.
		self.assertEqual(
			keys, {f"team:T-REC-LINE:{week}:{code}" for code in ("oee-up", "zero-scrap", "quality-up")}
		)
		self.assertFalse(
			[
				n
				for n in recognize_team_highlights()
				if frappe.db.get_value("Recognition", n, "team") == "T-REC-LINE"
			]
		)

	def test_a_bad_week_says_nothing(self):
		machine = make_machine("T-REC-M4", line="T-REC-LINE-2").name
		start, _end = last_complete_week(getdate())
		self.period(machine, start, oee=40, good=400, scrap=40)
		self.period(machine, add_days(start, -7), oee=70, good=480, scrap=5)
		recognize_team_highlights()
		self.assertFalse(frappe.db.exists("Recognition", {"team": "T-REC-LINE-2"}))

	def period(self, machine, day, oee, good, scrap, planned=600):
		"""An OEE Period with fixed figures, stored without recomputing it from machine events."""
		start = add_to_date(get_datetime(day), hours=6)
		doc = frappe.get_doc(
			{
				"doctype": "OEE Period",
				"machine": machine,
				"from_time": start,
				"to_time": add_to_date(start, minutes=planned),
				"planned_minutes": planned,
				"oee": oee,
				"good_count": good,
				"scrap_count": scrap,
			}
		)
		doc.set_new_name()
		doc.owner = doc.modified_by = "Administrator"
		doc.creation = doc.modified = get_datetime()
		doc.db_insert()
		return doc.name
