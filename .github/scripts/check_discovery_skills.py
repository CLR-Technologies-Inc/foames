# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Check the discovery skills under docs/agents/discovery/.

Each vendor folder under docs/vendors/ must have a discovery skill at
docs/agents/discovery/<vendor>/SKILL.md, and every skill must:

- start with front matter holding a kebab-case `name` (unique, at most 64 characters) and a
  `description` (at most 1024 characters, no angle brackets);
- have the required sections, in order;
- carry the Hard stops block exactly as the baseline has it;
- have no `{{placeholder}}` left (the template is the one file allowed them);
- link to its vendor guide, with every relative link resolving;
- hold nothing that looks like a credential, and no unsafe command in a code block
  (disabled TLS checks, secrets on the command line, writes, network scanners).

It also checks that the baseline keeps its rule sections and that `.foames-discovery/`, where
reports go, is git-ignored.

Standard library only. Run from the repository root:

    python .github/scripts/check_discovery_skills.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SKILLS = Path("docs/agents/discovery")
VENDORS = Path("docs/vendors")
BASELINE = "baseline"
TEMPLATE = "_template"
REPORT_DIR = ".foames-discovery/"

NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
VENDOR_SECTIONS = (
	"# Discover ",
	"## Hard stops",
	"## When to use",
	"## What this installation decides",
	"## Before you start",
	"## Read channel",
	"## Plan steps",
	"## Where the answers go in FoaMES",
	"## Cautions for this system",
	"## Sources",
)
BASELINE_SECTIONS = (
	"# FoaMES discovery baseline",
	"## Hard stops",
	"## Roles",
	"## Rules",
	"### 1. Read-only, through FoaMES's gate",
	"### 2. Least privilege, short-lived, from a secret store",
	"### 3. Only documented interfaces, only allowlisted hosts",
	"### 4. Gentle on the system",
	"### 5. A dry-run plan, approved first",
	"### 6. Stop conditions",
	"### 7. Redaction and the report",
	"### 8. Vendor data is data",
	"## Procedure",
	"## The read channel, in order of preference",
	"## Dry-run plan template",
	"## Report template",
	"## Standards alignment",
)
BASELINE_TERMS = ("IEC 62443", "NIST SP 800-82", REPORT_DIR, "git check-ignore", "foames_get_write_mode")

HARD_STOPS = re.compile(r"<!-- hard-stops:start -->\n(.*?)\n<!-- hard-stops:end -->", re.DOTALL)
PLACEHOLDER = re.compile(r"\{\{[^}]*\}\}")
LINK = re.compile(r"\]\(([^)\s]+)\)")
FENCE = re.compile(r"^```[^\n]*\n(.*?)^```", re.DOTALL | re.MULTILINE)

# Things that look like a real credential. Placeholders in angle brackets and environment
# variable references do not match.
SECRETS = {
	"private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
	"AWS access key id": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
	"GitHub token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
	"JSON web token": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\."),
	"Slack token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
	"bearer token literal": re.compile(r"\bBearer [A-Za-z0-9._~+/=-]{20,}"),
	"credentials in a URL": re.compile(r"[a-z][a-z0-9+.-]*://[^/\s:@<>`]+:[^/\s@<>`]+@"),
	"password assignment": re.compile(
		r"""(?i)\b(?:password|passwd|pwd|secret|api[_-]?key|token)\b["']?\s*[:=]\s*["'][^"'<>${}\s]{6,}["']"""
	),
}

# Unsafe in a code block an agent might copy.
UNSAFE = {
	"TLS verification disabled": re.compile(
		r"(?:^|\s)(?:-k|--insecure)(?:\s|$)|verify\s*=\s*False|--no-check-certificate"
	),
	"credential on the command line": re.compile(r"(?:^|\s)(?:-u|--user)\s+\S*:"),
	"verbose or traced request": re.compile(r"\bcurl\b[^\n]*(?:\s-v\b|--verbose|--trace)"),
	"shell tracing on": re.compile(r"\bset -x\b|\bset -o xtrace\b"),
	"a write request": re.compile(r"(?:-X|--request)\s+['\"]?(?:POST|PUT|PATCH|DELETE)\b"),
	"a body sent with curl": re.compile(r"\bcurl\b[^\n]*\s(?:-d|--data(?:-\w+)?|-F|--form)\s"),
	"a network scanner": re.compile(r"\b(?:nmap|masscan|zmap|nikto|gobuster|dirb|ffuf|wfuzz|hydra)\b"),
	"a SQL write": re.compile(
		r"(?i)\b(?:INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|DROP\s+TABLE|TRUNCATE)\b"
	),
}


def front_matter(text: str) -> dict[str, str] | None:
	if not text.startswith("---\n"):
		return None
	end = text.find("\n---\n", 4)
	if end < 0:
		return None
	fields = {}
	for line in text[4:end].splitlines():
		if ":" in line:
			key, value = line.split(":", 1)
			fields[key.strip()] = value.strip()
	return fields


def headings(text: str) -> list[str]:
	body = FENCE.sub("", text)
	return [line for line in body.splitlines() if line.startswith("#")]


