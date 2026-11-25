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

"""AVEVA Manufacturing Execution System adapter.

AVEVA's MES, formerly Wonderware, for batch, hybrid and process industries.
The profile in `profile.py` says how FoaMES reaches it; the shared machinery is in
`foames.foames_adapters.mes`. Setup is in docs/mes-adapters.md (the framework) and
docs/vendors/aveva_mes/README.md (this system).
"""

ADAPTER_KEY = "AVEVA_MES"
