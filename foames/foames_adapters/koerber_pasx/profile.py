# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The Körber Werum PAS-X MES profile: what FoaMES assumes about the system, and where the rest comes from."""

from foames.foames_adapters.mes.profile import Profile
from foames.foames_adapters.mes.rest import AUTH_BASIC, AUTH_BEARER

PROFILE = Profile(
	key="PASX",
	label="Körber Werum PAS-X MES",
	vendor="Körber (Werum IT Solutions)",
	product="Werum PAS-X MES for pharma and biotech",
	docs_url="https://www.koerber-pharma.com/en/solutions/software",
	base_url_hint="https://pasx.example.com",
	auth_methods=(AUTH_BASIC, AUTH_BEARER),
	api_key_header="",
	token_url_hint="",
	site_label="",
	headers={},
	entities={},
	notes=(
		"Werum PAS-X, from Körber, is the dominant on-premise MES for pharmaceutical and biotech production "
		"and runs in validated GxP environments. Its interfaces (PAS-X Connect and the integration services "
		"for ERP, automation and equipment) are documented for customers and implemented per site under "
		"change control, so this profile ships no paths. Treat the adapter as read-first: resolve batches, "
		"materials and equipment from PAS-X so FoaMES's machine data can be seen next to the batch record. "
		"Any write into PAS-X touches an electronic batch record and belongs in the site's validation scope; "
		"if one is needed, it goes through the REST Request operation and a Client Reference the PAS-X "
		"service keeps, and it is configured, tested and documented as part of the validated system."
	),
)
