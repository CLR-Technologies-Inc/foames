# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Self-tests for the benchmark harness. Run from benchmarks/: python -m unittest discover tests"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

from foames_bench import agents, recommend, report, runner, sandbox, scoring, tasks, usage
from foames_bench.paths import BENCH_ROOT, repo_root


class TestUsageParsers(unittest.TestCase):
	def test_claude_result(self):
		out = json.dumps(
			{
				"type": "result",
				"total_cost_usd": 0.42,
				"num_turns": 7,
				"usage": {
					"input_tokens": 10,
					"cache_creation_input_tokens": 5,
					"cache_read_input_tokens": 100,
					"output_tokens": 50,
				},
			}
		)
		u = usage.parse("claude-json", out)
		self.assertEqual((u.input_tokens, u.cached_input_tokens, u.output_tokens, u.turns), (15, 100, 50, 7))
		self.assertEqual((u.cost_usd, u.cost_source), (0.42, "reported"))

	def test_codex_jsonl_is_summed_and_priced(self):
		lines = [
			{"type": "thread.started"},
			{
				"type": "turn.completed",
				"usage": {"input_tokens": 1000, "cached_input_tokens": 500, "output_tokens": 100},
			},
			{
				"type": "turn.completed",
				"usage": {"input_tokens": 2000, "cached_input_tokens": 0, "output_tokens": 300},
			},
		]
		u = usage.parse(
			"codex-jsonl",
			"\n".join(map(json.dumps, lines)),
			{"input_per_mtok": 1.0, "cached_input_per_mtok": 0.1, "output_per_mtok": 10.0},
		)
		self.assertEqual(
			(u.input_tokens, u.cached_input_tokens, u.output_tokens, u.turns), (3000, 500, 400, 2)
		)
		self.assertAlmostEqual(u.cost_usd, (3000 * 1 + 500 * 0.1 + 400 * 10) / 1e6)
		self.assertEqual(u.cost_source, "estimated")

	def test_gemini(self):
		out = json.dumps(
			{
				"response": "ok",
				"stats": {
					"models": {"m": {"tokens": {"prompt": 10, "candidates": 4, "thoughts": 2, "cached": 3}}}
				},
			}
		)
		u = usage.parse("gemini-json", out)
		self.assertEqual((u.input_tokens, u.output_tokens, u.cached_input_tokens), (10, 6, 3))

	def test_garbage_is_unknown(self):
		u = usage.parse("claude-json", "not json at all")
		self.assertIsNone(u.cost_usd)
		self.assertEqual(u.cost_source, "unknown")


class TestScoring(unittest.TestCase):
	def graded(self, functional=1.0, invariant=1.0, regression=1.0):
		return {
			"hidden": {"functional": {"pass_rate": functional}, "invariant": {"pass_rate": invariant}},
			"regression": {"pass_rate": regression},
			"agent_tests": {"new_test_functions": 2, "pass_rate": 1.0},
			"changed_files": ["foames/foames_mes/counters.py"],
			"out_of_scope": [],
			"purity_violations": [],
			"deliverables": {},
			"notes_words": 100,
			"rubric": None,
		}

	def test_a_broken_invariant_is_not_a_success(self):
		task = tasks.select(["counter-reset"])[0]
		s = scoring.score(task, self.graded(invariant=0.9), seconds=10, cost_usd=0.01)
		self.assertFalse(s["success"])
		self.assertEqual(s["efficiency"], 0.0)

	def test_cheap_and_wrong_never_beats_correct(self):
		task = tasks.select(["counter-reset"])[0]
		wrong = scoring.score(task, self.graded(functional=0.5, invariant=0.5), seconds=1, cost_usd=0.0)
		right = scoring.score(task, self.graded(), seconds=task.budget_seconds, cost_usd=task.budget_usd)
		self.assertGreater(right["composite"], wrong["composite"])

	def test_purity_violation_fails(self):
		task = tasks.select(["counter-reset"])[0]
		g = self.graded()
		g["purity_violations"] = ["foames/foames_mes/counters.py"]
		self.assertFalse(scoring.score(task, g, 1, 0.0)["success"])


