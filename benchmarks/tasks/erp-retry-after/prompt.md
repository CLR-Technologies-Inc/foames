# S/4HANA throttles us, and a confirmation was posted twice

Two reports from the integration team about the S/4HANA outbox (`foames/foames_adapters/s4hana/outbox.py`, with the HTTP client in `odata.py`):

1. During month-end the SAP gateway answers 429 or 503 with a `Retry-After` header, often 300 seconds or more. The outbox ignores it and comes back after one minute, then two, and keeps getting throttled. Make the outbox honour `Retry-After`:
   - `ODataError` gets a `retry_after` attribute: seconds as an `int`, or `None`. `error_from_response` fills it from a `Retry-After` header in either form HTTP allows (delay in seconds, or an HTTP date), and leaves it `None` when the header is missing or unreadable.
   - `Outcome` gets a `retry_after` field (default `None`) that `send` fills from the error.
   - `retry_delay(attempts, retry_after=None)` waits at least as long as the server asked, never longer than `MAX_DELAY_SECONDS`, and behaves as it does today when `retry_after` is `None`.

2. Last week a production order confirmation was posted to S/4HANA twice. The first attempt ended in a gateway timeout (HTTP 504) and the retry posted it again. Find out why and fix it.

Integration code that posts to an ERP is held to invariant 6 in `AGENTS.md`.
