# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Draw a P&ID view as SVG, with live values overlaid. Pure: no Frappe.

The view is the plain data `dexpi.PlantDiagram.view()` returns, or `auto_layout()` builds for a
drawing typed in by hand: an extent in drawing units with Y growing upwards (as in DEXPI), the
drawn items with positions, and the lines as polylines. The symbols are simplified generic
shapes in the spirit of ISA-5.1 and ISO 10628 (a bubble for an instrument, with a bar for one in
a central control room; a bow tie for a valve; a circle for a pump; a vessel outline), not the
originating tool's own symbol catalogue. The drawing stays the source of truth; this view is for
seeing the plant's live state on the layout people know.

Every tagged element is a `<g class="pid-item" data-tag="...">`, so the page can attach clicks and
an agent can read the SVG without parsing geometry. Nothing here touches the plant.
"""

from __future__ import annotations

from xml.sax.saxutils import escape, quoteattr

from foames.foames_pid.isa51 import try_parse_tag

PUMPS = ("Pump", "Compressor", "Blower", "Fan", "Ejector")
VESSELS = ("Tank", "Vessel", "Column", "Drum", "Tower", "Silo", "Reactor", "Separator")
EXCHANGERS = ("HeatExchanger", "Cooler", "Heater", "Condenser", "Reboiler", "Evaporator")

STYLE = """
.pid { font-family: var(--font-stack, system-ui, sans-serif); }
.pid .sheet { fill: var(--bg-color, #fff); stroke: var(--border-color, #ccc); }
.pid .line { fill: none; stroke: var(--text-muted, #555); }
.pid .line.Process { stroke-width: 0.5; }
.pid .line.Measuring, .pid .line.Signal { stroke-width: 0.25; stroke-dasharray: 1.5 1; }
.pid .sym { fill: var(--bg-color, #fff); stroke: var(--text-color, #222); stroke-width: 0.35; }
.pid .lbl { fill: var(--text-color, #222); text-anchor: middle; dominant-baseline: middle; }
.pid .val { fill: var(--text-color, #222); text-anchor: middle; font-weight: 600; }
.pid .pid-item { cursor: pointer; }
.pid .pid-item:hover .sym { stroke: #1565c0; stroke-width: 0.6; }
.pid .Running .sym { fill: #c8e6c9; } .pid .Idle .sym { fill: #fff3c4; }
.pid .Down .sym { fill: #ffcdd2; } .pid .Setup .sym { fill: #bbdefb; } .pid .Unknown .sym { fill: #e0e0e0; }
.pid .flag-high .val, .pid .flag-low .val { fill: #c62828; }
.pid .flag-stale .val { fill: #757575; font-style: italic; }
"""


def _num(value: float) -> str:
	return f"{value:.2f}".rstrip("0").rstrip(".")


def _fmt_value(value) -> str:
	if isinstance(value, int | float):
		magnitude = abs(value)
		if magnitude >= 1000:
			return f"{value:,.0f}"
		if magnitude >= 10:
			return f"{value:.1f}"
		return f"{value:.2f}"
	return str(value)


class _Canvas:
	def __init__(self, extent):
		self.min_x, self.min_y, self.max_x, self.max_y = (float(v) for v in extent)
		self.width = max(self.max_x - self.min_x, 1.0)
		self.height = max(self.max_y - self.min_y, 1.0)
		self.unit = max(self.width, self.height) / 100.0  # symbol scale: 1% of the sheet
		self.parts: list[str] = []

	def x(self, x: float) -> float:
		return x - self.min_x

	def y(self, y: float) -> float:
		return self.max_y - y  # DEXPI's Y grows upwards, SVG's downwards

	def add(self, text: str) -> None:
		self.parts.append(text)


def _symbol(c: _Canvas, item: dict, x: float, y: float) -> str:
	s = c.unit
	kind = item.get("kind")
	cls = item.get("component_class") or ""
	if kind == "Instrument":
		r = s * 0.9
		parts = [f'<circle class="sym" cx="{_num(x)}" cy="{_num(y)}" r="{_num(r)}"/>']
		if (item.get("location") or "").lower().startswith("central"):
			parts.append(
				f'<line class="sym" x1="{_num(x - r)}" y1="{_num(y)}" x2="{_num(x + r)}" y2="{_num(y)}"/>'
			)
		parsed = try_parse_tag(item.get("tag") or "")
		top, bottom = (parsed.letters, parsed.loop_number) if parsed else (item.get("tag") or "", "")
		size = s * (0.55 if len(top) <= 4 else 0.42)
		parts.append(
			f'<text class="lbl" x="{_num(x)}" y="{_num(y - r * 0.4)}" font-size="{_num(size)}">{escape(top)}</text>'
		)
		if bottom:
			parts.append(
				f'<text class="lbl" x="{_num(x)}" y="{_num(y + r * 0.45)}" font-size="{_num(s * 0.42)}">{escape(bottom)}</text>'
			)
		return "".join(parts)
	if kind == "Valve":
		w, h = s * 0.8, s * 0.5
		return (
			f'<polygon class="sym" points="{_num(x - w)},{_num(y - h)} {_num(x + w)},{_num(y + h)} '
			f'{_num(x + w)},{_num(y - h)} {_num(x - w)},{_num(y + h)}"/>'
		)
	if kind == "OffPage":
		w, h = s * 1.4, s * 0.6
		return (
			f'<polygon class="sym" points="{_num(x - w)},{_num(y - h)} {_num(x + w * 0.5)},{_num(y - h)} '
			f'{_num(x + w)},{_num(y)} {_num(x + w * 0.5)},{_num(y + h)} {_num(x - w)},{_num(y + h)}"/>'
		)
	if kind == "Actuator":
		return f'<rect class="sym" x="{_num(x - s * 0.4)}" y="{_num(y - s * 0.4)}" width="{_num(s * 0.8)}" height="{_num(s * 0.8)}"/>'
	if kind == "Equipment":
		if any(word in cls for word in PUMPS):
			r = s * 1.6
			return (
				f'<circle class="sym" cx="{_num(x)}" cy="{_num(y)}" r="{_num(r)}"/>'
				f'<polyline class="sym" fill="none" points="{_num(x - r * 0.5)},{_num(y - r * 0.85)} '
				f'{_num(x + r)},{_num(y)} {_num(x - r * 0.5)},{_num(y + r * 0.85)}"/>'
			)
		if any(word in cls for word in VESSELS):
			w, h = s * 4.0, s * 7.0
			return f'<rect class="sym" x="{_num(x - w / 2)}" y="{_num(y - h / 2)}" width="{_num(w)}" height="{_num(h)}" rx="{_num(w / 2)}"/>'
		if any(word in cls for word in EXCHANGERS):
			r = s * 1.8
			return (
				f'<circle class="sym" cx="{_num(x)}" cy="{_num(y)}" r="{_num(r)}"/>'
				f'<polyline class="sym" fill="none" points="{_num(x - r)},{_num(y)} {_num(x - r / 3)},{_num(y - r / 2)} '
				f'{_num(x + r / 3)},{_num(y + r / 2)} {_num(x + r)},{_num(y)}"/>'
			)
		w, h = s * 4.0, s * 2.6
		return f'<rect class="sym" x="{_num(x - w / 2)}" y="{_num(y - h / 2)}" width="{_num(w)}" height="{_num(h)}" rx="{_num(s * 0.4)}"/>'
	return ""


def _label_offset(c: _Canvas, item: dict) -> tuple[float, float] | None:
	kind = item.get("kind")
	cls = item.get("component_class") or ""
	if kind == "Equipment":
		if any(word in cls for word in VESSELS):
			return 0.0, c.unit * 4.4
		return 0.0, c.unit * 2.6
	if kind == "Valve":
		return 0.0, c.unit * 1.3
	return None


def render_svg(view: dict, overlay: dict | None = None, descriptions: dict | None = None) -> str:
	"""An SVG document for `view`, with `overlay` ({tag: {state, value, unit, flag}}) applied."""
	overlay = overlay or {}
	descriptions = descriptions or {}
	c = _Canvas(view.get("extent") or (0, 0, 420, 297))
	c.add(
		f'<svg xmlns="http://www.w3.org/2000/svg" class="pid" viewBox="0 0 {_num(c.width)} {_num(c.height)}" '
		f'preserveAspectRatio="xMidYMid meet" role="img"><style>{STYLE}</style>'
		f'<rect class="sheet" x="0" y="0" width="{_num(c.width)}" height="{_num(c.height)}"/>'
	)
	for line in view.get("lines") or []:
		points = " ".join(f"{_num(c.x(p[0]))},{_num(c.y(p[1]))}" for p in line.get("points") or [])
		if not points:
			continue
		tag_attr = f" data-line={quoteattr(line['tag'])}" if line.get("tag") else ""
		c.add(f'<polyline class="line {escape(line.get("kind") or "Process")}"{tag_attr} points="{points}"/>')

	for item in view.get("items") or []:
		if item.get("x") is None or item.get("y") is None:
			continue
		kind = item.get("kind")
		if kind in ("Nozzle", "Piping") or (kind == "Equipment" and item.get("parent_id")):
			continue  # drawn as part of their line or equipment
		x, y = c.x(float(item["x"])), c.y(float(item["y"]))
		symbol = _symbol(c, item, x, y)
		if not symbol:
			continue
		tag = item.get("tag") or ""
		live = overlay.get(tag) or {}
		classes = ["pid-item", f"pid-{(kind or 'other').lower()}"]
		if live.get("state"):
			classes.append(str(live["state"]))
		if live.get("flag"):
			classes.append(f"flag-{live['flag']}")
		attrs = f' class="{" ".join(escape(cl) for cl in classes)}"'
		if tag:
			attrs += f" data-tag={quoteattr(tag)}"
		else:
			attrs = ' class="pid-untagged"'
		title = tag + (f" - {descriptions[tag]}" if descriptions.get(tag) else "")
		body = [f"<title>{escape(title)}</title>" if title else "", symbol]
		offset = _label_offset(c, item)
		if tag and offset:
			body.append(
				f'<text class="lbl" x="{_num(x + offset[0])}" y="{_num(y + offset[1])}" font-size="{_num(c.unit * 0.8)}">{escape(tag)}</text>'
			)
		value_text = ""
		if live.get("value") is not None:
			value_text = f"{_fmt_value(live['value'])} {live.get('unit') or ''}".strip()
		elif live.get("state") and kind == "Equipment":
			value_text = str(live["state"])
		if value_text:
			below = c.unit * (2.0 if kind == "Instrument" else 5.4 if kind == "Equipment" else 2.4)
			body.append(
				f'<text class="val" x="{_num(x)}" y="{_num(y + below)}" font-size="{_num(c.unit * 0.75)}">{escape(value_text)}</text>'
			)
		c.add(f"<g{attrs}>{''.join(body)}</g>")
	c.add("</svg>")
	return "".join(c.parts)


def _anchor(tag: str, by_tag: dict, positions: dict, line_source: dict) -> str:
	"""The placed equipment a component hangs from, following parents through lines and loops."""
	seen = {tag}
	current = (by_tag.get(tag) or {}).get("parent_tag") or ""
	while current and current not in seen:
		seen.add(current)
		if current in positions:
			return current
		if line_source.get(current) in positions:
			return line_source[current]
		current = (by_tag.get(current) or {}).get("parent_tag") or ""
	return ""


def auto_layout(components: list[dict], connections: list[dict]) -> dict:
	"""A view for a drawing with no imported geometry, from its tag register.

	Equipment is laid left to right in process order (following Process connections from the
	equipment nothing feeds), each with its instruments and valves stacked above it; components
	with no equipment parent go in a row along the top. Process connections become straight lines.
	"""
	by_tag = {c["tag"]: c for c in components}
	equipment = [c["tag"] for c in components if c.get("component_type") == "Equipment"]
	downstream: dict[str, list[str]] = {}
	fed = set()
	for link in connections:
		if (
			link.get("kind", "Process") == "Process"
			and link.get("from_tag") in by_tag
			and link.get("to_tag") in by_tag
		):
			downstream.setdefault(link["from_tag"], []).append(link["to_tag"])
			fed.add(link["to_tag"])
	order: list[str] = []
	for start in [t for t in equipment if t not in fed] + equipment:
		stack = [start]
		while stack:
			tag = stack.pop(0)
			if tag in order or tag not in by_tag or by_tag[tag].get("component_type") != "Equipment":
				continue
			order.append(tag)
			stack.extend(downstream.get(tag, []))
	columns = max(len(order), 1)
	width = max(420.0, 60.0 * columns + 40)
	height = 297.0
	positions: dict[str, tuple[float, float]] = {}
	for index, tag in enumerate(order):
		positions[tag] = (
			40.0 + index * (width - 80) / max(columns - 1, 1) if columns > 1 else width / 2,
			110.0,
		)
	# A line is drawn from the equipment it leaves, so things on the line sit above that equipment.
	line_source: dict[str, str] = {}
	for link in connections:
		if link.get("kind", "Process") == "Process" and link.get("via"):
			line_source.setdefault(link["via"], link.get("from_tag") or "")
	stacked: dict[str, int] = {}
	loose: list[str] = []
	for comp in components:
		tag = comp["tag"]
		if tag in positions or comp.get("component_type") == "Line":
			continue
		anchor = _anchor(tag, by_tag, positions, line_source)
		if anchor:
			level = stacked.get(anchor, 0)
			stacked[anchor] = level + 1
			ax, ay = positions[anchor]
			positions[tag] = (ax + (level % 2) * 14 - 7, ay + 32 + (level // 2) * 14 + (level % 2) * 7)
		else:
			loose.append(tag)
	for index, tag in enumerate(loose):
		positions[tag] = (20.0 + (index % 18) * 22, height - 20.0 - (index // 18) * 18)
	items = []
	for comp in components:
		if comp["tag"] not in positions:
			continue
		x, y = positions[comp["tag"]]
		kind = comp.get("component_type")
		items.append(
			{
				"id": comp["tag"],
				"kind": kind if kind in ("Equipment", "Instrument", "Valve") else "Actuator",
				"component_class": comp.get("component_class") or "",
				"tag": comp["tag"],
				"x": x,
				"y": y,
				"parent_id": "",
				"location": comp.get("component_class") or "",
			}
		)
	lines = []
	for link in connections:
		a = positions.get(link.get("from_tag")) or positions.get(line_source.get(link.get("from_tag"), ""))
		b = positions.get(link.get("to_tag"))
		if a and b and link.get("kind", "Process") == "Process":
			lines.append(
				{
					"id": f"{link['from_tag']}>{link['to_tag']}",
					"kind": "Process",
					"tag": link.get("via") or "",
					"points": [list(a), list(b)],
				}
			)
		elif a and b:
			lines.append(
				{
					"id": f"{link['from_tag']}>{link['to_tag']}",
					"kind": "Signal",
					"tag": "",
					"points": [list(a), list(b)],
				}
			)
	return {"extent": [0.0, 0.0, width, height], "units": "", "items": items, "lines": lines}
