# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""What one MES adapter declares about its system: the profile.

A profile is plain data, so a vendor folder is small and a reader can see at a glance what FoaMES
assumes about the system. Every value that names a path or a field is either documented in the
vendor's public API reference, in which case the profile says where, or absent, in which case the
site maps it in MES Connection. Profiles never guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from foames.foames_adapters.mes.entities import EntitySpec
from foames.foames_adapters.mes.rest import AUTH_METHODS

# How an outbox operation is kept from being performed twice.
UPSERT = "Upsert"  # the system keys the record on something in the payload; sending again overwrites
CLIENT_REFERENCE = (
	"Client Reference"  # the payload carries a reference the system keeps and can be searched by
)
MANUAL = "Manual"  # neither: an unclear answer stops the posting for a person to check
IDEMPOTENCY_KINDS = (UPSERT, CLIENT_REFERENCE, MANUAL)

GENERIC_REQUEST = "REST Request"


@dataclass
class Operation:
	"""One kind of write to the system."""

	label: str
	method: str = "POST"
	path: str = ""  # relative to the base URL; empty for the generic request, whose payload names it
	required: tuple[str, ...] = ()  # payload fields the operation cannot do without
	idempotency: str = MANUAL
	# Client Reference: the payload field the marker is written into, and how to find a record by it.
	reference_field: str = ""
	lookup_path: str = ""
	lookup_query: str = ""  # the query parameter the marker is sent as; empty means filter client-side
	# Dotted path into the answer that identifies the created record.
	document_path: str = "id"
	# Fields of the payload that, together with the marker, narrow the search for an earlier posting.
	lookup_fields: tuple[str, ...] = ()


# The one operation every profile has: a request whose method, path and body the caller gives.
# The payload may also name `reference_field`, `lookup_path` and `lookup_query` to make it a
# Client Reference posting; otherwise an unclear answer stops it for a person to check.
GENERIC_OPERATION = Operation(label=GENERIC_REQUEST, required=("method", "path"), idempotency=MANUAL)


@dataclass
class Profile:
	key: str  # stored on External Reference and MES Connection
	label: str  # shown to users
	vendor: str
	product: str
	docs_url: str  # where the public API documentation lives
	base_url_hint: str  # what Base URL looks like, for the form
	auth_methods: tuple[str, ...]  # the styles the system supports, first is the default
	api_key_header: str = ""  # for API Key Header: the header the key is sent in
	token_url_hint: str = ""  # for OAuth 2.0: what the token URL looks like
	site_label: str = ""  # what {site} means for this system (plant, tenant, customer), empty if unused
	headers: dict = field(default_factory=dict)  # headers every call carries; values may carry {site}
	# Entity lookups documented well enough to ship. Everything else is mapped by the site.
	entities: dict[str, EntitySpec] = field(default_factory=dict)
	operations: dict[str, Operation] = field(default_factory=dict)
	# What a person should know before connecting: integration style, licensing, where the paths are.
	notes: str = ""

	def __post_init__(self):
		if not self.key or not self.label or not self.docs_url:
			raise ValueError("A profile needs a key, a label and a documentation URL")
		for method in self.auth_methods:
			if method not in AUTH_METHODS:
				raise ValueError(f"{self.key}: unknown authentication method {method!r}")
		if not self.auth_methods:
			raise ValueError(f"{self.key}: at least one authentication method")
		self.operations = {GENERIC_REQUEST: GENERIC_OPERATION, **self.operations}
		for name, operation in self.operations.items():
			if name != operation.label:
				raise ValueError(f"{self.key}: operation {name!r} is labelled {operation.label!r}")
			if operation.idempotency not in IDEMPOTENCY_KINDS:
				raise ValueError(f"{self.key}: {name} has idempotency {operation.idempotency!r}")
			if operation.idempotency == CLIENT_REFERENCE and not (
				operation.reference_field and operation.lookup_path
			):
				raise ValueError(f"{self.key}: {name} needs a reference field and a lookup path")

	@property
	def default_auth(self) -> str:
		return self.auth_methods[0]

	def operation(self, name: str) -> Operation:
		if name in self.operations:
			return self.operations[name]
		raise KeyError(name)

	def operation_names(self) -> list[str]:
		return list(self.operations)
