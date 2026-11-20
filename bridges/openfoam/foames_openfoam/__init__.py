# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Isolated OpenFOAM CFD runner and provider for FoaMES."""

from foames_openfoam.cases import BUILTIN_CASES, CaseSpec, case_names, get_case
from foames_openfoam.lifecycle import RUN_STATES, Run, RunStore, idempotency_key, transition
from foames_openfoam.manifest import ManifestError, config_hash, validate_manifest
from foames_openfoam.runner import Cancelled, RunnerError, request_cancel, residual_summary, run_case
from foames_openfoam.service import Provider, serve

__version__ = "0.1.0"

__all__ = [
	"BUILTIN_CASES",
	"CaseSpec",
	"Cancelled",
	"ManifestError",
	"Provider",
	"RUN_STATES",
	"Run",
	"RunStore",
	"RunnerError",
	"case_names",
	"config_hash",
	"get_case",
	"idempotency_key",
	"request_cancel",
	"residual_summary",
	"run_case",
	"serve",
	"transition",
	"validate_manifest",
]
