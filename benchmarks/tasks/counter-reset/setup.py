"""Plant the defect: a counter that drops is taken as a fresh count from zero, so a reset or an
out-of-order reading invents production."""

from pathlib import Path

ORIGINAL = """	# A reset or an out-of-order reading. Nothing is invented.
	return 0.0
"""
DEFECT = """	# The counter restarted from zero: count what it has made since.
	return float(current)
"""


def setup(workspace: Path):
	path = workspace / "foames" / "foames_mes" / "counters.py"
	text = path.read_text(encoding="utf-8")
	assert ORIGINAL in text, "counters.py changed upstream; update the task setup"
	path.write_text(text.replace(ORIGINAL, DEFECT), encoding="utf-8")
