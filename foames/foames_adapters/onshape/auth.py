# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Onshape API-key request signatures.

Onshape's "request signature" scheme (the medium-security option for internal
use; OAuth2 is required for App Store distribution) signs each request with the
API key pair. The signed string is, in order and lowercased, the HTTP method,
the On-Nonce value, the Date header value, the Content-Type, the URL path
(without the query string) and the URL query string, each separated by a
newline; the HMAC-SHA256 digest uses the secret key and is sent Base64-encoded
in `Authorization: On <access key>:HmacSHA256:<signature>`.

This module imports nothing from Frappe.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from email.utils import formatdate
from urllib.parse import urlsplit

NONCE_LENGTH = 25
NONCE_ALPHABET = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"


def nonce() -> str:
	"""A fresh per-request nonce: at least 16 alphanumeric characters, unique each call."""
	return "".join(secrets.choice(NONCE_ALPHABET) for _ in range(NONCE_LENGTH))


def http_date(now: float | None = None) -> str:
	"""The RFC 7231 date header Onshape requires; accurate within five minutes of the request."""
	return formatdate(now if now is not None else time.time(), usegmt=True)


def signed_string(method: str, nonce_value: str, date: str, content_type: str, path: str, query: str) -> bytes:
	"""The exact byte string the HMAC covers: fields in order, lowercased, newline-separated."""
	parts = [method, nonce_value, date, content_type, path, query]
	return ("\n".join(parts) + "\n").lower().encode("utf-8")


def signature(secret_key: str, method: str, url: str, nonce_value: str, date: str, content_type: str) -> str:
	"""Base64 HMAC-SHA256 of the signed string, keyed with the API secret."""
	parts = urlsplit(url)
	message = signed_string(method, nonce_value, date, content_type, parts.path, parts.query)
	digest = hmac.new(secret_key.encode("utf-8"), message, hashlib.sha256).digest()
	return base64.b64encode(digest).decode("ascii")


def auth_headers(
	method: str,
	url: str,
	access_key: str,
	secret_key: str,
	*,
	nonce_value: str | None = None,
	date: str | None = None,
	content_type: str = "application/json",
) -> dict[str, str]:
	"""The headers for one signed request: Date, On-Nonce, Content-Type and Authorization."""
	nonce_value = nonce_value or nonce()
	date = date or http_date()
	return {
		"Date": date,
		"On-Nonce": nonce_value,
		"Content-Type": content_type,
		"Authorization": "On {0}:HmacSHA256:{1}".format(
			access_key, signature(secret_key, method, url, nonce_value, date, content_type)
		),
	}
