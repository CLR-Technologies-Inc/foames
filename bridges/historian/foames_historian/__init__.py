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

"""Read-only bridge from process historians (PI, InfluxDB, Ignition, TimescaleDB and other SQL
historians) to FoaMES machine events."""

from foames_historian.config import build_source, from_dict, load
from foames_historian.mapping import MappingError, SampleMapper, TagMapping, load_tag_map
from foames_historian.model import AGGREGATES, HistorianError, Sample, aggregate, parse_duration, parse_time
from foames_historian.sender import SendError, WebhookSender, ingest_url, sign
from foames_historian.sources import (
	IgnitionSQLSource,
	IgnitionWebDevSource,
	InfluxQLSource,
	PIWebAPISource,
	Source,
	SQLSource,
)
from foames_historian.sync import Checkpoint, SyncResult, sync_once

__version__ = "0.1.0"

__all__ = [
	"AGGREGATES",
	"Checkpoint",
	"HistorianError",
	"IgnitionSQLSource",
	"IgnitionWebDevSource",
	"InfluxQLSource",
	"MappingError",
	"PIWebAPISource",
	"SQLSource",
	"Sample",
	"SampleMapper",
	"SendError",
	"Source",
	"SyncResult",
	"TagMapping",
	"WebhookSender",
	"aggregate",
	"build_source",
	"from_dict",
	"ingest_url",
	"load",
	"load_tag_map",
	"parse_duration",
	"parse_time",
	"sign",
	"sync_once",
]
