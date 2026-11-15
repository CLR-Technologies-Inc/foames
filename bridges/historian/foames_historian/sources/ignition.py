# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Ignition Tag Historian, read-only, two ways.

`IgnitionSQLSource` reads the SQL historian's tables directly, as Inductive Automation documents
them ("Ignition Database Table Reference"; works with every database Ignition supports):

	sqlth_drv         one row per historian driver: id, name (the gateway), provider (tag provider)
	sqlth_scinfo      scan classes / history sets: id, drvid
	sqlth_te          one row per stored tag: id, tagpath (lower case, no provider), scid,
	                  datatype (0 int, 1 float, 2 string, 3 date), created, retired (epoch ms)
	sqlth_partitions  data partitions: pname, drvid, start_time, end_time (epoch ms)
	<pname>           sqlt_data_<drv>_<yyyy>_<mm> by default: tagid, intvalue, floatvalue,
	                  stringvalue, datevalue, dataintegrity (192 = good), t_stamp (epoch ms)

A tag is written as in Ignition, `[default]Line1/Press1/Good`; the provider is optional. A tag
that was retired and re-created has several ids, all read. This is the quickest path to years of
history and needs only a read-only database login, but it skips the historian's own
interpolation and any values still in the store-and-forward cache.

`IgnitionWebDevSource` calls a WebDev endpoint on the gateway that runs
`system.tag.queryTagHistory` and answers JSON (the script is in the guide). Use it when the
database is not reachable from where the bridge runs, or to let the gateway aggregate.
"""

from __future__ import annotations

import re

from foames_historian.model import (
	BAD,
	HistorianError,
	Sample,
	epoch_ms,
	finite_or_none,
	from_epoch_ms,
	iso,
	opc_quality,
)
from foames_historian.sources.base import Source
from foames_historian.sources.sql import _DBSource

_PARTITION = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TAG = re.compile(r"^\s*(?:\[([^\]]*)\])?\s*(.+?)\s*$")
DATATYPE_COLUMNS = {0: 1, 1: 2, 2: 3, 3: 4}  # sqlth_te.datatype -> index in the data row
# FoaMES aggregate -> Ignition aggregation mode for queryTagHistory (first and last are bucketed by the bridge)
IGNITION_MODES = {
	"mean": "SimpleAverage",
	"min": "Minimum",
	"max": "Maximum",
	"count": "Count",
	"sum": "Sum",
}
WEBDEV_AGGREGATES = ("mean", "min", "max", "count", "sum")


def split_tag(tag: str):
	"""(provider or None, tag path in lower case) from `[provider]path` or `path`."""
	match = _TAG.match(tag or "")
	if not match or not match.group(2):
		raise HistorianError(f"not an Ignition tag path: {tag!r}")
	provider = (match.group(1) or "").strip().lower() or None
	return provider, match.group(2).strip().lower()


class IgnitionSQLSource(_DBSource):
	kind = "ignition"

	def __init__(self, name, connect, *, paramstyle: str = "format", gateway: str | None = None):
		super().__init__(name, connect, paramstyle=paramstyle)
		self.gateway = gateway

	def tag_ids(self, tag, start_ms, end_ms):
		"""[(tag id, datatype, driver id)] for the tag's rows alive during the window."""
		provider, path = split_tag(tag)

		def build(p):
			sql = (
				"SELECT te.id, te.datatype, sc.drvid FROM sqlth_te te "
				"JOIN sqlth_scinfo sc ON te.scid = sc.id "
				"JOIN sqlth_drv d ON sc.drvid = d.id "
				f"WHERE LOWER(te.tagpath) = {p(path)} "
				f"AND (te.created IS NULL OR te.created < {p(end_ms)}) "
				f"AND (te.retired IS NULL OR te.retired >= {p(start_ms)})"
			)
			if provider:
				sql += f" AND LOWER(d.provider) = {p(provider)}"
			if self.gateway:
				sql += f" AND d.name = {p(self.gateway)}"
			return sql

		return [(row[0], row[1], row[2]) for row in self.fetch(build)]

	def partitions(self, driver_id, start_ms, end_ms):
		def build(p):
			return (
				f"SELECT pname FROM sqlth_partitions WHERE drvid = {p(driver_id)} "
				f"AND start_time < {p(end_ms)} AND end_time > {p(start_ms)} ORDER BY start_time"
			)

		names = []
		for (pname,) in self.fetch(build):
			if not _PARTITION.match(str(pname)):
				raise HistorianError(f"refusing to read Ignition partition with an unusual name: {pname!r}")
			names.append(pname)
		return names

	def _read_raw(self, tag, start, end):
		start_ms, end_ms = epoch_ms(start), epoch_ms(end)
		ids = self.tag_ids(tag, start_ms, end_ms)
		if not ids:
			raise HistorianError(f"the Ignition historian has no tag {tag!r} in that window")
		datatypes = {tag_id: datatype for tag_id, datatype, _ in ids}
		out = []
		for driver_id in sorted({d for _, _, d in ids}):
			tag_ids = sorted(t for t, _, d in ids if d == driver_id)
			for table in self.partitions(driver_id, start_ms, end_ms):

				def build(p, table=table, tag_ids=tag_ids):
					marks = ", ".join(p(t) for t in tag_ids)
					return (
						"SELECT tagid, intvalue, floatvalue, stringvalue, datevalue, dataintegrity, t_stamp "
						f"FROM {table} WHERE tagid IN ({marks}) "
						f"AND t_stamp >= {p(start_ms)} AND t_stamp < {p(end_ms)} ORDER BY t_stamp"
					)

				for row in self.fetch(build):
					out.append(self._sample(tag, row, datatypes.get(row[0])))
		return out

	def _sample(self, tag, row, datatype):
		index = DATATYPE_COLUMNS.get(datatype)
		raw = row[index] if index is not None else next((v for v in row[1:5] if v is not None), None)
		if datatype == 3 and raw is not None:
			value = raw if isinstance(raw, str) else iso(raw) if hasattr(raw, "astimezone") else str(raw)
		else:
			value = finite_or_none(raw)
		quality = opc_quality(row[5])
		if value is None:
			quality = BAD
		return Sample(
			tag=tag,
			timestamp=from_epoch_ms(row[6]),
			value=value,
			quality=quality,
			extra={"dataintegrity": row[5]},
		)


