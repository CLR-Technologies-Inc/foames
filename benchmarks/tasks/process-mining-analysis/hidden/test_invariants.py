import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

WORKSPACE = Path(os.environ["FOAMES_BENCH_WORKSPACE"])


class TestReproducible(unittest.TestCase):
	def test_script_regenerates_the_answers(self):
		"""The numbers must come from the script, run on the data, not be typed in."""
		with tempfile.TemporaryDirectory() as tmp:
			copy = Path(tmp) / "ws"
			shutil.copytree(WORKSPACE, copy, ignore=shutil.ignore_patterns(".git"))
			(copy / "answers.json").unlink(missing_ok=True)
			env = {
				**os.environ,
				"PYTHONPATH": os.pathsep.join([str(copy / ".foames-bench" / "stubs"), str(copy)]),
			}
			subprocess.run(
				[sys.executable, "analysis/analyze.py"],
				cwd=copy,
				env=env,
				check=True,
				capture_output=True,
				timeout=120,
			)
			regenerated = json.loads((copy / "answers.json").read_text(encoding="utf-8"))
		self.assertEqual(regenerated, json.loads((WORKSPACE / "answers.json").read_text(encoding="utf-8")))

	def test_script_follows_the_data(self):
		"""Drop the incomplete orders from the data: the script's answers must change with it."""
		with tempfile.TemporaryDirectory() as tmp:
			copy = Path(tmp) / "ws"
			shutil.copytree(WORKSPACE, copy, ignore=shutil.ignore_patterns(".git"))
			csv_path = copy / "data" / "weld_cell_events.csv"
			lines = csv_path.read_text(encoding="utf-8").splitlines()
			kept = [lines[0]] + [
				l for l in lines[1:] if not l.startswith(("WO-0017,", "WO-0033,", "WO-0052,"))
			]
			csv_path.write_text("\n".join(kept) + "\n", encoding="utf-8")
			env = {
				**os.environ,
				"PYTHONPATH": os.pathsep.join([str(copy / ".foames-bench" / "stubs"), str(copy)]),
			}
			subprocess.run(
				[sys.executable, "analysis/analyze.py"],
				cwd=copy,
				env=env,
				check=True,
				capture_output=True,
				timeout=120,
			)
			changed = json.loads((copy / "answers.json").read_text(encoding="utf-8"))
		self.assertEqual(changed["cases"], 57)
		self.assertEqual(changed["incomplete_cases"], [])

	def test_foames_code_untouched(self):
		result = subprocess.run(
			["git", "diff", "--name-only", "task-start", "--", "foames"],
			cwd=WORKSPACE,
			capture_output=True,
			text=True,
		)
		self.assertEqual(result.stdout.strip(), "")
