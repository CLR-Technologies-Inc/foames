# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for name_guard.py. The words here are placeholders, never real names."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))

import name_guard as ng


class TestFind(unittest.TestCase):
	def setUp(self):
		self.words = ng.parse_words("# comment\nAcme|exempt\nGlobex, initech\n")

	def test_parse(self):
		self.assertEqual([w.index for w in self.words], [1, 2, 3])
		self.assertEqual([w.exempt for w in self.words], [True, False, False])

	def test_whole_words_any_case(self):
		self.assertEqual(ng.find_in_text("tenant GLOBEX here", self.words), [(1, 2)])
		self.assertEqual(ng.find_in_text("tenant_globex", self.words), [(1, 2)])
		self.assertEqual(ng.find_in_text("globexian globex2", self.words), [])

	def test_exempt_word(self):
		self.assertEqual(ng.find_in_text("Copyright Acme Technologies Inc.", self.words), [])
		self.assertEqual(ng.find_in_text("github.com/Acme-Technologies-Inc/x", self.words), [])
		self.assertEqual(ng.find_in_text("estate = 'acme'", self.words), [(1, 1)])
		self.assertEqual(ng.find_in_text("grant to Acme", self.words, exempt_path=True), [])

	def test_exempt_path_does_not_cover_other_words(self):
		self.assertEqual(ng.find_in_text("Initech", self.words, exempt_path=True), [(1, 3)])

	def test_exempt_paths(self):
		self.assertTrue(ng.path_is_exempt("cla/ICLA.md"))
		self.assertTrue(ng.path_is_exempt("LICENSE"))
		self.assertFalse(ng.path_is_exempt("docs/cla/ICLA.md"))

	def test_line_numbers(self):
		self.assertEqual(ng.find_in_text("a\nb initech\nc", self.words), [(2, 3)])

	def test_emails(self):
		allowed = ng.DEFAULT_ALLOWED_EMAILS
		self.assertTrue(ng.email_allowed("noreply@anthropic.com", allowed))
		self.assertTrue(ng.email_allowed("123+someone@users.noreply.github.com", allowed))
		self.assertFalse(ng.email_allowed("someone@example.com", allowed))

	def test_no_words_warns_only(self):
		old = os.environ.pop("NAME_GUARD_WORDS", None)
		try:
			os.environ["NAME_GUARD_WORDS"] = ""
			self.assertEqual(ng.main(["--text-env", "NOPE"]), 0)
			self.assertEqual(ng.main(["--require", "--text-env", "NOPE"]), 1)
		finally:
			if old is not None:
				os.environ["NAME_GUARD_WORDS"] = old


if __name__ == "__main__":
	unittest.main()
