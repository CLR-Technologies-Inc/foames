# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import unittest
from datetime import datetime, timedelta, timezone

from foames.foames_adapters.insights_hub import production
from foames.foames_adapters.insights_hub.outbox import SEVERITY_ERROR, SEVERITY_INFORMATION
from foames.foames_adapters.insights_hub.production import RollUpOptions

CET = timezone(timedelta(hours=1))
START = datetime(2026, 11, 4, 10, 0)
END = datetime(2026, 11, 4, 10, 10)


class TestTimeSeriesPayload(unittest.TestCase):
	def test_counts_run_time_and_job(self):
		intervals = [(START, START + timedelta(minutes=4)), (START + timedelta(minutes=6), END)]
		payload = production.timeseries_payload(
			"a1",
			START,
			END,
			{"good": 120, "scrap": 3},
			intervals,
			RollUpOptions(tz=CET),
			job="1000123|0010",
			state="Running",
		)
		self.assertEqual((payload["entityId"], payload["propertySetName"]), ("a1", "FoaMESProduction"))
		self.assertEqual(
			payload["data"],
			[
				{
					"_time": "2026-11-04T09:10:00.000Z",
					"goodCount": 120.0,
					"scrapCount": 3.0,
					"runMinutes": 8.0,
					"windowMinutes": 10.0,
					"job": "1000123|0010",
					"state": "Running",
				}
			],
		)

	def test_renamed_variables_and_aspect(self):
		options = RollUpOptions(property_set="Prod", variables={"good": "ok", "scrap": "nok"})
		payload = production.timeseries_payload("a1", START, END, {"good": 1}, [], options)
		record = payload["data"][0]
		self.assertEqual(payload["propertySetName"], "Prod")
		self.assertEqual((record["ok"], record["nok"], record["runMinutes"]), (1.0, 0.0, 0.0))
		self.assertNotIn("job", record)
		self.assertNotIn("state", record)

	def test_nothing_to_report_queues_nothing(self):
		self.assertIsNone(production.timeseries_payload("a1", START, END, {}, [], RollUpOptions()))
		self.assertIsNone(
			production.timeseries_payload("a1", START, END, {"energy_kwh": 5}, [], RollUpOptions())
		)

	def test_run_time_alone_is_reported(self):
		payload = production.timeseries_payload("a1", START, END, {}, [(START, END)], RollUpOptions())
		self.assertEqual(payload["data"][0]["runMinutes"], 10.0)

	def test_naive_time_without_timezone_is_taken_as_utc(self):
		payload = production.timeseries_payload("a1", START, END, {"good": 1}, [], RollUpOptions())
		self.assertEqual(payload["data"][0]["_time"], "2026-11-04T10:10:00.000Z")


class TestWindows(unittest.TestCase):
	def test_window_end_reads_back_in_site_time(self):
		payload = production.timeseries_payload("a1", START, END, {"good": 1}, [], RollUpOptions(tz=CET))
		self.assertEqual(production.window_end(payload, CET), END)
		self.assertEqual(production.window_end(payload), END - timedelta(hours=1))
		self.assertIsNone(production.window_end({"data": []}))
		self.assertIsNone(production.window_end({"data": [{"_time": "junk"}]}))

	def test_window_key(self):
		self.assertEqual(production.window_key("Press 1", END), "Press 1:timeseries:2026-11-04 10:10:00")
		self.assertEqual(
			production.window_key("Press 1", END),
			production.window_key("Press 1", END.replace(microsecond=5)),
		)


class TestStateEvents(unittest.TestCase):
	def test_down_is_an_error_event(self):
		payload = production.state_event_payload("a1", "Press 1", "Down", "Running", END, CET)
		self.assertEqual(
			payload,
			{
				"entityId": "a1",
				"timestamp": "2026-11-04T09:10:00.000Z",
				"severity": SEVERITY_ERROR,
				"description": "Press 1 is Down (was Running)",
				"code": "FOAMES.STATE.DOWN",
				"source": "FoaMES",
				"acknowledged": False,
			},
		)

	def test_other_states_are_informational(self):
		payload = production.state_event_payload("a1", "Press 1", "Running", None, END, None)
		self.assertEqual(
			(payload["severity"], payload["description"]), (SEVERITY_INFORMATION, "Press 1 is Running")
		)

	def test_state_key_keeps_sub_second_precision(self):
		self.assertEqual(
			production.state_key("Press 1", "Down", END), "Press 1:state:Down:2026-11-04 10:10:00"
		)
		self.assertNotEqual(
			production.state_key("Press 1", "Running", END),
			production.state_key("Press 1", "Running", END.replace(microsecond=400000)),
		)


if __name__ == "__main__":
	unittest.main()
