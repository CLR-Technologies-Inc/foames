"""Reference solution for erp-retry-after."""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("erp_retry_setup", Path(__file__).with_name("setup.py"))
_setup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_setup)


def _replace(path: Path, old: str, new: str):
	text = path.read_text(encoding="utf-8")
	assert old in text, f"{path.name}: {old[:60]!r} not found"
	path.write_text(text.replace(old, new, 1), encoding="utf-8")


PARSER = '''

def parse_retry_after(value: str | None, now: float | None = None) -> int | None:
	"""Seconds from a Retry-After header: a delay in seconds or an HTTP date. None when unreadable."""
	if value is None:
		return None
	value = str(value).strip()
	if value.isdigit():
		return int(value)
	try:
		from email.utils import parsedate_to_datetime

		when = parsedate_to_datetime(value)
	except (TypeError, ValueError, IndexError):
		return None
	if when is None:
		return None
	seconds = when.timestamp() - (time.time() if now is None else now)
	return max(int(round(seconds)), 0)
'''


def apply(workspace: Path):
	s4 = workspace / "foames" / "foames_adapters" / "s4hana"
	outbox, odata = s4 / "outbox.py", s4 / "odata.py"
	_replace(outbox, _setup.DEFECT, _setup.ORIGINAL)

	_replace(
		odata,
		"def __init__(self, message, status=None, code=None, details=None, transient=False, maybe_applied=False):",
		"def __init__(\n\t\tself, message, status=None, code=None, details=None, transient=False, maybe_applied=False, retry_after=None\n\t):",
	)
	_replace(
		odata,
		"		self.maybe_applied = maybe_applied\n",
		"		self.maybe_applied = maybe_applied\n		self.retry_after = retry_after\n",
	)
	_replace(odata, "\n\ndef error_from_response(", PARSER + "\n\ndef error_from_response(")
	_replace(
		odata,
		"		maybe_applied=write and status >= 500,\n	)",
		'		maybe_applied=write and status >= 500,\n		retry_after=parse_retry_after(response.header("Retry-After")),\n	)',
	)

	_replace(
		outbox,
		"	response: dict | None = None\n",
		"	response: dict | None = None\n	retry_after: int | None = None\n",
	)
	_replace(
		outbox,
		'			return Outcome("Failed", error=str(e), details=e.details)',
		'			return Outcome("Failed", error=str(e), details=e.details, retry_after=e.retry_after)',
	)
	_replace(
		outbox,
		_setup.ORIGINAL,
		"""		return Outcome(
			"Unknown" if e.maybe_applied or verify_first else "Retry",
			error=str(e),
			details=e.details,
			retry_after=getattr(e, "retry_after", None),
		)""",
	)
	_replace(
		outbox,
		'''def retry_delay(attempts: int) -> int:
	"""Seconds to wait after the given number of failed attempts: 1, 2, 4 ... minutes, capped at 6 h."""
	return min(BASE_DELAY_SECONDS * 2 ** max(attempts - 1, 0), MAX_DELAY_SECONDS)''',
		'''def retry_delay(attempts: int, retry_after: int | None = None) -> int:
	"""Seconds to wait after the given number of failed attempts: 1, 2, 4 ... minutes, or longer when
	the server asked for longer with Retry-After, capped at 6 h."""
	backoff = BASE_DELAY_SECONDS * 2 ** max(min(attempts, 30) - 1, 0)
	if retry_after is not None and retry_after > 0:
		backoff = max(backoff, int(retry_after))
	return min(backoff, MAX_DELAY_SECONDS)''',
	)
	_replace(
		workspace / "foames" / "foames_adapters" / "doctype" / "s4hana_outbox" / "s4hana_outbox.py",
		"seconds=outbox.retry_delay(self.attempts))",
		"seconds=outbox.retry_delay(self.attempts, result.retry_after))",
	)
	(s4 / "test_retry_after.py").write_text(
		"""import unittest

from foames.foames_adapters.s4hana import outbox
from foames.foames_adapters.s4hana.odata import Response, error_from_response


class TestRetryAfter(unittest.TestCase):
	def test_header_is_read(self):
		self.assertEqual(error_from_response(Response(429, {"Retry-After": "300"}, b"")).retry_after, 300)

	def test_delay_honours_the_server(self):
		self.assertEqual(outbox.retry_delay(1, retry_after=300), 300)
		self.assertEqual(outbox.retry_delay(1), 60)
""",
		encoding="utf-8",
	)
	(workspace / "BENCH_NOTES.md").write_text(
		"Reference solution. The duplicate came from send() returning Retry for a 5xx on the POST, so the "
		"next attempt posted again without first searching for the marker; a 5xx on a write may come after "
		"S/4HANA committed it, so it is Unknown and the retry verifies first (AGENTS.md invariant 6). "
		"Retry-After is parsed in both forms and only ever lengthens the wait, capped at six hours. The "
		"S4HANA Outbox DocType passes Outcome.retry_after to retry_delay; that call site needs a Frappe site to test.\n",
		encoding="utf-8",
	)
