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

"""InfluxDB through the InfluxQL `/query` endpoint, read-only. Standard library only.

`/query` is served by InfluxDB 1.x, by 2.x through its 1.x compatibility API (map the bucket to a
database and retention policy with a DBRP mapping), and by InfluxDB 3 Core and Enterprise. Only
SELECT statements are built; nothing is ever written.

A tag in the tag map is `<measurement>/<field>`, optionally followed by tag filters written like a
URL query: `machine_data/temperature?line=L1&machine=press-1`. Names are quoted as identifiers
and filter values as string literals, so a tag map cannot inject InfluxQL.
"""

from __future__ import annotations

import urllib.parse

from foames_historian.model import HistorianError, Sample, finite_or_none, from_epoch_ms, iso
from foames_historian.sources.base import Source

FUNCTIONS = {
	"mean": "MEAN",
	"min": "MIN",
	"max": "MAX",
	"first": "FIRST",
	"last": "LAST",
	"count": "COUNT",
	"sum": "SUM",
}


def parse_tag(tag: str):
	"""(measurement, field, {tag key: value}) from `measurement/field?k=v&k2=v2`."""
	path, _, query = tag.partition("?")
	measurement, sep, field = path.rpartition("/")
	if not sep or not measurement or not field:
		raise HistorianError(f"InfluxDB tag {tag!r} must be <measurement>/<field>, optionally ?tag=value&...")
	return measurement, field, dict(urllib.parse.parse_qsl(query, keep_blank_values=True))


def quote_ident(name: str) -> str:
	return '"' + name.replace("\\", "\\\\").replace('"', '\\"') + '"'


def quote_string(value: str) -> str:
	return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def build_query(tag, start, end, *, function=None, interval=None, retention_policy=None) -> str:
	measurement, field, filters = parse_tag(tag)
	source = quote_ident(measurement)
	if retention_policy:
		source = f"{quote_ident(retention_policy)}.{source}"
	selected = f"{function}({quote_ident(field)})" if function else quote_ident(field)
	where = [f"time >= {quote_string(iso(start))}", f"time < {quote_string(iso(end))}"]
	where += [f"{quote_ident(k)} = {quote_string(v)}" for k, v in sorted(filters.items())]
	query = f"SELECT {selected} FROM {source} WHERE {' AND '.join(where)}"
	if function:
		query += f" GROUP BY time({int(interval.total_seconds() * 1000)}ms) fill(none)"
	return query + " ORDER BY time ASC"


class InfluxQLSource(Source):
	kind = "influxdb"

	def __init__(self, name, http, *, database: str, retention_policy: str | None = None):
		super().__init__(name)
		if not database:
			raise HistorianError("an InfluxDB source needs a database (or a bucket mapped to one)")
		self.http = http
		self.database = database
		self.retention_policy = retention_policy

	def _read_raw(self, tag, start, end):
		return self._query(tag, build_query(tag, start, end, retention_policy=self.retention_policy))

	def _read_aggregated(self, tag, start, end, interval, how):
		query = build_query(
			tag,
			start,
			end,
			function=FUNCTIONS[how],
			interval=interval,
			retention_policy=self.retention_policy,
		)
		return self._query(tag, query, extra={"aggregate": how})

	def _query(self, tag, query, extra=None):
		answer = self.http.get_json("query", {"db": self.database, "q": query, "epoch": "ms"})
		if not isinstance(answer, dict):
			raise HistorianError(f"InfluxDB answered something unexpected for {tag!r}")
		if answer.get("error"):
			raise HistorianError(f"InfluxDB refused the query for {tag!r}: {answer['error']}")
		out = []
		for result in answer.get("results") or []:
			if result.get("error"):
				raise HistorianError(f"InfluxDB refused the query for {tag!r}: {result['error']}")
			for series in result.get("series") or []:
				columns = series.get("columns") or []
				if "time" not in columns or len(columns) < 2:
					continue
				t_index = columns.index("time")
				v_index = 1 if t_index == 0 else 0
				for row in series.get("values") or []:
					value = finite_or_none(row[v_index])
					if value is None:
						continue
					out.append(
						Sample(
							tag=tag,
							timestamp=from_epoch_ms(row[t_index]),
							value=value,
							extra=dict(extra or {}),
						)
					)
		return out
