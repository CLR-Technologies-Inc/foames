# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Instrument tags in the ANSI/ISA-5.1 identification-letter convention. Pure: no Frappe.

An instrument tag is a functional identification (letters) and a loop number, for example
`FIC-101` (flow indicating controller in loop 101), `PDT-2003A`, `10-LSHH-305` or `TT101`. The
first letter is the measured or initiating variable; it may be followed by variable modifiers
(D differential, F ratio, J scan, K time rate of change, Q integrate or totalize, S safety);
the succeeding letters are readout, passive and output functions (I indicate, C control,
T transmit, V valve, ...) and function modifiers (H high, L low, M middle).

Letters marked "user's choice" in the standard (B, C, D, M, N, O as first letters, and so on)
are reported as such; a plant's own legend can override any meaning with `legend=`.

Where the standard leaves an ambiguity the parser resolves it the way P&IDs commonly do and
documents it here:

- `S` straight after the first letter is the safety modifier when it ends the tag or is
  followed only by `V` or `E` (PSV, TSE), otherwise it is the switch function (LSH, PSLL).
- `F` straight after the first letter is the ratio modifier only when the first letter is `F`
  (FFIC); elsewhere it is not a valid succeeding letter and the tag is flagged.
- `D`, `J`, `K` and `Q` straight after the first letter are always variable modifiers.
- `H`, `L` and `M` after a function letter modify it (LSHH: switch high-high; LAL: alarm
  low). `L` with no function before it is the light (pilot lamp) readout, as in `HL`.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

# First letter: measured or initiating variable (ISA-5.1-2009, table 4.1).
FIRST_LETTERS = {
	"A": "Analysis",
	"B": "Burner, combustion",
	"C": "User's choice",
	"D": "User's choice",
	"E": "Voltage",
	"F": "Flow, flow rate",
	"G": "User's choice",
	"H": "Hand",
	"I": "Current",
	"J": "Power",
	"K": "Time, schedule",
	"L": "Level",
	"M": "User's choice",
	"N": "User's choice",
	"O": "User's choice",
	"P": "Pressure",
	"Q": "Quantity",
	"R": "Radiation",
	"S": "Speed, frequency",
	"T": "Temperature",
	"U": "Multivariable",
	"V": "Vibration, machine analysis",
	"W": "Weight, force",
	"X": "Unclassified",
	"Y": "Event, state, presence",
	"Z": "Position, dimension",
}

# Modifiers of the first letter.
VARIABLE_MODIFIERS = {
	"D": "Differential",
	"F": "Ratio",
	"J": "Scan",
	"K": "Time rate of change",
	"Q": "Integrate, totalize",
	"S": "Safety",
}

# Succeeding letters: readout or passive function and output function.
FUNCTION_LETTERS = {
	"A": "Alarm",
	"B": "User's choice",
	"C": "Control",
	"E": "Sensor, primary element",
	"G": "Glass, gauge, viewing device",
	"I": "Indicate",
	"K": "Control station",
	"L": "Light",
	"N": "User's choice",
	"O": "Orifice, restriction",
	"P": "Point, test connection",
	"Q": "Integrate, totalize",
	"R": "Record",
	"S": "Switch",
	"T": "Transmit",
	"U": "Multifunction",
	"V": "Valve, damper, louver",
	"W": "Well, probe",
	"X": "Unclassified",
	"Y": "Compute, convert, relay",
	"Z": "Driver, actuator, final control element",
}

# Modifiers of a function letter.
FUNCTION_MODIFIERS = {"H": "High", "L": "Low", "M": "Middle, intermediate"}

# Which functions a tag carries, by kind: lets the register say whether a tag reads a value
# (and so should be tied to a Measurement), switches, alarms or acts.
READOUT = set("AEGILOPRWU")
OUTPUT = set("CKSTVYZ")

# Prefix (optional area or unit number), letters, separator, loop number, optional suffix.
_TAG = re.compile(
	r"""^\s*
	(?:(?P<area>[0-9][0-9A-Z]{0,5})-)?       # optional area or unit number, e.g. 10- or 2U-
	(?P<letters>[A-Z]{1,6})
	-?
	(?P<loop>[0-9]{1,6}(?:\.[0-9]{1,4})?)    # loop number, DEXPI style 4712.01 included
	(?P<suffix>[A-Z]{0,2})                   # parallel instruments A, B, ...
	(?:-(?P<extra>[0-9A-Z]{1,6}))?           # optional trailing qualifier
	\s*$""",
	re.VERBOSE,
)


@dataclass
class InstrumentTag:
	tag: str
	letters: str
	loop_number: str
	area: str = ""
	suffix: str = ""
	first_letter: str = ""
	variable: str = ""
	variable_modifiers: list[str] = field(default_factory=list)
	functions: list[str] = field(default_factory=list)
	meaning: str = ""
	reads_value: bool = False
	is_switch: bool = False
	is_alarm: bool = False
	is_final_element: bool = False
	warnings: list[str] = field(default_factory=list)

	@property
	def loop(self) -> str:
		"""The loop identifier: first letter plus loop number (and area), e.g. `F-101`."""
		base = f"{self.first_letter}-{self.loop_number}"
		return f"{self.area}-{base}" if self.area else base

	def as_dict(self) -> dict:
		data = asdict(self)
		data["loop"] = self.loop
		return data


