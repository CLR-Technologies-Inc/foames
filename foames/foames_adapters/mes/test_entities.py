# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import unittest

from foames.foames_adapters.mes.entities import (
	BY_JSON,
	BY_ODATA,
	BY_PATH,
	BY_QUERY,
	EntitySpec,
	parse_query,
	spec_from_override,
	value_at,
)


class TestRequests(unittest.TestCase):
	def test_path_lookup_with_placeholder_and_without(self):
		spec = EntitySpec("parts/{id}/details", ("id",), lookup=BY_PATH)
		self.assertEqual(spec.request({"id": "A/1"}), ("parts/A%2F1/details", {}, True))
		plain = EntitySpec("parts", ("id",), lookup=BY_PATH, extra_query={"expand": "unit"})
		self.assertEqual(plain.request({"id": "A 1"}), ("parts/A%201", {"expand": "unit"}, True))

	def test_query_lookup_adds_keys_to_fixed_parameters(self):
		spec = EntitySpec("order/v1/orders", ("order",), lookup=BY_QUERY, extra_query={"plant": "{site}"})
		self.assertEqual(
			spec.request({"order": "1000123"}),
			("order/v1/orders", {"plant": "{site}", "order": "1000123"}, False),
		)

	def test_odata_lookup(self):
		spec = EntitySpec("Orders", ("Order", "Plant"), lookup=BY_ODATA)
		path, query, single = spec.request({"Order": "O'1", "Plant": "1010"})
		self.assertEqual((path, single), ("Orders", False))
		self.assertEqual(query, {"$filter": "Order eq 'O''1' and Plant eq '1010'", "$top": "2"})

	def test_json_filter_lookup(self):
		spec = EntitySpec("tables/t1/records", ("number",), lookup=BY_JSON)
		self.assertEqual(spec.request({"number": "7"})[1], {"filter": '{"number":"7"}'})

	def test_unknown_lookup(self):
		with self.assertRaises(ValueError):
			EntitySpec("x", ("id",), lookup="Magic").request({"id": "1"})


class TestKeysAndLabels(unittest.TestCase):
	spec = EntitySpec("batches", ("material", "batch"), label_field="description")

	def test_composite_key_round_trip(self):
		self.assertEqual(self.spec.keys_for("FG-1| B7 "), {"material": "FG-1", "batch": "B7"})
		self.assertEqual(self.spec.external_id_for({"material": "FG-1", "batch": "B7"}), "FG-1|B7")
		for bad in ("FG-1", "FG-1|B7|x", "|B7", "", None):
			with self.assertRaises(ValueError, msg=bad):
				self.spec.keys_for(bad)

	def test_label_and_dotted_paths(self):
		self.assertEqual(
			self.spec.label_for({"material": "FG-1", "batch": "B7", "description": "Lot 7"}), "Lot 7"
		)
		self.assertEqual(self.spec.label_for({"material": "FG-1", "batch": "B7"}), "FG-1|B7")
		record = {"material": {"description": "Foam", "tags": ["a", "b"]}}
		self.assertEqual(value_at(record, "material.description"), "Foam")
		self.assertEqual(value_at(record, "material.tags.1"), "b")
		self.assertIsNone(value_at(record, "material.missing"))
		self.assertIsNone(value_at(record, "material.tags.9"))


class TestOverrides(unittest.TestCase):
	def test_row_becomes_a_spec(self):
		spec = spec_from_override(
			{
				"path": " mdm/v1/parts ",
				"lookup": "Query",
				"key_fields": "number",
				"label_field": " name ",
				"extra_query": "a=1&plant={site}",
			}
		)
		self.assertEqual(
			(spec.path, spec.lookup, spec.key_fields, spec.label_field),
			("mdm/v1/parts", BY_QUERY, ("number",), "name"),
		)
		self.assertEqual(spec.extra_query, {"a": "1", "plant": "{site}"})

	def test_lookup_defaults_to_query(self):
		self.assertEqual(spec_from_override({"path": "p", "key_fields": "k"}).lookup, BY_QUERY)

	def test_bad_rows(self):
		for row in (
			{"key_fields": "k"},
			{"path": "p", "key_fields": " , "},
			{"path": "p", "key_fields": "k", "lookup": "Magic"},
			{"path": "p", "key_fields": "k", "extra_query": "=1"},
		):
			with self.assertRaises(ValueError, msg=row):
				spec_from_override(row)

	def test_parse_query(self):
		self.assertEqual(parse_query(""), {})
		self.assertEqual(parse_query("a=1\nb=x=y"), {"a": "1", "b": "x=y"})
		self.assertEqual(parse_query("flag"), {"flag": ""})


if __name__ == "__main__":
	unittest.main()
