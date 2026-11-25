# Copyright 2026 CLR Technologies Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""Post events to the FoaMES machine-event webhook, signed. Standard library only.

The signature is the one in foames.foames_mes.signing: hex HMAC-SHA256 of `<timestamp>.<body>`
with the webhook secret from Machine Data Settings, sent in `X-FoaMES-Signature`, with the Unix
timestamp in `X-FoaMES-Timestamp`. Events carry ids derived from the source, the tag and the sample
time, so a retry after an unclear answer or a replayed window cannot store a reading twice; FoaMES
reports the repeat as a rejected duplicate. (Same code as the Bluesky bridge's sender; each bridge
is a standalone package, so it is copied rather than shared.)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
import urllib.error
import urllib.request

INGEST_PATH = "/api/method/foames.foames_mes.api.ingest_machine_events"
SIGNATURE_HEADER = "X-FoaMES-Signature"
TIMESTAMP_HEADER = "X-FoaMES-Timestamp"

log = logging.getLogger("foames_historian")


class SendError(RuntimeError):
	pass


def sign(secret: str, timestamp: int | str, body: bytes) -> str:
	return hmac.new(secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()


def ingest_url(site: str) -> str:
	"""The webhook URL for a site URL (or the full webhook URL, unchanged)."""
	site = site.rstrip("/")
	return site if site.endswith(INGEST_PATH) else site + INGEST_PATH


class WebhookSender:
	"""send(events) posts them in batches and returns the combined {"accepted", "rejected"}.

	A rejected duplicate is normal after a retry or a replay. Network errors and 5xx answers are
	retried with exponential backoff; a 4xx answer (bad signature, bad body) raises at once."""

	def __init__(
		self,
		site: str,
		secret: str,
		*,
		batch_size: int = 200,
		timeout: float = 30,
		retries: int = 4,
		backoff: float = 1.0,
		opener=None,
		clock=time.time,
		sleep=time.sleep,
	):
		if not secret:
			raise SendError("the FoaMES webhook secret is empty")
		self.url = ingest_url(site)
		self.secret = secret
		self.batch_size = max(int(batch_size), 1)
		self.timeout = timeout
		self.retries = max(int(retries), 0)
		self.backoff = backoff
		self._open = opener or urllib.request.urlopen
		self._clock = clock
		self._sleep = sleep

	def send(self, events: list[dict]) -> dict:
		result = {"accepted": [], "rejected": []}
		for start in range(0, len(events), self.batch_size):
			answer = self._post(events[start : start + self.batch_size])
			result["accepted"].extend(answer.get("accepted") or [])
			result["rejected"].extend(answer.get("rejected") or [])
		return result

	def _post(self, batch: list[dict]) -> dict:
		body = json.dumps({"events": batch}, separators=(",", ":"), default=str).encode()
		attempt = 0
		while True:
			timestamp = str(int(self._clock()))
			request = urllib.request.Request(
				self.url,
				data=body,
				method="POST",
				headers={
					"Content-Type": "application/json",
					TIMESTAMP_HEADER: timestamp,
					SIGNATURE_HEADER: sign(self.secret, timestamp, body),
				},
			)
			try:
				with self._open(request, timeout=self.timeout) as response:
					payload = json.loads(response.read() or b"{}")
				return payload.get("message", payload) if isinstance(payload, dict) else {}
			except urllib.error.HTTPError as e:
				if e.code < 500 or attempt >= self.retries:
					raise SendError(f"FoaMES answered {e.code}: {_reason(e)}") from e
			except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
				if attempt >= self.retries:
					raise SendError(f"cannot reach FoaMES at {self.url}: {e}") from e
			delay = self.backoff * (2**attempt)
			log.warning("posting to FoaMES failed, retrying in %.1f s", delay)
			self._sleep(delay)
			attempt += 1


def _reason(error) -> str:
	try:
		return error.read().decode("utf-8", errors="replace")[:500]
	except Exception:
		return str(error)
