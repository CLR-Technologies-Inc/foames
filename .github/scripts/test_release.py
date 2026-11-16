# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for release.py: version forms, Git tags and collecting changelog fragments."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import release  # noqa: E402

CHANGELOG = f"# Changelog\n\n{release.MARKER}\n\n## [0.2.0] - 2026-11-16\n\n- Old.\n"


class TestVersions(unittest.TestCase):
	def test_tags(self):
		self.assertEqual(release.git_tag("0.2.0"), "v0.2.0")
		self.assertEqual(release.git_tag("0.3.0.dev0"), "v0.3.0-dev.0")
		self.assertEqual(release.git_tag("0.3.0rc1"), "v0.3.0-rc.1")
		self.assertEqual(release.git_tag("0.3.0b2"), "v0.3.0-beta.2")

	def test_prerelease(self):
		self.assertFalse(release.is_prerelease("0.2.0"))
		self.assertTrue(release.is_prerelease("0.3.0.dev0"))
		self.assertTrue(release.is_prerelease("0.3.0rc1"))

	def test_rejects_other_forms(self):
		for bad in ("0.3", "v0.3.0", "0.3.0-rc.1", "0.3.0.post1", "0.3.0dev"):
			with self.assertRaises(ValueError, msg=bad):
				release.parse_version(bad)

	def test_repo_version_is_valid(self):
		root = Path(__file__).resolve().parents[2]
		release.parse_version(release.read_version(root))


class TestFragments(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.TemporaryDirectory()
		self.root = Path(self.tmp.name)
		(self.root / "foames").mkdir()
		(self.root / "foames/__init__.py").write_text('__version__ = "0.3.0.dev0"\n')
		(self.root / "changelog.d").mkdir()
		(self.root / "changelog.d/README.md").write_text("how to\n")
		(self.root / "CHANGELOG.md").write_text(CHANGELOG)

	def tearDown(self):
		self.tmp.cleanup()

	def frag(self, name, text):
		(self.root / "changelog.d" / name).write_text(text)

	def test_set_version(self):
		release.set_version(self.root, "0.3.0rc1")
		self.assertEqual(release.read_version(self.root), "0.3.0rc1")
		with self.assertRaises(ValueError):
			release.set_version(self.root, "0.3")

	def test_bad_names(self):
		self.frag("notes.md", "x")
		self.frag("81.feature.md", "x")
		self.frag("82.added.md", "  \n")
		_found, bad = release.fragments(self.root)
		self.assertEqual(len(bad), 3)

	def test_collect(self):
		self.frag("81.added.md", "A new thing.\n")
		self.frag("82.fixed.md", "- One fix (#82).\n- Another.\n")
		self.frag("pfmea-docs.docs.md", "Better PFMEA docs.\n")
		section = release.collect(self.root, "0.3.0", "2026-12-01")
		self.assertIn("## [0.3.0] - 2026-12-01", section)
		self.assertIn("- A new thing. (#81)", section)
		self.assertIn("- One fix (#82).", section)
		self.assertNotIn("(#82) (#82)", section)
		self.assertLess(section.index("### Added"), section.index("### Fixed"))
		self.assertLess(section.index("### Fixed"), section.index("### Documentation"))
		text = (self.root / "CHANGELOG.md").read_text()
		self.assertLess(text.index("[0.3.0]"), text.index("[0.2.0]"))
		left = sorted(p.name for p in (self.root / "changelog.d").iterdir())
		self.assertEqual(left, ["README.md"])

	def test_collect_twice_refused(self):
		with self.assertRaises(ValueError):
			release.collect(self.root, "0.2.0", "2026-11-16")


if __name__ == "__main__":
	unittest.main()
