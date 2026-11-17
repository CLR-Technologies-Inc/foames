# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Catch unintended disclosure in the public repository, with specific rules.

This is not an omnibus block on names and emails. Information that is meant to be
public passes: a contributor's own identity on the commits they author, authorship
trailers, attribution and citation files, references already in the repository, and
documentation placeholders. Three separate checks look for what should not be here.

1. Guarded words. FoaMES isolates tenants and providers generically and never names a
   particular company in that role. The words to keep out are private, so they are not
   in this repository: CI reads them from the ``NAME_GUARD_WORDS`` secret and a local
   checkout from the same environment variable or ``.git/name-guard-words`` (inside
   .git, so never committed). Checked in every tracked file and path, commit messages
   and pull request text.

2. Author identity. A commit's author and committer name and email are the
   contributor's own signature and pass as they are. The only exception is an identity
   the project has marked private in the same list (``identity:<address or domain>``),
   for example a personal address configured on a machine by mistake.

3. Other people's email addresses. An address that appears in *new* content (added
   lines, commit messages, pull request text) must belong to someone who took part in
   the change, or already be public. It passes when it is:
   - the author or committer of a commit in the change, or named in an authorship
     trailer (Co-authored-by, Signed-off-by, Reviewed-by and the like);
   - already present in the repository before the change;
   - a noreply address, or on a documentation domain (example.com, .test, .invalid...);
   - in an attribution or reference file (NOTICE, AUTHORS, CONTRIBUTORS, CITATION,
     .bib, CHANGELOG, .mailmap, CODEOWNERS);
   - listed in ``PUBLIC_EMAILS`` (comma-separated, for addresses published elsewhere).

List format: one entry per line (commas also separate); ``#`` starts a comment.
``word`` is banned everywhere. ``word|exempt`` is still allowed where it names the
copyright holder: in LICENSE, NOTICE, the CLA, CONTRIBUTING and licensing files,
wherever "Technologies" follows it, and on a line about copyright, licensing or the CLA. ``identity:<address or domain>`` marks a private
author identity. Matching ignores case; words need whole-word matches.

Findings print only where something was found, never the word or the address, so the
public CI log does not disclose them either.

Usage:
  name_guard.py --range BASE..HEAD [--text-env VAR ...]   CI: the whole change
  name_guard.py --staged [PATH ...]                       pre-commit: staged changes
  name_guard.py --message FILE                            commit-msg hook
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field

WORD_EXEMPT_PATHS = ("LICENSE", "NOTICE", "CONTRIBUTING.md", "cla/*", "docs/licensing.md")
COMPANY_SUFFIX = re.compile(r"[ -]Technologies", re.IGNORECASE)
LEGAL_CONTEXT = re.compile(r"\b(copyright|licen[cs]e[ds]?|CLAs?|contributor|NOTICE|SPDX)\b", re.IGNORECASE)
ATTRIBUTION_PATHS = (
	"NOTICE*",
	"*/NOTICE*",
	"AUTHORS*",
	"*/AUTHORS*",
	"CONTRIBUTORS*",
	"*/CONTRIBUTORS*",
	"CITATION*",
	"*.cff",
	"*.bib",
	"CHANGELOG*",
	"*/CHANGELOG*",
	".mailmap",
	"CODEOWNERS",
	".github/CODEOWNERS",
)
DOC_DOMAINS = ("example.com", "example.org", "example.net", "localhost")
DOC_TLDS = (".example", ".test", ".invalid", ".localhost")
TRAILER = re.compile(
	r"^(co-authored-by|signed-off-by|reviewed-by|acked-by|tested-by|reported-by|suggested-by|helped-by):",
	re.IGNORECASE,
)
EMAIL = re.compile(r"(?<![\w.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?![\w-])")  # NOSONAR
EMAIL_ERE = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"  # for git grep, which has no lookbehind
REV = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/^~@-]*")  # a revision git may be asked about, never an option
LIST_FILE = os.path.join(".git", "name-guard-words")


@dataclass(frozen=True)
class Word:
	index: int
	pattern: re.Pattern
	exempt: bool


@dataclass
class GuardList:
	words: list[Word] = field(default_factory=list)
	identities: list[str] = field(default_factory=list)

	@property
	def empty(self) -> bool:
		return not self.words and not self.identities


def parse_list(raw: str) -> GuardList:
	result = GuardList()
	for item in re.split(r"[,\n]", raw):
		item = item.strip()
		if not item or item.startswith("#"):
			continue
		if item.lower().startswith("identity:"):
			ident = item.split(":", 1)[1].strip().lower().lstrip("@")
			if ident:
				result.identities.append(ident)
			continue
		text, _, flag = item.partition("|")
		text = text.strip()
		if text:
			pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(text)}(?![A-Za-z0-9])", re.IGNORECASE)
			result.words.append(Word(len(result.words) + 1, pattern, flag.strip().lower() == "exempt"))
	return result


def parse_words(raw: str) -> list[Word]:
	return parse_list(raw).words


