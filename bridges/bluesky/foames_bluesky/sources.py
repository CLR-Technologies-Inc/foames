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

"""Where finished runs are read from: JSON Lines files and Tiled servers.

Both yield the same (name, document) pairs a live RunEngine emits, so one RunMapper serves all
three paths.
"""

from __future__ import annotations

import json


def jsonl_documents(path):
	"""(name, doc) pairs from a JSON Lines file with one `[name, doc]` array per line, the format
	suitcase-jsonl writes. Blank lines are skipped."""
	# The path is one the operator named on the command line of a local tool, not request input.
	with open(path, encoding="utf-8") as handle:  # nosemgrep
		for number, line in enumerate(handle, 1):
			line = line.strip()
			if not line:
				continue
			item = json.loads(line)
			if not (isinstance(item, list) and len(item) == 2 and isinstance(item[1], dict)):
				raise ValueError(f"{path}:{number}: expected [name, document]")
			yield str(item[0]), item[1]


def tiled_documents(uri: str, uids, api_key: str | None = None, client=None):
	"""(name, doc) pairs for each run uid in a Tiled catalog of Bluesky runs.

	Needs the Tiled client and the Bluesky run structure for it (`pip install "tiled[client]"
	bluesky-tiled-plugins`, or databroker 2 for older catalogs); both give run nodes a
	`documents()` method that replays the run's documents. `client` is the catalog node itself,
	for callers that already hold one (and for tests)."""
	if client is None:
		try:
			from tiled.client import from_uri
		except ImportError as e:
			raise RuntimeError(
				'reading from Tiled needs the Tiled client: pip install "tiled[client]" bluesky-tiled-plugins'
			) from e
		client = from_uri(uri, api_key=api_key)
	for uid in uids:
		run = client[uid]
		documents = getattr(run, "documents", None)
		if documents is None:
			raise RuntimeError(
				f"Tiled node {uid!r} is not a Bluesky run (install bluesky-tiled-plugins or databroker)"
			)
		yield from documents()
