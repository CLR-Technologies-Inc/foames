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

"""A small read-only HTTP client the REST sources share. Standard library only.

Only GET is offered: the bridge never writes to a historian. Credentials go in headers built from
the environment (see `config.py`) and are never logged or put in a URL.
"""

from __future__ import annotations

import base64
import json
import ssl
import urllib.error
import urllib.parse
import urllib.request

from foames_historian.model import HistorianError


def basic_auth(username: str, password: str) -> str:
	return "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()


class HttpClient:
	def __init__(
		self, base_url: str, *, headers=None, timeout: float = 30, verify=True, ca_file=None, opener=None
	):
		if not base_url:
			raise HistorianError("the historian URL is empty")
		self.base_url = base_url.rstrip("/")
		self.headers = {"Accept": "application/json", **(headers or {})}
		self.timeout = timeout
		self._context = None
		if base_url.startswith("https") and (ca_file or verify is False):
			self._context = ssl.create_default_context(cafile=ca_file)
			if verify is False:
				self._context.check_hostname = False
				self._context.verify_mode = ssl.CERT_NONE
		self._open = opener or self._urlopen

	def _urlopen(self, request, timeout):
		return urllib.request.urlopen(request, timeout=timeout, context=self._context)

	def url(self, path: str, params=None) -> str:
		if not path:
			url = self.base_url
		elif path.startswith(("http://", "https://")):
			url = path
		else:
			url = f"{self.base_url}/{path.lstrip('/')}"
		if params:
			query = urllib.parse.urlencode([(k, v) for k, v in params.items() if v is not None], doseq=True)
			url += ("&" if "?" in url else "?") + query
		return url

	def get_json(self, path: str, params=None):
		request = urllib.request.Request(self.url(path, params), method="GET", headers=self.headers)
		try:
			with self._open(request, timeout=self.timeout) as response:
				body = response.read()
		except urllib.error.HTTPError as e:
			raise HistorianError(f"{_safe(request.full_url)} answered {e.code}: {_reason(e)}") from e
		except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
			raise HistorianError(f"cannot reach {_safe(request.full_url)}: {e}") from e
		try:
			return json.loads(body or b"null")
		except ValueError as e:
			raise HistorianError(f"{_safe(request.full_url)} did not answer JSON") from e


def _safe(url: str) -> str:
	"""The URL without its query string, for messages (queries can hold tag names, never secrets,
	but keep messages short)."""
	return url.split("?", 1)[0]


def _reason(error) -> str:
	try:
		return error.read().decode("utf-8", errors="replace")[:300]
	except Exception:
		return str(error)
