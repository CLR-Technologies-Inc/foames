# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0
"""Pick a hosted agent's model from its `_model_candidates` before a benchmark run.

Free API tiers change their catalogues often (a model goes paid-only or is retired for new users), so
an agent in agents.json lists candidate models in order of preference. This script asks the provider
which ones the key can use and rewrites the agent's "model" in agents.json (in the job's checkout only).

  python scripts/pick_hosted_model.py AGENT [--agents agents.json] [--notes DIR]

It writes DIR/model-digest.txt (the chosen id, the date and why) and DIR/provider-models.txt (the ids
the provider listed). It never prints or writes the key.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Some API fronts refuse urllib's default User-Agent, so send a plain client name (no contact details).
UA = "foames-bench/1.0"
LISTED: dict[str, str] = {}


def _get(url: str, headers: dict | None = None, data: dict | None = None, timeout: int = 180):
	"""(status, headers, json). A timeout or network error gives status 0 and the error as "error"."""
	body = json.dumps(data).encode() if data is not None else None
	req = urllib.request.Request(
		url, data=body, headers={"Content-Type": "application/json", "User-Agent": UA, **(headers or {})}
	)
	try:
		with urllib.request.urlopen(req, timeout=timeout) as r:
			return r.status, dict(r.headers), json.loads(r.read() or b"{}")
	except urllib.error.HTTPError as e:
		try:
			payload = json.loads(e.read() or b"{}")
		except ValueError:
			payload = {}
		return e.code, dict(e.headers), payload
	except (OSError, ValueError) as e:
		return 0, {}, {"error": {"message": f"{type(e).__name__}: {e}"}}


def _err(d: dict) -> str:
	e = d.get("error", "")
	return (e.get("message", "") if isinstance(e, dict) else str(e))[:160]


def gemini_models(key: str) -> list[str]:
	ids, token = [], ""
	while True:
		status, _, d = _get(
			f"https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000&pageToken={token}",
			{"x-goog-api-key": key},
		)
		LISTED["gemini"] = f"model list HTTP {status} {_err(d)}".strip()
		ids += [
			m["name"].split("/", 1)[1]
			for m in d.get("models", [])
			if "generateContent" in m.get("supportedGenerationMethods", [])
		]
		token = d.get("nextPageToken", "")
		if not token:
			return ["gemini/" + i for i in ids]


def gemini_works(key: str, model: str) -> tuple[bool, str]:
	status, _, d = _get(
		f"https://generativelanguage.googleapis.com/v1beta/models/{model.split('/', 1)[1]}:generateContent",
		{"x-goog-api-key": key},
		{"contents": [{"parts": [{"text": "Say OK."}]}], "generationConfig": {"maxOutputTokens": 8}},
	)
	# A slow answer (status 0, a timeout) still counts: the model is listed and aider retries on its own.
	return status in (200, 0), f"HTTP {status or 'timeout'} {_err(d)}".strip()


def groq_models(key: str) -> list[str]:
	status, _, d = _get("https://api.groq.com/openai/v1/models", {"Authorization": f"Bearer {key}"})
	LISTED["groq"] = f"model list HTTP {status} {_err(d)}".strip()
	return ["groq/" + m["id"] for m in d.get("data", [])]


def groq_works(key: str, model: str, min_tpm: int) -> tuple[bool, str, int]:
	status, headers, d = _get(
		"https://api.groq.com/openai/v1/chat/completions",
		{"Authorization": f"Bearer {key}"},
		{
			"model": model.split("/", 1)[1],
			"messages": [{"role": "user", "content": "Say OK."}],
			"max_tokens": 8,
		},
	)
	h = {k.lower(): v for k, v in headers.items()}
	tpm = int(h.get("x-ratelimit-limit-tokens", "0") or 0)
	why = f"HTTP {status} {_err(d)}, tokens per minute {tpm or 'unknown'}, requests per day {h.get('x-ratelimit-limit-requests', 'unknown')}"
	return status == 200 and (tpm == 0 or tpm >= min_tpm), why, tpm


def openrouter_models() -> dict[str, int]:
	_, _, d = _get("https://openrouter.ai/api/v1/models")
	return {"openrouter/" + m["id"]: int(m.get("context_length") or 0) for m in d.get("data", [])}


def pick(agent: dict, notes: Path) -> str:
	provider = agent["model"].split("/", 1)[0]
	key = os.environ.get(agent.get("_secret", ""), "")
	tried: list[str] = []
	if provider == "gemini":
		listed = gemini_models(key)
		for c in agent["_model_candidates"]:
			if c["model"] in listed:
				ok, why = gemini_works(key, c["model"])
				tried.append(f"{c['model']}: {why}")
				if ok:
					return _done(c["model"], listed, tried, notes)
			else:
				tried.append(f"{c['model']}: not listed")
		flash = sorted(
			(m for m in listed if "flash" in m and "lite" not in m and "image" not in m and "tts" not in m),
			reverse=True,
		)
		for m in flash[:3]:
			ok, why = gemini_works(key, m)
			tried.append(f"{m}: {why}")
			if ok:
				return _done(m, listed, tried, notes)
	elif provider == "groq":
		listed = groq_models(key)
		for c in agent["_model_candidates"]:
			if listed and c["model"] not in listed:
				tried.append(f"{c['model']}: not listed")
				continue
			ok, why, _ = groq_works(key, c["model"], c.get("min_tpm", 0))
			tried.append(f"{c['model']}: {why}")
			if ok:
				return _done(c["model"], listed, tried, notes)
		# None of the named candidates fits: try the other listed chat models and take the one with the
		# largest tokens-per-minute limit that still fits an aider request.
		need = max((c.get("min_tpm", 0) for c in agent["_model_candidates"]), default=0)
		skip = ("whisper", "tts", "guard", "playai", "orpheus", "compound", "distil")
		named = {c["model"] for c in agent["_model_candidates"]}
		fits = []
		for m in [m for m in listed if m not in named and not any(k in m for k in skip)][:20]:
			ok, why, tpm = groq_works(key, m, need)
			tried.append(f"{m}: {why}")
			if ok:
				fits.append((tpm, m))
		if fits:
			return _done(max(fits)[1], listed, tried, notes)
	elif provider == "openrouter":
		ctx = openrouter_models()
		listed = sorted(ctx)
		free = [m for m in listed if m.endswith(":free")]
		for c in agent["_model_candidates"]:
			if c["model"] == "openrouter/*:free" and free:
				best = max(free, key=lambda m: (ctx[m], m))
				tried.append(f"{best}: largest-context free model ({ctx[best]} tokens)")
				return _done(best, free, tried, notes)
			tried.append(f"{c['model']}: {'listed' if c['model'] in free else 'not listed as free'}")
			if c["model"] in free:
				return _done(c["model"], free, tried, notes)
	else:
		raise SystemExit(f"no model picker for provider {provider}")
	tried += LISTED.values()
	_done("", listed, tried, notes)
	raise SystemExit(
		f"{agent['name']}: no candidate model is usable on this key today; see {notes}/model-digest.txt"
	)


def _done(model: str, listed: list[str], tried: list[str], notes: Path) -> str:
	notes.mkdir(parents=True, exist_ok=True)
	day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
	if not model:
		print("Models the provider listed:", ", ".join(listed) or "none")
	head = (
		f"API model id {model}, called {day} (picked from the agent's candidates; the provider may update a model behind an unversioned id)"
		if model
		else f"No usable model on {day}"
	)
	(notes / "model-digest.txt").write_text(
		head + "\n" + "".join(f"- {t}\n" for t in tried), encoding="utf-8"
	)
	(notes / "provider-models.txt").write_text("\n".join(listed) + "\n", encoding="utf-8")
	print(head)
	print("\n".join(tried))
	return model


def main(argv=None):
	ap = argparse.ArgumentParser()
	ap.add_argument("agent")
	ap.add_argument("--agents", type=Path, default=Path(__file__).resolve().parent.parent / "agents.json")
	ap.add_argument("--notes", type=Path, default=Path("notes"))
	opts = ap.parse_args(argv)
	doc = json.loads(opts.agents.read_text(encoding="utf-8"))
	agent = next(a for a in doc["agents"] if a["name"] == opts.agent)
	if not agent.get("_model_candidates"):
		return
	agent["model"] = pick(agent, opts.notes)
	opts.agents.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
	main()
