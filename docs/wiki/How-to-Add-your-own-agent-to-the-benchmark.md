**Goal:** benchmark a harness, model or script that `agents.json` does not list yet.

> **CI-tested.** The commands on this page run, as written, in the [Docker smoke test](https://github.com/CLR-Technologies-Inc/foames/actions/workflows/docker-smoke.yml) on every change to them. Steps that need your own agent or API key are the exception.

**You need:** the benchmark set up ([Tutorial 4](Tutorial-4-Your-first-agent-benchmark-run)), and an agent that can run **unattended** from a command line in a working directory or sandbox: no questions, no permission prompts.

The shipped `agents.json` has a Gemini CLI entry (`gemini-frontier`) but no Google Antigravity entry yet, and the sandbox image installs Gemini CLI, not `agy`. To benchmark the Antigravity CLI, add it here like any other agent: check its non-interactive mode and flags in [Google's docs](https://antigravity.google/docs/cli/gcli-migration/) first, and install it in the image.

## 1. Run it by hand once

In a prepared workspace, check the exact command, flags and output format:

```bash
foames-bench prepare --task counter-reset --dest /tmp/ws
cd /tmp/ws && my-agent --non-interactive --prompt-file /tmp/counter-reset.prompt.md
```

Note how it takes the prompt (an argument, a file or standard input), how it picks a model, and whether it prints token usage or cost.

## 2. Add an entry to agents.json

Copy `agents.json` if you want to keep your entries separate, and pass it with `--agents-file`. Add one object:

```json
{"name": "my-agent", "harness": "my-harness", "tier": "baseline", "model": "my-model-id",
 "command": ["my-agent", "--non-interactive", "--model", "{model}", "--prompt-file", "{prompt_file}"],
 "usage_parser": "generic",
 "prices": {"input_per_mtok": 0.0, "output_per_mtok": 0.0},
 "sandbox": {"env": ["MY_PROVIDER_KEY"]},
 "notes": "What this is and which version you checked."}
```

- Placeholders `{prompt}`, `{prompt_file}`, `{workspace}` and `{model}` are filled in for each run. Set `"stdin": true` to also pipe the prompt in.
- `usage_parser`: `claude-json`, `codex-jsonl`, `gemini-json`, `generic` (any OpenAI- or Anthropic-style `usage` object in the output) or `none`.
- `prices` in dollars per million tokens turn token counts into an estimated cost. For a local model, set `"fixed_cost_usd": 0.0` instead.
- `tier` is `oss`, `baseline` or `frontier`, which `recommend` uses.
- Every field is listed on [Benchmark configuration](Reference-Benchmark-configuration#agentsjson).

## 3. Make it run in the sandbox

The Docker image has Claude Code, Codex CLI, Gemini CLI and OpenCode. For anything else, rebuild it with your tool:

```bash
# NPM_AGENTS replaces the default list, so keep the ones you still want
docker build -t foames-bench-agent --build-arg NPM_AGENTS="@anthropic-ai/claude-code @openai/codex @google/gemini-cli opencode-ai my-agent-cli@1.2.3" sandbox
# Generate and review a lock for your Python/platform, with every transitive dependency
# pinned using == and wheel SHA-256 hashes (for example with pip-compile --generate-hashes).
# Place that lock in the Docker build context, then select it:
cp /path/to/reviewed-requirements.lock sandbox/requirements-my-agent.txt
docker build -t foames-bench-agent --build-arg PIP_AGENT_REQUIREMENTS="requirements-my-agent.txt" sandbox
```

Or give your entry its own image with `"sandbox": {"image": "my-image"}`. Variables beyond the default keys go in `sandbox.env`; a login folder goes in `sandbox.mounts` as `"~/.config/my-agent:/tmp/.config/my-agent:rw"`. A model served by Ollama on the host is at `http://host.docker.internal:11434` on macOS and Windows; on Linux use `"network": "host"`.

## 4. Check and run

```bash
foames-bench agents                                # yours should say available
foames-bench run --tasks counter-reset --agents my-agent --reps 1 --sandbox docker --cap-usd 2
```

If the run times out, the agent is probably waiting for input: find its non-interactive flag. If the cost shows as unknown, choose a usage parser or set prices.

## A harness with no command line

Use `foames-bench prepare` and `foames-bench grade` as in [Run the agent benchmark](How-to-Run-the-agent-benchmark#testing-by-hand-or-from-any-harness), and isolate the agent yourself.

To write a new task rather than a new agent, see [benchmarks/docs/writing-tasks.md](https://github.com/CLR-Technologies-Inc/foames/blob/main/benchmarks/docs/writing-tasks.md).
