# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Check that every source file carries the FoaMES license header.

Each tracked, non-empty Python, JavaScript, shell, YAML or Dockerfile file must start (after an
optional shebang line) with:

    # Copyright (c) <year> CLR Technologies Inc. and contributors
    # SPDX-License-Identifier: Apache-2.0

(`//` instead of `#` in JavaScript). Files that came from a third party and keep their own notice
are listed in THIRD_PARTY below. No file may point at a `license.txt`: the license is in LICENSE.

Standard library only. Run from the repository root:

    python .github/scripts/check_license_headers.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

SUFFIXES = {".py", ".js", ".sh", ".yml", ".yaml"}
NAMES = {"Dockerfile"}
# Paths of third-party files that keep their original header. Add a NOTICE entry with each one.
THIRD_PARTY: set[str] = set()

COPYRIGHT = r"Copyright \(c\) \d{4}(?:-\d{4})? CLR Technologies Inc\. and contributors"
SPDX = r"SPDX-License-Identifier: Apache-2\.0"
DANGLING = re.compile(r"see\s+licen[cs]e\.txt", re.IGNORECASE)


def header_pattern(comment: str) -> re.Pattern[str]:
	c = re.escape(comment)
	return re.compile(rf"(?:#![^\n]*\n)?{c} {COPYRIGHT}\n{c} {SPDX}\n")


HEADERS = {"#": header_pattern("#"), "//": header_pattern("//")}


def tracked_files(root: Path) -> list[str]:
	out = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True)
	return out.stdout.split()


def problems(root: Path, files: list[str]) -> list[str]:
	found = []
	for name in files:
		path = root / name
		if not path.is_file():
			continue
		try:
			text = path.read_text(encoding="utf-8")
		except UnicodeDecodeError:
			continue
		if DANGLING.search(text) and name != ".github/scripts/check_license_headers.py":
			found.append(f"{name}: refers to a license.txt; the license is in LICENSE")
		checked = path.suffix in SUFFIXES or path.name in NAMES
		if not checked or name in THIRD_PARTY or not text.strip():
			continue
		comment = "//" if path.suffix == ".js" else "#"
		if not HEADERS[comment].match(text):
			found.append(f"{name}: missing the Apache-2.0 license header")
	return found


def main() -> int:
	root = Path(__file__).resolve().parents[2]
	found = problems(root, tracked_files(root))
	for line in found:
		print(line)
	if found:
		print(f"\n{len(found)} file(s) need fixing. The header is described in CONTRIBUTING.md.")
		return 1
	return 0


if __name__ == "__main__":
	sys.exit(main())
