import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _mutants import MUTANTS

WORKSPACE = Path(os.environ["FOAMES_BENCH_WORKSPACE"])
STUBS = Path(os.environ["FOAMES_BENCH_STUBS"])


def acceptance_files(root: Path):
	return sorted((root / "acceptance").glob("test_*.py")) if (root / "acceptance").exists() else []


def run_acceptance(root: Path) -> int:
	"""Exit code of the acceptance tests run against the code in root."""
	files = acceptance_files(root)
	if not files:
		return 5
	env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(root), str(STUBS)])}
	code = (
		"import importlib.util, sys, unittest\n"
		"suite = unittest.TestSuite()\n"
		"for i, f in enumerate(sys.argv[1:]):\n"
		"    spec = importlib.util.spec_from_file_location(f'acc{i}', f)\n"
		"    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
		"    suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(m))\n"
		"r = unittest.TextTestRunner(verbosity=0).run(suite)\n"
		"sys.exit(0 if r.wasSuccessful() and r.testsRun else 1)\n"
	)
	result = subprocess.run(
		[sys.executable, "-c", code, *map(str, files)], cwd=root, env=env, capture_output=True, timeout=180
	)
	return result.returncode


class TestSpecification(unittest.TestCase):
	def test_foames_code_untouched(self):
		result = subprocess.run(
			["git", "diff", "--name-only", "task-start", "--", "foames"],
			cwd=WORKSPACE,
			capture_output=True,
			text=True,
		)
		self.assertEqual(result.stdout.strip(), "")

	def test_acceptance_tests_exist_and_pass(self):
		self.assertTrue(acceptance_files(WORKSPACE), "no acceptance/test_*.py")
		self.assertEqual(run_acceptance(WORKSPACE), 0)


def _mutant_test(name):
	path, old, new = MUTANTS[name]

	def test(self):
		with tempfile.TemporaryDirectory() as tmp:
			copy = Path(tmp) / "ws"
			shutil.copytree(WORKSPACE, copy, ignore=shutil.ignore_patterns(".git"))
			target = copy / path
			text = target.read_text(encoding="utf-8")
			self.assertIn(old, text, f"mutant {name} no longer applies")
			target.write_text(text.replace(old, new, 1), encoding="utf-8")
			self.assertNotEqual(run_acceptance(copy), 0, f"the acceptance tests did not catch: {name}")

	return test


for _name in MUTANTS:
	setattr(TestSpecification, f"test_catches_{_name}", _mutant_test(_name))
