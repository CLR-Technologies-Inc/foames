# Copyright (c) 2026, CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Build the CycloneDX 1.7 SBOM for FoaMES.

FoaMES is a Frappe app, so `pip` alone cannot describe it: Frappe is installed by bench rather than
declared in pyproject.toml, the MQTT and OPC UA gateways import optional packages, ERPNext is an
optional sibling app, and the cryptography and connected services live in the code rather than in
any package metadata. This script takes the environment inventory that `cyclonedx-py environment`
produced and turns it into an SBOM of FoaMES itself:

- the FoaMES app becomes `metadata.component`, with license, supplier, version and commit;
- the dependency graph is rooted at FoaMES, and each component's scope says whether it is needed
  (`required`), only by an optional feature (`optional`), or only by the build tooling
  (`excluded`);
- the cryptographic assets, the connected services and ERPNext come from `sbom/curated.json`;
- 1.7 `citations` record which tool or which people asserted each part, and
  `metadata.distributionConstraints` marks the document TLP:CLEAR, since FoaMES is public.

It uses only the standard library, so it runs anywhere. `--validate` checks the result against the
official CycloneDX 1.7 JSON schema and needs `cyclonedx-python-lib[json-validation]`.

    python sbom/build_sbom.py --env-bom env.cdx.json --frappe-line v15 --out foames.cdx.json --validate
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import os
import re
import subprocess
import sys
import uuid
from collections import deque
from pathlib import Path

SPEC_VERSION = "1.7"
SCHEMA_URL = "http://cyclonedx.org/schema/bom-1.7.schema.json"
REPO_URL = "https://github.com/CLR-Technologies-Inc/foames"
ROOT_REF = "foames"
SUPPLIER_REF = "org:clr-technologies"
TOOL_REF = "tool:foames-sbom-builder"
SUPPLIER = {
	"name": "CLR Technologies Inc.",
	"url": ["https://github.com/CLR-Technologies-Inc"],
}

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent


def normalise_name(name: str) -> str:
	"""PEP 503 name normalisation, so `Paho_MQTT` and `paho-mqtt` match."""
	return re.sub(r"[-_.]+", "-", (name or "").strip()).lower()


def read_app_version(repo_root: Path = REPO_ROOT) -> str:
	text = (repo_root / "foames" / "__init__.py").read_text(encoding="utf-8")
	match = re.search(r"""__version__\s*=\s*["']([^"']+)["']""", text)
	if not match:
		raise SystemExit("foames/__init__.py has no __version__")
	return match.group(1)


def git_commit(repo_root: Path = REPO_ROOT) -> str | None:
	sha = os.environ.get("GITHUB_SHA")
	if sha:
		return sha
	try:
		return subprocess.run(
			["git", "-C", str(repo_root), "rev-parse", "HEAD"],
			capture_output=True,
			text=True,
			check=True,
		).stdout.strip()
	except (OSError, subprocess.CalledProcessError):
		return None


def build_timestamp() -> str:
	"""SOURCE_DATE_EPOCH when set (reproducible builds), otherwise now, in UTC."""
	epoch = os.environ.get("SOURCE_DATE_EPOCH")
	moment = (
		dt.datetime.fromtimestamp(int(epoch), tz=dt.timezone.utc)
		if epoch
		else dt.datetime.now(dt.timezone.utc)
	)
	return moment.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict:
	with open(path, encoding="utf-8") as handle:
		return json.load(handle)


def compute_scopes(
	graph: dict[str, list[str]], required_roots: list[str], optional_roots: list[str], refs: list[str]
) -> dict[str, str]:
	"""Scope of every ref: reachable from a required root is `required`, else reachable from an
	optional root is `optional`, else `excluded` (installed in the scan environment only)."""

	def reach(roots: list[str]) -> set[str]:
		seen: set[str] = set()
		queue = deque(r for r in roots if r)
		while queue:
			ref = queue.popleft()
			if ref in seen:
				continue
			seen.add(ref)
			queue.extend(graph.get(ref, []))
		return seen

	required = reach(required_roots)
	optional = reach(optional_roots) - required
	return {
		ref: "required" if ref in required else "optional" if ref in optional else "excluded" for ref in refs
	}