class TestRecommend(unittest.TestCase):
	def test_every_cell_is_filled(self):
		data = recommend.load()
		ids = {t.id for t in tasks.all_tasks()}
		for b in recommend.TRL_BANDS:
			for c in recommend.COMPLEXITIES:
				cell = data["cells"][b][c]
				self.assertIn(cell["primary"], data["tiers"])
				self.assertTrue(set(cell["qualify_with"]) <= ids, (b, c))

	def test_band(self):
		self.assertEqual(
			[recommend.band(t) for t in (1, 3, 4, 6, 7, 9)], ["1-3", "1-3", "4-6", "4-6", "7-9", "7-9"]
		)
		with self.assertRaises(ValueError):
			recommend.band(10)

	def test_qualify_prefers_cheapest_qualified(self):
		def row(agent, cost, quality=0.95, success=True):
			return {
				"agent": agent,
				"model": "",
				"agent_tier": "",
				"task": "counter-reset",
				"usage": {"cost_usd": cost},
				"scores": {"quality": quality, "success": success},
			}

		cell = {"qualify_with": ["counter-reset"], "min_quality": 0.9}
		ranked = recommend.qualify([row("dear", 1.0), row("cheap", 0.1), row("bad", 0.0, 0.5, False)], cell)
		self.assertEqual([a["agent"] for a in ranked], ["cheap", "dear", "bad"])
		self.assertFalse(ranked[-1]["qualifies"])


class TestEndToEnd(unittest.TestCase):
	def test_a_command_agent_that_fixes_the_bug(self):
		"""A command agent (here a Python one-liner) goes through the same path a real CLI does."""
		task = tasks.select(["counter-reset"])[0]
		fix = (
			"import pathlib; p = pathlib.Path('foames/foames_mes/counters.py'); "
			"p.write_text(p.read_text().replace('return float(current)', 'return 0.0')); "
			'print(\'{"type": "result", "total_cost_usd": 0.01, "num_turns": 1}\')'
		)
		agent = agents.Agent(
			name="scripted", command=[sys.executable, "-c", fix], usage_parser="claude-json", tier="oss"
		)
		with tempfile.TemporaryDirectory() as tmp:
			rows = runner.run([task], [agent], repo_root(), Path(tmp), log=lambda *a, **k: None)
			summary = report.write(Path(tmp))
		row = rows[0]
		self.assertTrue(row["scores"]["success"], row["scores"])
		self.assertEqual(row["usage"]["cost_usd"], 0.01)
		self.assertEqual(row["graded"]["changed_files"], ["foames/foames_mes/counters.py"])
		self.assertEqual(summary["by_agent"]["scripted"]["cost_per_success_usd"], 0.01)
		# It wrote no tests and no notes, so its process score is below a full one.
		self.assertLess(row["scores"]["process"], 0.9)


class TestReviewFixes(unittest.TestCase):
	def test_failing_subtests_are_recorded(self):
		from foames_bench import grading

		with tempfile.TemporaryDirectory() as tmp:
			test = Path(tmp) / "test_sub.py"
			test.write_text(
				"import unittest\n\nclass T(unittest.TestCase):\n\tdef test_x(self):\n"
				"\t\tfor i in range(2):\n\t\t\twith self.subTest(i=i):\n\t\t\t\tself.assertEqual(i, 0)\n",
				encoding="utf-8",
			)
			rows = grading.run_tests([test], repo_root())
		self.assertIn("fail", [r["outcome"] for r in rows])
		self.assertLess(grading.pass_rate(rows), 1.0)

	def test_workspace_inside_the_checkout_is_refused(self):
		from foames_bench import workspace

		task = tasks.select(["counter-reset"])[0]
		with self.assertRaises(SystemExit):
			workspace.create(repo_root(), repo_root() / "results" / "ws", task)

	def test_skipped_tests_earn_no_test_credit(self):
		task = tasks.select(["counter-reset"])[0]
		graded = TestScoring().graded()
		graded["agent_tests"] = {"new_test_functions": 3, "pass_rate": None, "tests": [{"outcome": "skip"}]}
		with_skips = scoring.score(task, graded, 1, 0.0)["process"]
		graded["agent_tests"] = {"new_test_functions": 3, "pass_rate": 1.0, "tests": [{"outcome": "pass"}]}
		self.assertLess(with_skips, scoring.score(task, graded, 1, 0.0)["process"])

	def test_editing_the_task_during_a_run_fails_it(self):
		task = tasks.select(["counter-reset"])[0]
		target = task.path / "hidden" / "test_invariants.py"
		original = target.read_text(encoding="utf-8")
		script = "import pathlib, sys; p = pathlib.Path(sys.argv[1]); p.write_text(p.read_text() + '\\n# edited\\n')"
		agent = agents.Agent(name="tamper", command=[sys.executable, "-c", script, str(target)])
		try:
			with tempfile.TemporaryDirectory() as tmp:
				row = runner.run([task], [agent], repo_root(), Path(tmp), log=lambda *a, **k: None)[0]
		finally:
			target.write_text(original, encoding="utf-8")
		self.assertFalse(row["scores"]["success"])
		self.assertTrue(row["scores"]["tampered"])


