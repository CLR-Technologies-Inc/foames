# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tulip's read API paths and queries, and a read through the framework's REST client against a
scripted Tulip. No site and no Tulip instance needed.

python -m unittest foames.foames_adapters.tulip.test_api
"""

import json
import unittest

from foames.foames_adapters.mes.fake import FakeMES, ok
from foames.foames_adapters.mes.rest import AUTH_BASIC, Connection, RestClient
from foames.foames_adapters.tulip import api as tulip
from foames.foames_adapters.tulip.profile import PROFILE


class TestPaths(unittest.TestCase):
	def test_with_and_without_workspace(self):
		self.assertEqual(tulip.tables_path(), "api/v3/tables")
		self.assertEqual(tulip.tables_path("DEFAULT"), "api/v3/w/DEFAULT/tables")
		self.assertEqual(tulip.records_path("T_orders", "ws1"), "api/v3/w/ws1/tables/T_orders/records")
		self.assertEqual(
			tulip.records_path("T_orders", None, "WO 1/2"), "api/v3/tables/T_orders/records/WO%201%2F2"
		)
		self.assertEqual(tulip.count_path("T_orders"), "api/v3/tables/T_orders/count")
		self.assertEqual(tulip.machines_path("ws1"), "api/v3/w/ws1/machines")
		self.assertEqual(tulip.stations_path(), "api/stations/v1/stations")

	def test_rejects_bad_ids(self):
		for bad in ("", "a/b", "x y", "../t"):
			with self.assertRaises(ValueError):
				tulip.records_path(bad)
		with self.assertRaises(ValueError):
			tulip.records_path("T", record=" ")


class TestQueries(unittest.TestCase):
	def test_records_query(self):
		query = tulip.records_query(
			limit=500,
			offset=20,
			filters=[
				{"field": "status", "functionType": "isIn", "arg": ["Open", "Running"]},
				{"field": "lot", "functionType": "notBlank"},
			],
			filter_aggregator="any",
			fields="id,status",
			sort=[{"sortBy": "_updatedAt", "sortDir": "desc"}],
		)
		self.assertEqual(query["limit"], 100)
		self.assertEqual(query["offset"], 20)
		self.assertEqual(
			json.loads(query["filters"]),
			[
				{"field": "status", "functionType": "isIn", "arg": ["Open", "Running"]},
				{"field": "lot", "functionType": "notBlank"},
			],
		)
		self.assertEqual(query["filterAggregator"], "any")
		self.assertEqual(json.loads(query["fields"]), ["id", "status"])
		self.assertEqual(json.loads(query["sortOptions"]), [{"sortBy": "_updatedAt", "sortDir": "desc"}])

	def test_dict_filters_are_equal_filters(self):
		query = tulip.records_query(filters={"order": "WO-1"})
		self.assertEqual(
			json.loads(query["filters"]), [{"field": "order", "functionType": "equal", "arg": "WO-1"}]
		)

	def test_invalid_filters(self):
		for filters in (
			[{"functionType": "equal", "arg": 1}],
			[{"field": "a", "functionType": "like", "arg": 1}],
			[{"field": "a", "functionType": "equal"}],
			[{"field": "a", "functionType": "isIn", "arg": "x"}],
			"not json",
		):
			with self.assertRaises(ValueError):
				tulip.records_query(filters=filters)
		with self.assertRaises(ValueError):
			tulip.records_query(filter_aggregator="some")
		with self.assertRaises(ValueError):
			tulip.records_query(limit=0)
		with self.assertRaises(ValueError):
			tulip.records_query(sort=[{"sortBy": "a", "sortDir": "up"}])

	def test_stations_query(self):
		query = tulip.stations_query(
			limit=10, sort="-lastModified.at,name", station_group="g'1", archived=True
		)
		self.assertEqual(query["filter"], "stationGroupId eq 'g''1'")
		self.assertEqual(query["archived"], "true")
		with self.assertRaises(ValueError):
			tulip.stations_query(sort="colour")

	def test_flatten_machines(self):
		answer = [
			{"id": "mt1", "name": "Press", "machines": [{"id": "m1", "name": "Press 1"}]},
			{"id": "mt2", "name": "Oven", "machines": None},
		]
		self.assertEqual(
			tulip.flatten_machines(answer),
			[{"id": "m1", "name": "Press 1", "machine_type_id": "mt1", "machine_type": "Press"}],
		)
		self.assertEqual(tulip.flatten_machines({"unexpected": True}), [])


class TestReadThroughTheClient(unittest.TestCase):
	def test_records_are_read_with_basic_auth_and_encoded_filters(self):
		fake = FakeMES().on("GET", "/tables/T_orders/records", ok([{"id": "WO-1", "status": "Open"}]))
		client = RestClient(
			Connection(
				base_url="https://acme.tulip.co",
				auth=AUTH_BASIC,
				username="key",
				password="secret",
				site="ws1",
			),
			transport=fake,
		)
		rows = client.get(
			tulip.records_path("T_orders", "ws1"),
			tulip.records_query(filters={"status": "Open"}, limit=5),
		)
		self.assertEqual(rows, [{"id": "WO-1", "status": "Open"}])
		request = fake.requests[0]
		self.assertEqual(request["method"], "GET")
		self.assertEqual(request["path"], "/api/v3/w/ws1/tables/T_orders/records")
		self.assertEqual(
			json.loads(request["query"]["filters"]),
			[{"field": "status", "functionType": "equal", "arg": "Open"}],
		)
		self.assertTrue(request["headers"]["Authorization"].startswith("Basic "))

	def test_profile_reads_the_workspace_from_site(self):
		self.assertIn("Workspace", PROFILE.site_label)
		self.assertIn("read-only", PROFILE.notes)


if __name__ == "__main__":
	unittest.main()
