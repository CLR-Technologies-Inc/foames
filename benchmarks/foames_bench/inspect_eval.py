# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Optional Inspect AI front end. EXPERIMENTAL: written against the Inspect AI and inspect_swe
documentation, not yet run end to end. The standard-library runner (`foames-bench run`) is the
supported path; use this when you want Inspect's logs, viewer, model routing and sandboxes.

    pip install inspect-ai inspect-swe
    pip install -e benchmarks            # so `python -m foames_bench` works in the sandbox
    FOAMES_REPO=/path/to/foames inspect eval benchmarks/foames_bench/inspect_eval.py \\
        -T agent=claude_code -T tasks=counter-reset,oee-unknown-time --model anthropic/<model>

Each sample prepares a FoaMES workspace in the sandbox's working directory, hands it to an agent
from inspect_swe (claude_code, codex_cli, gemini_cli, opencode, ...) and grades it with the same
grader as the standard runner. Inspect records tokens and cost per sample itself. With the
"local" sandbox the agent runs on your machine; use a Docker sandbox for isolation, with FoaMES
and this package installed in the image.
"""

import json

from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import Score, Target, mean, scorer
from inspect_ai.solver import Generate, TaskState, chain, solver
from inspect_ai.util import sandbox

from foames_bench import tasks as tasks_mod


@solver
def prepare_workspace():
	async def solve(state: TaskState, generate: Generate) -> TaskState:
		result = await sandbox().exec(
			["python", "-m", "foames_bench", "prepare", "--task", state.metadata["task"], "--dest", "."]
		)
		if not result.success:
			raise RuntimeError(f"could not prepare the workspace: {result.stderr}")
		return state

	return solve


@scorer(metrics=[mean()])
def foames_grader():
	async def score(state: TaskState, target: Target) -> Score:
		result = await sandbox().exec(
			["python", "-m", "foames_bench", "grade", "--task", state.metadata["task"], "--workspace", "."]
		)
		if not result.success:
			return Score(value=0.0, explanation=f"grader failed: {result.stderr[-1000:]}")
		scores = json.loads(result.stdout)["scores"]
		return Score(
			value=scores["quality"], answer="success" if scores["success"] else "fail", metadata=scores
		)

	return score


def _agent(name: str):
	import inspect_swe

	if not hasattr(inspect_swe, name):
		raise ValueError(f"inspect_swe has no agent {name!r}")
	return getattr(inspect_swe, name)()


@task
def foames_bench(
	agent: str = "claude_code", tasks: str = "", tier: str = "pure", sandbox_type: str = "local"
):
	selected = tasks_mod.select([t for t in tasks.split(",") if t] or None, tier)
	dataset = [
		Sample(id=t.id, input=t.prompt, metadata={"task": t.id, "complexity": t.complexity}) for t in selected
	]
	return Task(
		dataset=dataset,
		solver=chain(prepare_workspace(), _agent(agent)),
		scorer=foames_grader(),
		sandbox=sandbox_type,
	)
