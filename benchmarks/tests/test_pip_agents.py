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

"""Verify the image's pip policy against local wheels, without a network or global installation."""

import hashlib
import importlib.util
import shlex
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

DOCKERFILE = Path(__file__).resolve().parents[1] / "sandbox/Dockerfile"


@unittest.skipUnless(importlib.util.find_spec("pip"), "requires pip")
class PipAgentLockTests(unittest.TestCase):
	def install(self, requirement):
		with tempfile.TemporaryDirectory() as directory:
			root = Path(directory)
			wheel = root / "fixture_agent-1.0-py3-none-any.whl"
			with zipfile.ZipFile(wheel, "w") as archive:
				archive.writestr("fixture_agent.py", "VALUE = 1\n")
				archive.writestr(
					"fixture_agent-1.0.dist-info/METADATA",
					"Metadata-Version: 2.1\nName: fixture-agent\nVersion: 1.0\n",
				)
				archive.writestr(
					"fixture_agent-1.0.dist-info/WHEEL",
					"Wheel-Version: 1.0\nGenerator: fixture\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
				)
				archive.writestr("fixture_agent-1.0.dist-info/RECORD", "")
			digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
			lock = root / "requirements.txt"
			lock.write_text(requirement.replace("{hash}", digest))
			line = next(line for line in DOCKERFILE.read_text().splitlines() if "&& pip install " in line)
			arguments = shlex.split(line.split("&& pip install ", 1)[1])
			self.assertIn("--require-hashes", arguments)
			self.assertEqual(arguments[arguments.index("--only-binary") + 1], ":all:")
			arguments[-1] = str(lock)
			result = subprocess.run(
				[
					sys.executable,
					"-m",
					"pip",
					"install",
					*arguments,
					"--no-index",
					"--find-links",
					str(root),
					"--target",
					str(root / "installed"),
					"--disable-pip-version-check",
				],
				capture_output=True,
				text=True,
			)
			return result.returncode, (root / "installed/fixture_agent.py").exists(), result.stderr

	def test_exact_pin_and_matching_hash_install_the_local_wheel(self):
		code, installed, error = self.install("fixture-agent==1.0 --hash=sha256:{hash}\n")
		self.assertEqual(code, 0, error)
		self.assertTrue(installed)

	def test_unpinned_unhashed_and_tampered_dependencies_are_refused(self):
		for requirement in (
			"fixture-agent\n",
			"fixture-agent==1.0\n",
			"fixture-agent==1.0 --hash=sha256:" + "0" * 64 + "\n",
		):
			with self.subTest(requirement=requirement):
				code, installed, _ = self.install(requirement)
				self.assertNotEqual(code, 0)
				self.assertFalse(installed)


if __name__ == "__main__":
	unittest.main()
