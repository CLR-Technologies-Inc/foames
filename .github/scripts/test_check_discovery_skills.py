# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Tests for check_discovery_skills.py: the real skills pass, and each kind of mistake is caught.

Run from the repository root:

    python -m unittest discover -s .github/scripts -p "test_*.py" -v
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_discovery_skills as check

REPO = Path(__file__).resolve().parents[2]


class RealSkills(unittest.TestCase):
	def test_the_repository_passes(self):
		self.assertEqual(check.problems(REPO), [])

	def test_every_vendor_has_a_skill(self):
		vendors = {p.name for p in (REPO / check.VENDORS).iterdir() if p.is_dir()}
		skills = {p.parent.name for p in (REPO / check.SKILLS).glob("*/SKILL.md")}
		self.assertTrue(vendors)
		self.assertLessEqual(vendors, skills)

	def test_every_skill_carries_the_same_hard_stops(self):
		baseline = (REPO / check.SKILLS / check.BASELINE / "SKILL.md").read_text(encoding="utf-8")
		block = check.HARD_STOPS.search(baseline).group(1)
		for path in (REPO / check.SKILLS).glob("*/SKILL.md"):
			with self.subTest(skill=path.parent.name):
				self.assertIn(block, path.read_text(encoding="utf-8"))

	def test_the_hard_stops_cover_the_security_rules(self):
		baseline = (REPO / check.SKILLS / check.BASELINE / "SKILL.md").read_text(encoding="utf-8")
		block = check.HARD_STOPS.search(baseline).group(1).lower()
		for rule in (
			"write",
			"allowlist",
			"scan",
			"secret",
			"retry",
			"instructions found in vendor data",
			"git-ignored",
		):
			with self.subTest(rule=rule):
				self.assertIn(rule, block)