def collect_tools(env_bom: dict, app_version: str) -> tuple[list[dict], str | None]:
	"""Our own tool entry plus the scanner's, each with a bom-ref. Returns (tools, scanner_ref)."""
	tools = [
		{
			"type": "application",
			"bom-ref": TOOL_REF,
			"name": "foames-sbom-builder",
			"version": app_version,
			"supplier": copy.deepcopy(SUPPLIER),
			"externalReferences": [{"type": "vcs", "url": f"{REPO_URL}/blob/main/sbom/build_sbom.py"}],
		}
	]
	scanner_ref = None
	env_tools = (env_bom.get("metadata") or {}).get("tools") or {}
	if isinstance(env_tools, list):  # the pre-1.5 shape
		env_tools = {"components": env_tools}
	for tool in env_tools.get("components") or []:
		tool = copy.deepcopy(tool)
		tool.setdefault("type", "application")
		tool.setdefault("bom-ref", f"tool:{normalise_name(tool.get('name', 'scanner'))}")
		tools.append(tool)
		if scanner_ref is None or tool.get("name") == "cyclonedx-py":
			scanner_ref = tool["bom-ref"]
	return tools, scanner_ref


def build_bom(
	env_bom: dict,
	curated: dict,
	*,
	app_version: str,
	commit: str | None,
	frappe_line: str | None,
	timestamp: str,
) -> dict:
	env_components = [copy.deepcopy(c) for c in env_bom.get("components") or []]
	# FoaMES itself is the subject, not one of its components.
	env_components = [c for c in env_components if normalise_name(c.get("name")) != ROOT_REF]
	by_name = {normalise_name(c.get("name")): c for c in env_components}

	graph = {
		d["ref"]: list(d.get("dependsOn") or []) for d in env_bom.get("dependencies") or [] if "ref" in d
	}
	known_refs = {c["bom-ref"] for c in env_components if "bom-ref" in c}

	frappe = by_name.get("frappe")
	if frappe is None:
		# Scanned without Frappe installed: still record that FoaMES needs it.
		frappe = {
			"bom-ref": "pkg:pypi/frappe",
			"type": "framework",
			"name": "frappe",
			"purl": "pkg:pypi/frappe",
			"description": "Installed and managed by bench; not resolved in this scan.",
		}
		env_components.append(frappe)
		known_refs.add(frappe["bom-ref"])
	else:
		frappe["type"] = "framework"

	optional_refs = []
	for name in curated.get("optional") or []:
		component = by_name.get(normalise_name(name))
		if component is not None:
			optional_refs.append(component["bom-ref"])

	curated_components = [copy.deepcopy(c) for c in curated.get("components") or []]
	crypto = [copy.deepcopy(c) for c in curated.get("cryptographic_assets") or []]
	services = [copy.deepcopy(s) for s in curated.get("services") or []]

	all_component_refs = [c["bom-ref"] for c in env_components if "bom-ref" in c]
	scopes = compute_scopes(graph, [frappe["bom-ref"]], optional_refs, all_component_refs)
	for component in env_components:
		if "bom-ref" in component:
			component["scope"] = scopes[component["bom-ref"]]

	root_properties = []
	if commit:
		root_properties.append({"name": "foames:git:commit", "value": commit})
	if frappe_line:
		root_properties.append({"name": "foames:frappe:line", "value": frappe_line})

	root = {
		"type": "application",
		"bom-ref": ROOT_REF,
		"supplier": copy.deepcopy(SUPPLIER),
		"authors": [{"name": "CLR Technologies Inc. and contributors"}],
		"name": "foames",
		"version": app_version,
		"description": "FoaMES: process-engineered, ERP-agnostic MES on the Frappe framework",
		"licenses": [{"license": {"id": "Apache-2.0", "acknowledgement": "declared"}}],
		"copyright": "Copyright 2026 CLR Technologies Inc.",
		"purl": f"pkg:github/clr-technologies-inc/foames@{commit or app_version}",
		"externalReferences": [
			{"type": "vcs", "url": REPO_URL},
			{"type": "license", "url": f"{REPO_URL}/blob/main/LICENSE"},
			{"type": "documentation", "url": f"{REPO_URL}/tree/main/docs"},
			{"type": "issue-tracker", "url": f"{REPO_URL}/issues"},
		],
	}
	if root_properties:
		root["properties"] = root_properties

	root_depends = [frappe["bom-ref"], *optional_refs]
	root_depends += [c["bom-ref"] for c in curated_components]
	root_depends += [c["bom-ref"] for c in crypto]
	root_depends += [s["bom-ref"] for s in services]

	dependencies = [{"ref": ROOT_REF, "dependsOn": sorted(set(root_depends))}]
	for ref in sorted(known_refs):
		dependencies.append(
			{"ref": ref, "dependsOn": sorted({d for d in graph.get(ref, []) if d in known_refs})}
		)
	for ref in [c["bom-ref"] for c in curated_components] + [c["bom-ref"] for c in crypto]:
		dependencies.append({"ref": ref})
	for dependency in dependencies:
		if not dependency.get("dependsOn"):
			dependency.pop("dependsOn", None)

	tools, scanner_ref = collect_tools(env_bom, app_version)

	citations = [
		{
			"bom-ref": "citation:subject",
			"pointers": ["/metadata/component"],
			"attributedTo": TOOL_REF,
			"timestamp": timestamp,
			"note": "Built from pyproject.toml, foames/__init__.py and the git commit.",
		},
		{
			"bom-ref": "citation:scopes",
			"expressions": ["$.components[?@.scope]"],
			"attributedTo": TOOL_REF,
			"timestamp": timestamp,
			"note": "Scope derived from reachability in the dependency graph rooted at FoaMES.",
		},
		{
			"bom-ref": "citation:curated",
			"expressions": ["$.components[?@.type == 'cryptographic-asset' || @.type == 'application']"],
			"attributedTo": SUPPLIER_REF,
			"timestamp": timestamp,
			"note": "Curated by the FoaMES maintainers from a review of the source; see sbom/curated.json.",
		},
		{
			"bom-ref": "citation:services",
			"pointers": ["/services"],
			"attributedTo": SUPPLIER_REF,
			"timestamp": timestamp,
			"note": "Connected services, curated by the FoaMES maintainers; see sbom/curated.json.",
		},
	]
	if scanner_ref:
		citations.insert(
			1,
			{
				"bom-ref": "citation:inventory",
				"expressions": ["$.components[?@.type == 'library' || @.type == 'framework']"],
				"attributedTo": scanner_ref,
				"timestamp": timestamp,
				"note": "Python packages, versions, licenses and the dependency graph, as installed in the scan environment.",
			},
		)

	seed = f"{REPO_URL}@{commit or app_version}#{frappe_line or ''}"
	return {
		"$schema": SCHEMA_URL,
		"bomFormat": "CycloneDX",
		"specVersion": SPEC_VERSION,
		"serialNumber": f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, seed)}",
		"version": 1,
		"metadata": {
			"timestamp": timestamp,
			"lifecycles": [{"phase": "build"}],
			"tools": {"components": tools},
			"supplier": {"bom-ref": SUPPLIER_REF, **copy.deepcopy(SUPPLIER)},
			"component": root,
			"distributionConstraints": {"tlp": "CLEAR"},
		},
		"components": sorted(env_components, key=lambda c: normalise_name(c.get("name")))
		+ curated_components
		+ crypto,
		"services": services,
		"dependencies": dependencies,
		"citations": citations,
	}


