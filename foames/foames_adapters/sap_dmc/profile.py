# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The SAP Digital Manufacturing profile: what FoaMES assumes about the system, and where the rest comes from."""

from foames.foames_adapters.mes.entities import BY_QUERY, EntitySpec
from foames.foames_adapters.mes.profile import Profile
from foames.foames_adapters.mes.rest import AUTH_OAUTH

PROFILE = Profile(
	key="SAP_DMC",
	label="SAP Digital Manufacturing",
	vendor="SAP",
	product="SAP Digital Manufacturing (DMC, formerly Digital Manufacturing Cloud for execution)",
	docs_url="https://api.sap.com/package/SAPDigitalManufacturingCloud/rest",
	base_url_hint="https://api.<region>.dmc.cloud.sap",
	auth_methods=(AUTH_OAUTH,),
	api_key_header="",
	token_url_hint="https://<subdomain>.authentication.<region>.hana.ondemand.com/oauth/token",
	site_label="Plant",
	headers={},
	entities={
		# Public APIs from the SAP Digital Manufacturing package on the SAP Business Accelerator Hub. Each
		# takes the plant as a query parameter; check the paths and parameter names against the package's
		# OpenAPI description for your release before use.
		"Item": EntitySpec(
			path="material/v1/materials",
			key_fields=("material",),
			lookup=BY_QUERY,
			label_field="description",
			extra_query={"plant": "{site}"},
		),
		"Work Order": EntitySpec(
			path="order/v1/orders",
			key_fields=("order",),
			lookup=BY_QUERY,
			label_field="material.description",
			extra_query={"plant": "{site}"},
		),
		"Workstation": EntitySpec(
			path="resource/v1/resources",
			key_fields=("resource",),
			lookup=BY_QUERY,
			label_field="description",
			extra_query={"plant": "{site}"},
		),
		"Location": EntitySpec(
			path="workcenter/v1/workcenters",
			key_fields=("workCenter",),
			lookup=BY_QUERY,
			label_field="description",
			extra_query={"plant": "{site}"},
		),
		# An SFC (shop floor control unit) is the piece or lot being made and the unit of execution a
		# machine works on, so it stands in for the Job Card.
		"Job Card": EntitySpec(
			path="sfc/v1/sfcdetail",
			key_fields=("sfc",),
			lookup=BY_QUERY,
			label_field="order",
			extra_query={"plant": "{site}"},
		),
	},
	notes=(
		"SAP Digital Manufacturing is SAP's cloud MES, usually chosen by plants that already run SAP S/4HANA "
		"or ECC and want execution, batch tracking and multi-site transparency inside the SAP landscape. Its "
		"public REST APIs are published as the SAP Digital Manufacturing package on the SAP Business Accelerator "
		"Hub (api.sap.com), with an OpenAPI description per API. A caller needs a service instance of the "
		"Digital Manufacturing APIs on SAP BTP: its client id and secret are exchanged for a bearer token at "
		"the subaccount's XSUAA token URL (OAuth 2.0 client credentials), and every call carries the plant as "
		"a query parameter, which this profile fills from the connection's site. The defaults ship the material, "
		"order, resource, work center and SFC reads; check them against the OpenAPI descriptions for your "
		"release, and map operations, routings, BOMs or shifts the same way. Writes such as an SFC start or "
		"complete, a quantity confirmation or a resource status go through the REST Request operation with the "
		"path from the API package; SAP's APIs do not take a client reference, so an unclear answer stops the "
		"posting for a person to check. Orders usually originate in S/4HANA; use the S/4HANA adapter for the "
		"order itself when both are connected and this one for execution data."
	),
)
