# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Post a collector report to foames.foames_topology.api.ingest. Standard library only.

Authenticates with a Frappe API key and secret of a user with the FoaMES Integration role
(`Authorization: token <key>:<secret>`). Network errors and 5xx answers are retried with
exponential backoff; a 4xx answer raises at once."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

INGEST_PATH = "/api/method/foames.foames_topology.api.ingest"


class SendError(RuntimeError):
	pass


def ingest_url(site: str) -> str:
	site = site.rstrip("/")
	return site if site.endswith(INGEST_PATH) else site + INGEST_PATH


def send(report: dict, site: str, api_key: str, api_secret: str, *, timeout=30, retries=4, backoff=1.0, opener=None, sleep=time.sleep) -> dict:
	opener = opener or urllib.request.urlopen
	body = json.dumps({"report": report}, default=str).encode()
	request = urllib.request.Request(
		ingest_url(site),
		data=body,
		method="POST",
		headers={
			"Content-Type": "application/json",
			"Accept": "application/json",
			"Authorization": f"token {api_key}:{api_secret}",
		},
	)
	attempt = 0
	while True:
		try:
			with opener(request, timeout=timeout) as response:
				return json.loads(response.read() or b"{}").get("message") or {}
		except urllib.error.HTTPError as e:
			if e.code < 500 or attempt >= retries:
				detail = e.read().decode(errors="replace")[:500] if hasattr(e, "read") else ""
				raise SendError(f"FoaMES answered {e.code}: {detail}") from e
		except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
			if attempt >= retries:
				raise SendError(f"could not reach FoaMES: {e}") from e
		sleep(backoff * (2**attempt))
		attempt += 1