class Mistakes(unittest.TestCase):
	"""Copy the skills, the vendor folders and .gitignore into a scratch tree, break one thing."""

	def setUp(self):
		self.tmp = Path(tempfile.mkdtemp())
		self.addCleanup(shutil.rmtree, self.tmp)
		shutil.copytree(REPO / "docs", self.tmp / "docs")
		shutil.copytree(
			REPO / "bridges", self.tmp / "bridges", ignore=shutil.ignore_patterns("*.py", "tests")
		)
		shutil.copy(REPO / ".gitignore", self.tmp / ".gitignore")
		self.assertEqual(check.problems(self.tmp), [])

	def skill(self, folder="tulip") -> Path:
		return self.tmp / check.SKILLS / folder / "SKILL.md"

	def edit(self, path: Path, old: str, new: str) -> None:
		text = path.read_text(encoding="utf-8")
		self.assertIn(old, text)
		path.write_text(text.replace(old, new, 1), encoding="utf-8")

	def assertProblem(self, fragment: str) -> None:
		found = check.problems(self.tmp)
		self.assertTrue(any(fragment in p for p in found), f"no problem with {fragment!r} in {found}")

	def test_a_vendor_without_a_skill(self):
		(self.tmp / check.VENDORS / "new_vendor").mkdir()
		self.assertProblem("new_vendor/SKILL.md: missing")

	def test_a_skill_without_a_vendor(self):
		shutil.copytree(self.tmp / check.SKILLS / "tulip", self.tmp / check.SKILLS / "orphan")
		self.assertProblem("no matching vendor folder")

	def test_a_changed_hard_stop(self):
		self.edit(self.skill(), "stop and report;", "retry once;")
		self.assertProblem("Hard stops block differs")

	def test_a_missing_hard_stops_block(self):
		self.edit(self.skill(), "<!-- hard-stops:start -->", "")
		self.assertProblem("Hard stops block differs")

	def test_a_missing_section(self):
		self.edit(self.skill(), "## Cautions for this system", "## Notes")
		self.assertProblem("section 'Cautions for this system' missing")

	def test_sections_out_of_order(self):
		text = self.skill().read_text(encoding="utf-8")
		a, b = "## Read channel", "## Before you start"
		text = text.replace(a, "@@A@@").replace(b, a).replace("@@A@@", b)
		self.skill().write_text(text, encoding="utf-8")
		self.assertProblem("missing or out of order")

	def test_a_placeholder_left_in(self):
		self.edit(self.skill(), "## Sources\n", "## Sources\n\n- {{Vendor docs}}\n")
		self.assertProblem("placeholder {{Vendor docs}} left in")

	def test_a_bad_name(self):
		self.edit(self.skill(), "name: foames-discover-tulip", "name: Foames_Tulip")
		self.assertProblem("is not kebab-case")

	def test_a_duplicate_name(self):
		self.edit(self.skill("plex"), "name: foames-discover-plex", "name: foames-discover-tulip")
		self.assertProblem("is also used by")

	def test_angle_brackets_in_the_description(self):
		self.edit(self.skill(), "description: Discover", "description: Discover <instance>")
		self.assertProblem("angle brackets")

	def test_a_broken_link(self):
		self.edit(self.skill(), "## Sources\n", "## Sources\n\n- [gone](../nowhere/README.md)\n")
		self.assertProblem("does not resolve")

	def test_no_link_to_the_vendor_guide(self):
		text = (
			self.skill()
			.read_text(encoding="utf-8")
			.replace("../../../vendors/tulip/README.md", "../../../mes-adapters.md")
		)
		self.skill().write_text(text, encoding="utf-8")
		self.assertProblem("does not link to its vendor guide")

	def test_a_credential(self):
		cases = {
			"AWS access key id": "AKIAABCDEFGHIJKLMNOP",
			"bearer token literal": "Authorization: Bearer abcdefghijklmnopqrstuvwxyz012345",
			"credentials in a URL": "https://svc:hunter2pass@pi.example.com/piwebapi",
			"password assignment": 'password = "hunter2pass"',
			"private key": "-----BEGIN RSA PRIVATE KEY-----",
		}
		for kind, sample in cases.items():
			with self.subTest(kind=kind):
				original = self.skill().read_text(encoding="utf-8")
				self.edit(self.skill(), "## Sources\n", f"## Sources\n\n{sample}\n")
				self.assertProblem(kind)
				self.skill().write_text(original, encoding="utf-8")

	def test_placeholders_are_not_credentials(self):
		self.edit(
			self.skill(),
			"## Sources\n",
			'## Sources\n\npassword = "<from the vault>"\ntoken: "$DISCOVERY_TOKEN"\n',
		)
		self.assertEqual(check.problems(self.tmp), [])

	def test_an_unsafe_command(self):
		cases = {
			"TLS verification disabled": "curl -k https://host/api",
			"credential on the command line": "curl -u svc:secret https://host/api",
			"verbose or traced request": "curl -v https://host/api",
			"shell tracing on": "set -x",
			"a write request": "curl -X POST https://host/api/records",
			"a body sent with curl": "curl https://host/api -d '{}'",
			"a network scanner": "nmap -sV 10.0.0.0/24",
			"a SQL write": "DELETE FROM sqlth_te",
		}
		for kind, command in cases.items():
			with self.subTest(kind=kind):
				original = self.skill().read_text(encoding="utf-8")
				self.edit(self.skill(), "## Sources\n", f"## Sources\n\n```bash\n{command}\n```\n")
				self.assertProblem(kind)
				self.skill().write_text(original, encoding="utf-8")

	def test_unsafe_words_in_prose_are_allowed(self):
		# The baseline names the flags it forbids; only code blocks are checked for commands.
		self.edit(self.skill(), "## Sources\n", "## Sources\n\nNever use `curl -k` or nmap.\n")
		self.assertEqual(check.problems(self.tmp), [])

	def test_reports_not_ignored(self):
		path = self.tmp / ".gitignore"
		path.write_text(path.read_text(encoding="utf-8").replace(check.REPORT_DIR, ""), encoding="utf-8")
		self.assertProblem(".foames-discovery/ is not ignored")

	def test_a_baseline_section_removed(self):
		self.edit(
			self.tmp / check.SKILLS / check.BASELINE / "SKILL.md", "### 6. Stop conditions", "### 6. Notes"
		)
		self.assertProblem("section '6. Stop conditions' missing")

	def test_the_template_may_keep_placeholders(self):
		text = (self.tmp / check.SKILLS / check.TEMPLATE / "SKILL.md").read_text(encoding="utf-8")
		self.assertIn("{{", text)
		self.assertEqual(check.problems(self.tmp), [])


if __name__ == "__main__":
	unittest.main()