def load_list() -> GuardList:
	raw = os.environ.get("NAME_GUARD_WORDS", "")
	if not raw.strip() and os.path.exists(LIST_FILE):
		# A fixed path inside the local .git directory, not request input.
		with open(LIST_FILE, encoding="utf-8") as f:  # nosemgrep
			raw = f.read()
	return parse_list(raw)


def matches_any(path: str, patterns: tuple[str, ...]) -> bool:
	path = path.replace("\\", "/")
	return any(fnmatch.fnmatch(path, p) for p in patterns)


def path_is_exempt(path: str) -> bool:
	return matches_any(path, WORD_EXEMPT_PATHS)


# ---- check 1: guarded words -------------------------------------------------


def find_in_text(text: str, words: list[Word], exempt_path: bool = False) -> list[tuple[int, int]]:
	"""Return (line number, word index) for each guarded word found in text."""
	hits = []
	for lineno, line in enumerate(text.splitlines(), 1):
		for word in words:
			for m in word.pattern.finditer(line):
				if word.exempt and (
					exempt_path or COMPANY_SUFFIX.match(line, m.end()) or LEGAL_CONTEXT.search(line)
				):
					continue
				hits.append((lineno, word.index))
				break
	return hits


def scan_files_for_words(paths: list[str], words: list[Word]) -> list[str]:
	problems = []
	for path in paths:
		if not os.path.isfile(path):
			continue
		try:
			# Tracked files or paths pre-commit passes in, in a local or CI checkout; not request input.
			with open(path, encoding="utf-8") as f:  # nosemgrep  # NOSONAR
				text = f.read()
		except (UnicodeDecodeError, OSError):
			continue
		for lineno, index in find_in_text(text, words, path_is_exempt(path)):
			problems.append(f"{path}:{lineno}: guarded word #{index}")
		for _lineno, index in find_in_text(path, words):
			problems.append(f"{path}: file path contains guarded word #{index}")
	return problems


# ---- check 2: author identity -------------------------------------------------


def identity_is_private(email: str, identities: list[str]) -> bool:
	email = email.strip().lower()
	domain = email.rpartition("@")[2]
	for ident in identities:
		if "@" in ident:
			if email == ident:
				return True
		elif domain == ident or domain.endswith("." + ident):
			return True
	return False


def check_identity(label: str, email: str, guard: GuardList) -> list[str]:
	if identity_is_private(email, guard.identities) or find_in_text(email, guard.words):
		msg = (
			f"{label}: the email is one the project keeps private; commit with your GitHub noreply "
			"address or another address you intend to publish (see CONTRIBUTING.md)"
		)
		return [msg]
	return []


# ---- check 3: other people's email addresses ---------------------------------


@dataclass
class EmailPolicy:
	participants: set[str]
	already_public: set[str]

	def allows(self, email: str, path: str | None = None) -> bool:
		email = email.lower()
		domain = email.rpartition("@")[2]
		if email in self.participants or email in self.already_public:
			return True
		if "noreply" in email or domain in DOC_DOMAINS or domain.endswith(DOC_TLDS):
			return True
		if any(domain.endswith("." + d) for d in DOC_DOMAINS):
			return True
		return bool(path and matches_any(path, ATTRIBUTION_PATHS))


def public_emails() -> set[str]:
	raw = os.environ.get("PUBLIC_EMAILS", "")
	return {e.strip().lower() for e in raw.split(",") if e.strip()}


def trailer_emails(message: str) -> set[str]:
	found = set()
	for line in message.splitlines():
		if TRAILER.match(line.strip()):
			found.update(e.lower() for e in EMAIL.findall(line))
	return found


def message_without_trailers(message: str) -> str:
	return "\n".join("" if TRAILER.match(line.strip()) else line for line in message.splitlines())


def emails_in_text(text: str, policy: EmailPolicy, path: str | None = None) -> list[int]:
	"""Line numbers holding an address the policy does not allow."""
	return [
		lineno
		for lineno, line in enumerate(text.splitlines(), 1)
		if any(not policy.allows(e, path) for e in EMAIL.findall(line))
	]


def added_lines(diff: str) -> list[tuple[str, int, str]]:
	"""(path, new line number, text) for each line a unified diff with -U0 adds."""
	out, path, lineno = [], None, 0
	for line in diff.splitlines():
		if line.startswith("+++ "):
			target = line[4:]
			path = target[2:] if target.startswith("b/") else None
		elif line.startswith("@@"):
			m = re.search(r"\+(\d+)", line)
			lineno = int(m.group(1)) if m else 0
		elif line.startswith("+") and path:
			out.append((path, lineno, line[1:]))
			lineno += 1
	return out


def check_added_lines(diff: str, policy: EmailPolicy) -> list[str]:
	problems = []
	for path, lineno, text in added_lines(diff):
		if any(not policy.allows(e, path) for e in EMAIL.findall(text)):
			problems.append(f"{path}:{lineno}: email address of someone who is not part of this change")
	return problems


# ---- git helpers ----------------------------------------------------------------


