# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The tag register (instrument index and equipment list) as CSV. Pure: no Frappe.

Plants keep their instrument index in a spreadsheet long before any P&ID tool exports DEXPI, so
FoaMES reads and writes the register as CSV. Column headers are matched loosely ("Tag",
"Tag No.", "Tag Number" all mean the tag); unknown columns are kept as attributes.
"""

from __future__ import annotations

import csv
import io
import re

from foames.foames_pid.isa51 import normalise, try_parse_tag

COLUMNS = [
	"tag",
	"component_type",
	"component_class",
	"description",
	"drawing",
	"plant_area",
	"parent_tag",
	"loop_number",
	"machine",
	"event_type",
	"signal_name",
	"signal_source",
	"signal_address",
	"historian_tag",
	"engineering_unit",
	"range_low",
	"range_high",
]

ALIASES = {
	"tag": ("tag", "tag no", "tag number", "tag name", "tagname", "instrument tag", "item tag"),
	"component_type": ("type", "component type", "item type", "category"),
	"component_class": ("class", "component class", "instrument type", "equipment type", "dexpi class"),
	"description": ("description", "service", "service description", "name"),
	"drawing": ("drawing", "p&id", "pid", "p&id no", "p&id number", "drawing number", "drawing no"),
	"plant_area": ("area", "plant area", "unit", "process unit"),
	"parent_tag": ("parent", "parent tag", "equipment", "line", "line number", "located on"),
	"loop_number": ("loop", "loop no", "loop number"),
	"machine": ("machine", "foames machine"),
	"event_type": ("event type", "signal type"),
	"signal_name": ("signal", "signal name", "measurement", "measurement name", "counter"),
	"signal_source": ("source", "signal source", "protocol"),
	"signal_address": (
		"address",
		"signal address",
		"node id",
		"opc ua node",
		"scada tag",
		"plc address",
		"io address",
	),
	"historian_tag": ("historian", "historian tag", "pi tag", "pi point"),
	"engineering_unit": ("unit of measure", "uom", "eu", "engineering unit", "units"),
	"range_low": ("range low", "lrv", "lower range", "range min", "min"),
	"range_high": ("range high", "urv", "upper range", "range max", "max"),
}

COMPONENT_TYPES = ("Equipment", "Instrument", "Line", "Valve", "Actuator", "Other")


class RegisterError(ValueError):
	pass


def _header_key(header: str) -> str:
	return re.sub(r"[^a-z0-9&]+", " ", (header or "").lower()).strip()


def _column_for(header: str) -> str:
	key = _header_key(header)
	for column, names in ALIASES.items():
		if key == column.replace("_", " ") or key in names:
			return column
	return ""


def _float(value: str, field: str, line: int):
	value = (value or "").strip()
	if value == "":
		return None
	# 1,250.5 (thousands separator) or 12,5 (decimal comma)
	value = value.replace(",", "") if "." in value else value.replace(",", ".")
	try:
		return float(value)
	except ValueError:
		raise RegisterError(f"Row {line}: {field} {value!r} is not a number")


def guess_type(tag: str) -> str:
	"""Instrument when the tag reads as an ISA-5.1 instrument with functions, otherwise Equipment."""
	parsed = try_parse_tag(tag)
	if parsed and parsed.functions:
		return "Valve" if parsed.is_final_element and not parsed.reads_value else "Instrument"
	return "Equipment"


def read_register(text: str) -> tuple[list[dict], list[str]]:
	"""Rows of the register as dicts keyed by COLUMNS (plus `attributes`), and warnings."""
	if not text or not text.strip():
		raise RegisterError("The register is empty")
	text = text.lstrip("\ufeff")
	header_line = text.splitlines()[0]
	# The header has no quoted delimiters in practice; the commonest of the three wins, comma on a tie.
	delimiter = max((",", ";", "\t"), key=lambda d: (header_line.count(d), d == ","))
	reader = csv.reader(io.StringIO(text), delimiter=delimiter)
	try:
		headers = next(reader)
	except StopIteration:
		raise RegisterError("The register is empty")
	columns = [_column_for(h) for h in headers]
	if "tag" not in columns:
		raise RegisterError("The register needs a Tag column")
	rows: list[dict] = []
	warnings: list[str] = []
	seen: set[str] = set()
	for line, values in enumerate(reader, start=2):
		if not any(v.strip() for v in values):
			continue
		row: dict = {"attributes": {}}
		for header, column, value in zip(headers, columns, values, strict=False):
			value = value.strip()
			if column:
				row[column] = value
			elif header.strip() and value:
				row["attributes"][header.strip()] = value
		tag = normalise(row.get("tag") or "")
		if not tag:
			warnings.append(f"Row {line}: no tag, skipped")
			continue
		if tag in seen:
			warnings.append(f"Row {line}: tag {tag} repeats an earlier row, skipped")
			continue
		seen.add(tag)
		row["tag"] = tag
		kind = (row.get("component_type") or "").strip().title()
		row["component_type"] = kind if kind in COMPONENT_TYPES else guess_type(tag)
		for field in ("range_low", "range_high"):
			row[field] = _float(row.get(field) or "", field, line)
		if row.get("parent_tag"):
			row["parent_tag"] = normalise(row["parent_tag"])
		rows.append(row)
	return rows, warnings


def write_register(rows: list[dict]) -> str:
	out = io.StringIO()
	writer = csv.writer(out, lineterminator="\n")
	writer.writerow(COLUMNS)
	for row in rows:
		writer.writerow(["" if row.get(c) is None else row.get(c) for c in COLUMNS])
	return out.getvalue()
