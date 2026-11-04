# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The Aegis FactoryLogix profile: what FoaMES assumes about the system, and where the rest comes from."""

from foames.foames_adapters.mes.profile import Profile
from foames.foames_adapters.mes.rest import AUTH_BASIC, AUTH_BEARER, AUTH_OAUTH

PROFILE = Profile(
	key="FACTORYLOGIX",
	label="Aegis FactoryLogix",
	vendor="Aegis Software",
	product="FactoryLogix MES for electronics",
	docs_url="https://www.aiscorp.com/",
	base_url_hint="https://factorylogix.example.com",
	auth_methods=(AUTH_BASIC, AUTH_BEARER, AUTH_OAUTH),
	api_key_header="",
	token_url_hint="",
	site_label="",
	headers={},
	entities={},
	notes=(
		"Aegis FactoryLogix is an MES built for electronics manufacturing: PCB assembly, box build and the "
		"traceability those need. Its integration surface (the FactoryLogix xTend API and its web services) is "
		"documented for customers on Aegis's portal rather than publicly, so this profile ships no paths; take "
		"them from your installation's API documentation and enter them as Entity Mappings. Machine data on an "
		"SMT line usually reaches FactoryLogix through its own equipment connectors (IPC-CFX); FoaMES reads "
		"the same machines through its gateways and uses this adapter for the work orders, assemblies and "
		"stations FactoryLogix owns. Writes go through the REST Request operation."
	),
)
