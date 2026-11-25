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

"""FoaMES Validation: equipment qualification and process validation.

Protocols (IQ, OQ, PQ, PPQ, CPV) carry acceptance criteria; executions record what was observed,
with evidence, and are approved by someone other than the person who executed them. Criteria on
machine measurements are judged from Measurement events with the SPC arithmetic in
`foames.foames_mes.spc`. `qualification` holds the rules and has no Frappe dependency; the DocTypes,
`api` and `tasks` bind them to a site.
"""
