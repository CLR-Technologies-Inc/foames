# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The Critical Manufacturing MES profile: what FoaMES assumes about the system, and where the rest comes from."""

from foames.foames_adapters.mes.profile import Profile
from foames.foames_adapters.mes.rest import AUTH_BASIC, AUTH_BEARER

PROFILE = Profile(
	key="CMF_MES",
	label="Critical Manufacturing MES",
	vendor="Critical Manufacturing (an ASMPT company)",
	product="Critical Manufacturing MES",
	docs_url="https://help.criticalmanufacturing.com/",
	base_url_hint="https://mes.example.com/api",
	auth_methods=(AUTH_BEARER, AUTH_BASIC),
	api_key_header="",
	token_url_hint="",
	site_label="",
	headers={},
	entities={},
	notes=(
		"Critical Manufacturing MES, an ASMPT subsidiary, serves high-tech, complex discrete and "
		"semiconductor manufacturing with a highly configurable data model. Its REST API exposes the system's "
		"business objects and services (the Light Business Objects of its API) and is documented in the "
		"product's help portal, with a security service that issues the tokens the API wants as a bearer "
		"credential. Because the object model is configured per customer, the resources behind materials, "
		"resources, lots and steps differ between installations; take the service paths from the portal and "
		"your installation's own API documentation and enter them as Entity Mappings. Writes go through the "
		"REST Request operation."
	),
)
