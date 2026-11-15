In this tutorial you will go from nothing to a scored test of your own coding agent on FoaMES. You will check that the benchmark's grader works, run one task with an agent of your choice inside a sandbox, and read its score. Any CLI or harness works: Claude Code, Codex CLI, Gemini CLI, OpenCode, Aider, Google Antigravity (added as your own agent), or a script of your own.

**You need:** Git, Python 3.10 or later, and Docker (recommended) on Linux, macOS or Windows. Your agent's CLI and an API key for it, or a local model. **You do not need a Frappe site**: the six benchmark tasks run with plain Python.

> Agents in the benchmark run with their permission prompts switched off so they can work unattended. The sandbox is what keeps them inside their workspace. Use a machine whose files you do not mind an agent seeing, and do not skip the sandbox step for a real result.

## 1. Get the benchmark

```bash
git clone https://github.com/CLR-Technologies-Inc/foames.git
cd foames/benchmarks
pip install -e .
```

This gives you the `foames-bench` command. (Without installing, `python -m foames_bench` does the same from this folder.)

## 2. Prove the grader works

```bash
foames-bench list
foames-bench validate
```

`list` shows six tasks. `validate` runs each task twice: once with the task's reference solution and once with an agent that changes nothing. It should end with *All 6 tasks valid: the reference passes and a no-op fails.* Every real agent you test must beat the no-op.

## 3. Build the sandbox

```bash
docker build -t foames-bench-agent sandbox
```

The image includes Claude Code, Codex CLI, Gemini CLI and OpenCode. An agent in the container sees only its workspace, at `/workspace`, and none of the hidden tests.

## 4. Make your agent available

Set the API key your agent needs in your shell. The sandbox passes the common ones through (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `OPENROUTER_API_KEY`, `OLLAMA_HOST` and proxy settings):

```bash
export ANTHROPIC_API_KEY=...     # or OPENAI_API_KEY, GEMINI_API_KEY, ...
foames-bench agents
```

`agents` lists the configured agents in `agents.json` and whether each CLI and sandbox is available. Pick one that says it is available, for example `claude-code-baseline`, `codex-frontier`, `gemini-frontier` or `opencode-local`. If your harness is not listed, follow [Add your own agent to the benchmark](How-to-Add-your-own-agent-to-the-benchmark) and come back.

Before a paid run, check the agent's command line by hand once: CLI flags change between releases.

## 5. Run one task

Start with the smallest task, which asks the agent to find why a PLC restart added phantom parts:

```bash
foames-bench run --tasks counter-reset --agents claude-code-baseline --reps 1 --sandbox docker --cap-usd 2
```

Use your agent's name instead of `claude-code-baseline`. The run prints one line per attempt, with PASS or fail, quality, composite score, time and cost, and the run directory it wrote, `runs/<run id>`.

## 6. Read the result

```bash
foames-bench report runs/<run id>
```

This writes `summary.md`, `summary.json` and `summary.csv` in the run directory and prints the table. Look at:

- **Success**: did correctness reach 0.8 with every invariant test passing?
- **Quality**: correctness and process together, from 0 to 1. This is what agents are ranked by.
- **Cost** and **Mean time**: what it took.

Then open `runs/<run id>/counter-reset/<agent>/rep-1/`. It holds the prompt the agent saw, its full output, `change.patch` with everything it changed, and `result.json` with every test result. Read the patch and the agent's `BENCH_NOTES.md` inside it: the score tells you whether the change is right, the notes tell you whether the agent understood why.

## What you learned

- The benchmark needs no site and no database, only Python and a sandbox.
- An agent is just a command line, so any CLI or harness can be tested.
- A run succeeds only if it keeps FoaMES's manufacturing invariants. A fast, cheap answer that breaks one is a failure.

Next: run all six tasks with several agents and repetitions in [Run the agent benchmark](How-to-Run-the-agent-benchmark). To give an agent live plant data instead of code, connect it to a dev site as in [Tutorial 3](Tutorial-3-Your-first-agent-over-MCP) and [Connect an agent CLI or harness](How-to-Connect-an-agent-CLI-or-harness).
