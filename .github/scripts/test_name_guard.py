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

"""Tests for name_guard.py. The words, names and addresses here are placeholders, never real ones."""

import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))

import name_guard as ng


def addr(local, domain):
	"""Build an address at run time, so this file holds no literal address the guard would flag."""
	return local + "@" + domain


AUTHOR = addr("jo", "uni.edu")
OLD_AUTHOR = addr("old", "uni.edu")
CITED = addr("cited", "journal.org")
COAUTHOR = addr("ann", "corp.co")
SIGNER = addr("b", "x.io")
STRANGER = addr("buyer", "client.co")


class TestGuardedWords(unittest.TestCase):
	def setUp(self):
		self.guard = ng.parse_list("# comment\nAcme|exempt\nGlobex, initech\nidentity:private.test\n")
		self.words = self.guard.words

	def test_parse(self):
		self.assertEqual([w.index for w in self.words], [1, 2, 3])
		self.assertEqual([w.exempt for w in self.words], [True, False, False])
		self.assertEqual(self.guard.identities, ["private.test"])

	def test_whole_words_any_case(self):
		self.assertEqual(ng.find_in_text("tenant GLOBEX here", self.words), [(1, 2)])
		self.assertEqual(ng.find_in_text("tenant_globex", self.words), [(1, 2)])
		self.assertEqual(ng.find_in_text("globexian globex2", self.words), [])

	def test_exempt_word(self):
		self.assertEqual(ng.find_in_text("Copyright Acme Technologies Inc.", self.words), [])
		self.assertEqual(ng.find_in_text("github.com/Acme-Technologies-Inc/x", self.words), [])
		self.assertEqual(ng.find_in_text("estate = 'acme'", self.words), [(1, 1)])
		self.assertEqual(ng.find_in_text("grant to Acme", self.words, exempt_path=True), [])
		self.assertEqual(ng.find_in_text("Initech", self.words, exempt_path=True), [(1, 3)])
		self.assertEqual(ng.find_in_text("Add the Acme contact address for corporate CLAs", self.words), [])
		self.assertEqual(ng.find_in_text("Initech under the license", self.words), [(1, 3)])

	def test_exempt_paths(self):
		self.assertTrue(ng.path_is_exempt("cla/ICLA.md"))
		self.assertTrue(ng.path_is_exempt("LICENSE"))
		self.assertFalse(ng.path_is_exempt("docs/cla/ICLA.md"))


class TestIdentity(unittest.TestCase):
	def setUp(self):
		self.guard = ng.parse_list("Globex\nidentity:private.test\nidentity:me@elsewhere.test\n")

	def test_own_identity_passes(self):
		# Whatever address a contributor signs with is theirs to publish.
		self.assertEqual(ng.check_identity("author", AUTHOR, self.guard), [])
		self.assertEqual(ng.check_identity("author", "1+jo@users.noreply.github.com", self.guard), [])

	def test_private_identity_is_caught(self):
		self.assertTrue(ng.check_identity("author", "Me@Private.test", self.guard))
		self.assertTrue(ng.check_identity("author", "me@mail.private.test", self.guard))
		self.assertTrue(ng.check_identity("author", "me@elsewhere.test", self.guard))
		self.assertFalse(ng.check_identity("author", "you@elsewhere.test", self.guard))
		self.assertTrue(ng.check_identity("author", "jo@globex.test", self.guard))


