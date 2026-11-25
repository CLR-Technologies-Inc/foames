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

"""Read-only historian sources."""

from foames_historian.sources.base import Source
from foames_historian.sources.ignition import IgnitionSQLSource, IgnitionWebDevSource
from foames_historian.sources.influx import InfluxQLSource
from foames_historian.sources.pi import PIWebAPISource
from foames_historian.sources.sql import SQLSource

__all__ = [
	"IgnitionSQLSource",
	"IgnitionWebDevSource",
	"InfluxQLSource",
	"PIWebAPISource",
	"SQLSource",
	"Source",
]
