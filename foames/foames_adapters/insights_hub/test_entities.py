# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

import unittest

from foames.foames_adapters.base import REFERENCE_TYPES
from foames.foames_adapters.insights_hub.entities import (
	BY_FILTER,
	BY_PATH,
	DEFAULT_ENTITIES,
	EntitySpec,
	spec_from_override,
	value_at,
)


class TestDefaults(unittest.TestCase):
	def test_defaults_are_kernel_types_on_asset_management(self):
		for reference_type, spec in DEFAULT_ENTITIES.items():
			self.assertIn(reference_type, REFERENCE_TYPES)
			self.assertEqual(spec.service, "assetmanagement/v3")
			self.assertEqual(spec.lookup, BY_PATH)
			self.assertEqual(len(spec.key_fields), 1)

	def test_path(self):
		self.assertEqual(DEFAULT_ENTITIES["Workstation"].path(), "assetmanagement/v3/assets")
		self.assertEqual(EntitySpec("/svc/v1/", "/things", ("id",)).path(), "svc/v1/things")


class TestKeys(unittest.TestCase):
	spec = EntitySpec("oi/v1", "batches", ("material", "batch"), lookup=BY_FILTER, label_field="description")

	def test_composite_key_round_trip(self):
		keys = self.spec.keys_for("FG-1| B7 ")
		self.assertEqual(keys, {"material": "FG-1", "batch": "B7"})
		self.assertEqual(self.spec.external_id_for({"material": "FG-1", "batch": "B7"}), "FG-1|B7")

	def test_wrong_arity_or_empty_part_is_refused(self):
		for bad in ("FG-1", "FG-1|B7|x", "|B7", "", None):
			with self.assertRaises(ValueError, msg=bad):
				self.spec.keys_for(bad)

	def test_label_falls_back_to_the_id(self):
		self.assertEqual(
			self.spec.label_for({"material": "FG-1", "batch": "B7", "description": "Lot 7"}), "Lot 7"
		)
		self.assertEqual(
			self.spec.label_for({"material": "FG-1", "batch": "B7", "description": ""}), "FG-1|B7"
		)
		self.assertEqual(EntitySpec("s", "r", ("id",)).label_for({"id": 5}), "5")

	def test_dotted_label_paths(self):
		asset = {"assetId": "a1", "location": {"locality": "Hamburg", "tags": ["x", "y"]}}
		self.assertEqual(value_at(asset, "location.locality"), "Hamburg")
		self.assertEqual(value_at(asset, "location.tags.1"), "y")
		self.assertIsNone(value_at(asset, "location.country"))
		self.assertIsNone(value_at(asset, "assetId.x"))
		self.assertEqual(
			EntitySpec("s", "r", ("assetId",), label_field="location.locality").label_for(asset), "Hamburg"
		)


class TestOverrides(unittest.TestCase):
	def test_row_becomes_a_spec(self):
		spec = spec_from_override(
			{
				"service": " oi/v1 ",
				"resource": "materials",
				"key_fields": "materialNumber",
				"lookup": "Path",
				"label_field": " name ",
			}
		)
		self.assertEqual(
			(spec.service, spec.resource, spec.key_fields, spec.lookup, spec.label_field),
			("oi/v1", "materials", ("materialNumber",), BY_PATH, "name"),
		)

	def test_lookup_defaults_to_path(self):
		self.assertEqual(
			spec_from_override({"service": "s", "resource": "r", "key_fields": "k"}).lookup, BY_PATH
		)

	def test_composite_keys_need_filter(self):
		with self.assertRaises(ValueError):
			spec_from_override({"service": "s", "resource": "r", "key_fields": "a, b", "lookup": "Path"})
		spec = spec_from_override({"service": "s", "resource": "r", "key_fields": "a, b", "lookup": "Filter"})
		self.assertEqual(spec.key_fields, ("a", "b"))

	def test_incomplete_rows_are_refused(self):
		for row in (
			{"resource": "r", "key_fields": "k"},
			{"service": "s", "key_fields": "k"},
			{"service": "s", "resource": "r", "key_fields": " , "},
			{"service": "s", "resource": "r", "key_fields": "k", "lookup": "Magic"},
		):
			with self.assertRaises(ValueError, msg=row):
				spec_from_override(row)


if __name__ == "__main__":
	unittest.main()
