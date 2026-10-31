# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Entity specs: how a kernel reference type and its external id become an OData key and back. No
Frappe site needed."""

import unittest

from foames.foames_adapters.base import REFERENCE_TYPES
from foames.foames_adapters.s4hana.entities import (
	DEFAULT_ENTITIES,
	KEY_SEPARATOR,
	EntitySpec,
	spec_from_override,
)


class TestDefaults(unittest.TestCase):
	def test_defaults_are_kernel_reference_types(self):
		for reference_type in DEFAULT_ENTITIES:
			self.assertIn(reference_type, REFERENCE_TYPES)

	def test_every_default_has_a_service_an_entity_set_and_keys(self):
		for spec in DEFAULT_ENTITIES.values():
			self.assertTrue(spec.service and spec.entity_set and spec.key_fields)
			for key in spec.key_defaults:
				self.assertIn(key, spec.key_fields)

	def test_every_default_round_trips_its_own_key(self):
		for spec in DEFAULT_ENTITIES.values():
			values = {name: f"V{i}" for i, name in enumerate(spec.key_fields)}
			external_id = spec.external_id_for(values)
			self.assertEqual(spec.keys_for(external_id), values)

	def test_stock_movement_composite_key(self):
		spec = DEFAULT_ENTITIES["Stock Movement"]
		self.assertEqual(
			spec.keys_for("2026|4900000001"),
			{"MaterialDocumentYear": "2026", "MaterialDocument": "4900000001"},
		)
		with self.assertRaises(ValueError):
			spec.keys_for("4900000001")

	def test_work_order_label_is_the_material(self):
		spec = DEFAULT_ENTITIES["Work Order"]
		self.assertEqual(spec.label_for({"ManufacturingOrder": "1000123", "Material": "FG-1"}), "FG-1")
		self.assertEqual(spec.label_for({"ManufacturingOrder": "1000123"}), "1000123")
		self.assertEqual(spec.query(), {})

	def test_item_query_expands_descriptions(self):
		self.assertEqual(DEFAULT_ENTITIES["Item"].query(), {"$expand": "to_Description"})


class TestKeys(unittest.TestCase):
	spec = EntitySpec(service="S", entity_set="E", key_fields=("A", "B", "C"), key_defaults={"B": "X"})

	def test_full_and_short_forms(self):
		self.assertEqual(self.spec.keys_for("1|2|3"), {"A": "1", "B": "2", "C": "3"})
		self.assertEqual(self.spec.keys_for("1|3"), {"A": "1", "B": "X", "C": "3"})

	def test_wrong_part_counts(self):
		for external_id in ("1", "1|2|3|4", ""):
			with self.assertRaises(ValueError) as raised:
				self.spec.keys_for(external_id)
			self.assertIn("A|B|C", str(raised.exception))

	def test_external_id_uses_the_short_form_only_when_defaults_apply(self):
		self.assertEqual(self.spec.external_id_for({"A": "1", "B": "X", "C": "3"}), "1|3")
		self.assertEqual(self.spec.external_id_for({"A": "1", "C": "3"}), "1|3")
		self.assertEqual(self.spec.external_id_for({"A": "1", "B": "Y", "C": "3"}), "1|Y|3")

	def test_external_id_turns_missing_values_into_empty_strings(self):
		spec = EntitySpec(service="S", entity_set="E", key_fields=("A", "B"))
		self.assertEqual(spec.external_id_for({"A": "1"}), "1|")
		self.assertEqual(spec.external_id_for({"A": 7, "B": None}), "7|")

	def test_single_key_spec(self):
		spec = EntitySpec(service="S", entity_set="E", key_fields=("Product",))
		self.assertEqual(spec.keys_for("FG-1"), {"Product": "FG-1"})
		self.assertEqual(spec.external_id_for({"Product": "FG-1"}), "FG-1")

	def test_separator(self):
		self.assertEqual(KEY_SEPARATOR, "|")


class TestLabels(unittest.TestCase):
	spec = EntitySpec(
		service="S",
		entity_set="E",
		key_fields=("Product",),
		label_field="Name",
		label_text=("to_Description", "Language", "ProductDescription"),
	)

	def entity(self, *texts, **extra):
		entity = {"Product": "FG-1", "to_Description": {"results": [dict(t) for t in texts]}}
		entity.update(extra)
		return entity

	def test_language_match_is_case_insensitive(self):
		entity = self.entity({"Language": "en", "ProductDescription": "Foam"})
		self.assertEqual(self.spec.label_for(entity, "EN"), "Foam")
		self.assertEqual(self.spec.label_for(entity, "en"), "Foam")

	def test_empty_text_in_the_session_language_falls_back_to_another(self):
		entity = self.entity(
			{"Language": "EN", "ProductDescription": ""}, {"Language": "DE", "ProductDescription": "Schaum"}
		)
		self.assertEqual(self.spec.label_for(entity, "EN"), "Schaum")

	def test_no_texts_fall_back_to_the_label_field_then_the_key(self):
		self.assertEqual(self.spec.label_for(self.entity(Name="Named"), "EN"), "Named")
		self.assertEqual(self.spec.label_for(self.entity(), "EN"), "FG-1")
		self.assertEqual(self.spec.label_for({"Product": "FG-1"}, "EN"), "FG-1")

	def test_texts_in_the_wrong_shape_are_ignored(self):
		self.assertEqual(self.spec.label_for({"Product": "FG-1", "to_Description": None}), "FG-1")
		self.assertEqual(self.spec.label_for({"Product": "FG-1", "to_Description": {}}), "FG-1")

	def test_label_field_value_is_a_string(self):
		spec = EntitySpec(service="S", entity_set="E", key_fields=("K",), label_field="N")
		self.assertEqual(spec.label_for({"K": "1", "N": 42}), "42")


class TestOverrides(unittest.TestCase):
	def test_whitespace_is_trimmed_everywhere(self):
		spec = spec_from_override(
			{
				"service": " API_X_SRV ",
				"entity_set": " A_X ",
				"key_fields": " A , B ,, ",
				"optional_keys": " B , Z ",
				"label_field": " Name ",
			}
		)
		self.assertEqual(
			(spec.service, spec.entity_set, spec.key_fields, spec.label_field),
			("API_X_SRV", "A_X", ("A", "B"), "Name"),
		)
		self.assertEqual(spec.key_defaults, {"B": ""})  # Z is not a key, so it is not a default
		self.assertIsNone(spec.label_text)

	def test_missing_pieces(self):
		for row in (
			{"service": "", "entity_set": "E", "key_fields": "K"},
			{"service": "S", "entity_set": "E", "key_fields": " , "},
			{"service": "S", "entity_set": "E"},
			{"entity_set": "E", "key_fields": "K"},
		):
			with self.assertRaises(ValueError):
				spec_from_override(row)

	def test_optional_key_round_trip(self):
		spec = spec_from_override(
			{
				"service": "S",
				"entity_set": "E",
				"key_fields": "Material,Plant,Batch",
				"optional_keys": "Plant",
			}
		)
		self.assertEqual(spec.keys_for("M|B"), {"Material": "M", "Plant": "", "Batch": "B"})
		self.assertEqual(spec.external_id_for({"Material": "M", "Plant": "", "Batch": "B"}), "M|B")
		self.assertEqual(spec.external_id_for({"Material": "M", "Plant": "1010", "Batch": "B"}), "M|1010|B")

	def test_none_values_are_tolerated(self):
		spec = spec_from_override(
			{"service": "S", "entity_set": "E", "key_fields": "K", "optional_keys": None, "label_field": None}
		)
		self.assertEqual((spec.key_defaults, spec.label_field), ({}, ""))


if __name__ == "__main__":
	unittest.main()
