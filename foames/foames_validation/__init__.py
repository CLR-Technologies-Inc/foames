# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""FoaMES Validation: equipment qualification and process validation.

Protocols (IQ, OQ, PQ, PPQ, CPV) carry acceptance criteria; executions record what was observed,
with evidence, and are approved by someone other than the person who executed them. Criteria on
machine measurements are judged from Measurement events with the SPC arithmetic in
`foames.foames_mes.spc`. `qualification` holds the rules and has no Frappe dependency; the DocTypes,
`api` and `tasks` bind them to a site.
"""
