# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Checks the usage agent skills under docs/agents/<agent>/SKILL.md against the tool catalogue.
No site is needed:

python -m unittest foames.foames_mcp.test_agent_skills

Every `foames_*` tool a skill names must be in the catalogue, or be listed in the skill's
`optional-tools` comment because it ships only in some versions; the skill must have front matter
a harness can load, the hard stops and the modes; and its relative links must resolve.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from foames.foames_mcp.tools import TOOLS_BY_NAME

ROOT = Path(__file__).resolve().parents[2]
AGENTS = ROOT / "docs" / "agents"
SKILLS = ("equipment-agent", "materials-agent")

FRONT_MATTER = re.compile(r"\A---\nname: ([a-z0-9]+(?:-[a-z0-9]+)*)\ndescription: ([^\n<>]+)\n---\n")
TOOL = re.compile(r"\bfoames_[a-z_]+\b")
OPTIONAL = re.compile(r"<!-- optional-tools: ([^>]*) -->")
LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")
WRITES = {"foames_post_suggestion", "foames_run_suggestion_rules", "foames_set_current_job"}


@unittest.skipUnless(AGENTS.exists(), "docs/ is not next to the app")
class TestAgentSkills(unittest.TestCase):
	def read(self, skill: str) -> str:
		return (AGENTS / skill / "SKILL.md").read_text(encoding="utf-8")

	def test_front_matter(self):
		names = set()
		for skill in SKILLS:
			match = FRONT_MATTER.match(self.read(skill))
			self.assertIsNotNone(match, skill)
			name, description = match.groups()
			self.assertLessEqual(len(name), 64)
			self.assertLessEqual(len(description), 1024)
			self.assertNotIn(name, names)
			names.add(name)

	def test_tools_exist(self):
		for skill in SKILLS:
			text = self.read(skill)
			optional = set()
			for block in OPTIONAL.findall(text):
				optional.update(t.strip() for t in block.split(",") if t.strip())
			for tool in set(TOOL.findall(text)) - optional:
				# Module paths such as foames_mcp are not tools.
				if tool.startswith(("foames_mcp", "foames_mes", "foames_material")):
					continue
				self.assertIn(tool, TOOLS_BY_NAME, f"{skill} names {tool}, which is not in the catalogue")
			self.assertFalse(optional & set(TOOLS_BY_NAME), f"{skill} marks a core tool optional")

	def test_only_suggestions_are_written(self):
		for skill in SKILLS:
			listed = re.search(r"<!-- tools:start -->(.*?)<!-- tools:end -->", self.read(skill), re.S)
			self.assertIsNotNone(listed, skill)
			writes = {t for t in TOOL.findall(listed.group(1)) if t in WRITES}
			self.assertEqual(writes, {"foames_post_suggestion"}, skill)

	def test_sections(self):
		for skill in SKILLS:
			text = self.read(skill)
			for heading in ("## Hard stops", "## Modes", "## Tools"):
				self.assertIn(heading, text, f"{skill} lacks {heading}")
			self.assertIn("Report mode (the default)", text)

	def test_links_resolve(self):
		for skill in SKILLS:
			folder = AGENTS / skill
			for target in LINK.findall(self.read(skill)):
				if target.startswith(("http://", "https://", "mailto:")):
					continue
				self.assertTrue((folder / target).resolve().exists(), f"{skill}: {target} does not exist")


if __name__ == "__main__":
	unittest.main()
