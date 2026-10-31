# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""How Python values are written into an OData V2 JSON body for S/4HANA.

OData V2 carries decimals as strings, dates (Edm.DateTime) as `YYYY-MM-DDTHH:MM:SS` and times of
day (Edm.Time) as ISO 8601 durations such as `PT08H30M00S`. S/4HANA accepts the ISO forms in JSON
bodies and answers with `/Date(ms)/` for dates, which `parse_date` reads back.
"""

import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation

DATE_PATTERN = re.compile(r"/Date\((-?\d+)(?:[+-]\d+)?\)/")


def decimal_string(value) -> str:
	"""`"12.5"` for 12.5, `"100"` for 100.0, `"0.001"` for 1e-3: no exponent, no trailing zeros."""
	if value is None or value == "":
		raise ValueError("A quantity is required")
	try:
		number = Decimal(str(value).strip())
	except InvalidOperation:
		raise ValueError(f"{value!r} is not a number")
	if number.is_nan() or number.is_infinite():
		raise ValueError(f"{value!r} is not a number")
	text = format(number.normalize(), "f")
	if "." in text:
		text = text.rstrip("0").rstrip(".")
	return text if text not in ("", "-0") else "0"


def date_string(value) -> str:
	"""An Edm.DateTime at midnight, from a date, a datetime or an ISO string."""
	if isinstance(value, datetime):
		value = value.date()
	if isinstance(value, date):
		return value.isoformat() + "T00:00:00"
	text = str(value).strip()
	if not text:
		raise ValueError("A date is required")
	return date.fromisoformat(text[:10]).isoformat() + "T00:00:00"


def datetime_string(value) -> str:
	"""An Edm.DateTime with its time of day, from a datetime or an ISO string."""
	if isinstance(value, datetime):
		return value.replace(microsecond=0, tzinfo=None).isoformat()
	if isinstance(value, date):
		return date_string(value)
	text = str(value).strip().replace(" ", "T")
	return datetime.fromisoformat(text).replace(microsecond=0, tzinfo=None).isoformat()


def time_string(value) -> str:
	"""An Edm.Time duration (`PT08H30M00S`), from a time, a datetime or `HH:MM[:SS]`."""
	if isinstance(value, datetime):
		value = value.time()
	if isinstance(value, time):
		return f"PT{value.hour:02d}H{value.minute:02d}M{value.second:02d}S"
	text = str(value).strip()
	if text.startswith("PT"):
		return text
	parts = text.split(":")
	if len(parts) not in (2, 3) or not all(p.isdigit() for p in parts):
		raise ValueError(f"{value!r} is not a time of day")
	hour, minute = int(parts[0]), int(parts[1])
	second = int(parts[2]) if len(parts) == 3 else 0
	if hour > 23 or minute > 59 or second > 59:
		raise ValueError(f"{value!r} is not a time of day")
	return f"PT{hour:02d}H{minute:02d}M{second:02d}S"


def parse_date(value) -> date | None:
	"""A date out of S/4HANA's `/Date(1761868800000)/`, an ISO string or None."""
	if value is None or value == "":
		return None
	if isinstance(value, datetime):
		return value.date()
	if isinstance(value, date):
		return value
	match = DATE_PATTERN.fullmatch(str(value).strip())
	if match:
		return (datetime(1970, 1, 1) + timedelta(milliseconds=int(match.group(1)))).date()
	return date.fromisoformat(str(value).strip()[:10])


def parse_datetime(value) -> datetime | None:
	if value is None or value == "":
		return None
	if isinstance(value, datetime):
		return value
	match = DATE_PATTERN.fullmatch(str(value).strip())
	if match:
		return datetime(1970, 1, 1) + timedelta(milliseconds=int(match.group(1)))
	return datetime.fromisoformat(str(value).strip().replace(" ", "T"))


def parse_time(value) -> time | None:
	"""A time of day out of `PT08H30M00S`, or `HH:MM:SS`."""
	if value is None or value == "":
		return None
	if isinstance(value, time):
		return value
	text = str(value).strip()
	match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", text)
	if match:
		hour, minute, second = (int(part or 0) for part in match.groups())
		return time(hour % 24, minute, second)
	return time.fromisoformat(text)


def parse_decimal(value) -> Decimal:
	if value is None or value == "":
		return Decimal(0)
	try:
		return Decimal(str(value))
	except InvalidOperation:
		return Decimal(0)


def clean(payload: dict) -> dict:
	"""The payload without None values, so optional fields that were not given are not sent."""
	return {key: value for key, value in payload.items() if value is not None}
