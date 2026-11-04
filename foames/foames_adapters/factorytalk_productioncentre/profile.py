# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""The Rockwell FactoryTalk ProductionCentre profile: what FoaMES assumes about the system, and where the rest comes from."""

from foames.foames_adapters.mes.profile import Profile
from foames.foames_adapters.mes.rest import AUTH_BASIC, AUTH_BEARER, AUTH_OAUTH

PROFILE = Profile(
	key="FTPC",
	label="Rockwell FactoryTalk ProductionCentre",
	vendor="Rockwell Automation",
	product="FactoryTalk ProductionCentre and FactoryTalk PharmaSuite",
	docs_url="https://www.rockwellautomation.com/en-us/support/documentation/literature-library.html",
	base_url_hint="https://ftpc.example.com",
	auth_methods=(AUTH_BASIC, AUTH_BEARER, AUTH_OAUTH),
	api_key_header="",
	token_url_hint="",
	site_label="",
	headers={},
	entities={},
	notes=(
		"FactoryTalk ProductionCentre (and PharmaSuite, its life-sciences edition) is Rockwell's on-premise "
		"enterprise MES, closely tied to Allen-Bradley and ControlLogix automation through FactoryTalk Linx. "
		"FoaMES does not go through it to reach the controllers: machine data comes in over OPC UA, MQTT or the "
		"webhook as on any other plant. The adapter is for the records ProductionCentre owns, orders, "
		"materials, equipment and batches. ProductionCentre publishes them through its web services and "
		"integration framework, which a site configures; the REST endpoints, their paths and their fields are "
		"therefore site-specific and are entered as Entity Mappings from the installation's own service "
		"documentation (Rockwell's Literature Library holds the product manuals). Writes (a batch step "
		"confirmation, an equipment status) go through the REST Request operation; whether a service is "
		"idempotent is for the site to declare on the payload."
	),
)
