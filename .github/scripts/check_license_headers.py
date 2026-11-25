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

"""Check that every source file carries the FoaMES Apache-2.0 license notice.

Each tracked, non-empty source file must start (after an optional shebang line, or an
`<!DOCTYPE>` line in HTML) with the Apache License 2.0 boilerplate notice from the LICENSE
appendix, followed by the SPDX identifier:

    # Copyright 2026 CLR Technologies Inc.
    #
    # Licensed under the Apache License, Version 2.0 (the "License");
    # ...
    # limitations under the License.
    #
    # SPDX-License-Identifier: Apache-2.0

`#` comments are used for Python, shell, YAML, TOML, pip requirements and Dockerfiles, `//` for JavaScript,
`/* */` for CSS and `<!-- -->` for HTML. Files that came from a third party and keep their own
notice are listed in THIRD_PARTY below, and generated files are skipped. No source file may point
at a `license.txt`: the license is in LICENSE. (Documentation may mention it, to explain the old
header.)

Standard library only. Run from the repository root:

    python .github/scripts/check_license_headers.py          # check
    python .github/scripts/check_license_headers.py --fix    # add or update the notice
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

HASH_SUFFIXES = {".py", ".sh", ".yml", ".yaml", ".toml"}
NAMES = {"Dockerfile"}
STYLE_BY_SUFFIX = {".js": "//", ".css": "/*", ".html": "<!--"}
# Paths of third-party files that keep their original header. Add a NOTICE entry with each one.
THIRD_PARTY: set[str] = {".github/workflows/scorecard.yml"}
# Generated output, rewritten by tools rather than by hand.
GENERATED_PREFIXES = ("benchmarks/results/",)

HOLDER = "CLR Technologies Inc."
YEAR = r"\d{4}(?:-\d{4})?"
NOTICE_BODY = [
	'Licensed under the Apache License, Version 2.0 (the "License");',
	"you may not use this file except in compliance with the License.",
	"You may obtain a copy of the License at",
	"",
	"    http://www.apache.org/licenses/LICENSE-2.0",
	"",
	"Unless required by applicable law or agreed to in writing, software",
	'distributed under the License is distributed on an "AS IS" BASIS,',
	"WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.",
	"See the License for the specific language governing permissions and",
	"limitations under the License.",
	"",
	"SPDX-License-Identifier: Apache-2.0",
]
DANGLING = re.compile(r"see\s+licen[cs]e\.txt", re.IGNORECASE)
# A file's first line that must stay first.
PREAMBLE = re.compile(r"(?:#![^\n]*\n|<!DOCTYPE[^\n]*\n)?", re.IGNORECASE)
# The short header that PR #62 introduced, replaced by --fix.
OLD_HEADER = re.compile(
	r"(?P<open>#|//|/\*|<!--) Copyright \(c\) (?P<year>\d{4}(?:-\d{4})?) CLR Technologies Inc\. and"
	r" contributors(?: \*/| -->)?\n"
	r"(?:#|//|/\*|<!--) SPDX-License-Identifier: Apache-2\.0(?: \*/| -->)?\n"
)


def notice_lines(year: str) -> list[str]:
	return [f"Copyright {year} {HOLDER}", "", *NOTICE_BODY]


def render(style: str, year: str) -> str:
	lines = notice_lines(year)
	if style in ("#", "//"):
		return "".join(f"{style} {line}\n" if line else f"{style}\n" for line in lines)
	if style == "/*":
		return "/*\n" + "".join(f" * {line}\n" if line else " *\n" for line in lines) + " */\n"
	return "<!--\n" + "".join(f"  {line}\n" if line else "\n" for line in lines) + "-->\n"


def pattern(style: str) -> re.Pattern[str]:
	marker = "@@YEAR@@"
	return re.compile(re.escape(render(style, marker)).replace(re.escape(marker), YEAR))


def style_for(path: Path) -> str | None:
	pip_file = path.suffix == ".txt" and (
		path.name.startswith("requirements") or path.parent.as_posix().endswith(".github/requirements")
	)
	if path.suffix in HASH_SUFFIXES or path.name in NAMES or pip_file:
		return "#"
	return STYLE_BY_SUFFIX.get(path.suffix)


def tracked_files(root: Path) -> list[str]:
	out = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True)
	return out.stdout.split()


def in_scope(name: str, path: Path, text: str) -> str | None:
	style = style_for(path)
	if style is None or name in THIRD_PARTY or name.startswith(GENERATED_PREFIXES):
		return None
	if not text.strip():
		return None
	return style


def has_notice(style: str, text: str) -> bool:
	pre = PREAMBLE.match(text)
	return bool(pattern(style).match(text, pre.end() if pre else 0))


def fixed(style: str, text: str) -> str:
	pre = PREAMBLE.match(text)
	head, rest = text[: pre.end()], text[pre.end() :]
	year = "2026"
	old = OLD_HEADER.match(rest)
	if old:
		year = old.group("year")
		rest = rest[old.end() :]
	sep = "" if rest.startswith("\n") or not rest else "\n"
	return head + render(style, year) + sep + rest


def problems(root: Path, files: list[str], fix: bool = False) -> list[str]:
	found = []
	for name in files:
		path = root / name
		if not path.is_file():
			continue
		try:
			text = path.read_text(encoding="utf-8")
		except UnicodeDecodeError:
			continue
		style = in_scope(name, path, text)
		if style is None:
			continue
		if DANGLING.search(text) and name != ".github/scripts/check_license_headers.py":
			found.append(f"{name}: refers to a license.txt; the license is in LICENSE")
		if not has_notice(style, text):
			if fix:
				path.write_text(fixed(style, text), encoding="utf-8")
			else:
				found.append(f"{name}: missing the Apache-2.0 license notice")
	return found


def main(argv: list[str]) -> int:
	root = Path(__file__).resolve().parents[2]
	found = problems(root, tracked_files(root), fix="--fix" in argv)
	for line in found:
		print(line)
	if found:
		print(f"\n{len(found)} file(s) need fixing. Run this script with --fix, or see CONTRIBUTING.md.")
		return 1
	return 0


if __name__ == "__main__":
	sys.exit(main(sys.argv[1:]))
