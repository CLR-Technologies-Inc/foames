# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""FoaMES Life Sciences: new product introduction and manufacturing science and technology (MSAT).

For biopharma and medical device plants: an NPI program run through stage gates with deliverables
and gate decisions, a product requirements document with its trace matrix, a tech transfer package
(critical process parameters with normal and proven acceptable ranges, critical quality attributes,
sending and receiving site) with a statistical comparability assessment, and process development
(PD) simulation: designed experiments, response-surface models, Monte Carlo what-if, design-space
maps and scale-up correlations.

The rules and the arithmetic are pure and import nothing from Frappe: `npi`, `requirements`,
`transfer`, `stats`, `doe` and `scaleup`. The DocTypes, `api` and `tasks` bind them to a site.
Everything here supports a person's decision; nothing advances a gate, approves a package or
changes a process on its own. The guide is docs/life-sciences.md.
"""
