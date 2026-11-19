# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Onshape CAD/PDM connector.

Onshape is a CAD and data-management source, not an ERP: this package does not
implement `foames.foames_adapters.base.ERPAdapter` and is not registered in the
`foames_erp_adapters` hook. It reads document, part-studio, part, assembly and
drawing metadata over Onshape's REST API and records revision-aware CAD
references in the `Onshape CAD Reference` DocType. Setup is in
docs/vendors/onshape/README.md.

Modules that import nothing from Frappe: `auth.py` (request signatures),
`model.py` (CAD reference values, URLs and pinned/unreleased state), `client.py`
(the REST client and its error classes) and `fake.py` (the scripted stand-in the
tests use). The Frappe side is `api.py` and the two DocTypes under
`foames/foames_adapters/doctype/onshape_*`.
"""
