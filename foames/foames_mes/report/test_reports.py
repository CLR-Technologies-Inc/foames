# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The script reports, the standard dashboard records the install creates, and who can see them."""

import frappe
from frappe.desk.query_report import run as run_report
from frappe.utils import add_days, getdate, now_datetime

from foames.foames_mes.api import record_events
from foames.tests_compat import IntegrationTestCase

WORKSPACES = {
	"FoaMES Operator": "FoaMES Operator",
	"FoaMES Supervisor": "FoaMES Supervisor",
	"FoaMES Maintenance": "FoaMES Maintenance",
	"FoaMES Quality": "FoaMES Quality",
	"FoaMES Integration": "FoaMES Integration",
}
REPORTS = (
	"OEE Trend",
	"Downtime Pareto",
	"MTBF and MTTR",
	"Suggestion Status",
	"Process Throughput",
	"ERP Outbox Health",
)
DASHBOARDS = ("FoaMES Plant", "FoaMES Maintenance", "FoaMES Quality", "FoaMES Integration")


def make_machine(code, **overrides):
	if frappe.db.exists("Machine", code):
		doc = frappe.get_doc("Machine", code)
		doc.update(overrides)
		doc.save()
		return doc
	values = {"doctype": "Machine", "code": code, "counter_rollover": 0}
	values.update(overrides)
	return frappe.get_doc(values).insert()


def make_reason(code, **overrides):
	if not frappe.db.exists("Downtime Reason", code):
		frappe.get_doc(
			{"doctype": "Downtime Reason", "code": code, "category": "Breakdown", **overrides}
		).insert()
	return code


def make_user(email, *roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": email.split("@")[0],
				"send_welcome_email": 0,
				"roles": [{"role": r} for r in roles],
			}
		).insert(ignore_permissions=True)
	else:
		user = frappe.get_doc("User", email)
		user.add_roles(*roles)
	return email


class TestDashboardRecords(IntegrationTestCase):
	"""Installing the app creates the roles, workspaces, cards, charts and dashboards."""

	def test_roles_exist(self):
		for role in ("FoaMES Supervisor", "FoaMES Maintenance"):
			self.assertTrue(frappe.db.exists("Role", role), role)

	def test_reports_are_installed(self):
		for name in REPORTS:
			self.assertTrue(frappe.db.exists("Report", name), name)
			self.assertEqual(frappe.db.get_value("Report", name, "report_type"), "Script Report")

	def test_workspaces_reference_existing_cards_and_charts(self):
		for name in WORKSPACES:
			doc = frappe.get_doc("Workspace", name)
			self.assertTrue(doc.public, name)
			self.assertTrue(doc.roles, f"{name} should be limited to its roles")
			for card in doc.number_cards:
				self.assertTrue(frappe.db.exists("Number Card", card.number_card_name), card.number_card_name)
			for chart in doc.charts:
				self.assertTrue(frappe.db.exists("Dashboard Chart", chart.chart_name), chart.chart_name)
			for shortcut in doc.shortcuts:
				if shortcut.type in ("DocType", "Report", "Dashboard", "Page"):
					self.assertTrue(
						frappe.db.exists(shortcut.type, shortcut.link_to), f"{name}: {shortcut.link_to}"
					)
			for link in doc.links:
				if link.type == "Link":
					self.assertTrue(frappe.db.exists(link.link_type, link.link_to), f"{name}: {link.link_to}")

	def test_dashboards_reference_existing_cards_and_charts(self):
		for name in DASHBOARDS:
			doc = frappe.get_doc("Dashboard", name)
			self.assertTrue(doc.is_standard)
			for chart in doc.charts:
				self.assertTrue(frappe.db.exists("Dashboard Chart", chart.chart), chart.chart)
			for card in doc.cards:
				self.assertTrue(frappe.db.exists("Number Card", card.card), card.card)

	def test_report_charts_point_at_installed_reports(self):
		charts = frappe.get_all(
			"Dashboard Chart",
			{"module": ("in", ("FoaMES MES", "FoaMES Adapters")), "chart_type": "Report"},
			["name", "report_name"],
		)
		self.assertGreaterEqual(len(charts), 10)
		for chart in charts:
			self.assertIn(chart.report_name, REPORTS, chart.name)


