# The container the benchmark runs agents in: it sees only the task workspace, mounted at
# /workspace, never the hidden tests or the reference solutions.
#
#   docker build -t foames-bench-agent benchmarks/sandbox
#   docker build -t foames-bench-agent --build-arg NPM_AGENTS="@openai/codex" benchmarks/sandbox
#
# The agent CLIs are installed at build time. Pin their versions with NPM_AGENTS and PIP_AGENTS
# (for example "@anthropic-ai/claude-code@2.1.0") when you need a run to be repeatable, and
# record the image digest with your results.
FROM python:3.12-slim

ARG NPM_AGENTS="@anthropic-ai/claude-code @openai/codex @google/gemini-cli opencode-ai"
ARG PIP_AGENTS=""

RUN apt-get update \
	&& apt-get install -y --no-install-recommends git ca-certificates curl nodejs npm \
	&& rm -rf /var/lib/apt/lists/*
RUN if [ -n "$NPM_AGENTS" ]; then npm install -g $NPM_AGENTS && npm cache clean --force; fi
RUN if [ -n "$PIP_AGENTS" ]; then pip install --no-cache-dir $PIP_AGENTS; fi

# The harness runs the container as your user with HOME=/tmp, so agents can write their config.
RUN git config --system user.name "foames-bench agent" \
	&& git config --system user.email "agent@localhost" \
	&& git config --system --add safe.directory /workspace
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /workspace
