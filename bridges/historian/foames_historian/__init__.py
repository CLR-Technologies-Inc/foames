# Copyright (c) 2026 CLR Technologies Inc. and contributors
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
