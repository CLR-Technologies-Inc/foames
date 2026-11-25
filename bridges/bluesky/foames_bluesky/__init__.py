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

"""Bridge from Bluesky runs (live, Tiled or JSON Lines) to FoaMES Measurement events."""

from foames_bluesky.callback import FoaMESCallback
from foames_bluesky.mapping import MappingError, RunMapper, map_documents, unpack_event_page
from foames_bluesky.sender import SendError, WebhookSender, ingest_url, sign
from foames_bluesky.sources import jsonl_documents, tiled_documents

__version__ = "0.1.0"

__all__ = [
	"FoaMESCallback",
	"MappingError",
	"RunMapper",
	"SendError",
	"WebhookSender",
	"ingest_url",
	"jsonl_documents",
	"map_documents",
	"sign",
	"tiled_documents",
	"unpack_event_page",
]
