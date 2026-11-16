# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep guarded names and unapproved author emails out of the public repository.

FoaMES isolates tenants and providers generically and never names a particular
company in that role. The list of words to keep out is private, so it is not in
this repository: CI reads it from the ``NAME_GUARD_WORDS`` secret, and a local
checkout reads it from the same environment variable or from
``.git/name-guard-words`` (inside .git, so it is never committed).

Word list format: one word per line (commas also separate). A word written as
``word|exempt`` is still allowed where it names the copyright holder: in the
license, NOTICE, CLA, CONTRIBUTING and licensing files, and wherever it is followed by
"Technologies" (as in the company name or the GitHub organisation). Lines
starting with ``#`` are comments. Matching ignores case and needs whole words.

Findings never print the matched text, only the file, line and the word's
position in the list, so the log does not disclose the words either.

Usage:
  name_guard.py [PATH ...]           scan the given files (default: all tracked files)
  name_guard.py --text-env VAR       also scan the text in environment variable VAR
  name_guard.py --check-authors A..B check author and committer emails in a commit range
  name_guard.py --check-git-email    check the local git user.email (skipped in CI)

Exit status is 1 when anything is found, 0 otherwise. With no word list it only
warns, unless --require is given.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import subprocess
import sys
from dataclasses import dataclass

EXEMPT_PATHS = ("LICENSE", "NOTICE", "CONTRIBUTING.md", "cla/*", "docs/licensing.md")
COMPANY_SUFFIX = re.compile(r"[ -]Technologies", re.IGNORECASE)
DEFAULT_ALLOWED_EMAILS = (
	"noreply@anthropic.com",
	"noreply@github.com",
	"*@users.noreply.github.com",
	"dev@clrtechnologies.co",
)
WORDS_FILE = os.path.join(".git", "name-guard-words")


@dataclass(frozen=True)
class Word:
	index: int
	pattern: re.Pattern
	exempt: bool


def parse_words(raw: str) -> list[Word]:
	words = []
	for item in re.split(r"[,\n]", raw):
		item = item.strip()
		if not item or item.startswith("#"):
			continue
		text, _, flag = item.partition("|")
		text = text.strip()
		if not text:
			continue
		pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(text)}(?![A-Za-z0-9])", re.IGNORECASE)
		words.append(Word(len(words) + 1, pattern, flag.strip().lower() == "exempt"))
	return words


def load_words() -> list[Word]:
	raw = os.environ.get("NAME_GUARD_WORDS", "")
	if not raw.strip() and os.path.exists(WORDS_FILE):
		# A fixed path inside the local .git directory, not request input.
		with open(WORDS_FILE, encoding="utf-8") as f:  # nosemgrep
			raw = f.read()
	return parse_words(raw)


def path_is_exempt(path: str) -> bool:
	path = path.replace("\\", "/")
	return any(fnmatch.fnmatch(path, p) for p in EXEMPT_PATHS)


def find_in_text(text: str, words: list[Word], exempt_path: bool = False) -> list[tuple[int, int]]:
	"""Return (line number, word index) for each guarded word found in text."""
	hits = []
	for lineno, line in enumerate(text.splitlines(), 1):
		for word in words:
			for m in word.pattern.finditer(line):
				if word.exempt and (exempt_path or COMPANY_SUFFIX.match(line, m.end())):
					continue
				hits.append((lineno, word.index))
				break
	return hits


def tracked_files() -> list[str]:
	out = subprocess.run(["git", "ls-files", "-z"], capture_output=True, check=True).stdout
	return [p for p in out.decode("utf-8").split("\0") if p]


def scan_files(paths: list[str], words: list[Word]) -> list[str]:
	problems = []
	for path in paths:
		if not os.path.isfile(path):
			continue
		try:
			# Tracked files or paths pre-commit passes in, in a local or CI checkout; not request input.
			with open(path, encoding="utf-8") as f:  # nosemgrep
				text = f.read()
		except (UnicodeDecodeError, OSError):
			continue
		for lineno, index in find_in_text(text, words, path_is_exempt(path)):
			problems.append(f"{path}:{lineno}: guarded word #{index}")
	# Path names can disclose a name too.
	for path in paths:
		for _lineno, index in find_in_text(path, words):
			problems.append(f"{path}: file path contains guarded word #{index}")
	return problems


def email_allowed(email: str, allowed: tuple[str, ...]) -> bool:
	return any(fnmatch.fnmatch(email.lower(), p.lower()) for p in allowed)


def allowed_emails() -> tuple[str, ...]:
	raw = os.environ.get("ALLOWED_AUTHOR_EMAILS", "")
	extra = tuple(e.strip() for e in raw.split(",") if e.strip())
	return DEFAULT_ALLOWED_EMAILS + extra


def check_authors(rev_range: str, words: list[Word]) -> list[str]:
	out = subprocess.run(
		["git", "log", "--format=%h%x00%ae%x00%ce", rev_range], capture_output=True, text=True, check=True
	).stdout
	problems = []
	allowed = allowed_emails()
	for line in out.splitlines():
		sha, author, committer = line.split("\0")
		for role, email in (("author", author), ("committer", committer)):
			if not email_allowed(email, allowed):
				problems.append(f"commit {sha}: {role} email is not an approved address")
			elif find_in_text(email, words):
				problems.append(f"commit {sha}: {role} email contains a guarded word")
	return problems


def check_git_email(words: list[Word]) -> list[str]:
	if os.environ.get("CI"):
		return []
	email = subprocess.run(["git", "config", "user.email"], capture_output=True, text=True).stdout.strip()
	if not email_allowed(email, allowed_emails()) or find_in_text(email, words):
		msg = (
			"git user.email for this repository is not an approved address; set it with "
			"`git config user.email <approved address>` (see CONTRIBUTING.md)"
		)
		return [msg]
	return []


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(
		description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
	)
	parser.add_argument("paths", nargs="*")
	parser.add_argument("--text-env", action="append", default=[])
	parser.add_argument("--check-authors")
	parser.add_argument("--check-git-email", action="store_true")
	parser.add_argument("--require", action="store_true", help="fail when no word list is configured")
	args = parser.parse_args(argv)

	words = load_words()
	problems = []
	if args.check_git_email:
		problems += check_git_email(words)
	if args.check_authors:
		problems += check_authors(args.check_authors, words)

	if not words:
		msg = "name guard: no word list configured (NAME_GUARD_WORDS or .git/name-guard-words); name scan skipped"
		if args.require:
			problems.append(msg)
		elif os.environ.get("GITHUB_ACTIONS"):
			print(f"::warning::{msg}")
		else:
			print(msg, file=sys.stderr)
	else:
		problems += scan_files(args.paths or tracked_files(), words)
		for var in args.text_env:
			for lineno, index in find_in_text(os.environ.get(var, ""), words):
				problems.append(f"{var}:{lineno}: guarded word #{index}")

	for p in problems:
		print(f"::error::{p}" if os.environ.get("GITHUB_ACTIONS") else p)
	return 1 if problems else 0


if __name__ == "__main__":
	sys.exit(main())
