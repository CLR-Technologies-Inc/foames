# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""AVEVA PI (OSIsoft PI) through the PI Web API, read-only. Standard library only.

Uses the published PI Web API endpoints only:

	GET points?path=\\\\<data server>\\<tag>                      PI Point -> WebId
	GET attributes?path=\\\\<AF server>\\<db>\\<element>|<attribute>   AF attribute -> WebId
	GET streams/{webId}/recorded?startTime&endTime&maxCount       compressed (archived) values
	GET streams/{webId}/summary?summaryType&summaryDuration       server-side aggregates

A tag in the tag map is a PI Point path (`\\\\PISRV01\\Press1.Temperature`), an AF attribute path
(anything with a `|`), or `webid:<WebId>`. Recorded values are paged with `maxCount`. Digital
states come back as their state name, and a system digital state (Shutdown, I/O Timeout, No Data
and the like) is bad quality, never a value.
"""

from __future__ import annotations

from foames_historian.model import (
	BAD,
	GOOD,
	UNCERTAIN,
	HistorianError,
	Sample,
	finite_or_none,
	iso,
	parse_time,
)
from foames_historian.sources.base import Source

# FoaMES aggregate -> (PI summaryType, calculationBasis or None for the source's setting)
SUMMARY_TYPES = {
	"mean": ("Average", None),
	"min": ("Minimum", None),
	"max": ("Maximum", None),
	"count": ("Count", "EventWeighted"),
	"sum": ("Total", "EventWeighted"),
}
RECORDED_FIELDS = (
	"Items.Timestamp;Items.Value;Items.Good;Items.Questionable;Items.Substituted;Items.UnitsAbbreviation"
)


class PIWebAPISource(Source):
	kind = "pi"

	def __init__(
		self,
		name,
		http,
		*,
		max_count: int = 10000,
		calculation_basis: str = "TimeWeighted",
		max_pages: int = 1000,
	):
		super().__init__(name)
		self.http = http
		self.max_count = max(int(max_count), 1)
		self.calculation_basis = calculation_basis
		self.max_pages = max_pages
		self._web_ids: dict[str, str] = {}

	def web_id(self, tag: str) -> str:
		if tag.lower().startswith("webid:"):
			return tag[6:]
		if tag not in self._web_ids:
			endpoint = "attributes" if "|" in tag else "points"
			answer = self.http.get_json(endpoint, {"path": tag, "selectedFields": "WebId;Name"})
			web_id = (answer or {}).get("WebId")
			if not web_id:
				raise HistorianError(f"PI Web API has no {endpoint[:-1]} at {tag!r}")
			self._web_ids[tag] = web_id
		return self._web_ids[tag]

	def _read_raw(self, tag, start, end):
		web_id = self.web_id(tag)
		out: list[Sample] = []
		cursor = start
		for _page in range(self.max_pages):
			answer = self.http.get_json(
				f"streams/{web_id}/recorded",
				{
					"startTime": iso(cursor),
					"endTime": iso(end),
					"boundaryType": "Inside",
					"maxCount": self.max_count,
					"selectedFields": RECORDED_FIELDS,
				},
			)
			items = _items(answer, tag)
			page = [self._sample(tag, item) for item in items]
			page = [s for s in page if s is not None]
			if out:
				# The next page starts at the last timestamp read, inclusive; drop what was already
				# read at that instant (several values may share it).
				last = out[-1].timestamp
				already = sum(1 for s in out if s.timestamp == last)
				same = [s for s in page if s.timestamp == last]
				page = same[already:] + [s for s in page if s.timestamp > last]
			out.extend(page)
			if len(items) < self.max_count or not page:
				return out
			cursor = out[-1].timestamp
		raise HistorianError(
			f"PI Web API: more than {self.max_pages} pages of values for {tag!r}; narrow the window"
		)

	def _read_aggregated(self, tag, start, end, interval, how):
		if how not in SUMMARY_TYPES:
			return super()._read_aggregated(tag, start, end, interval, how)
		summary_type, basis = SUMMARY_TYPES[how]
		answer = self.http.get_json(
			f"streams/{self.web_id(tag)}/summary",
			{
				"startTime": iso(start),
				"endTime": iso(end),
				"summaryType": summary_type,
				"summaryDuration": f"{interval.total_seconds():g}s",  # an AFTimeSpan
				"calculationBasis": basis or self.calculation_basis,
			},
		)
		out = []
		for item in _items(answer, tag):
			sample = self._sample(
				tag, item.get("Value") or {}, extra={"aggregate": how, "pi_summary": summary_type}
			)
			if sample is not None:
				out.append(sample)
		return out

	def _sample(self, tag, item, extra=None):
		if not isinstance(item, dict) or not item.get("Timestamp"):
			return None
		raw = item.get("Value")
		extra = dict(extra or {})
		quality = GOOD
		if item.get("Good") is False:
			quality = BAD
		elif item.get("Questionable"):
			quality = UNCERTAIN
		if item.get("Substituted"):
			extra["substituted"] = True
		if isinstance(raw, dict):
			# A digital state ({"Name", "Value", "IsSystem"}) or an error object.
			if "Name" in raw:
				extra["digital_code"] = raw.get("Value")
				value = str(raw["Name"])
				if raw.get("IsSystem"):
					quality = BAD
			else:
				value, quality = None, BAD
		else:
			value = finite_or_none(raw)
		return Sample(
			tag=tag,
			timestamp=parse_time(item["Timestamp"]),
			value=value,
			quality=quality,
			units=item.get("UnitsAbbreviation") or None,
			extra=extra,
		)


def _items(answer, tag):
	if not isinstance(answer, dict):
		raise HistorianError(f"PI Web API answered something unexpected for {tag!r}")
	errors = answer.get("Errors")
	if errors:
		raise HistorianError(f"PI Web API refused {tag!r}: {'; '.join(str(e) for e in errors)[:300]}")
	return answer.get("Items") or []
