# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0
"""Check the vendor terms pages cited in docs/vendor-interoperability.md for changes.

Reads .github/vendor-terms/pages.json. For each page in mode "fetch" it checks the site's
robots.txt, fetches the page with a generic user agent, reduces it to its visible text and
compares the SHA-256 of that text with the reviewed hash in .github/vendor-terms/state.json.
Pages in mode "manual" are never fetched; they are listed for a person to review.

Nothing from a page is stored or printed except its hash, its HTTP status and its size, so no
vendor text is copied into the repository or the workflow logs.

Writes a Markdown report and a candidate state file, and prints a JSON summary. Exit code is
always 0 unless the configuration itself is broken; the workflow decides what to open.

    python .github/scripts/check_vendor_terms.py --report report.md --new-state new-state.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html.parser
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path
from typing import ClassVar

ROOT = Path(__file__).resolve().parents[2]
PAGES = ROOT / ".github" / "vendor-terms" / "pages.json"
STATE = ROOT / ".github" / "vendor-terms" / "state.json"
USER_AGENT = "FoaMES-terms-check/1.0 (+https://github.com/CLR-Technologies-Inc/foames)"
TIMEOUT = 30
DELAY = 2.0  # seconds between requests to the same host


MANUAL_INTRO = (
	"These are never fetched automatically. Read each one in a browser, compare it with its row in "
	"docs/vendor-interoperability.md, and record the review date in .github/vendor-terms/state.json."
)


class _TextExtractor(html.parser.HTMLParser):
	"""Keeps visible text, drops scripts, styles and markup."""

	SKIP: ClassVar[set[str]] = {"script", "style", "noscript", "template", "svg", "head"}

	def __init__(self):
		super().__init__(convert_charrefs=True)
		self.parts: list[str] = []
		self._skip = 0

	def handle_starttag(self, tag, attrs):
		if tag in self.SKIP:
			self._skip += 1

	def handle_endtag(self, tag):
		if tag in self.SKIP and self._skip:
			self._skip -= 1

	def handle_data(self, data):
		if not self._skip:
			self.parts.append(data)


def visible_text(body: bytes, content_type: str) -> str:
	text = body.decode("utf-8", errors="replace")
	if "html" in content_type:
		parser = _TextExtractor()
		parser.feed(text)
		text = " ".join(parser.parts)
	return re.sub(r"\s+", " ", text).strip()


def robots_allows(url: str, cache: dict) -> bool | None:
	"""True or False from robots.txt; None if robots.txt could not be read (treated as allowed)."""
	parts = urllib.parse.urlsplit(url)
	origin = f"{parts.scheme}://{parts.netloc}"
	if origin not in cache:
		rp = urllib.robotparser.RobotFileParser()
		try:
			req = urllib.request.Request(origin + "/robots.txt", headers={"User-Agent": USER_AGENT})
			with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
				rp.parse(resp.read().decode("utf-8", errors="replace").splitlines())
			cache[origin] = rp
		except urllib.error.HTTPError as exc:
			# 4xx means no robots.txt (everything allowed); 5xx means unknown.
			cache[origin] = "allow" if 400 <= exc.code < 500 else None
		except Exception:
			cache[origin] = None
	rp = cache[origin]
	if rp == "allow":
		return True
	if rp is None:
		return None
	return rp.can_fetch(USER_AGENT, url)


def fetch(url: str) -> tuple[int, str, bytes, str]:
	req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en"})
	try:
		with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
			return resp.status, resp.headers.get("Content-Type", ""), resp.read(), resp.geturl()
	except urllib.error.HTTPError as exc:
		return exc.code, exc.headers.get("Content-Type", "") if exc.headers else "", b"", url


def check(pages: list[dict], state: dict) -> tuple[list[dict], dict]:
	results, new_state, robots_cache, last_hit = [], dict(state), {}, {}
	for page in pages:
		pid, url = page["id"], page["url"]
		row = {"id": pid, "vendor": page["vendor"], "url": url, "mode": page.get("mode", "fetch")}
		if row["mode"] == "manual":
			row["status"] = "manual"
			row["reason"] = page.get("reason", "")
			row["last_reviewed"] = state.get(pid, {}).get("reviewed")
			results.append(row)
			continue

		allowed = robots_allows(url, robots_cache)
		if allowed is False:
			row["status"] = "robots-disallowed"
			results.append(row)
			continue

		host = urllib.parse.urlsplit(url).netloc
		wait = DELAY - (time.monotonic() - last_hit.get(host, 0))
		if wait > 0:
			time.sleep(wait)
		try:
			code, ctype, body, final_url = fetch(url)
		except Exception as exc:  # network failure, DNS, timeout
			row.update(status="unreachable", error=type(exc).__name__)
			results.append(row)
			continue
		finally:
			last_hit[host] = time.monotonic()

		row["http"] = code
		if code >= 400:
			row["status"] = "broken-link"
			results.append(row)
			continue
		if final_url != url:
			row["redirected_to"] = final_url

		if page.get("binary"):
			digest = hashlib.sha256(body).hexdigest()
			size = len(body)
		else:
			text = visible_text(body, ctype)
			digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
			size = len(text)
		row["sha256"], row["size"] = digest, size

		known = state.get(pid, {}).get("sha256")
		if known is None:
			row["status"] = "no-baseline"
		elif known == digest:
			row["status"] = "unchanged"
		else:
			row["status"] = "changed"
			row["previous_sha256"] = known
		if row["status"] != "unchanged":
			new_state[pid] = {"sha256": digest, "reviewed": None}
		results.append(row)
	return results, new_state


def report(results: list[dict], include_manual: bool) -> str:
	today = dt.date.today().isoformat()
	need = [
		r
		for r in results
		if r["status"] in {"changed", "broken-link", "unreachable", "robots-disallowed", "no-baseline"}
	]
	manual = [r for r in results if r["status"] == "manual"]
	lines = [f"Vendor terms check run on {today}.", ""]
	lines.append(
		"This check compares a hash of each terms page's visible text with the hash recorded when it was last "
		"reviewed. It does not interpret the terms. A changed hash can be a real terms change or just a page "
		"redesign; a person must read the page and update docs/vendor-interoperability.md if FoaMES is affected."
	)
	lines.append("")
	if need:
		lines += [
			"## Pages that need a look",
			"",
			"| Vendor | Page | Status | Detail |",
			"| --- | --- | --- | --- |",
		]
		for r in need:
			detail = {
				"changed": f"text hash changed ({r.get('size', '?')} chars)",
				"no-baseline": "first check, no reviewed hash yet",
				"broken-link": f"HTTP {r.get('http')}; update the link in the doc",
				"unreachable": f"could not connect ({r.get('error', '')})",
				"robots-disallowed": "robots.txt now disallows automated readers; switch this page to manual",
			}[r["status"]]
			if r.get("redirected_to"):
				detail += f"; redirects to {r['redirected_to']}"
			lines.append(f"| {r['vendor']} | [{r['id']}]({r['url']}) | {r['status']} | {detail} |")
		lines.append("")
	if include_manual and manual:
		lines += [
			"## Pages a person must review",
			"",
			MANUAL_INTRO,
			"",
			"| Vendor | Page | Why manual | Last reviewed |",
			"| --- | --- | --- | --- |",
		]
		for r in manual:
			lines.append(
				f"| {r['vendor']} | [{r['id']}]({r['url']}) | {r['reason']} | {r.get('last_reviewed') or 'never'} |"
			)
		lines.append("")
	lines += [
		"## Closing this issue",
		"",
		"1. Read each listed page and update docs/vendor-interoperability.md (and the row's date) if anything that affects FoaMES changed.",
		"2. Replace .github/vendor-terms/state.json with the `new-state.json` artifact of this run (or copy the hashes from it), set `reviewed` to the review date for the pages you read, and open a pull request.",
		"3. Close this issue when that pull request merges.",
		"",
		"Not legal advice; see the note at the top of docs/vendor-interoperability.md.",
	]
	return "\n".join(lines) + "\n"


def main() -> int:
	ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	ap.add_argument("--report", type=Path, required=True)
	ap.add_argument("--new-state", type=Path, required=True)
	ap.add_argument("--include-manual", action="store_true", help="add the human-review list to the report")
	args = ap.parse_args()

	pages = json.loads(PAGES.read_text())["pages"]
	ids = [p["id"] for p in pages]
	if len(ids) != len(set(ids)):
		print("duplicate page id in pages.json", file=sys.stderr)
		return 2
	state = json.loads(STATE.read_text()) if STATE.exists() else {}

	results, new_state = check(pages, state)
	args.report.write_text(report(results, args.include_manual))
	args.new_state.write_text(json.dumps(new_state, indent=2, sort_keys=True) + "\n")

	counts: dict[str, int] = {}
	for r in results:
		counts[r["status"]] = counts.get(r["status"], 0) + 1
	attention = sum(
		counts.get(k, 0)
		for k in ("changed", "broken-link", "unreachable", "robots-disallowed", "no-baseline")
	)
	print(json.dumps({"counts": counts, "needs_attention": attention}))
	return 0


if __name__ == "__main__":
	sys.exit(main())
