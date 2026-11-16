# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Build a source and a tag map from a JSON configuration file.

	{
	  "source": {"type": "pi", "name": "pi-main", "url": "https://pi.example.com/piwebapi",
	             "auth": "basic", "username": "svc-foames"},
	  "tags": [{"tag": "\\\\\\\\PI01\\\\P1.Temp", "machine": "press-1", "name": "temperature"}]
	}

Source types: `pi`, `influxdb`, `ignition-sql`, `ignition-webdev`, `sql`, `timescaledb`.

Secrets are never read from the file: a password comes from FOAMES_HISTORIAN_PASSWORD and a token
from FOAMES_HISTORIAN_TOKEN (the names can be changed per source with `password_env` and
`token_env`). The SQL sources import the DB-API driver named in `driver` (psycopg, pymysql,
pyodbc, sqlite3, ...), so only the driver for the database in use needs installing.
"""

from __future__ import annotations

import importlib
import json
import os

from foames_historian.http import HttpClient, basic_auth
from foames_historian.mapping import check_source_name, load_tag_map
from foames_historian.model import HistorianError
from foames_historian.sources.ignition import IgnitionSQLSource, IgnitionWebDevSource
from foames_historian.sources.influx import InfluxQLSource
from foames_historian.sources.pi import PIWebAPISource
from foames_historian.sources.sql import SQLSource

SOURCE_TYPES = ("pi", "influxdb", "ignition-sql", "ignition-webdev", "sql", "timescaledb")
_HTTP_KEYS = {
	"type",
	"name",
	"url",
	"auth",
	"username",
	"password_env",
	"token_env",
	"verify",
	"ca_file",
	"timeout",
}
_SQL_KEYS = {"type", "name", "driver", "connect", "password_env", "paramstyle"}


def load(path: str, *, env=None, opener=None, driver_loader=None):
	"""(source, tag map) from the file at `path`."""
	try:
		# The path is one the operator named on the command line of a local tool, not request input.
		with open(path, encoding="utf-8") as f:  # nosemgrep
			raw = json.load(f)
	except (OSError, ValueError) as e:
		raise HistorianError(f"cannot read the configuration {path}: {e}") from e
	return from_dict(raw, env=env, opener=opener, driver_loader=driver_loader)


def from_dict(raw: dict, *, env=None, opener=None, driver_loader=None):
	if not isinstance(raw, dict) or not isinstance(raw.get("source"), dict):
		raise HistorianError('the configuration needs a "source" object and a "tags" list')
	source = build_source(raw["source"], env=env, opener=opener, driver_loader=driver_loader)
	return source, load_tag_map(raw.get("tags"))


def build_source(spec: dict, *, env=None, opener=None, driver_loader=None):
	env = os.environ if env is None else env
	kind = spec.get("type")
	if kind not in SOURCE_TYPES:
		raise HistorianError(f"source type must be one of {', '.join(SOURCE_TYPES)}, not {kind!r}")
	name = check_source_name(spec.get("name") or kind)
	if kind in ("pi", "influxdb", "ignition-webdev"):
		extra = {
			"pi": {"max_count", "calculation_basis"},
			"influxdb": {"database", "retention_policy"},
			"ignition-webdev": set(),
		}[kind]
		_no_unknown(spec, _HTTP_KEYS | extra)
		http = _http(spec, env, opener)
		if kind == "pi":
			options = {k: spec[k] for k in ("max_count", "calculation_basis") if k in spec}
			return PIWebAPISource(name, http, **options)
		if kind == "influxdb":
			return InfluxQLSource(
				name, http, database=spec.get("database"), retention_policy=spec.get("retention_policy")
			)
		return IgnitionWebDevSource(name, http, endpoint="")

	sql_extra = {
		"ignition-sql": {"gateway"},
		"sql": {"table", "time_column", "tag_column", "value_column", "quality_column", "time_type"},
		"timescaledb": {"table", "time_column", "tag_column", "value_column", "quality_column"},
	}[kind]
	_no_unknown(spec, _SQL_KEYS | sql_extra)
	connect, paramstyle = _driver(spec, env, driver_loader)
	if kind == "ignition-sql":
		return IgnitionSQLSource(name, connect, paramstyle=paramstyle, gateway=spec.get("gateway"))
	options = {k: spec[k] for k in sql_extra if k in spec}
	if kind == "timescaledb":
		options["dialect"] = "timescale"
		options["time_type"] = "timestamp"
	if "table" not in options:
		raise HistorianError(f"a {kind} source needs the table that holds the history")
	return SQLSource(name, connect, paramstyle=paramstyle, **options)


def _no_unknown(spec, allowed):
	unknown = set(spec) - allowed
	if "password" in unknown or "token" in unknown:
		raise HistorianError(
			"put the password or token in the FOAMES_HISTORIAN_PASSWORD / FOAMES_HISTORIAN_TOKEN "
			"environment variable, not in the configuration file"
		)
	if unknown:
		raise HistorianError(f"unknown source keys for {spec.get('type')}: {', '.join(sorted(unknown))}")


def _http(spec, env, opener):
	auth = spec.get("auth") or "none"
	headers = {}
	if auth == "basic":
		password = env.get(spec.get("password_env") or "FOAMES_HISTORIAN_PASSWORD", "")
		if not spec.get("username") or not password:
			raise HistorianError(
				"basic auth needs a username in the file and the password in the environment"
			)
		headers["Authorization"] = basic_auth(spec["username"], password)
	elif auth in ("bearer", "token"):
		token = env.get(spec.get("token_env") or "FOAMES_HISTORIAN_TOKEN", "")
		if not token:
			raise HistorianError(f"{auth} auth needs the token in the environment")
		# InfluxDB 2 and 3 take "Token <t>"; PI Web API (OpenID Connect) and others "Bearer <t>".
		headers["Authorization"] = f"{'Token' if auth == 'token' else 'Bearer'} {token}"
	elif auth != "none":
		raise HistorianError("auth must be none, basic, bearer or token")
	if not str(spec.get("url") or "").startswith(("https://", "http://")):
		raise HistorianError("the source needs an http(s) url")
	return HttpClient(
		spec["url"],
		headers=headers,
		timeout=spec.get("timeout", 30),
		verify=spec.get("verify", True),
		ca_file=spec.get("ca_file"),
		opener=opener,
	)


def _driver(spec, env, driver_loader):
	driver_name = spec.get("driver")
	if not driver_name:
		raise HistorianError("a SQL source needs a driver, such as psycopg, pymysql, pyodbc or sqlite3")
	try:
		driver = (driver_loader or importlib.import_module)(driver_name)
	except ImportError as e:
		raise HistorianError(f"the database driver {driver_name!r} is not installed: {e}") from e
	kwargs = dict(spec.get("connect") or {})
	if "password" in kwargs:
		raise HistorianError("put the database password in FOAMES_HISTORIAN_PASSWORD, not in the file")
	password = env.get(spec.get("password_env") or "FOAMES_HISTORIAN_PASSWORD")
	if password:
		kwargs["password"] = password
	paramstyle = spec.get("paramstyle") or getattr(driver, "paramstyle", "format")

	def connect():
		return driver.connect(**kwargs)

	return connect, paramstyle
