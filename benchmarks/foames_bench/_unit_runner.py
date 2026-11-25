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

"""Run unittest files by path and write one JSON line per test. Started in a subprocess by the
grader, with the workspace first on sys.path, so the tests import the agent's code.

Usage: python _unit_runner.py OUT.json FILE [FILE ...]
"""

import importlib.util
import json
import sys
import traceback
import unittest
from pathlib import Path


class Recorder(unittest.TestResult):
	def __init__(self):
		super().__init__()
		self.rows = []

	def _row(self, test, outcome, detail=""):
		self.rows.append({"test": test.id(), "outcome": outcome, "detail": detail[-2000:]})

	def addSuccess(self, test):
		self._row(test, "pass")

	def addFailure(self, test, err):
		self._row(test, "fail", self._exc_info_to_string(err, test))

	def addError(self, test, err):
		self._row(test, "error", self._exc_info_to_string(err, test))

	def addSubTest(self, test, subtest, err):
		# A failing subtest is a failed test; passing subtests are covered by the parent's success.
		if err is not None:
			outcome = "fail" if issubclass(err[0], test.failureException) else "error"
			self._row(subtest, outcome, self._exc_info_to_string(err, test))

	def addSkip(self, test, reason):
		self._row(test, "skip", reason)

	def addExpectedFailure(self, test, err):
		self._row(test, "pass")

	def addUnexpectedSuccess(self, test):
		self._row(test, "fail", "unexpected success")


def main(out: str, files: list[str]) -> int:
	result = Recorder()
	for i, file in enumerate(files):
		path = Path(file)
		try:
			spec = importlib.util.spec_from_file_location(f"bench_{i}_{path.stem}", path)
			module = importlib.util.module_from_spec(spec)
			sys.modules[spec.name] = module
			spec.loader.exec_module(module)
			unittest.defaultTestLoader.loadTestsFromModule(module).run(result)
		except Exception:
			# A file that does not import counts as one failed test, not as a crash of the grader.
			result.rows.append(
				{"test": f"{path.name}::import", "outcome": "error", "detail": traceback.format_exc()[-2000:]}
			)
	Path(out).write_text(json.dumps(result.rows), encoding="utf-8")
	return 0


if __name__ == "__main__":
	raise SystemExit(main(sys.argv[1], sys.argv[2:]))
