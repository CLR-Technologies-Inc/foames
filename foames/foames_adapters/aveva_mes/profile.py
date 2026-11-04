# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The AVEVA Manufacturing Execution System profile: what FoaMES assumes about the system, and where the rest comes from."""

from foames.foames_adapters.mes.profile import Profile
from foames.foames_adapters.mes.rest import AUTH_BASIC, AUTH_BEARER, AUTH_OAUTH

PROFILE = Profile(
	key="AVEVA_MES",
	label="AVEVA Manufacturing Execution System",
	vendor="AVEVA",
	product="AVEVA Manufacturing Execution System (formerly Wonderware MES)",
	docs_url="https://docs.aveva.com/",
	base_url_hint="https://mes.example.com",
	auth_methods=(AUTH_BASIC, AUTH_BEARER, AUTH_OAUTH),
	api_key_header="",
	token_url_hint="",
	site_label="",
	headers={},
	entities={},
	notes=(
		"AVEVA MES, formerly Wonderware MES, is widely used in batch, hybrid and process industries and sits "
		"on the AVEVA System Platform with its operator interfaces. Its operations, performance and quality "
		"functions are reached through the MES web services and the MES Web API documented on docs.aveva.com "
		"(an AVEVA Connect account is needed for parts of it); AVEVA Connect itself issues OAuth 2.0 tokens. "
		"Paths and fields are entered as Entity Mappings from that documentation; this profile ships none. "
		"Machine data stays FoaMES's own: AVEVA's utilization and OEE are computed in AVEVA, FoaMES's in "
		"FoaMES, and the two are reconciled through the references, not by copying numbers either way. "
		"Writes go through the REST Request operation."
	),
)