class IgnitionWebDevSource(Source):
	"""GET <endpoint>?path=<tag>&start=<ms>&end=<ms>[&intervalMs=<ms>&aggregate=<mode>]
	answering [{"t": <ms>, "v": <value>, "q": <quality code>}, ...]."""

	kind = "ignition"

	def __init__(self, name, http, *, endpoint: str = ""):
		super().__init__(name)
		self.http = http
		self.endpoint = endpoint

	def _read_raw(self, tag, start, end):
		return self._get(tag, {"path": tag, "start": epoch_ms(start), "end": epoch_ms(end)})

	def _read_aggregated(self, tag, start, end, interval, how):
		if how not in WEBDEV_AGGREGATES:
			return super()._read_aggregated(tag, start, end, interval, how)
		params = {
			"path": tag,
			"start": epoch_ms(start),
			"end": epoch_ms(end),
			"intervalMs": int(interval.total_seconds() * 1000),
			"aggregate": IGNITION_MODES[how],
		}
		return self._get(tag, params, extra={"aggregate": how})

	def _get(self, tag, params, extra=None):
		answer = self.http.get_json(self.endpoint, params)
		if isinstance(answer, dict) and answer.get("error"):
			raise HistorianError(f"the Ignition gateway refused {tag!r}: {answer['error']}")
		if not isinstance(answer, list):
			raise HistorianError(f"the Ignition WebDev endpoint answered something unexpected for {tag!r}")
		out = []
		for row in answer:
			if not isinstance(row, dict) or row.get("t") is None:
				continue
			value = finite_or_none(row.get("v"))
			quality = opc_quality(row.get("q", 192))
			out.append(
				Sample(
					tag=tag,
					timestamp=from_epoch_ms(row["t"]),
					value=value,
					quality=BAD if value is None else quality,
					extra=dict(extra or {}),
				)
			)
		return out