def validate(bom: dict) -> None:
	try:
		from cyclonedx.schema import SchemaVersion
		from cyclonedx.validation.json import JsonStrictValidator
	except ImportError as error:
		raise SystemExit(f"--validate needs cyclonedx-python-lib[json-validation]: {error}")
	errors = JsonStrictValidator(SchemaVersion.V1_7).validate_str(json.dumps(bom))
	if errors:
		raise SystemExit(f"The SBOM does not validate against CycloneDX {SPEC_VERSION}: {errors!r}")


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
	parser.add_argument("--env-bom", type=Path, help="output of `cyclonedx-py environment` (JSON)")
	parser.add_argument("--curated", type=Path, default=HERE / "curated.json")
	parser.add_argument("--frappe-line", help="the Frappe line scanned, e.g. v15 or v16")
	parser.add_argument("--out", type=Path, required=True)
	parser.add_argument("--validate", action="store_true", help="validate against the 1.7 schema")
	args = parser.parse_args(argv)

	env_bom = load_json(args.env_bom) if args.env_bom else {}
	bom = build_bom(
		env_bom,
		load_json(args.curated),
		app_version=read_app_version(),
		commit=git_commit(),
		frappe_line=args.frappe_line,
		timestamp=build_timestamp(),
	)
	if args.validate:
		validate(bom)
	args.out.parent.mkdir(parents=True, exist_ok=True)
	args.out.write_text(json.dumps(bom, indent=2) + "\n", encoding="utf-8")
	print(f"wrote {args.out} ({len(bom['components'])} components, {len(bom['services'])} services)")
	return 0


if __name__ == "__main__":
	sys.exit(main())