def git(*args: str) -> str:
	return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def tracked_files() -> list[str]:
	return [p for p in git("ls-files", "-z").split("\0") if p]


def emails_at(rev: str) -> set[str]:
	"""Every address already in the tree at rev (public before the change)."""
	result = subprocess.run(
		["git", "grep", "-I", "-h", "-o", "-E", EMAIL_ERE, rev],
		capture_output=True,
		text=True,
	)
	return {e.lower() for e in EMAIL.findall(result.stdout)}


def local_email() -> str:
	return subprocess.run(["git", "config", "user.email"], capture_output=True, text=True).stdout.strip()


# ---- modes ------------------------------------------------------------------------


def run_range(rev_range: str, guard: GuardList, text_vars: list[str]) -> list[str]:
	base, _, head = rev_range.partition("..")
	head = head or "HEAD"
	for rev in (base, head):
		if not REV.fullmatch(rev):
			raise SystemExit(f"name guard: {rev!r} is not a revision range endpoint")
	merge_base = git("merge-base", base, head).strip() or base
	problems = []

	commits = []
	for record in git("log", "--format=%h%x00%ae%x00%ce%x00%B%x1e", f"{base}..{head}").split("\x1e"):
		if record.strip():
			sha, author, committer, message = record.strip("\n").split("\0", 3)
			commits.append((sha, author.lower(), committer.lower(), message))

	participants = public_emails()
	for sha, author, committer, message in commits:
		participants.update({author, committer} | trailer_emails(message))
		problems += check_identity(f"commit {sha} author", author, guard)
		if committer != author:
			problems += check_identity(f"commit {sha} committer", committer, guard)
	policy = EmailPolicy(participants, emails_at(merge_base))

	problems += check_added_lines(git("diff", "-U0", "--no-color", f"{merge_base}..{head}"), policy)
	for sha, _a, _c, message in commits:
		for lineno in emails_in_text(message_without_trailers(message), policy):
			problems.append(
				f"commit {sha} message:{lineno}: email address of someone who is not part of this change"
			)
		for lineno, index in find_in_text(message, guard.words):
			problems.append(f"commit {sha} message:{lineno}: guarded word #{index}")
	for var in text_vars:
		text = os.environ.get(var, "")
		for lineno in emails_in_text(text, policy):
			problems.append(f"{var}:{lineno}: email address of someone who is not part of this change")
		for lineno, index in find_in_text(text, guard.words):
			problems.append(f"{var}:{lineno}: guarded word #{index}")

	problems += scan_files_for_words(tracked_files(), guard.words)
	return problems


def run_staged(paths: list[str], guard: GuardList) -> list[str]:
	email = local_email()
	problems = check_identity("git user.email", email, guard) if email else []
	policy = EmailPolicy({email.lower()} | public_emails(), emails_at("HEAD"))
	problems += check_added_lines(git("diff", "--cached", "-U0", "--no-color"), policy)
	problems += scan_files_for_words(paths, guard.words)
	return problems


def run_message(path: str, guard: GuardList) -> list[str]:
	# The commit message file git passes to the commit-msg hook.
	with open(path, encoding="utf-8") as f:  # nosemgrep  # NOSONAR -- the commit-msg file git passes
		message = "\n".join(line for line in f.read().splitlines() if not line.startswith("#"))
	policy = EmailPolicy(
		{local_email().lower()} | public_emails() | trailer_emails(message), emails_at("HEAD")
	)
	problems = [
		f"commit message:{n}: email address of someone who is not part of this change"
		for n in emails_in_text(message_without_trailers(message), policy)
	]
	problems += [f"commit message:{n}: guarded word #{i}" for n, i in find_in_text(message, guard.words)]
	return problems


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(
		description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
	)
	parser.add_argument("paths", nargs="*")
	mode = parser.add_mutually_exclusive_group(required=True)
	mode.add_argument("--range", help="BASE..HEAD: check a whole change (CI)")
	mode.add_argument("--staged", action="store_true", help="check the staged changes (pre-commit)")
	mode.add_argument("--message", help="check a commit message file (commit-msg hook)")
	parser.add_argument(
		"--text-env", action="append", default=[], help="with --range: also check this variable"
	)
	parser.add_argument("--require", action="store_true", help="fail when no private list is configured")
	args = parser.parse_args(argv)

	guard = load_list()
	problems = []
	if guard.empty:
		msg = "name guard: no private list (NAME_GUARD_WORDS or .git/name-guard-words); words and private identities not checked"
		if args.require:
			problems.append(msg)
		elif os.environ.get("GITHUB_ACTIONS"):
			print(f"::warning::{msg}")
		else:
			print(msg, file=sys.stderr)

	if args.range:
		problems += run_range(args.range, guard, args.text_env)
	elif args.staged:
		problems += run_staged(args.paths, guard)
	else:
		problems += run_message(args.message, guard)

	for p in problems:
		print(f"::error::{p}" if os.environ.get("GITHUB_ACTIONS") else p)
	return 1 if problems else 0


if __name__ == "__main__":
	sys.exit(main())