class TestReports(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		self.day = add_days(getdate(now_datetime()), -3)
		self.line = "T-LINE-" + frappe.generate_hash(length=4).upper()
		self.machine = make_machine(
			"T-RPT-A",
			line=self.line,
			ideal_cycle_seconds=60,
			scheduled_minutes_per_day=480,
			shift_start="06:00:00",
		).name
		self.other = make_machine("T-RPT-B", line=self.line, ideal_cycle_seconds=30).name
		make_reason("T-JAM", title="Jam", category="Breakdown")
		make_reason("T-CHG", title="Changeover", category="Changeover", counts_as_planned=1)
		d = self.day
		record_events(
			[
				{"machine": self.machine, "type": "State", "state": "Running", "timestamp": f"{d}T06:00:00"},
				{"machine": self.machine, "type": "Count", "value": 0, "timestamp": f"{d}T06:00:00"},
				{"machine": self.machine, "type": "Count", "value": 200, "timestamp": f"{d}T10:00:00"},
				{"machine": self.machine, "type": "State", "state": "Down", "timestamp": f"{d}T10:00:00"},
				{"machine": self.machine, "type": "State", "state": "Running", "timestamp": f"{d}T11:00:00"},
				{"machine": self.machine, "type": "Count", "value": 350, "timestamp": f"{d}T13:59:00"},
				{"machine": self.machine, "type": "State", "state": "Idle", "timestamp": f"{d}T14:00:00"},
			]
		)
		# The automatic stoppage gets a reason; a second, planned one is recorded by hand.
		for name in frappe.get_all(
			"Downtime Record", {"machine": self.machine, "status": "Closed"}, pluck="name"
		):
			frappe.db.set_value("Downtime Record", name, "reason", "T-JAM")
		frappe.get_doc(
			{
				"doctype": "Downtime Record",
				"machine": self.other,
				"reason": "T-CHG",
				"start_time": f"{d} 08:00:00",
				"end_time": f"{d} 08:30:00",
			}
		).insert()
		frappe.get_doc(
			{
				"doctype": "Downtime Record",
				"machine": self.other,
				"start_time": f"{d} 12:00:00",
				"end_time": f"{d} 12:20:00",
			}
		).insert()
		for m in (self.machine, self.other):
			frappe.get_doc(
				{
					"doctype": "OEE Period",
					"machine": m,
					"from_time": f"{d} 06:00:00",
					"to_time": f"{d} 14:00:00",
					"planned_minutes": 480,
				}
			).insert()
		self.filters = {"from_date": str(add_days(self.day, -1)), "to_date": str(self.day)}

	def execute(self, report, **filters):
		return run_report(report, filters, ignore_prepared_report=True)

	def test_oee_trend_by_machine_and_line(self):
		out = self.execute("OEE Trend", group_by="Machine", line=self.line, **self.filters)
		rows = {r["machine"]: r for r in out["result"] if isinstance(r, dict)}
		self.assertEqual(set(rows), {self.machine, self.other})
		a = rows[self.machine]
		self.assertAlmostEqual(a["run_minutes"], 420)
		self.assertAlmostEqual(a["availability"], 420 / 480 * 100, places=3)
		self.assertAlmostEqual(a["good_count"], 350)
		self.assertEqual(a["line"], self.line)
		self.assertEqual(out["chart"]["type"], "line")
		self.assertIn(self.machine, [d["name"] for d in out["chart"]["data"]["datasets"]])

		by_line = self.execute("OEE Trend", group_by="Line", line=self.line, **self.filters)
		line_rows = [r for r in by_line["result"] if isinstance(r, dict)]
		self.assertEqual(len(line_rows), 1)
		self.assertEqual(line_rows[0]["group"], self.line)
		self.assertEqual(line_rows[0]["periods"], 2)
		self.assertAlmostEqual(line_rows[0]["planned_minutes"], 960)
		# Only one machine ran, so the line's availability is the time-weighted 420 minutes of the 960
		# planned less the 30-minute planned changeover, not an average of two percentages.
		self.assertAlmostEqual(line_rows[0]["planned_downtime_minutes"], 30)
		self.assertAlmostEqual(line_rows[0]["availability"], 420 / 930 * 100, places=3)
		metric = self.execute("OEE Trend", group_by="Line", metric="Quality", line=self.line, **self.filters)
		self.assertEqual(metric["chart"]["data"]["datasets"][0]["values"][-1], 100.0)

	def test_downtime_pareto(self):
		out = self.execute("Downtime Pareto", group_by="Reason", line=self.line, **self.filters)
		rows = {r["label"]: r for r in out["result"] if isinstance(r, dict)}
		self.assertAlmostEqual(rows["T-JAM"]["minutes"], 60)
		self.assertAlmostEqual(rows["Unclassified"]["minutes"], 20)
		self.assertNotIn("T-CHG", rows)  # planned downtime is out unless asked for
		self.assertAlmostEqual(rows["T-JAM"]["cumulative_share"], 75)
		self.assertEqual(rows["T-JAM"]["title"], "Jam")
		self.assertEqual(out["chart"]["type"], "axis-mixed")
		with_planned = self.execute(
			"Downtime Pareto", group_by="Category", include_planned=1, line=self.line, **self.filters
		)
		cats = {r["label"]: r["minutes"] for r in with_planned["result"] if isinstance(r, dict)}
		self.assertAlmostEqual(cats["Changeover"], 30)
		self.assertAlmostEqual(cats["Breakdown"], 60)
		by_machine = self.execute("Downtime Pareto", group_by="Machine", line=self.line, **self.filters)
		self.assertEqual(next(r["label"] for r in by_machine["result"] if isinstance(r, dict)), self.machine)

	def test_mtbf_and_mttr(self):
		out = self.execute("MTBF and MTTR", line=self.line, **self.filters)
		rows = {r["machine"]: r for r in out["result"] if isinstance(r, dict)}
		a, b = rows[self.machine], rows[self.other]
		self.assertEqual(a["failures"], 1)
		self.assertAlmostEqual(a["mttr_minutes"], 60)
		# Two days of a 480-minute schedule, less the hour down, per failure.
		self.assertAlmostEqual(a["mtbf_hours"], (960 - 60) / 60, places=3)
		self.assertEqual(b["failures"], 1)  # the unclassified stop counts; the changeover does not
		self.assertAlmostEqual(b["mttr_minutes"], 20)
		self.assertIsNotNone(b["mtbf_hours"])
		only = self.execute("MTBF and MTTR", breakdowns_only=1, line=self.line, **self.filters)
		self.assertEqual(
			{r["machine"]: r["failures"] for r in only["result"] if isinstance(r, dict)}[self.other], 0
		)

	def test_suggestion_status(self):
		from foames.foames_mes.api import post_suggestion

		agent = "t-" + frappe.generate_hash(length=6)
		name = post_suggestion(
			"Check the jam", "Downtime", "Jams every hour.", agent=agent, rule_key=f"{agent}:1"
		)
		post_suggestion("Watch the scrap", "Quality", "Scrap is up.", agent=agent, rule_key=f"{agent}:2")
		doc = frappe.get_doc("Agent Suggestion", name)
		doc.status = "Done"
		doc.save()
		today = getdate(now_datetime())
		out = self.execute(
			"Suggestion Status",
			group_by="Agent",
			agent=agent,
			from_date=str(add_days(today, -1)),
			to_date=str(today),
		)
		rows = [r for r in out["result"] if isinstance(r, dict)]
		self.assertEqual(len(rows), 1)
		self.assertEqual((rows[0]["open"], rows[0]["done"], rows[0]["total"]), (1, 1, 2))
		self.assertAlmostEqual(rows[0]["acceptance"], 50)
		self.assertIsNotNone(rows[0]["median_hours"])
		by_cat = self.execute(
			"Suggestion Status",
			group_by="Category",
			agent=agent,
			from_date=str(add_days(today, -1)),
			to_date=str(today),
		)
		self.assertEqual(
			{r["group"] for r in by_cat["result"] if isinstance(r, dict)}, {"Downtime", "Quality"}
		)

	def test_process_throughput(self):
		log = frappe.get_doc(
			{
				"doctype": "Process Event Log",
				"title": "Report test log",
				"from_time": f"{self.day} 00:00:00",
				"to_time": f"{add_days(self.day, 1)} 00:00:00",
			}
		).insert()
		log.extract()
		out = self.execute("Process Throughput", event_log=log.name, interval="Daily")
		rows = [r for r in out["result"] if isinstance(r, dict)]
		self.assertTrue(rows)
		self.assertEqual(sum(r["cases"] for r in rows), log.case_count)
		self.assertEqual(out["chart"]["type"], "axis-mixed")
		weekly = self.execute("Process Throughput", event_log=log.name, interval="Weekly")
		self.assertEqual(sum(r["cases"] for r in weekly["result"] if isinstance(r, dict)), log.case_count)
		# Without a log named, the latest extracted one is used.
		latest = self.execute("Process Throughput")
		self.assertTrue([r for r in latest["result"] if isinstance(r, dict)])

	def test_erp_outbox_health(self):
		from foames.foames_adapters.doctype.s4hana_outbox.s4hana_outbox import enqueue

		payload = {
			"GoodsMovementCode": "02",
			"PostingDate": str(self.day),
			"to_MaterialDocumentItem": [{"Material": "T-MAT", "Plant": "1000", "QuantityInEntryUnit": "1"}],
		}
		name = enqueue("Goods Movement", payload, "t-health-" + frappe.generate_hash(length=6))
		frappe.db.set_value(
			"S4HANA Outbox", name, {"status": "Failed", "last_error": "HTTP 500 from the test", "attempts": 3}
		)
		posting = frappe.get_doc("S4HANA Outbox", name)
		out = self.execute("ERP Outbox Health")
		rows = [r for r in out["result"] if isinstance(r, dict)]
		failed = [r for r in rows if r["adapter"] == "S/4HANA" and r["status"] == "Failed"]
		self.assertEqual(len(failed), 1)
		self.assertGreaterEqual(failed[0]["count"], 1)
		self.assertGreaterEqual(failed[0]["max_attempts"], 3)
		self.assertIn("HTTP 500", failed[0]["last_error"] or "")
		self.assertIn("S/4HANA", out["chart"]["data"]["labels"])
		summary = {s["label"]: s for s in out["report_summary"]}
		self.assertGreaterEqual(summary["Failed"]["value"], 1)
		self.assertEqual(
			self.execute("ERP Outbox Health", adapter="ERPNext")["chart"]["data"]["labels"].count("S/4HANA"),
			0,
		)
		posting.delete(ignore_permissions=True)


class TestRoleAccess(IntegrationTestCase):
	"""Each role sees its own workspace and can run the reports on it."""

	def setUp(self):
		super().setUp()
		make_machine("T-RPT-ROLE")
		self.users = {
			"FoaMES Operator": make_user("t-operator@foames.test", "FoaMES Operator"),
			"FoaMES Supervisor": make_user("t-supervisor@foames.test", "FoaMES Supervisor"),
			"FoaMES Maintenance": make_user("t-maintenance@foames.test", "FoaMES Maintenance"),
			"FoaMES Quality": make_user("t-quality@foames.test", "FoaMES Quality"),
		}

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def visible_pages(self):
		# Frappe v16 lists the sidebar through get_workspaces and memoises it per request, so the
		# memo is dropped between users.
		try:
			from frappe.desk.desktop import get_workspaces as list_workspaces
		except ImportError:  # Frappe v15
			from frappe.desk.desktop import get_workspace_sidebar_items as list_workspaces
		cache = getattr(frappe.local, "request_cache", None)
		if cache is not None:
			cache.clear()
		return {p.name for p in list_workspaces()["pages"]}

	def test_each_role_sees_its_workspace_and_not_the_others(self):
		for role, user in self.users.items():
			frappe.set_user(user)
			pages = self.visible_pages()
			self.assertIn(WORKSPACES[role], pages, role)
			for other_role, other_page in WORKSPACES.items():
				if other_role != role:
					self.assertNotIn(other_page, pages, f"{role} sees {other_page}")

	def test_engineer_sees_the_supervisor_maintenance_and_quality_workspaces(self):
		frappe.set_user(make_user("t-engineer@foames.test", "FoaMES Engineer"))
		pages = self.visible_pages()
		for page in ("FoaMES Supervisor", "FoaMES Maintenance", "FoaMES Quality", "FoaMES Integration"):
			self.assertIn(page, pages)
		self.assertNotIn("FoaMES Operator", pages)

	def test_roles_can_run_their_reports(self):
		allowed = {
			"FoaMES Operator": ("OEE Trend", "Downtime Pareto"),
			"FoaMES Supervisor": (
				"OEE Trend",
				"Downtime Pareto",
				"MTBF and MTTR",
				"Suggestion Status",
				"Process Throughput",
			),
			"FoaMES Maintenance": ("OEE Trend", "Downtime Pareto", "MTBF and MTTR", "Suggestion Status"),
			"FoaMES Quality": ("OEE Trend", "Downtime Pareto", "Suggestion Status", "Process Throughput"),
		}
		for role, reports in allowed.items():
			frappe.set_user(self.users[role])
			for report in reports:
				out = run_report(report, {}, ignore_prepared_report=True)
				self.assertIn("columns", out, f"{role}: {report}")
			frappe.set_user("Administrator")

	def test_operator_cannot_run_the_outbox_report(self):
		frappe.set_user(self.users["FoaMES Operator"])
		with self.assertRaises((frappe.PermissionError, frappe.ValidationError)):
			run_report("ERP Outbox Health", {}, ignore_prepared_report=True)

	def test_supervisor_workspace_charts_and_cards_are_permitted(self):
		from frappe.desk.desktop import get_desktop_page

		frappe.set_user(self.users["FoaMES Supervisor"])
		page = get_desktop_page('{"name": "FoaMES Supervisor", "title": "FoaMES Supervisor"}')
		names = {c.get("chart_name") for c in page["charts"]["items"]}
		self.assertIn("OEE Trend by Line", names)
		self.assertIn("Suggestion Status by Category", names)
		cards = {c.get("number_card_name") for c in page["number_cards"]["items"]}
		self.assertIn("OEE Last 7 Days", cards)

	def test_number_cards_return_numbers(self):
		from frappe.desk.doctype.number_card.number_card import get_result

		for name in ("Machines Running", "Open Stoppages", "OEE Last 7 Days", "Open Suggestions"):
			doc = frappe.get_doc("Number Card", name)
			value = get_result(doc, doc.filters_json)
			self.assertIsInstance(value, float, name)
