# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Built-in cases: named, allowlisted solver pipelines.

A case maps a manifest name onto a tutorial case directory inside the OpenFOAM
installation and an ordered command pipeline. Commands are fixed strings — the
manifest can only choose among registered cases and set numeric params that the
pipeline's templates substitute. This keeps `system/controlDict` and mesh
controls out of caller hands: no arbitrary commands, no path traversal.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Solvers allowed in this scaffold. Anything else needs a reviewed case entry.
ALLOWED_SOLVERS = ("simpleFoam", "icoFoam", "pisoFoam", "pimpleFoam", "laplacianFoam")


@dataclass(frozen=True)
class CaseSpec:
	"""One allowlisted case: where its files live and which pipeline it runs."""

	name: str
	tutorial: str  # path under $FOAM_TUTORIALS (or an absolute case dir in the worker)
	solver: str
	pipeline: tuple = field(default_factory=tuple)  # extra steps after checkMesh, before postProcess
	params: tuple = ()  # numeric params the manifest may set
	description: str = ""


BUILTIN_CASES = {
	"pitzdaily": CaseSpec(
		name="pitzdaily",
		tutorial="incompressible/simpleFoam/pitzDaily",
		solver="simpleFoam",
		pipeline=("postProcess",),
		params=("end_time", "write_interval"),
		description="The documented simpleFoam tutorial: blockMesh, checkMesh, solve, postProcess.",
	),
	"cavity": CaseSpec(
		name="cavity",
		tutorial="incompressible/icoFoam/cavity/cavity",
		solver="icoFoam",
		pipeline=(),
		params=("end_time",),
		description="The documented icoFoam lid-driven cavity tutorial.",
	),
}


def case_names() -> tuple:
	return tuple(sorted(BUILTIN_CASES))


def get_case(name: str) -> CaseSpec:
	from foames_openfoam.manifest import ManifestError

	try:
		return BUILTIN_CASES[name]
	except KeyError:
		raise ManifestError("unknown case {0!r}; known cases: {1}".format(name, ", ".join(case_names())))
