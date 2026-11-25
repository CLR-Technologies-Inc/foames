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

"""Tests for check_license_headers.py: detecting and adding the Apache-2.0 notice."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import check_license_headers as chk  # noqa: E402

BODY = "import os\n"


class NoticeTest(unittest.TestCase):
	def test_fix_adds_the_notice_to_a_bare_file(self):
		out = chk.fixed("#", BODY)
		self.assertTrue(chk.has_notice("#", out))
		self.assertTrue(out.endswith("\n\nimport os\n"))

	def test_fix_upgrades_the_two_line_header(self):
		old = "# Copyright (c) 2025 CLR Technologies Inc. and contributors\n"
		old += "# SPDX-License-Identifier: Apache-2.0\n\n" + BODY
		out = chk.fixed("#", old)
		self.assertTrue(chk.has_notice("#", out))
		self.assertIn("# Copyright 2025 CLR Technologies Inc.\n", out)
		self.assertNotIn("and contributors", out)
		self.assertEqual(out.count("SPDX-License-Identifier"), 1)

	def test_fix_replaces_the_frappe_generator_header(self):
		frappe = "// Copyright (c) 2026, CLR Technologies Inc. and contributors\n"
		frappe += "// For license information, please see license.txt\n\nfrappe.ui.form.on('X', {});\n"
		out = chk.fixed("//", frappe)
		self.assertTrue(chk.has_notice("//", out))
		self.assertIsNone(chk.DANGLING.search(out))
		self.assertEqual(out.count("Copyright"), 1)

	def test_shebang_and_doctype_stay_first(self):
		sh = chk.fixed("#", "#!/usr/bin/env bash\necho hi\n")
		self.assertTrue(sh.startswith("#!/usr/bin/env bash\n# Copyright 2026 CLR Technologies Inc.\n"))
		self.assertTrue(chk.has_notice("#", sh))
		html = chk.fixed("<!--", "<!doctype html>\n<html></html>\n")
		self.assertTrue(html.startswith("<!doctype html>\n<!--\n  Copyright 2026"))
		self.assertTrue(chk.has_notice("<!--", html))

	def test_css_block_and_year_range(self):
		css = chk.render("/*", "2026-2027") + "body{}\n"
		self.assertTrue(chk.has_notice("/*", css))

	def test_short_header_is_rejected(self):
		self.assertFalse(chk.has_notice("#", "# SPDX-License-Identifier: Apache-2.0\n" + BODY))

	def test_fix_mode_on_a_repository(self):
		with tempfile.TemporaryDirectory() as tmp:
			root = Path(tmp)
			subprocess.run(["git", "init", "-q"], cwd=root, check=True)
			(root / "a.py").write_text(BODY, encoding="utf-8")
			(root / "data.json").write_text("{}\n", encoding="utf-8")
			subprocess.run(["git", "add", "."], cwd=root, check=True)
			files = chk.tracked_files(root)
			self.assertEqual(chk.problems(root, files), ["a.py: missing the Apache-2.0 license notice"])
			self.assertEqual(chk.problems(root, files, fix=True), [])
			self.assertEqual(chk.problems(root, files), [])
			self.assertEqual((root / "data.json").read_text(encoding="utf-8"), "{}\n")


if __name__ == "__main__":
	unittest.main()
