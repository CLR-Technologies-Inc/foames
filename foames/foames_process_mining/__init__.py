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

"""FoaMES Process Mining.

Turns what FoaMES and its ERP adapters record into event logs, and runs standard process-mining
analyses over them: directly-follows discovery, variant and performance analysis, and conformance
against a reference model. The analyses in `eventlog`, `xes`, `ocel`, `discovery` and `conformance`
have no Frappe dependency; `extractors`, `api` and the DocTypes bind them to a site.
"""