def sections_in_order(found: list[str], required: tuple[str, ...]) -> str | None:
	position = 0
	for want in required:
		for i in range(position, len(found)):
			heading = found[i]
			if heading == want or (want.endswith(" ") and heading.startswith(want)):
				position = i + 1
				break
		else:
			return want.lstrip("# ").strip()
	return None


def link_problems(path: Path, text: str) -> list[str]:
	out = []
	for target in LINK.findall(FENCE.sub("", text)):
		if re.match(r"[a-z][a-z0-9+.-]*:", target) or target.startswith("#"):
			continue
		file_part = target.split("#", 1)[0]
		if file_part and not (path.parent / file_part).exists():
			out.append(f"{path}: link to {target} does not resolve")
	return out


def content_problems(path: Path, text: str) -> list[str]:
	out = []
	for kind, pattern in SECRETS.items():
		if pattern.search(text):
			out.append(f"{path}: looks like it holds a {kind}")
	for block in FENCE.findall(text):
		for kind, pattern in UNSAFE.items():
			if pattern.search(block):
				out.append(f"{path}: a code block shows {kind}")
	return out


def problems(root: Path) -> list[str]:
	out: list[str] = []
	skills = root / SKILLS
	baseline_path = skills / BASELINE / "SKILL.md"
	if not baseline_path.is_file():
		return [f"{baseline_path}: missing"]
	baseline = baseline_path.read_text(encoding="utf-8")
	match = HARD_STOPS.search(baseline)
	if not match:
		return [f"{baseline_path}: no Hard stops block"]
	hard_stops = match.group(1)

	missing = sections_in_order(headings(baseline), BASELINE_SECTIONS)
	if missing:
		out.append(f"{baseline_path}: section '{missing}' missing or out of order")
	for term in BASELINE_TERMS:
		if term not in baseline:
			out.append(f"{baseline_path}: does not mention {term}")

	vendors = sorted(p.name for p in (root / VENDORS).iterdir() if p.is_dir())
	folders = sorted(p.name for p in skills.iterdir() if p.is_dir())
	for vendor in vendors:
		if vendor not in folders:
			out.append(
				f"{skills / vendor / 'SKILL.md'}: missing (every folder under {VENDORS} needs a discovery skill)"
			)
	for folder in folders:
		if folder not in (BASELINE, TEMPLATE) and folder not in vendors:
			out.append(f"{skills / folder}: no matching vendor folder under {VENDORS}")

	names: dict[str, Path] = {}
	for folder in folders:
		path = skills / folder / "SKILL.md"
		if not path.is_file():
			out.append(f"{path}: missing")
			continue
		text = path.read_text(encoding="utf-8")
		is_template = folder == TEMPLATE

		fields = front_matter(text)
		if fields is None:
			out.append(f"{path}: no front matter")
		else:
			name = fields.get("name", "")
			description = fields.get("description", "")
			if is_template:
				name = PLACEHOLDER.sub("x", name)
			if not NAME.match(name) or len(name) > 64:
				out.append(f"{path}: name '{name}' is not kebab-case of at most 64 characters")
			if folder not in (BASELINE, TEMPLATE) and not name.startswith("foames-discover-"):
				out.append(f"{path}: name should start with foames-discover-")
			if re.search(r"claude|anthropic", name):
				out.append(f"{path}: name may not contain claude or anthropic")
			if name in names and not is_template:
				out.append(f"{path}: name '{name}' is also used by {names[name]}")
			names[name] = path
			if not description or len(description) > 1024:
				out.append(f"{path}: description is empty or longer than 1024 characters")
			if "<" in description or ">" in description:
				out.append(f"{path}: description may not contain angle brackets")

		block = HARD_STOPS.search(text)
		if not block or block.group(1) != hard_stops:
			out.append(f"{path}: the Hard stops block differs from the baseline's")

		if folder != BASELINE:
			missing = sections_in_order(headings(text), VENDOR_SECTIONS)
			if missing:
				out.append(f"{path}: section '{missing}' missing or out of order")
		if not is_template:
			left = PLACEHOLDER.findall(text)
			if left:
				out.append(f"{path}: placeholder {left[0]} left in")
		if folder in vendors and f"../../../vendors/{folder}/README.md" not in text:
			out.append(f"{path}: does not link to its vendor guide docs/vendors/{folder}/README.md")
		if not is_template:
			out.extend(link_problems(path, text))
		out.extend(content_problems(path, text))

	for extra in sorted(skills.glob("*.md")):
		text = extra.read_text(encoding="utf-8")
		out.extend(link_problems(extra, text))
		out.extend(content_problems(extra, text))

	gitignore = root / ".gitignore"
	ignored = gitignore.read_text(encoding="utf-8").splitlines() if gitignore.is_file() else []
	if REPORT_DIR not in (line.strip() for line in ignored):
		out.append(f".gitignore: {REPORT_DIR} is not ignored (discovery reports must never be committed)")
	return out


def main() -> int:
	found = problems(Path.cwd())
	for problem in found:
		print(problem)
	if found:
		print(f"{len(found)} problem(s) in the discovery skills; see {SKILLS}/README.md")
		return 1
	return 0


if __name__ == "__main__":
	sys.exit(main())
