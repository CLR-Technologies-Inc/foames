# Copyright 2026 CLR Technologies Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""The Proficy Smart Factory MES (Velotic) profile: what FoaMES assumes about the system, and where the rest comes from."""

from foames.foames_adapters.mes.profile import Profile
from foames.foames_adapters.mes.rest import AUTH_BASIC, AUTH_OAUTH

PROFILE = Profile(
	key="PROFICY",
	label="Proficy Smart Factory MES (Velotic)",
	vendor="Velotic (formerly GE Vernova Proficy)",
	product="Proficy Smart Factory MES (Proficy Plant Applications) with Kepware",
	docs_url="https://www.ge.com/digital/documentation/",
	base_url_hint="https://plantapps.example.com",
	auth_methods=(AUTH_OAUTH, AUTH_BASIC),
	api_key_header="",
	token_url_hint="https://<host>/uaa/oauth/token",
	site_label="",
	headers={},
	entities={},
	notes=(
		"Proficy Smart Factory MES, built on Proficy Plant Applications, is a long-standing MES in process "
		"and hybrid industries. The Proficy software business, including Kepware, moved from GE Vernova to "
		"Velotic; its documentation lives on the Proficy documentation portal (the GE Digital documentation "
		"site at the time of writing, superseded by Velotic's). Plant Applications publishes REST APIs for its "
		"web client and integrations, with tokens from its UAA service (OAuth 2.0 client credentials at the "
		"UAA token URL). Take the production, product and equipment resources from that reference and enter "
		"them as Entity Mappings; this profile ships none. Kepware is a data source for FoaMES through OPC UA "
		"or MQTT rather than through this adapter. Writes go through the REST Request operation."
	),
)
