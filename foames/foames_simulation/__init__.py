# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Optional CFD simulation runs through an isolated OpenFOAM provider.

OpenFOAM is a solver, not a system of record: this module is not an ERP
adapter and registers nothing in `foames_erp_adapters`. It submits case
manifests to a separately deployed `foames-openfoam` provider
(`bridges/openfoam`), tracks runs in the `Simulation Run` DocType and exposes
the results as *candidate* validation evidence — a converged solve is never
automatic approval. The solver can never command plant equipment, SCADA or an
ERP.

Pure modules (no Frappe imports): `simulation.py` (lifecycle mirror and helpers)
and `client.py` (the provider HTTP client with an injectable transport).
"""
