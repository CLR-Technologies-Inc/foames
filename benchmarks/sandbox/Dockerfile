# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

# The container the benchmark runs agents in: it sees only the task workspace, mounted at
# /workspace, never the hidden tests or the reference solutions.
#
#   docker build -t foames-bench-agent benchmarks/sandbox
#   docker build -t foames-bench-agent --build-arg NPM_AGENTS="@openai/codex" benchmarks/sandbox
#
# The agent CLIs are installed at build time. Pin npm versions with NPM_AGENTS
# (for example "@anthropic-ai/claude-code@2.1.0") when you need a run to be repeatable, and
# record the image digest with your results.
FROM python:3.12-slim

ARG NPM_AGENTS="@anthropic-ai/claude-code @openai/codex @google/gemini-cli opencode-ai"
ARG PIP_AGENTS=""
ARG PIP_AGENT_REQUIREMENTS="requirements-agents.txt"

RUN apt-get update \
	&& apt-get install -y --no-install-recommends git ca-certificates curl nodejs npm \
	&& rm -rf /var/lib/apt/lists/*
COPY install-npm-agents.sh /tmp/install-npm-agents.sh
RUN set -f; sh /tmp/install-npm-agents.sh $NPM_AGENTS
COPY ${PIP_AGENT_REQUIREMENTS} /tmp/requirements-agents.txt
RUN if [ -n "$PIP_AGENTS" ]; then echo "PIP_AGENTS is retired; use a fully pinned, hashed PIP_AGENT_REQUIREMENTS lockfile" >&2; exit 1; fi \
	&& pip install --only-binary :all: --require-hashes --no-cache-dir -r /tmp/requirements-agents.txt

# The harness runs the container as your user with HOME=/tmp, so agents can write their config.
RUN git config --system user.name "foames-bench agent" \
	&& git config --system user.email "agent@localhost" \
	&& git config --system --add safe.directory /workspace
ENV PYTHONDONTWRITEBYTECODE=1
# Never run agents as root. On Linux and macOS the harness passes --user with your uid:gid,
# which overrides this; where it cannot (Windows hosts), the agent runs as this unprivileged
# user with the same HOME=/tmp layout.
RUN useradd --uid 10001 --user-group --no-create-home --home-dir /tmp --shell /usr/sbin/nologin agent \
	&& mkdir -p /workspace && chown agent:agent /workspace
ENV HOME=/tmp
USER agent
WORKDIR /workspace
