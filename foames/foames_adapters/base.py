# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The contract every ERP adapter implements.

The FoaMES core never links to ERP records directly. It stores an External Reference holding an
ERP system key, a kernel reference type and the record's identifier in that ERP. An adapter turns
that triple into a resolved record, so the same core can run against ERPNext, SAP S/4HANA or no
ERP at all.
"""

from dataclasses import dataclass, field

# Reference types the kernel understands. Adapters map each one to their own record type.
REFERENCE_TYPES = (
	"Item",
	"Unit of Measure",
	"Batch",
	"Serial Number",
	"Work Order",
	"Operation",
	"Location",
	"Stock Movement",
	"Job Card",
	"Bill of Materials",
	"Routing",
	"Workstation",
)


@dataclass
class ResolvedReference:
	"""What an adapter returns for a record it found."""

	reference_type: str
	external_id: str
	label: str
	data: dict = field(default_factory=dict)


class ERPAdapter:
	"""Base class for ERP adapters.

	Subclasses set `key` (stored on External Reference), `label` (shown to users) and
	`reference_map` (kernel reference type -> the ERP's own record type), and implement
	`is_available` and `fetch`.
	"""

	key: str = ""
	label: str = ""
	reference_map: dict[str, str] = {}  # noqa: RUF012

	def is_available(self) -> bool:
		"""Whether this ERP can be reached from the current site."""
		raise NotImplementedError

	def supports(self, reference_type: str) -> bool:
		return reference_type in self.reference_map

	def resolve(self, reference_type: str, external_id: str) -> ResolvedReference | None:
		"""Return the resolved record, or None when it does not exist in the ERP."""
		if not self.supports(reference_type):
			raise UnsupportedReferenceType(f"{self.label} does not support reference type {reference_type}")
		if not self.is_available():
			raise AdapterUnavailable(f"{self.label} is not available on this site")
		return self.fetch(self.reference_map[reference_type], reference_type, external_id)

	def fetch(self, erp_type: str, reference_type: str, external_id: str) -> ResolvedReference | None:
		raise NotImplementedError


class AdapterError(Exception):
	pass


class AdapterUnavailable(AdapterError):
	pass


class UnsupportedReferenceType(AdapterError):
	pass
