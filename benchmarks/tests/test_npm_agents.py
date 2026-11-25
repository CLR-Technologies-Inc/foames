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

"""Exercise sandbox installation with npm replaced by a local command recorder."""

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

INSTALLER = Path(__file__).resolve().parents[1] / "sandbox/install-npm-agents.sh"
MOCK_NPM = """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["NPM_LOG"], "a") as log:
    log.write(json.dumps(sys.argv[1:]) + "\\n")
if os.environ.get("NPM_FAIL") == sys.argv[1]:
    sys.exit(9)
"""


@unittest.skipUnless(os.name != "nt" and shutil.which("sh"), "needs a POSIX shell")
class NpmAgentTests(unittest.TestCase):
	def install(self, specs, fail=""):
		with tempfile.TemporaryDirectory() as directory:
			root = Path(directory)
			mock = root / "npm"
			mock.write_text(MOCK_NPM)
			mock.chmod(0o755)
			log = root / "npm.jsonl"
			result = subprocess.run(
				["sh", str(INSTALLER), *specs],
				env={
					**os.environ,
					"PATH": str(root) + os.pathsep + os.environ["PATH"],
					"NPM_LOG": str(log),
					"NPM_FAIL": fail,
				},
				capture_output=True,
			)
			calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
			return result.returncode, calls

	def test_rebuild_uses_installed_names_for_plain_scoped_versioned_and_tagged_specs(self):
		specs = [
			"plain",
			"pinned@1.2.3",
			"tagged@latest",
			"@scope/plain",
			"@scope/pinned@2.3.4",
			"@scope/tagged@latest",
		]
		code, calls = self.install(specs)
		self.assertEqual(code, 0)
		self.assertEqual(calls[0], ["install", "-g", "--ignore-scripts", *specs])
		self.assertEqual(
			calls[1:-1],
			[
				["rebuild", "-g", name]
				for name in ["plain", "pinned", "tagged", "@scope/plain", "@scope/pinned", "@scope/tagged"]
			],
		)
		self.assertEqual(calls[-1], ["cache", "clean", "--force"])

	def test_empty_agent_list_never_invokes_npm(self):
		self.assertEqual(self.install([]), (0, []))

	def test_install_failure_prevents_rebuild(self):
		code, calls = self.install(["example@latest"], fail="install")
		self.assertNotEqual(code, 0)
		self.assertEqual(len(calls), 1)

	def test_native_rebuild_failure_fails_the_image_build(self):
		code, calls = self.install(["example@latest", "another"], fail="rebuild")
		self.assertNotEqual(code, 0)
		self.assertEqual(calls[-1], ["rebuild", "-g", "example"])


if __name__ == "__main__":
	unittest.main()
