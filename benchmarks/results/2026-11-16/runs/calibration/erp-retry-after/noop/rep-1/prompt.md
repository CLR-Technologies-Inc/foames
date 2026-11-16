# S/4HANA throttles us, and a confirmation was posted twice

Two reports from the integration team about the S/4HANA outbox (`foames/foames_adapters/s4hana/outbox.py`, with the HTTP client in `odata.py`):

1. During month-end the SAP gateway answers 429 or 503 with a `Retry-After` header, often 300 seconds or more. The outbox ignores it and comes back after one minute, then two, and keeps getting throttled. Make the outbox honour `Retry-After`:
   - `ODataError` gets a `retry_after` attribute: seconds as an `int`, or `None`. `error_from_response` fills it from a `Retry-After` header in either form HTTP allows (delay in seconds, or an HTTP date), and leaves it `None` when the header is missing or unreadable.
   - `Outcome` gets a `retry_after` field (default `None`) that `send` fills from the error.
   - `retry_delay(attempts, retry_after=None)` waits at least as long as the server asked, never longer than `MAX_DELAY_SECONDS`, and behaves as it does today when `retry_after` is `None`.
   - The S4HANA Outbox DocType (`foames/foames_adapters/doctype/s4hana_outbox/s4hana_outbox.py`) schedules the next attempt with what the server asked for. That file needs a Frappe site to run and none is available here, so change it with care.

2. Last week a production order confirmation was posted to S/4HANA twice. The first attempt ended in a gateway timeout (HTTP 504) and the retry posted it again. Find out why and fix it.

Integration code that posts to an ERP is held to invariant 6 in `AGENTS.md`.

## How to work

- This directory is a copy of FoaMES, an ERP-agnostic manufacturing execution system on the Frappe framework. Read `AGENTS.md` first: it lists the invariants every change must keep.
- No Frappe site is available. The modules this task touches are pure Python. Run tests like this from the repository root:

  ```
  PYTHONPATH=.foames-bench/stubs:. python -m unittest foames.foames_mes.test_machine_data_logic
  ```

  `.foames-bench/stubs` holds a stand-in `frappe` package that only lets imports succeed; do not change it.
- Add or update unit tests for what you change, next to the module, in a `test_*.py` file.
- Keep the change to what the task needs. Do not reformat unrelated code.
- When you finish, write `BENCH_NOTES.md` in the repository root: what you changed, what you assumed, and anything the data or the request cannot tell you. A few short paragraphs are enough.
- Work without asking questions; nobody will answer. Where the request is ambiguous, choose the reading that keeps the plant's numbers honest, and say so in `BENCH_NOTES.md`.
