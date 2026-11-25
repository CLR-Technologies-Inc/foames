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

"""FoaMES Life Sciences: new product introduction (NPI) and manufacturing science and technology
(MSAT).

For biopharma and medical device plants: an NPI program run through stage gates with deliverables
and entry and exit criteria, governed by the Phase Review Discipline (PRD: a phase review board
whose Chair decides each gate in a formal phase review, up to launch readiness), a product requirements document with its trace matrix, a tech transfer package
(critical process parameters with normal and proven acceptable ranges, critical quality attributes,
sending and receiving site) with a statistical comparability assessment, and process development
(PD) simulation: designed experiments, response-surface models, Monte Carlo what-if, design-space
maps and scale-up correlations.

The rules and the arithmetic are pure and import nothing from Frappe: `npi`, `phase_review`, `requirements`,
`transfer`, `stats`, `doe` and `scaleup`. The DocTypes, `api` and `tasks` bind them to a site.
Everything here supports a person's decision; nothing advances a gate, approves a package or
changes a process on its own. The guide is docs/life-sciences.md.
"""
