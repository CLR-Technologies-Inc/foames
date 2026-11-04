# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The DELMIA Apriso profile: what FoaMES assumes about the system, and where the rest comes from."""

from foames.foames_adapters.mes.profile import Profile
from foames.foames_adapters.mes.rest import AUTH_BASIC, AUTH_BEARER, AUTH_OAUTH

PROFILE = Profile(
	key="APRISO",
	label="DELMIA Apriso",
	vendor="Dassault Systèmes",
	product="DELMIA Apriso (MOM, on the 3DEXPERIENCE platform)",
	docs_url="https://www.3ds.com/support/documentation/",
	base_url_hint="https://apriso.example.com",
	auth_methods=(AUTH_BASIC, AUTH_BEARER, AUTH_OAUTH),
	api_key_header="",
	token_url_hint="",
	site_label="",
	headers={},
	entities={},
	notes=(
		"DELMIA Apriso is Dassault Systèmes' global multi-plant MOM suite, strongest in aerospace and "
		"automotive and deeply integrated with ENOVIA PLM and the 3DEXPERIENCE platform. Apriso exposes its "
		"business processes as web services through the Business Integrator and Apriso Services: each site "
		"publishes the operations it needs (REST or SOAP), so there is no fixed public catalogue of paths and "
		"this profile ships none. Take the published operations from the installation's own service "
		"definitions and the Apriso documentation on the Dassault Systèmes support portal (login needed), and "
		"enter them as Entity Mappings; a service that answers a filtered GET with one object works with the "
		"Query lookup. Writes go through the REST Request operation; an Apriso operation that accepts a "
		"client-side reference can be made a Client Reference posting on the payload."
	),
)