def _suffix(suffix: str | None, extra: str | None) -> str:
	if extra and not suffix and extra.isalpha() and len(extra) <= 2:
		return extra  # "TT-101-A": a parallel-instrument letter written after a hyphen
	return (suffix or "") + (f"-{extra}" if extra else "")


class TagError(ValueError):
	pass


def normalise(tag: str) -> str:
	"""Uppercase and trimmed, with runs of spaces, hyphens and underscores collapsed to one hyphen.

	Dots are kept: they belong to loop numbers such as `4712.01`.
	"""
	return re.sub(r"[-_ ]+", "-", (tag or "").strip().upper()).strip("-")


def tag_key(text: str) -> str:
	"""Letters and digits only, uppercase: `FIC-101`, `fic_101` and `FIC101` share the key `FIC101`."""
	return re.sub(r"[^0-9A-Z]", "", (text or "").upper())


def parse_tag(tag: str, legend: dict | None = None) -> InstrumentTag:
	"""Parse an instrument tag. Raises TagError when it does not look like one.

	`legend` maps letters to a plant's own meanings for the user's-choice letters, as
	{"first": {"M": "Moisture"}, "function": {"B": "Blind"}}.
	"""
	text = normalise(tag)
	match = _TAG.match(text)
	if not match:
		raise TagError(f"{tag!r} is not an instrument tag (letters followed by a loop number)")
	letters = match["letters"]
	area = match["area"] or ""
	legend = legend or {}
	first_names = {**FIRST_LETTERS, **(legend.get("first") or {})}
	function_names = {**FUNCTION_LETTERS, **(legend.get("function") or {})}

	result = InstrumentTag(
		tag=text,
		letters=letters,
		loop_number=match["loop"],
		area=area,
		suffix=_suffix(match["suffix"], match["extra"]),
		first_letter=letters[0],
		variable=first_names.get(letters[0], ""),
	)
	if letters[0] not in first_names:
		result.warnings.append(f"{letters[0]} is not a first letter")

	rest = letters[1:]
	# Variable modifiers straight after the first letter.
	while rest:
		letter = rest[0]
		if letter in ("D", "J", "K", "Q"):
			result.variable_modifiers.append(VARIABLE_MODIFIERS[letter])
		elif letter == "F" and letters[0] == "F" and not result.variable_modifiers:
			result.variable_modifiers.append(VARIABLE_MODIFIERS["F"])
		elif letter == "S" and rest[1:] and set(rest[1:]) <= {"V", "E"} and not result.variable_modifiers:
			result.variable_modifiers.append(VARIABLE_MODIFIERS["S"])
		else:
			break
		rest = rest[1:]

	# Functions, each optionally followed by H/L/M modifiers.
	functions: list[str] = []
	for letter in rest:
		last = next((f for f in reversed(functions) if not f.endswith("*")), "")
		if letter in FUNCTION_MODIFIERS and last in ("A", "S", "L", "I", "C", "Y"):
			functions.append(letter + "*")
			continue
		if letter in function_names:
			functions.append(letter)
		else:
			result.warnings.append(f"{letter} is not a succeeding letter")
	names: list[str] = []
	for item in functions:
		if item.endswith("*"):
			modifier = FUNCTION_MODIFIERS[item[0]]
			names[-1] = f"{names[-1]} {modifier.split(',')[0].lower()}"
			continue
		names.append(function_names[item])
	result.functions = [f for f in functions if not f.endswith("*")]
	plain = set(result.functions)
	result.reads_value = bool(plain & {"I", "R", "T", "C", "U"})
	result.is_switch = "S" in plain
	result.is_alarm = "A" in plain
	result.is_final_element = bool(plain & {"V", "Z"})

	words = [result.variable.split(",")[0]]
	for modifier in result.variable_modifiers:
		word = modifier.split(",")[0].lower()
		if modifier == "Differential":
			words.insert(0, modifier)  # differential pressure
		else:
			words.append(word)  # pressure safety, flow ratio, flow integrate
	words += [n.split(",")[0].lower() for n in names]
	result.meaning = " ".join(w if i == 0 else w.lower() for i, w in enumerate(words)).strip()
	result.meaning = result.meaning[:1].upper() + result.meaning[1:]
	return result


def try_parse_tag(tag: str, legend: dict | None = None) -> InstrumentTag | None:
	try:
		return parse_tag(tag, legend)
	except TagError:
		return None


def compose_tag(category: str, functions: str, number: str, modifier: str = "", separator: str = "") -> str:
	"""Build a tag from DEXPI-style parts: category letter, modifier, function letters, loop number.

	DEXPI files write the parts without a separator (`PI4712.01`), and that is the default.
	"""
	letters = f"{category or ''}{modifier or ''}{functions or ''}".upper().replace(" ", "")
	number = (number or "").strip()
	return f"{letters}{separator}{number}" if number else letters
