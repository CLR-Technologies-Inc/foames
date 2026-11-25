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

"""Optional collectors for the FoaMES topology graph. Standard library only.

* network: hosts on a Tailscale tailnet (from `tailscale status --json`), as Host assets on the
  physical layer, each joined to the tailnet by a Network link;
* agents: AI agent activity from a JSON Lines event log, as Agent and Agent Task assets on the
  data layer, with Delegates links for who handed what to whom and Runs On links to hosts.

Each builds a collector report and posts it to foames.foames_topology.api.ingest, which stamps it
with the collector's provider name, keeps it to the tenants the API user may write, and refuses
anything another provider owns. Both are read-only towards what they observe.
"""

__version__ = "0.1.0"
