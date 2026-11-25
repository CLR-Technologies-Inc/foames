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

"""The Rockwell Plex Smart Manufacturing Platform profile: what FoaMES assumes about the system, and where the rest comes from."""

from foames.foames_adapters.mes.profile import Profile
from foames.foames_adapters.mes.rest import AUTH_API_KEY, AUTH_BASIC

PROFILE = Profile(
	key="PLEX",
	label="Rockwell Plex Smart Manufacturing Platform",
	vendor="Rockwell Automation",
	product="Plex Smart Manufacturing Platform (cloud MES and ERP)",
	docs_url="https://developers.plex.com/",
	base_url_hint="https://connect.plex.com",
	auth_methods=(AUTH_API_KEY, AUTH_BASIC),
	api_key_header="X-Plex-Connect-Api-Key",
	token_url_hint="",
	site_label="Plex Customer ID (PCN)",
	headers={"X-Plex-Connect-Customer-Id": "{site}"},
	entities={},
	notes=(
		"Plex is Rockwell Automation's cloud-native SaaS platform for mid-to-large discrete manufacturers, "
		"and the one system in this family that is also the plant's ERP. Its public REST APIs are published on "
		"the Plex Developer Portal (developers.plex.com), reached through the Plex Connect gateway with an API "
		"key in the X-Plex-Connect-Api-Key header and the customer (PCN) in X-Plex-Connect-Customer-Id, which "
		"this profile fills from the connection's site. The portal groups the APIs by area (master data such as "
		"parts and units, production, scheduling and jobs, inventory, quality, engineering); open the area you "
		"need, copy the resource path and its query parameter into an Entity Mapping with the Query lookup. "
		"Older integrations use Plex Data Sources (a stored-procedure style call, Basic authentication); those "
		"can be reached with the REST Request operation. FoaMES holds no Plex paths of its own."
	),
)
