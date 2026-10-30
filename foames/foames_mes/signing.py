# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""HMAC-SHA256 signing for the machine-event webhook. No Frappe dependency.

The sender signs `<timestamp>.<body>` with the shared secret and sends the hex digest in the
`X-FoaMES-Signature` header and the Unix timestamp in `X-FoaMES-Timestamp`. The receiver rejects
a signature older than the configured tolerance, which blocks replay of a captured request.
"""

import hashlib
import hmac
import time

SIGNATURE_HEADER = "X-FoaMES-Signature"
TIMESTAMP_HEADER = "X-FoaMES-Timestamp"


def sign(secret: str, timestamp: int | str, body: bytes | str) -> str:
	if isinstance(body, str):
		body = body.encode()
	message = f"{timestamp}.".encode() + body
	return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify(
	secret: str,
	timestamp: int | str,
	body: bytes | str,
	signature: str,
	tolerance_seconds: int = 300,
	now=None,
) -> bool:
	try:
		ts = int(timestamp)
	except (TypeError, ValueError):
		return False
	now = int(now if now is not None else time.time())
	if tolerance_seconds and abs(now - ts) > tolerance_seconds:
		return False
	expected = sign(secret, ts, body)
	return hmac.compare_digest(expected, (signature or "").strip().lower())
