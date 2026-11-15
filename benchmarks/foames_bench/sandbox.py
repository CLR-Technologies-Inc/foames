# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Run an agent, and the tests it wrote, where it can see its workspace and nothing of the benchmark.

Three backends:

- `docker`: the agent runs in a container built from `sandbox/Dockerfile`, which mounts only the
  workspace at /workspace. Works on Linux, macOS and Windows (Docker Desktop). The strongest, and
  the one to use for results you publish.
- `unshare`: Linux without a container runtime. A private mount and PID namespace (util-linux
  `unshare`) hides the whole `benchmarks/` directory behind an empty tmpfs, mounts the FoaMES
  checkout read-only, and mounts the workspace back in its place. The agent keeps your user's
  home directory, so CLI logins work, and the host network.
- `none`: no isolation. Only for trying an agent out; the run is marked unsandboxed.

`auto` picks docker when the daemon answers and the image exists, else unshare when the kernel
allows it, else stops and says what to do. Built-in agents (reference, noop) never need one.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from foames_bench.paths import BENCH_ROOT

DEFAULT_IMAGE = "foames-bench-agent"
# API keys an agent CLI commonly reads; passed into a container only when they are set.
DEFAULT_PASSTHROUGH = (
	"ANTHROPIC_API_KEY",
	"ANTHROPIC_BASE_URL",
	"OPENAI_API_KEY",
	"OPENAI_BASE_URL",
	"GEMINI_API_KEY",
	"GOOGLE_API_KEY",
	"OPENROUTER_API_KEY",
	"OLLAMA_HOST",
	"HTTPS_PROXY",
	"HTTP_PROXY",
	"NO_PROXY",
)

# Runs inside the new namespaces: keep the workspace reachable, mount the checkout read-only, hide
# every given path behind an empty tmpfs, put the workspace back, and start the command there.
_UNSHARE_SCRIPT = r"""
set -e
ws=$1; stage=$2; repo=$3; shift 3
mount --bind "$ws" "$stage"
mount --bind "$repo" "$repo"
mount -o remount,bind,ro "$repo"
while [ "$1" != "--" ]; do
	mount -t tmpfs -o size=1m,mode=755 foames-bench-hidden "$1"
	shift
done
shift
mkdir -p "$ws"
mount --bind "$stage" "$ws"
cd "$ws"
exec "$@"
"""


class SandboxUnavailable(RuntimeError):
	pass


class NoSandbox:
	name = "none"
	python = sys.executable

	def available(self) -> tuple[bool, str]:
		return True, "no isolation"

	def inside(self, workspace: Path, path: Path) -> str:
		"""A host path as the sandboxed process sees it."""
		return str(path)

	def wrap(self, argv: list[str], workspace: Path, env: dict, forward=()) -> tuple[list[str], dict]:
		"""The command line to run, and the environment to run it with. `forward` names the
		variables of `env` that the sandboxed process must see (the host environment is inherited
		where the backend allows it)."""
		return argv, env

	def cleanup(self):
		pass


class UnshareSandbox(NoSandbox):
	name = "unshare"

	def __init__(self, repo: Path, hide: list[Path] | None = None):
		self.repo = repo.resolve()
		self.hide = [p.resolve() for p in (hide or [BENCH_ROOT])]
		self._stage = None
		# The tests run with this interpreter; one inside a hidden folder (benchmarks/.venv) is gone.
		exe = Path(sys.executable).resolve()
		if any(exe.is_relative_to(p) for p in self.hide):
			self.python = shutil.which("python3", path="/usr/local/bin:/usr/bin:/bin") or "python3"

	def _base(self) -> list[str]:
		# --kill-child: when the harness kills unshare on a timeout, the agent and everything it
		# started go with it.
		return [
			"unshare",
			"--mount",
			"--map-root-user",
			"--fork",
			"--kill-child",
			"--pid",
			"--mount-proc",
			"--",
		]

	def available(self) -> tuple[bool, str]:
		if not shutil.which("unshare"):
			return False, "util-linux unshare is not installed"
		try:
			probe = subprocess.run(
				[
					*self._base(),
					"sh",
					"-c",
					"mount -t tmpfs none /mnt 2>/dev/null || mount -t tmpfs none /tmp",
				],
				capture_output=True,
				text=True,
				timeout=20,
			)
		except (OSError, subprocess.TimeoutExpired) as e:
			return False, str(e)
		if probe.returncode != 0:
			return False, "the kernel does not allow unprivileged mount namespaces: " + probe.stderr.strip()[
				-200:
			]
		return True, "mount and PID namespaces"

	def wrap(self, argv, workspace, env, forward=()):
		self.cleanup()
		self._stage = tempfile.mkdtemp(prefix="foames-bench-stage-")
		hide = [str(path) for path in self.hide]
		return [
			*self._base(),
			"sh",
			"-c",
			_UNSHARE_SCRIPT,
			"foames-bench-sandbox",
			str(workspace.resolve()),
			self._stage,
			str(self.repo),
			*hide,
			"--",
			*argv,
		], env

	def cleanup(self):
		if self._stage:
			shutil.rmtree(self._stage, ignore_errors=True)
			self._stage = None


