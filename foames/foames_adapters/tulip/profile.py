# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The Tulip profile: what FoaMES assumes about the system, and where the rest comes from."""

from foames.foames_adapters.mes.profile import Profile
from foames.foames_adapters.mes.rest import AUTH_BASIC

PROFILE = Profile(
	key="TULIP",
	label="Tulip",
	vendor="Tulip Interfaces",
	product="Tulip frontline operations platform (composable MES)",
	docs_url="https://support.tulip.co/docs/api-overview",
	base_url_hint="https://<instance>.tulip.co",
	auth_methods=(AUTH_BASIC,),
	api_key_header="",
	token_url_hint="",
	site_label="",
	headers={},
	entities={},
	notes=(
		"Tulip is a no-code frontline operations platform and composable MES, used in regulated industries "
		"with electronic signatures. Its public API is documented on support.tulip.co: a bot (API token) is "
		"created in the instance's account settings and its key and secret are sent as Basic authentication. "
		"Tulip has no fixed order or material model: records live in Tulip Tables the site designs, read and "
		"written through the Tables API (api/v3/tables/<table id>/records, with a JSON filters parameter), "
		"and machines are Tulip machines with attributes. So every reference type is mapped by the site to the "
		"table that holds it, with the Query lookup and the table's own field ids as key and label; this "
		"profile ships no paths. Machine attributes can be reported to Tulip through the REST Request "
		"operation; a table record created through the API carries its own id, so a record write can be made "
		"a Client Reference posting on a field the table has for it."
	),
)
