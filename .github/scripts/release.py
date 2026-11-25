# Copyright 2026 CLR Technologies Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""FoaMES versioning and changelog fragments.

The version lives in one place, `foames/__init__.py` (`__version__`, PEP 440). Pull requests never
edit CHANGELOG.md: each adds a fragment under `changelog.d/`, and a release collects them. That keeps
the changelog out of merge conflicts. See docs/versioning.md.

Standard library only. Run from the repository root:

    python .github/scripts/release.py version            # 0.3.0.dev0
    python .github/scripts/release.py tag                # v0.3.0-dev.0 (the Git tag for it)
    python .github/scripts/release.py check              # fragment names and the version string
    python .github/scripts/release.py preview            # the next section, without writing
    python .github/scripts/release.py set 0.3.0rc1       # change __version__
    python .github/scripts/release.py collect 0.3.0 --date 2026-12-01
                                                        # fragments -> CHANGELOG.md section, removed
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

VERSION_FILE = Path("foames/__init__.py")
FRAGMENTS = Path("changelog.d")
CHANGELOG = Path("CHANGELOG.md")

# Section order in a release, and the fragment category that feeds each.
CATEGORIES = {
	"added": "Added",
	"changed": "Changed",
	"fixed": "Fixed",
	"security": "Security",
	"deprecated": "Deprecated",
	"removed": "Removed",
	"docs": "Documentation",
}
# changelog.d/<id>.<category>.md, where <id> is the PR number or a short slug (letters, digits, -).
FRAGMENT = re.compile(r"^(?P<id>[A-Za-z0-9][A-Za-z0-9-]*)\.(?P<cat>[a-z]+)\.md$")
# The PEP 440 forms FoaMES uses: X.Y.Z, X.Y.Z.devN, X.Y.ZaN, X.Y.ZbN, X.Y.ZrcN.
VERSION = re.compile(r"^(?P<base>\d+\.\d+\.\d+)(?:(?P<pre>a|b|rc)(?P<pren>\d+)|\.dev(?P<dev>\d+))?$")
VERSION_LINE = re.compile(r'^__version__ = "([^"]*)"$', re.M)
SEMVER_PRE = {"a": "alpha", "b": "beta", "rc": "rc"}
MARKER = "<!-- releases go below; release.py collect inserts the newest first -->"


def parse_version(text: str) -> re.Match[str]:
	m = VERSION.match(text)
	if not m:
		raise ValueError(f"{text!r} is not X.Y.Z, X.Y.Z.devN, X.Y.ZaN, X.Y.ZbN or X.Y.ZrcN")
	return m


def git_tag(version: str) -> str:
	"""The SemVer Git tag for a PEP 440 version: 0.3.0rc1 -> v0.3.0-rc.1, 0.3.0.dev0 -> v0.3.0-dev.0."""
	m = parse_version(version)
	if m["pre"]:
		return f"v{m['base']}-{SEMVER_PRE[m['pre']]}.{m['pren']}"
	if m["dev"] is not None:
		return f"v{m['base']}-dev.{m['dev']}"
	return f"v{m['base']}"


def is_prerelease(version: str) -> bool:
	m = parse_version(version)
	return bool(m["pre"] or m["dev"] is not None)


def read_version(root: Path) -> str:
	m = VERSION_LINE.search((root / VERSION_FILE).read_text(encoding="utf-8"))
	if not m:
		raise ValueError(f"no __version__ line in {VERSION_FILE}")
	return m.group(1)


def set_version(root: Path, version: str) -> None:
	parse_version(version)
	path = root / VERSION_FILE
	text = path.read_text(encoding="utf-8")
	path.write_text(VERSION_LINE.sub(f'__version__ = "{version}"', text, count=1), encoding="utf-8")


def fragments(root: Path) -> tuple[list[tuple[str, str, Path]], list[str]]:
	"""(id, category, path) for each fragment, and the problems found."""
	found, bad = [], []
	folder = root / FRAGMENTS
	if not folder.is_dir():
		return found, bad
	for path in sorted(folder.iterdir()):
		if path.name in {"README.md", ".gitkeep"} or path.is_dir():
			continue
		m = FRAGMENT.match(path.name)
		if not m:
			bad.append(f"{path.name}: name it <pr-number or slug>.<category>.md")
		elif m["cat"] not in CATEGORIES:
			bad.append(f"{path.name}: category must be one of {', '.join(CATEGORIES)}")
		elif not path.read_text(encoding="utf-8").strip():
			bad.append(f"{path.name}: empty")
		else:
			found.append((m["id"], m["cat"], path))
	return found, bad


def _entry(frag_id: str, text: str) -> list[str]:
	"""A fragment's lines as bullets, with the PR number appended to the first when the id is one."""
	lines = [ln.rstrip() for ln in text.strip().splitlines() if ln.strip()]
	bullets = [ln if ln.lstrip().startswith(("-", "*")) else f"- {ln}" for ln in lines]
	if frag_id.isdigit() and f"#{frag_id}" not in bullets[0]:
		bullets[0] += f" (#{frag_id})"
	return bullets


def render(version: str, date: str, found: list[tuple[str, str, Path]]) -> str:
	out = [f"## [{version}] - {date}", ""]
	for cat, title in CATEGORIES.items():
		items = [b for fid, c, p in found if c == cat for b in _entry(fid, p.read_text(encoding="utf-8"))]
		if items:
			out += [f"### {title}", "", *items, ""]
	if len(out) == 2:
		out += ["No user-facing changes.", ""]
	return "\n".join(out)


def collect(root: Path, version: str, date: str) -> str:
	parse_version(version)
	found, bad = fragments(root)
	if bad:
		raise ValueError("; ".join(bad))
	section = render(version, date, found)
	path = root / CHANGELOG
	text = path.read_text(encoding="utf-8")
	if MARKER not in text:
		raise ValueError(f"{CHANGELOG} lacks the marker line {MARKER}")
	if f"## [{version}]" in text:
		raise ValueError(f"{CHANGELOG} already has a {version} section")
	path.write_text(  # NOSONAR -- CHANGELOG under the operator's checkout root
		text.replace(MARKER, f"{MARKER}\n\n{section}".rstrip() + "\n", 1), encoding="utf-8"
	)
	for _fid, _cat, p in found:
		p.unlink()
	return section


def main(argv: list[str] | None = None) -> int:
	ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	sub = ap.add_subparsers(dest="cmd", required=True)
	sub.add_parser("version")
	sub.add_parser("tag")
	sub.add_parser("check")
	sub.add_parser("preview")
	s = sub.add_parser("set")
	s.add_argument("version")
	c = sub.add_parser("collect")
	c.add_argument("version")
	c.add_argument("--date", default=dt.date.today().isoformat())
	args = ap.parse_args(argv)
	root = Path.cwd()
	try:
		if args.cmd == "version":
			print(read_version(root))
		elif args.cmd == "tag":
			print(git_tag(read_version(root)))
		elif args.cmd == "check":
			parse_version(read_version(root))
			_found, bad = fragments(root)
			for line in bad:
				print(f"changelog.d/{line}", file=sys.stderr)
			return 1 if bad else 0
		elif args.cmd == "preview":
			found, _bad = fragments(root)
			print(render(read_version(root), "unreleased", found))
		elif args.cmd == "set":
			set_version(root, args.version)
		elif args.cmd == "collect":
			print(collect(root, args.version, args.date))
	except ValueError as exc:
		print(f"release.py: {exc}", file=sys.stderr)
		return 1
	return 0


if __name__ == "__main__":
	sys.exit(main())
