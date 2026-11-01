# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The S/4HANA adapter registered through the `foames_erp_adapters` hook.

A Job Card has no single S/4HANA record, so unless a site maps it in S4HANA Settings it resolves
as an order operation: `ORDER|OPERATION` (or `ORDER|SEQUENCE|OPERATION` outside the standard
sequence), read from the order's operations. That is what a machine's
current job names when its counts roll up to S/4HANA confirmations (see `rollup.py`).
"""

from foames.foames_adapters.base import AdapterError, AdapterUnavailable, ERPAdapter, ResolvedReference
from foames.foames_adapters.s4hana.odata import ODataError

ADAPTER_KEY = "S4HANA"
JOB_CARD = "Job Card"


class S4HANAAdapter(ERPAdapter):
	key = ADAPTER_KEY
	label = "SAP S/4HANA"

	def __init__(self, settings=None, transport=None):
		# Both are for tests; on a site the settings are read from S4HANA Settings.
		self._settings = settings
		self._transport = transport

	@property
	def settings(self):
		if self._settings is not None:
			return self._settings
		from foames.foames_adapters.doctype.s4hana_settings.s4hana_settings import get_settings

		return get_settings()

	@property
	def reference_map(self) -> dict[str, str]:
		mapped = {
			reference_type: spec.entity_set for reference_type, spec in self.settings.entity_specs().items()
		}
		mapped.setdefault(JOB_CARD, "Order Operation")
		return mapped

	def is_available(self) -> bool:
		settings = self.settings
		return bool(settings.enabled and settings.base_url)

	def fetch(self, erp_type: str, reference_type: str, external_id: str) -> ResolvedReference | None:
		settings = self.settings
		specs = settings.entity_specs()
		if reference_type == JOB_CARD and JOB_CARD not in specs:
			return self.fetch_operation(external_id)
		spec = specs[reference_type]
		try:
			keys = spec.keys_for(external_id)
		except ValueError:
			# An ID that cannot be a key of this entity cannot exist in S/4HANA.
			return None
		try:
			entity = settings.client(self._transport).get_entity(
				spec.service, spec.entity_set, keys, spec.query()
			)
		except ODataError as e:
			raise self.adapter_error(e)
		if not entity:
			return None
		return ResolvedReference(
			reference_type=reference_type,
			external_id=spec.external_id_for(entity) or external_id,
			label=spec.label_for(entity, settings.language or "EN"),
			data={"service": spec.service, "entity_set": spec.entity_set, "keys": keys},
		)

	def fetch_operation(self, external_id: str) -> ResolvedReference | None:
		"""An order operation (`ORDER|OPERATION`) as a Job Card, with what a roll-up needs to know."""
		from foames.foames_adapters.s4hana import orders
		from foames.foames_adapters.s4hana.production import job_id, normal_sequence, parse_job

		try:
			order, operation, sequence = parse_job(external_id)
		except ValueError:
			return None
		settings = self.settings
		try:
			found = orders.production_order(
				settings.client(self._transport),
				order,
				process_order=bool(getattr(settings, "confirm_process_orders", 0)),
			)
		except ODataError as e:
			raise self.adapter_error(e)
		if not found:
			return None
		step = next(
			(
				op
				for op in found["operations"]
				if same_operation(op["operation"], operation)
				and normal_sequence(op["sequence"]) == sequence
				and not op["suboperation"]
			),
			None,
		)
		if not step:
			return None
		text = step["text"] or step["work_center"] or found["material"]
		return ResolvedReference(
			reference_type=JOB_CARD,
			external_id=job_id(found["order"] or order, step["operation"], step["sequence"]),
			label=f"{found['order'] or order} {step['operation']}: {text}",
			data={
				"order": found["order"] or order,
				"operation": step["operation"],
				"sequence": sequence,
				"work_center": step["work_center"],
				"plant": step["plant"] or found["plant"],
				"unit": step["unit"] or found["unit"],
				"quantity": str(step["quantity"]),
				"confirmed_yield": str(step["confirmed_yield"]),
			},
		)

	def adapter_error(self, error: ODataError) -> AdapterError:
		if error.transient or error.status in (401, 403):
			return AdapterUnavailable(f"{self.label}: {error}")
		return AdapterError(f"{self.label}: {error}")


def same_operation(a, b) -> bool:
	"""Operation numbers compare without their leading zeros: `10` and `0010` are one operation."""
	return (str(a or "").lstrip("0") or "0") == (str(b or "").lstrip("0") or "0")