class DockerSandbox(NoSandbox):
	name = "docker"
	python = "python3"

	def __init__(self, image: str = DEFAULT_IMAGE, network: str = "bridge", passthrough=(), mounts=()):
		self.image = image
		self.network = network
		self.passthrough = tuple(dict.fromkeys([*DEFAULT_PASSTHROUGH, *passthrough]))
		self.mounts = list(mounts)
		self._name = None

	def available(self) -> tuple[bool, str]:
		if not shutil.which("docker"):
			return False, "docker is not installed"
		try:
			info = subprocess.run(
				["docker", "image", "inspect", self.image], capture_output=True, text=True, timeout=30
			)
		except (OSError, subprocess.TimeoutExpired) as e:
			return False, str(e)
		if info.returncode != 0:
			reason = info.stderr.strip().splitlines()[-1] if info.stderr.strip() else "unknown error"
			return (
				False,
				f"image {self.image} is not available ({reason}); build it with: docker build -t {self.image} benchmarks/sandbox",
			)
		return True, f"image {self.image}"

	def has_command(self, exe: str) -> tuple[bool, str]:
		"""Whether the image has an agent's CLI: it runs in the container, not on the host."""
		probe = subprocess.run(
			["docker", "run", "--rm", "--entrypoint", "sh", self.image, "-c", f'command -v "{exe}"'],
			capture_output=True,
			text=True,
			timeout=120,
		)
		if probe.returncode == 0:
			return True, f"{probe.stdout.strip()} in image {self.image}"
		return False, f"{exe} is not in image {self.image}; add it to benchmarks/sandbox/Dockerfile"

	def inside(self, workspace: Path, path: Path) -> str:
		relative = Path(path).resolve().relative_to(workspace.resolve())
		return "/workspace/" + relative.as_posix() if str(relative) != "." else "/workspace"

	def wrap(self, argv, workspace, env, forward=()):
		self.cleanup()
		self._name = f"foames-bench-{uuid.uuid4().hex[:12]}"
		cmd = ["docker", "run", "--rm", "-i", "--name", self._name, "--network", self.network]
		cmd += ["-v", f"{workspace.resolve()}:/workspace", "-w", "/workspace"]
		if hasattr(os, "getuid"):
			cmd += ["--user", f"{os.getuid()}:{os.getgid()}", "-e", "HOME=/tmp"]
		# "host:target" mounts read-only; "host:target:rw" read-write (an agent's login directory).
		for mount in self.mounts:
			host, target, *mode = mount.split(":")
			cmd += ["-v", f"{Path(host).expanduser()}:{target}:{mode[0] if mode else 'ro'}"]
		for name in self.passthrough:
			if name in env and name not in forward:
				cmd += ["-e", name]
		for name in forward:
			if name in env:
				cmd += ["-e", f"{name}={env[name]}"]
		return [*cmd, self.image, *argv], env

	def cleanup(self):
		if self._name:
			subprocess.run(["docker", "kill", self._name], capture_output=True)
			self._name = None


def make(kind: str, repo: Path, agent=None, image: str | None = None, network: str | None = None):
	"""The sandbox for a run. `kind` is auto, docker, unshare or none."""
	agent_opts = getattr(agent, "sandbox", None) or {}
	docker = DockerSandbox(
		image=image or agent_opts.get("image", DEFAULT_IMAGE),
		network=network or agent_opts.get("network", "bridge"),
		passthrough=agent_opts.get("env", ()),
		mounts=agent_opts.get("mounts", ()),
	)
	unshare = UnshareSandbox(repo)
	if kind == "none":
		return NoSandbox()
	if kind in ("docker", "unshare"):
		box = docker if kind == "docker" else unshare
		ok, why = box.available()
		if not ok:
			raise SandboxUnavailable(f"{kind} sandbox unavailable: {why}")
		return box
	if kind != "auto":
		raise ValueError(f"unknown sandbox {kind!r}; use auto, docker, unshare or none")
	reasons = []
	for box in (docker, unshare):
		ok, why = box.available()
		if ok:
			return box
		reasons.append(f"{box.name}: {why}")
	raise SandboxUnavailable(
		"no sandbox is available (" + "; ".join(reasons) + "). Build the Docker image "
		"(docker build -t foames-bench-agent benchmarks/sandbox), or pass --sandbox none to run "
		"agents without isolation (results are then marked unsandboxed)."
	)
