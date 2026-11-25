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

"""SQL historians, read-only, through any Python DB-API 2.0 driver.

`SQLSource` reads a narrow ("tall") table with one row per tag and time, the layout of most
home-grown historians and of a TimescaleDB hypertable:

	CREATE TABLE tag_history (time timestamptz, tag text, value double precision, quality int);

With `dialect="timescale"` aggregates run on the server with `time_bucket`; otherwise raw rows
are read and bucketed by the bridge. The Ignition SQL historian has its own layout and its own
source in `ignition.py`, on the same helpers.

The driver is the operator's choice (psycopg, pymysql, pyodbc, sqlite3, ...) and is passed in as a
`connect` callable, so this module imports none. Table and column names come from the
configuration and are checked against a strict pattern; values are always bound as parameters.
Give the bridge a database user that can only SELECT.
"""

from __future__ import annotations

import re
from datetime import datetime

from foames_historian.model import (
	HistorianError,
	Sample,
	epoch_ms,
	finite_or_none,
	from_epoch_ms,
	from_epoch_seconds,
	opc_quality,
	parse_time,
)
from foames_historian.sources.base import Source

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")
TIME_TYPES = ("timestamp", "iso", "epoch_ms", "epoch_s")
DIALECTS = ("generic", "timescale")
TIMESCALE_FUNCTIONS = {
	"mean": "avg({v})",
	"min": "min({v})",
	"max": "max({v})",
	"count": "count({v})",
	"sum": "sum({v})",
	"first": "first({v}, {t})",
	"last": "last({v}, {t})",
}


def ident(name: str) -> str:
	if not isinstance(name, str) or not _IDENT.match(name):
		raise HistorianError(f"{name!r} is not a plain table or column name (letters, digits, _ and one .)")
	return name


class Placeholders:
	"""Builds the driver's placeholder for each bound value (DB-API `paramstyle`)."""

	def __init__(self, paramstyle: str):
		if paramstyle not in ("qmark", "format", "pyformat", "numeric", "named"):
			raise HistorianError(f"unknown paramstyle {paramstyle!r}")
		self.paramstyle = paramstyle
		self.values: list = []

	def __call__(self, value) -> str:
		self.values.append(value)
		n = len(self.values)
		return {"qmark": "?", "format": "%s", "pyformat": "%s", "numeric": f":{n}", "named": f":p{n}"}[
			self.paramstyle
		]

	@property
	def params(self):
		if self.paramstyle == "named":
			return {f"p{i + 1}": v for i, v in enumerate(self.values)}
		return tuple(self.values)


class _DBSource(Source):
	def __init__(self, name, connect, *, paramstyle: str = "format"):
		super().__init__(name)
		self._connect = connect
		self._connection = None
		self.paramstyle = paramstyle
		Placeholders(paramstyle)  # validate early

	@property
	def connection(self):
		if self._connection is None:
			try:
				self._connection = self._connect()
			except Exception as e:
				raise HistorianError(f"cannot connect to the {self.kind} historian: {e}") from e
		return self._connection

	def fetch(self, build) -> list[tuple]:
		"""Run the query `build(placeholders)` returns and give back all rows."""
		bind = Placeholders(self.paramstyle)
		sql = build(bind)
		cursor = self.connection.cursor()
		try:
			cursor.execute(sql, bind.params)
			return list(cursor.fetchall())
		except Exception as e:
			raise HistorianError(f"the {self.kind} historian refused a query: {e}") from e
		finally:
			try:
				cursor.close()
			except Exception:
				pass

	def close(self):
		if self._connection is not None:
			try:
				self._connection.close()
			finally:
				self._connection = None


class SQLSource(_DBSource):
	kind = "sql"

	def __init__(
		self,
		name,
		connect,
		*,
		table: str,
		time_column: str = "time",
		tag_column: str = "tag",
		value_column: str = "value",
		quality_column: str | None = None,
		time_type: str = "timestamp",
		dialect: str = "generic",
		paramstyle: str = "format",
	):
		super().__init__(name, connect, paramstyle=paramstyle)
		if time_type not in TIME_TYPES:
			raise HistorianError(f"time_type must be one of {', '.join(TIME_TYPES)}")
		if dialect not in DIALECTS:
			raise HistorianError(f"dialect must be one of {', '.join(DIALECTS)}")
		if dialect == "timescale" and time_type != "timestamp":
			raise HistorianError("the timescale dialect needs a timestamp time column")
		self.table = ident(table)
		self.time_column = ident(time_column)
		self.tag_column = ident(tag_column)
		self.value_column = ident(value_column)
		self.quality_column = ident(quality_column) if quality_column else None
		self.time_type = time_type
		self.dialect = dialect

	def _bound_time(self, moment: datetime):
		if self.time_type == "epoch_ms":
			return epoch_ms(moment)
		if self.time_type == "epoch_s":
			return epoch_ms(moment) / 1000
		if self.time_type == "iso":
			return moment.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
		return moment

	def _time(self, raw) -> datetime:
		if self.time_type == "epoch_ms":
			return from_epoch_ms(raw)
		if self.time_type == "epoch_s":
			return from_epoch_seconds(raw)
		return parse_time(raw)

	def _read_raw(self, tag, start, end):
		t, v = self.time_column, self.value_column
		q = f", {self.quality_column}" if self.quality_column else ""

		def build(p):
			return (
				f"SELECT {t}, {v}{q} FROM {self.table} WHERE {self.tag_column} = {p(tag)} "
				f"AND {t} >= {p(self._bound_time(start))} AND {t} < {p(self._bound_time(end))} ORDER BY {t}"
			)

		out = []
		for row in self.fetch(build):
			quality = opc_quality(row[2]) if self.quality_column else opc_quality(None)
			out.append(
				Sample(tag=tag, timestamp=self._time(row[0]), value=finite_or_none(row[1]), quality=quality)
			)
		return out

	def _read_aggregated(self, tag, start, end, interval, how):
		if self.dialect != "timescale":
			return super()._read_aggregated(tag, start, end, interval, how)
		t, v = self.time_column, self.value_column
		function = TIMESCALE_FUNCTIONS[how].format(v=v, t=t)

		def build(p):
			bucket = (
				f"time_bucket(make_interval(secs => {p(interval.total_seconds())}), {t}, "
				"TIMESTAMPTZ '1970-01-01 00:00:00+00')"
			)
			return (
				f"SELECT {bucket} AS bucket, {function} FROM {self.table} WHERE {self.tag_column} = {p(tag)} "
				f"AND {t} >= {p(start)} AND {t} < {p(end)} GROUP BY bucket ORDER BY bucket"
			)

		out = []
		for bucket, value in self.fetch(build):
			value = finite_or_none(value)
			if value is not None:
				out.append(
					Sample(tag=tag, timestamp=parse_time(bucket), value=value, extra={"aggregate": how})
				)
		return out