class TestOtherPeoplesEmails(unittest.TestCase):
	def setUp(self):
		self.policy = ng.EmailPolicy({AUTHOR}, {CITED})

	def test_allowed(self):
		p = self.policy
		self.assertTrue(p.allows(AUTHOR.upper()))
		self.assertTrue(p.allows(CITED))
		self.assertTrue(p.allows("noreply@anthropic.com"))
		self.assertTrue(p.allows("someone@example.com"))
		self.assertTrue(p.allows("x@sub.example.org"))
		self.assertTrue(p.allows("x@host.test"))
		self.assertTrue(p.allows(STRANGER, "NOTICE"))
		self.assertTrue(p.allows(STRANGER, "CITATION.cff"))
		self.assertTrue(p.allows(STRANGER, "docs/refs.bib"))

	def test_blocked(self):
		self.assertFalse(self.policy.allows(STRANGER))
		self.assertFalse(self.policy.allows(STRANGER, "foames/x.py"))

	def test_trailers(self):
		msg = f"Fix it\n\nper {STRANGER}\n\nCo-authored-by: Ann <{COAUTHOR}>\nSigned-off-by: B <{SIGNER}>"
		self.assertEqual(ng.trailer_emails(msg), {COAUTHOR, SIGNER})
		self.assertNotIn(COAUTHOR, ng.message_without_trailers(msg))
		policy = ng.EmailPolicy(ng.trailer_emails(msg), set())
		self.assertEqual(ng.emails_in_text(ng.message_without_trailers(msg), policy), [3])

	def test_added_lines(self):
		diff = (
			"diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1,0 +5,2 @@\n"
			f"+x = '{STRANGER}'\n+y = 1\n"
			"diff --git a/gone.py b/gone.py\n--- a/gone.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-z\n"
		)
		self.assertEqual(ng.added_lines(diff), [("a.py", 5, f"x = '{STRANGER}'"), ("a.py", 6, "y = 1")])
		problems = ng.check_added_lines(diff, self.policy)
		self.assertEqual(len(problems), 1)
		self.assertNotIn(STRANGER, problems[0])


class TestModes(unittest.TestCase):
	"""The CI and commit-msg modes end to end, in a throwaway repository."""

	def git(self, *args, env=None):
		subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True, env=env)

	def commit(self, email, files, message="change"):
		for path, text in files.items():
			with open(os.path.join(self.repo, path), "w", encoding="utf-8") as f:
				f.write(text)
		self.git("add", "-A")
		env = dict(os.environ, GIT_AUTHOR_NAME="X", GIT_AUTHOR_EMAIL=email)
		env.update(GIT_COMMITTER_NAME="X", GIT_COMMITTER_EMAIL=email)
		self.git("commit", "-q", "-m", message, env=env)

	def setUp(self):
		self.tmp = tempfile.TemporaryDirectory()
		self.repo = self.tmp.name
		self.git("init", "-q", "-b", "main")
		self.commit(OLD_AUTHOR, {"refs.md": f"Ask {CITED}\n"})
		self.git("tag", "base")
		self.cwd = os.getcwd()
		os.chdir(self.repo)
		os.environ["NAME_GUARD_WORDS"] = "Globex\nidentity:private.test"

	def tearDown(self):
		os.chdir(self.cwd)
		os.environ.pop("NAME_GUARD_WORDS", None)
		self.tmp.cleanup()

	def check(self):
		return ng.run_range("base..HEAD", ng.load_list(), [])

	def test_own_address_trailers_and_references_pass(self):
		self.commit(
			AUTHOR,
			{"a.md": f"Contact {AUTHOR}; see {CITED}; demo@example.com\n"},
			f"Add a\n\nCo-authored-by: Ann <{COAUTHOR}>",
		)
		self.commit(AUTHOR, {"b.md": f"Thanks to {COAUTHOR}\n"})
		self.assertEqual(self.check(), [])

	def test_third_party_address_is_caught(self):
		self.commit(AUTHOR, {"a.md": f"Customer contact: {STRANGER}\n"})
		self.assertEqual(len(self.check()), 1)

	def test_private_identity_and_words_are_caught(self):
		self.commit("me@private.test", {"a.md": "tenant globex\n"}, "Mention Globex")
		problems = self.check()
		self.assertTrue(any("keeps private" in p for p in problems))
		self.assertTrue(any("message" in p and "guarded word" in p for p in problems))
		self.assertTrue(any(p.startswith("a.md:1") for p in problems))

	def test_commit_message_hook(self):
		path = os.path.join(self.repo, "MSG")
		with open(path, "w", encoding="utf-8") as f:
			f.write(f"Fix\n\nper {STRANGER}\n\nCo-authored-by: A <{COAUTHOR}>\n# {STRANGER} in a comment\n")
		self.assertEqual(len(ng.run_message(path, ng.load_list())), 1)


if __name__ == "__main__":
	unittest.main()
