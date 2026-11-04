# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Token use and cost from an agent's own output.

The agent CLIs report usage in different shapes and change them between releases, so every parser
is tolerant: it returns what it can find and says where the number came from. `cost_source` is
"reported" when the agent printed a dollar figure, "estimated" when it was priced from token counts
with the prices in agents.json, and "unknown" otherwise. A run with unknown cost is still graded;
it is just left out of cost-per-success.
"""

import json
from dataclasses import asdict, dataclass


@dataclass
class Usage:
	input_tokens: int = 0
	output_tokens: int = 0
	cached_input_tokens: int = 0
	turns: int | None = None
	cost_usd: float | None = None
	cost_source: str = "unknown"

	def to_dict(self) -> dict:
		return asdict(self)


def _json_objects(text: str):
	"""Every JSON object in the text: the whole text if it is one, else one per line (JSONL)."""
	text = text.strip()
	if not text:
		return []
	try:
		value = json.loads(text)
		return value if isinstance(value, list) else [value]
	except ValueError:
		pass
	out = []
	for line in text.splitlines():
		line = line.strip()
		if line.startswith("{"):
			try:
				out.append(json.loads(line))
			except ValueError:
				continue
	return out


def _int(value) -> int:
	try:
		return int(value or 0)
	except (TypeError, ValueError):
		return 0


def parse_claude_json(text: str) -> Usage:
	"""`claude -p --output-format json` (one result object) or `stream-json` (JSONL ending in one)."""
	usage = Usage()
	for obj in _json_objects(text):
		if not isinstance(obj, dict) or obj.get("type") not in (None, "result"):
			continue
		u = obj.get("usage") or {}
		if u:
			usage.input_tokens = _int(u.get("input_tokens")) + _int(u.get("cache_creation_input_tokens"))
			usage.cached_input_tokens = _int(u.get("cache_read_input_tokens"))
			usage.output_tokens = _int(u.get("output_tokens"))
		if obj.get("num_turns") is not None:
			usage.turns = _int(obj.get("num_turns"))
		cost = obj.get("total_cost_usd", obj.get("cost_usd"))
		if cost is not None:
			usage.cost_usd, usage.cost_source = float(cost), "reported"
	return usage


def parse_codex_jsonl(text: str) -> Usage:
	"""`codex exec --json`: JSONL events; usage arrives on turn-completed events and is summed."""
	usage = Usage()
	turns = 0
	for obj in _json_objects(text):
		if not isinstance(obj, dict):
			continue
		u = obj.get("usage") or (obj.get("msg") or {}).get("usage") or {}
		if obj.get("type", "").endswith("turn.completed") or u:
			turns += 1 if obj.get("type", "").endswith("turn.completed") else 0
			usage.input_tokens += _int(u.get("input_tokens"))
			usage.cached_input_tokens += _int(u.get("cached_input_tokens"))
			usage.output_tokens += _int(u.get("output_tokens"))
	usage.turns = turns or None
	return usage


def parse_gemini_json(text: str) -> Usage:
	"""`gemini -p ... --output-format json`: {"response", "stats": {"models": {name: {"tokens"}}}}."""
	usage = Usage()
	for obj in _json_objects(text):
		models = ((obj or {}).get("stats") or {}).get("models") or {}
		for stats in models.values():
			tokens = (stats or {}).get("tokens") or {}
			usage.input_tokens += _int(tokens.get("prompt"))
			usage.cached_input_tokens += _int(tokens.get("cached"))
			usage.output_tokens += _int(tokens.get("candidates")) + _int(tokens.get("thoughts"))
	return usage


def parse_generic(text: str) -> Usage:
	"""Any output that carries OpenAI- or Anthropic-style usage objects; the last one wins."""
	usage = Usage()
	for obj in _json_objects(text):
		u = (obj or {}).get("usage") if isinstance(obj, dict) else None
		if isinstance(u, dict):
			usage.input_tokens = _int(u.get("input_tokens") or u.get("prompt_tokens"))
			usage.output_tokens = _int(u.get("output_tokens") or u.get("completion_tokens"))
	return usage


PARSERS = {
	"claude-json": parse_claude_json,
	"codex-jsonl": parse_codex_jsonl,
	"gemini-json": parse_gemini_json,
	"generic": parse_generic,
	"none": lambda text: Usage(),
}


def price(usage: Usage, prices: dict | None) -> Usage:
	"""Fill in an estimated cost from per-million-token prices when the agent reported none."""
	if usage.cost_usd is not None or not prices:
		return usage
	if not (usage.input_tokens or usage.output_tokens or usage.cached_input_tokens):
		return usage
	cost = (
		usage.input_tokens * prices.get("input_per_mtok", 0)
		+ usage.cached_input_tokens * prices.get("cached_input_per_mtok", prices.get("input_per_mtok", 0))
		+ usage.output_tokens * prices.get("output_per_mtok", 0)
	) / 1_000_000
	usage.cost_usd, usage.cost_source = round(cost, 6), "estimated"
	return usage


def parse(parser: str, stdout: str, prices: dict | None = None) -> Usage:
	if parser not in PARSERS:
		raise ValueError(f"unknown usage parser {parser!r}; use one of {', '.join(PARSERS)}")
	return price(PARSERS[parser](stdout), prices)
