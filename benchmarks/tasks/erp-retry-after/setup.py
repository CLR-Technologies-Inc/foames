"""Plant the defect: a server error on a posting is retried blind instead of being checked first,
so a 5xx that came after S/4HANA committed the posting produces a duplicate."""

from pathlib import Path

ORIGINAL = """		return Outcome(
			"Unknown" if e.maybe_applied or verify_first else "Retry", error=str(e), details=e.details
		)"""
DEFECT = """		return Outcome("Retry", error=str(e), details=e.details)"""


def setup(workspace: Path):
	path = workspace / "foames" / "foames_adapters" / "s4hana" / "outbox.py"
	text = path.read_text(encoding="utf-8")
	assert ORIGINAL in text, "outbox.py changed upstream; update the task setup"
	path.write_text(text.replace(ORIGINAL, DEFECT), encoding="utf-8")
