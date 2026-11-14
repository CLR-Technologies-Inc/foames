# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""A Bluesky callback that forwards runs to FoaMES as they are taken.

Subscribe it to a RunEngine, or better, to a RemoteDispatcher (0MQ) or a Kafka consumer in a
separate process, so a slow or unreachable FoaMES never holds up data acquisition:

	from foames_bluesky import FoaMESCallback, RunMapper, WebhookSender

	callback = FoaMESCallback(
		RunMapper("xrd-1", summaries=("mean",)),
		WebhookSender("https://foames.example.com", secret),
	)
	RE.subscribe(callback)

The callback never raises into Bluesky. Events that could not be posted stay in `pending` and go
with the next flush; their ids make the resend safe.
"""

from __future__ import annotations

import logging

from foames_bluesky.mapping import RunMapper
from foames_bluesky.sender import WebhookSender

log = logging.getLogger("foames_bluesky")


class FoaMESCallback:
	def __init__(self, mapper: RunMapper, sender: WebhookSender, *, flush_every: int = 200):
		self.mapper = mapper
		self.sender = sender
		self.flush_every = max(int(flush_every), 1)
		self.pending: list[dict] = []
		self.rejected: list[dict] = []

	def __call__(self, name: str, doc: dict):
		try:
			self.pending.extend(self.mapper(name, doc))
		except Exception:
			log.exception("could not map a Bluesky %s document for FoaMES", name)
			return
		if name == "stop" or len(self.pending) >= self.flush_every:
			self.flush()

	def flush(self) -> bool:
		"""Post what is pending. Returns False (and keeps the events) when FoaMES cannot be reached."""
		if not self.pending:
			return True
		batch, self.pending = self.pending, []
		try:
			result = self.sender.send(batch)
		except Exception:
			log.exception("could not post %d events to FoaMES; kept for the next flush", len(batch))
			self.pending = batch + self.pending
			return False
		rejected = [r for r in result.get("rejected") or [] if r.get("reason") != "duplicate event id"]
		if rejected:
			log.warning("FoaMES rejected %d events: %s", len(rejected), rejected[0].get("reason"))
			self.rejected.extend(rejected)
		return True