# The agent fixes the counter bug and reports what else it could reach.
PROBE = """
import json, pathlib, sys
hidden, config, repo_file = sys.argv[1:4]
p = pathlib.Path("foames/foames_mes/counters.py")
p.write_text(p.read_text().replace("return float(current)", "return 0.0"))
def readable(path):
	try:
		return bool(pathlib.Path(path).read_text())
	except OSError:
		return False
def writable(path):
	try:
		with open(path, "a"):
			return True
	except OSError:
		return False
pathlib.Path("probe.json").write_text(json.dumps({
	"hidden": readable(hidden), "config": readable(config), "repo_write": writable(repo_file),
}))
"""


class TestSandbox(unittest.TestCase):
	def probe(self, box):
		task = tasks.select(["counter-reset"])[0]
		hidden = task.path / "hidden" / "test_invariants.py"
		repo_file = repo_root() / "foames" / "hooks.py"
		python = box.python if box is not None else sys.executable
		agent = agents.Agent(
			name="probe",
			command=[
				python,
				"-c",
				PROBE,
				str(hidden),
				str(BENCH_ROOT / "agents.json"),
				str(repo_file),
			],
		)
		before = repo_file.read_bytes()
		with tempfile.TemporaryDirectory() as tmp:
			row = runner.run_one(
				task, agent, repo_root(), Path(tmp) / "rep-1", keep_workspace=True, sandbox=box
			)
			seen = json.loads((Path(tmp) / "rep-1" / "workspace" / "probe.json").read_text())
		self.assertEqual(repo_file.read_bytes(), before)
		return row, seen

	def test_unshare_hides_the_benchmark(self):
		box = sandbox.UnshareSandbox(repo_root())
		ok, why = box.available()
		if not ok:
			self.skipTest(why)
		row, seen = self.probe(box)
		self.assertEqual(seen, {"hidden": False, "config": False, "repo_write": False})
		self.assertEqual(row["sandbox"], "unshare")
		# The hidden tests still ran, inside the sandbox, against the agent's fix.
		self.assertTrue(row["scores"]["success"], row["scores"])
		self.assertGreater(len(row["graded"]["hidden"]["invariant"]["tests"]), 1)

	def test_docker_hides_the_benchmark(self):
		"""Needs a Docker daemon and an image with python3; FOAMES_BENCH_TEST_IMAGE names another one."""
		import os

		image = os.environ.get("FOAMES_BENCH_TEST_IMAGE", sandbox.DEFAULT_IMAGE)
		box = sandbox.DockerSandbox(image=image, network="none")
		ok, why = box.available()
		if not ok:
			self.skipTest(why)
		row, seen = self.probe(box)
		self.assertEqual(seen, {"hidden": False, "config": False, "repo_write": False})
		self.assertEqual(row["sandbox"], "docker")
		self.assertTrue(row["scores"]["success"], row["scores"])

	def test_without_a_sandbox_the_answers_are_readable(self):
		row, seen = self.probe(None)
		self.assertTrue(seen["hidden"])
		self.assertEqual(row["sandbox"], "none")

	def test_docker_command_line(self):
		box = sandbox.DockerSandbox(
			image="img", network="none", passthrough=["MY_KEY"], mounts=["~/.cfg:/tmp/.cfg:rw"]
		)
		ws = Path("/tmp/ws")
		argv, _ = box.wrap(
			["agent", box.inside(ws, ws / "a" / "p.md")],
			ws,
			{"MY_KEY": "secret", "OTHER": "x", "FOAMES_BENCH_STUBS": "/workspace/s"},
			forward=("FOAMES_BENCH_STUBS",),
		)
		joined = " ".join(argv)
		self.assertIn("-v /tmp/ws:/workspace", joined)
		self.assertIn("--network none", joined)
		self.assertIn(f"{Path('~/.cfg').expanduser()}:/tmp/.cfg:rw", joined)
		# A key is named, so its value stays out of the command line; a harness variable is set.
		self.assertIn("-e MY_KEY", joined)
		self.assertNotIn("secret", joined)
		self.assertNotIn("OTHER", joined)
		self.assertIn("FOAMES_BENCH_STUBS=/workspace/s", joined)
		self.assertEqual(argv[-3:], ["img", "agent", "/workspace/a/p.md"])
		box._name = None

	def test_auto_refuses_to_fall_back_to_no_sandbox(self):
		original = (sandbox.DockerSandbox.available, sandbox.UnshareSandbox.available)
		sandbox.DockerSandbox.available = sandbox.UnshareSandbox.available = lambda self: (False, "off")
		try:
			with self.assertRaises(sandbox.SandboxUnavailable):
				sandbox.make("auto", repo_root())
		finally:
			sandbox.DockerSandbox.available, sandbox.UnshareSandbox.available = original


if __name__ == "__main__":
	unittest.main()
