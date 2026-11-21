# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""The manufacturing-data validation track: public datasets replayed through FoaMES's pure code.

The agent benchmark asks whether an agent can change FoaMES correctly. This track asks whether
FoaMES itself handles real manufacturing data correctly: counts, the OEE time ledger, SPC limits
and signals, and process-mining views. It is deterministic, so every stage runs once.

    datasets/manifest.json   what each dataset is, its license, where it comes from
    fetch                    download into a cache (never into the repository), check the license the
                             source states and the checksums, write provenance.json
    adapters                 normalise each source into rows FoaMES understands
    checks                   run FoaMES's code and compare it with values computed here,
                             independently, from the raw rows

Each dataset also has a synthetic fixture in the same shape, so the checks and the adapters run
offline (`--synthetic`) and in the self-tests. Standard library only.
"""

from __future__ import annotations

import csv
import fnmatch
import hashlib
import io
import json
import lzma
import math
import os
import random
import re
import shutil
import stat
import statistics
import sys
import tempfile
import urllib.request
import zipfile
import zlib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from itertools import pairwise
from pathlib import Path

from . import machining
from .paths import BENCH_ROOT, repo_root

MANIFEST = BENCH_ROOT / "datasets" / "manifest.json"
D2_N2 = 2 / math.sqrt(math.pi)  # d2 for moving ranges of two, written out rather than taken from FoaMES
TOL = 1e-9


# ----------------------------------------------------------------------------- manifest


def load_manifest(path: Path | None = None) -> dict:
	return json.loads(Path(path or MANIFEST).read_text())


def dataset(manifest: dict, dataset_id: str) -> dict:
	for d in manifest["datasets"]:
		if d["id"] == dataset_id:
			return d
	raise SystemExit(f"unknown dataset {dataset_id!r}; see `foames-bench data list`")


def enabled(manifest: dict) -> list[dict]:
	return [d for d in manifest["datasets"] if d.get("status") == "enabled"]


def cache_root() -> Path:
	return Path(os.environ.get("FOAMES_BENCH_DATA") or Path.home() / ".cache" / "foames-bench" / "datasets")


# -------------------------------------------------------------------------------- fetch


class FetchRefused(Exception):
	pass


def _get(url: str, timeout: int = 120, auth: str | None = None) -> bytes:
	req = urllib.request.Request(url, headers={"User-Agent": "foames-bench"})
	if auth:
		# Unredirected: Kaggle answers a download with a redirect to signed storage, which must not
		# receive the Kaggle credentials.
		req.add_unredirected_header("Authorization", auth)
	with urllib.request.urlopen(req, timeout=timeout) as resp:
		return resp.read()


KAGGLE_API = "https://www.kaggle.com/api/v1"


def kaggle_auth(env=None, home: Path | None = None) -> str | None:
	"""An Authorization header from KAGGLE_API_TOKEN, KAGGLE_USERNAME and KAGGLE_KEY, or
	~/.kaggle/kaggle.json, the places the Kaggle CLI reads. None when there are no credentials."""
	import base64

	env = os.environ if env is None else env
	if env.get("KAGGLE_API_TOKEN"):
		return f"Bearer {env['KAGGLE_API_TOKEN']}"
	user, key = env.get("KAGGLE_USERNAME"), env.get("KAGGLE_KEY")
	if not (user and key):
		path = Path(env.get("KAGGLE_CONFIG_DIR") or (home or Path.home()) / ".kaggle") / "kaggle.json"
		try:
			cfg = json.loads(path.read_text())
		except (OSError, ValueError):
			return None
		user, key = cfg.get("username"), cfg.get("key")
	if not (user and key):
		return None
	return "Basic " + base64.b64encode(f"{user}:{key}".encode()).decode()


def kaggle_license(meta: dict) -> str:
	"""The license a Kaggle dataset states, normalised to an SPDX-style id where it is a common one.
	Share-alike, non-commercial and no-derivatives variants never normalise to plain CC BY."""
	names = [meta.get("licenseName"), meta.get("license_name")]
	for lic in meta.get("licenses") or []:
		names.append(lic.get("name") if isinstance(lic, dict) else lic)
	for name in names:
		text = str(name or "").strip().lower()
		if not text:
			continue
		flat = re.sub(r"[\s_()]+", "-", text)
		if re.search(r"(^|-)(sa|nc|nd)(-|$)|sharealike|noncommercial|noderiv|non-commercial", flat):
			return flat.strip("-")
		if "cc0" in flat or "public-domain" in flat:
			return "cc0-1.0"
		if re.search(r"cc-by-4\.0|attribution-4\.0", flat):
			return "cc-by-4.0"
		if "apache" in flat and "2.0" in flat:
			return "apache-2.0"
		if flat in ("mit", "mit-license"):
			return "mit"
		return flat.strip("-")
	return ""


def _norm_license(value) -> str:
	if isinstance(value, dict):
		value = value.get("id") or value.get("title") or ""
	return str(value or "").strip().lower()


def fetch(ds: dict, dest: Path | None = None, getter=_get) -> Path:
	"""Download one dataset into the cache and return its folder. Refuses a dataset that is not
	enabled, whose source states a license outside the manifest's list, or whose checksum differs."""
	if ds.get("status") != "enabled":
		raise FetchRefused(f"{ds['id']} is {ds.get('status')}: {ds.get('note', 'not enabled')}")
	folder = Path(dest) if dest else _safe_member_path(cache_root(), ds["id"], f"dataset {ds['id']!r}")
	folder.mkdir(parents=True, exist_ok=True)
	# Stage the whole dataset, not each archive in isolation: a later Zenodo file can fail its
	# checksum or decoding after an earlier one has been fully validated. Provenance is staged too.
	with tempfile.TemporaryDirectory(prefix=".fetch-dataset-", dir=folder) as temporary:
		staging = Path(temporary)
		_fetch_into(ds, staging, getter)
		_publish_dataset(staging, folder)
	return folder


def _fetch_into(ds: dict, folder: Path, getter) -> None:
	src = ds["source"]
	provenance = {
		"dataset": ds["id"],
		"title": ds["title"],
		"fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
		"citation": ds.get("citation"),
		"files": [],
	}
	allowed = {x.lower() for x in ds.get("licenses", [])}
	if src["type"] == "zenodo":
		record = json.loads(getter(f"https://zenodo.org/api/records/{src['record']}"))
		meta = record.get("metadata", {})
		lic = _norm_license(meta.get("license"))
		if lic not in allowed:
			raise FetchRefused(
				f"{ds['id']}: Zenodo states license {lic!r}, manifest allows {sorted(allowed)}"
			)
		provenance.update(
			license=lic,
			doi=record.get("doi"),
			version=meta.get("version"),
			creators=[c.get("name") for c in meta.get("creators", [])],
			record=src["record"],
			latest=record.get("links", {}).get("latest"),
		)
		patterns = src.get("files") or ["*"]
		for f in record.get("files", []):
			if not any(fnmatch.fnmatch(f["key"], p) for p in patterns):
				continue
			data = getter(f["links"]["self"])
			algo, _, want = str(f.get("checksum", "")).partition(":")
			got = hashlib.new(algo or "md5", data).hexdigest()
			if want and got != want:
				raise FetchRefused(f"{ds['id']}/{f['key']}: {algo} {got} != {want}")
			_store(folder, f["key"], data)
			provenance["files"].append({"name": f["key"], "bytes": len(data), algo or "md5": got})
	elif src["type"] == "url":
		if not ds.get("license_verified"):
			raise FetchRefused(f"{ds['id']}: license not verified in the manifest")
		data = getter(src["url"])
		got = hashlib.sha256(data).hexdigest()
		if src.get("sha256") and got != src["sha256"]:
			raise FetchRefused(f"{ds['id']}: sha256 {got} != pinned {src['sha256']}")
		name = src["url"].rsplit("/", 1)[-1]
		_store(folder, name, data)
		provenance.update(license=sorted(allowed)[0] if allowed else None, url=src["url"])
		provenance["files"].append(
			{"name": name, "bytes": len(data), "sha256": got, "pinned": bool(src.get("sha256"))}
		)
	elif src["type"] == "kaggle":
		get = getter
		if getter is _get:
			auth = kaggle_auth()
			if not auth:
				raise FetchRefused(
					f"{ds['id']}: Kaggle needs credentials (KAGGLE_USERNAME and KAGGLE_KEY, KAGGLE_API_TOKEN, or "
					+ "~/.kaggle/kaggle.json). Or download the archive from "
					+ f"https://www.kaggle.com/datasets/{src['ref']} and run `foames-bench data import {ds['id']} <zip>`"
				)

			def get(url):
				return _get(url, auth=auth)

		meta = json.loads(get(f"{KAGGLE_API}/datasets/view/{src['ref']}"))
		lic = kaggle_license(meta)
		if lic not in allowed:
			raise FetchRefused(
				f"{ds['id']}: Kaggle states license {lic!r}, manifest allows {sorted(allowed)}"
			)
		data = get(f"{KAGGLE_API}/datasets/download/{src['ref']}")
		got = hashlib.sha256(data).hexdigest()
		if src.get("sha256") and got != src["sha256"]:
			raise FetchRefused(f"{ds['id']}: sha256 {got} != pinned {src['sha256']}")
		name = src["ref"].rsplit("/", 1)[-1] + ".zip"
		_store(folder, name, data)
		provenance.update(
			license=lic,
			kaggle=src["ref"],
			url=f"https://www.kaggle.com/datasets/{src['ref']}",
			version=meta.get("currentVersionNumber") or meta.get("versionNumber"),
			upstream=src.get("upstream"),
		)
		provenance["files"].append(
			{"name": name, "bytes": len(data), "sha256": got, "pinned": bool(src.get("sha256"))}
		)
	else:
		raise FetchRefused(f"{ds['id']}: source type {src['type']!r} is not fetched automatically")
	(folder / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")


def import_archive(ds: dict, archive: Path, dest: Path | None = None) -> Path:
	"""Put an archive downloaded by hand (a Kaggle download in a browser, say) into the cache, with
	the same license gate, zip rules and provenance as a fetch. The license must be verified in the
	manifest, since a local file cannot state one."""
	if ds.get("status") != "enabled":
		raise FetchRefused(f"{ds['id']} is {ds.get('status')}: {ds.get('note', 'not enabled')}")
	if not ds.get("license_verified"):
		raise FetchRefused(f"{ds['id']}: license not verified in the manifest")
	archive = Path(archive)
	if archive.suffix.lower() != ".zip" or not archive.is_file():
		raise FetchRefused(f"{archive}: give the dataset's .zip archive")
	data = archive.read_bytes()
	got = hashlib.sha256(data).hexdigest()
	pinned = ds["source"].get("sha256")
	if pinned and got != pinned:
		raise FetchRefused(f"{ds['id']}: sha256 {got} != pinned {pinned}")
	folder = Path(dest) if dest else _safe_member_path(cache_root(), ds["id"], f"dataset {ds['id']!r}")
	folder.mkdir(parents=True, exist_ok=True)
	with tempfile.TemporaryDirectory(prefix=".fetch-dataset-", dir=folder) as temporary:
		staging = Path(temporary)
		# The stored name comes from the manifest, never from the user's path.
		name = f"{ds['id']}.zip"
		_store(staging, name, data)
		provenance = {
			"dataset": ds["id"],
			"title": ds["title"],
			"fetched_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
			"citation": ds.get("citation"),
			"license": sorted(x.lower() for x in ds.get("licenses", []))[0],
			"license_evidence": ds.get("license_evidence"),
			"imported_from": "manual download",
			"source": ds["source"],
			"files": [{"name": name, "bytes": len(data), "sha256": got, "pinned": bool(pinned)}],
		}
		(staging / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
		_publish_dataset(staging, folder)
	return folder


def _publish_dataset(staging: Path, folder: Path) -> None:
	"""Publish only after all downloads, checksum/ZIP validation and provenance serialization.

	Preflight the complete destination namespace before replacing files. Individual replacements are
	atomic; this is not a crash-atomic filesystem transaction or a concurrent-writer protocol.
	"""
	files, directories = [], set()
	for path in _published_paths(staging, "*"):
		relative = path.relative_to(staging)
		dest = _safe_member_path(folder, relative.as_posix(), "dataset publication")
		entry = folder
		for part in relative.parts:
			entry = entry / part
			try:
				info = entry.lstat()
			except (FileNotFoundError, NotADirectoryError):
				break
			if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & getattr(
				stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0
			):
				raise FetchRefused(f"dataset publication: refusing symlink or junction {relative}")
		if path.is_dir():
			if dest.exists() and not dest.is_dir():
				raise FetchRefused(f"dataset publication: directory {relative} is already a file")
			directories.add(dest)
		else:
			if dest.exists() and not dest.is_file():
				raise FetchRefused(f"dataset publication: file {relative} is already a directory")
			files.append((path, dest))
	for path in sorted(directories, key=lambda p: len(p.parts)):
		path.mkdir(parents=True, exist_ok=True)
	# Publish provenance last so successfully staged payloads precede their new record.
	for path, dest in sorted(files, key=lambda item: item[1].name == "provenance.json"):
		path.replace(dest)


def _safe_member_path(folder: Path, name: str, what: str) -> Path:
	"""Join a remote-controlled archive member name under ``folder``. Zip names use "/" but a
	crafted archive may carry "\\", drive letters or ".."; rebuild the path from clean parts so
	nothing can land outside ``folder``."""
	parts = [p for p in re.split(r"[\\/]+", name) if p not in ("", ".")]
	if not parts or any(p == ".." or ":" in p for p in parts):
		raise FetchRefused(f"{what}: unsafe member path {name!r}")
	root = folder.resolve()
	dest = root.joinpath(*parts).resolve()
	if not dest.is_relative_to(root):
		raise FetchRefused(f"{what}: member path {name!r} escapes the folder")
	return dest


def _store(folder: Path, name: str, data: bytes) -> None:
	folder = folder.resolve()
	target = _safe_member_path(folder, Path(name).name, name)
	if target.suffix.lower() != ".zip":
		target.write_bytes(data)
		return
	try:
		with zipfile.ZipFile(io.BytesIO(data)) as zf:
			members = []
			files = {target}
			directories = set()
			# Validate the entire namespace before creating directories or replacing cached files.
			for member in zf.infolist():
				dest = _safe_member_path(folder, member.filename, f"{name}!{member.filename}")
				if stat.S_ISLNK(member.external_attr >> 16):
					raise FetchRefused(f"{name}: zip member {member.filename!r} is a link")
				if dest in (folder, target):
					raise FetchRefused(
						f"{name}: zip member {member.filename!r} conflicts with the cache or archive"
					)
				if member.is_dir():
					directories.add(dest)
				else:
					files.add(dest)
				for parent in dest.parents:
					if parent == folder:
						break
					directories.add(parent)
				members.append((member, dest))
			if files & directories:
				raise FetchRefused(f"{name}: zip members have conflicting file and directory paths")
			for path in directories:
				if path.exists() and not path.is_dir():
					raise FetchRefused(f"{name}: directory path {path.relative_to(folder)} is already a file")
			for path in files:
				if path.exists() and not path.is_file():
					raise FetchRefused(f"{name}: file path {path.relative_to(folder)} is already a directory")
			# Decode every member to temporary files first: a late CRC/decompression failure must
			# leave the old archive, extracted files and their provenance together and unchanged.
			with tempfile.TemporaryDirectory(prefix=".fetch-", dir=folder) as temporary:
				staging = Path(temporary)
				staged = []
				for index, (member, dest) in enumerate(members):
					path = staging / str(index)
					with zf.open(member) as source, path.open("wb") as output:
						shutil.copyfileobj(source, output)
					if not member.is_dir():
						staged.append((path, dest))
				archive = staging / "archive"
				archive.write_bytes(data)
				for path in sorted(directories, key=lambda p: len(p.parts)):
					path.mkdir(parents=True, exist_ok=True)
				for path, dest in staged:
					path.replace(dest)
				archive.replace(target)
	except (
		zipfile.BadZipFile,
		EOFError,
		RuntimeError,
		zlib.error,
		UnicodeDecodeError,
		lzma.LZMAError,
	) as error:
		raise FetchRefused(f"{name}: invalid or unsupported zip archive: {error}") from error


# ----------------------------------------------------------------------------- helpers


def _foames(*names):
	"""FoaMES's pure modules, by name, from the checkout under test."""
	root = repo_root()
	if str(root) not in sys.path:
		sys.path.insert(0, str(root))
	from foames.foames_mes import counters, ecl, kpi, oee, spc
	from foames.foames_process_mining import discovery, eventlog

	mods = {
		"counters": counters,
		"ecl": ecl,
		"kpi": kpi,
		"oee": oee,
		"spc": spc,
		"discovery": discovery,
		"eventlog": eventlog,
	}
	return tuple(mods[n] for n in names) if len(names) != 1 else mods[names[0]]


def _pick(headers: list[str], candidates, what: str, path) -> str:
	if isinstance(candidates, str):
		candidates = [candidates]
	for c in candidates:
		if c in headers:
			return c
	lower = {h.lower(): h for h in headers}
	for c in candidates:
		if c.lower() in lower:
			return lower[c.lower()]
	raise SchemaMismatch(f"{path}: no {what} column among {candidates}; headers are {headers}")


class SchemaMismatch(Exception):
	pass


def _ts(value: str, fmt: str | None = None) -> datetime:
	value = str(value).strip().strip('"')
	if fmt:
		return datetime.strptime(value, fmt)
	try:
		return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
	except ValueError:
		pass
	for f in (
		"%d/%m/%Y %H:%M:%S",
		"%d.%m.%Y %H:%M:%S",
		"%Y/%m/%d %H:%M:%S",
		"%m/%d/%Y %H:%M",
		"%d.%m.%Y %H:%M",
	):
		try:
			return datetime.strptime(value, f)
		except ValueError:
			continue
	raise ValueError(f"unrecognised timestamp {value!r}")


def _published_paths(folder: Path, pattern: str):
	"""Ignore internal staging directories left behind by an interrupted fetch or extraction.

	Inspect relative directory components so the staging root itself remains publishable, and an
	ordinary file whose name starts with ``.fetch-`` remains usable.
	"""
	for path in folder.rglob(pattern):
		relative = path.relative_to(folder)
		directories = relative.parts if path.is_dir() else relative.parent.parts
		if not any(part.startswith(".fetch-") for part in directories):
			yield path


def _csvs(folder: Path) -> list[Path]:
	return sorted(p for p in _published_paths(folder, "*.csv") if p.is_file())


def _read_csv(path: Path) -> tuple[list[str], list[dict]]:
	text = path.read_text(encoding="utf-8-sig", errors="replace")
	sample = text[:4096]
	try:
		dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
	except csv.Error:
		dialect = csv.excel
	reader = csv.DictReader(io.StringIO(text), dialect=dialect)
	rows = list(reader)
	return list(reader.fieldnames or []), rows


def _find_file(folder: Path, hints) -> Path:
	files = _csvs(folder)
	for hint in hints:
		for p in files:
			if hint.lower() in p.name.lower():
				return p
	raise SchemaMismatch(
		f"{folder}: no CSV whose name contains any of {hints}; found {[p.name for p in files]}"
	)


@dataclass
class Check:
	id: str
	passed: bool
	expected: object = None
	observed: object = None
	detail: str = ""

	def as_dict(self):
		return {
			"id": self.id,
			"passed": self.passed,
			"expected": self.expected,
			"observed": self.observed,
			"detail": self.detail,
		}


@dataclass
class Result:
	dataset: str
	stage: str
	synthetic: bool
	checks: list[Check] = field(default_factory=list)
	metrics: dict = field(default_factory=dict)
	error: str | None = None
	notes: list = field(default_factory=list)

	@property
	def passed(self) -> bool:
		return self.error is None and bool(self.checks) and all(c.passed for c in self.checks)

	def as_dict(self):
		return {
			"dataset": self.dataset,
			"stage": self.stage,
			"synthetic": self.synthetic,
			"passed": self.passed,
			"error": self.error,
			"checks": [c.as_dict() for c in self.checks],
			"metrics": self.metrics,
		}


def _close(a, b, tol=TOL) -> bool:
	return abs(float(a) - float(b)) <= tol * max(1.0, abs(float(a)), abs(float(b)))


# ------------------------------------------------------------------------- phase timeline


def load_phase_timeline(folder: Path, ds: dict, max_rows: int | None) -> list[tuple[str, datetime, str]]:
	"""(session, timestamp, phase) rows from the CNC changeover export, phases lower-cased."""
	cols = ds["columns"]
	out = []
	for path in _csvs(folder):
		headers, rows = _read_csv(path)
		try:
			t = _pick(headers, cols["timestamp"], "timestamp", path)
			ph = _pick(headers, cols["phase"], "phase", path)
		except SchemaMismatch:
			continue
		try:
			se = _pick(headers, cols["session"], "session", path)
		except SchemaMismatch:
			se = None
		for row in rows:
			if not row.get(t) or not row.get(ph):
				continue
			out.append((row[se] if se else path.stem, _ts(row[t]), str(row[ph]).strip().lower()))
	if not out:
		heads = {p.name: _read_csv(p)[0][:20] for p in _csvs(folder)[:5]}
		raise SchemaMismatch(f"no file with timestamp and phase columns; headers: {heads}")
	out.sort(key=lambda r: (r[0], r[1]))
	return out[:max_rows] if max_rows else out


def segments(rows: list[tuple[str, datetime, str]]) -> dict[str, list[tuple[str, datetime, datetime]]]:
	"""Consecutive rows with one phase become one segment, ending where the next one starts; a
	session's last segment ends at its last row. Computed here, independently of FoaMES."""
	by_session: dict[str, list[tuple[str, datetime, datetime]]] = {}
	for session in sorted({r[0] for r in rows}):
		rs = [r for r in rows if r[0] == session]
		segs = []
		start, phase = rs[0][1], rs[0][2]
		for _, ts, p in rs[1:]:
			if p != phase:
				segs.append((phase, start, ts))
				start, phase = ts, p
		segs.append((phase, start, rs[-1][1]))
		by_session[session] = segs
	return by_session


def check_phase_timeline(rows, ds: dict) -> tuple[list[Check], dict]:
	oee, discovery, eventlog = _foames("oee", "discovery", "eventlog")
	segs = segments(rows)
	states = ds.get("phase_states", {})
	checks, metrics = [], {"sessions": len(segs), "rows": len(rows)}

	# Process mining: start/complete events per segment, session as case.
	events = []
	for session, ss in segs.items():
		for phase, a, b in ss:
			events.append(eventlog.Event(session, phase, a, lifecycle=eventlog.START))
			events.append(eventlog.Event(session, phase, b, lifecycle=eventlog.COMPLETE))
	log = eventlog.EventLog(events, name=ds["id"])

	expected_variants = {}
	for session, ss in segs.items():
		expected_variants.setdefault(tuple(p for p, _, _ in ss), []).append(session)
	observed = {tuple(v["variant"]): v["cases"] for v in discovery.variant_table(log)}
	checks.append(
		Check(
			"process-mining/variants",
			observed == {k: len(v) for k, v in expected_variants.items()},
			len(expected_variants),
			len(observed),
			"variant sequences and their case counts",
		)
	)

	order_ok = all(all(x.timestamp <= y.timestamp for x, y in pairwise(tr)) for tr in log.traces().values())
	checks.append(Check("process-mining/event-order", order_ok, True, order_ok, "every trace in time order"))

	acts = discovery.activity_durations(log)
	for phase in sorted({p for ss in segs.values() for p, _, _ in ss}):
		durs = [(b - a).total_seconds() for ss in segs.values() for p, a, b in ss if p == phase]
		exp = statistics.median(durs)
		got = acts.get(phase, {}).get("median_service_seconds")
		checks.append(
			Check(f"process-mining/median-duration/{phase}", got is not None and _close(exp, got), exp, got)
		)

	setup_phases = [p for p, s in states.items() if s == "Setup"]
	setup = {s: sum((b - a).total_seconds() for p, a, b in ss if p in setup_phases) for s, ss in segs.items()}
	metrics["setup_seconds_by_session"] = setup
	rw = discovery.rework(eventlog.EventLog([e for e in events if e.lifecycle == eventlog.COMPLETE]))
	exp_rw = {}
	for ss in segs.values():
		seen = {}
		for p, _, _ in ss:
			seen[p] = seen.get(p, 0) + 1
		for p, n in seen.items():
			if n > 1:
				exp_rw[p] = exp_rw.get(p, 0) + 1
	checks.append(
		Check("process-mining/repeated-phases", rw == exp_rw, exp_rw, rw, "sessions that repeat a phase")
	)

	# OEE time ledger per session: every minute in exactly one bucket, unmapped phases unknown.
	worst = 0.0
	for session, ss in segs.items():
		planned = sum((b - a).total_seconds() for _, a, b in ss) / 60
		intervals = [((b - a).total_seconds() / 60, states.get(p, "Unknown"), False) for p, a, b in ss]
		ledger = oee.ledger_from_states(intervals, planned)
		exp_setup = setup[session] / 60
		exp_run = sum(m for m, st, _ in intervals if st == "Running")
		worst = max(
			worst,
			abs(ledger.setup_minutes - exp_setup),
			abs(ledger.run_minutes - exp_run),
			abs(ledger.accounted_minutes - planned),
		)
	checks.append(
		Check(
			"oee/ledger-accounts-every-minute", worst <= 1e-6, 0.0, worst, "max minutes off across sessions"
		)
	)
	unmapped = sorted({p for ss in segs.values() for p, _, _ in ss if p not in states})
	metrics["unmapped_phases"] = unmapped
	return checks, metrics


# --------------------------------------------------------------------- downtime and counts


def load_bottling(folder: Path, ds: dict, max_rows: int | None):
	cols = ds["columns"]
	dpath = _find_file(folder, cols["downtime_file"])
	h, rows = _read_csv(dpath)
	s, e = (
		_pick(h, cols["downtime_start"], "downtime start", dpath),
		_pick(h, cols["downtime_end"], "downtime end", dpath),
	)
	downtime = sorted((_ts(r[s]), _ts(r[e])) for r in rows if r.get(s) and r.get(e))
	cpath = _find_file(folder, cols["counts_file"])
	h, rows = _read_csv(cpath)
	t, c = (
		_pick(h, cols["count_timestamp"], "count timestamp", cpath),
		_pick(h, cols["count"], "count", cpath),
	)
	counts = sorted((_ts(r[t]), float(r[c])) for r in rows if r.get(t) and r.get(c) not in (None, ""))
	if max_rows:
		counts = counts[:max_rows]
		if counts:
			end = counts[-1][0] + timedelta(hours=1)
			downtime = [(a, b) for a, b in downtime if a < end]
	return downtime, counts


def merge_intervals(intervals):
	out = []
	for a, b in sorted(intervals):
		if b < a:
			continue
		if out and a <= out[-1][1]:
			out[-1] = (out[-1][0], max(out[-1][1], b))
		else:
			out.append((a, b))
	return out


def check_bottling(downtime, counts, ds: dict, seed: int = 7) -> tuple[list[Check], dict]:
	counters, oee = _foames("counters", "oee")
	checks, metrics = [], {"downtime_events": len(downtime), "count_rows": len(counts)}
	if not counts:
		raise SchemaMismatch("no production counts")

	# Counts: replay the hourly counts as a running PLC counter. FoaMES must recover exactly the
	# source total and invent nothing: once with a 16-bit rollover, once with a controller restart.
	rng = random.Random(seed)
	expected_total = sum(max(c, 0) for _, c in counts)
	rollover = 65535

	def replay(reset_at=None, wrap=None):
		reading, readings = 0.0, [0.0]
		for i, (_, c) in enumerate(counts):
			if i == reset_at:
				reading = 0.0  # restart: the counter is back at zero and nothing was produced
				readings.append(reading)
			reading += max(c, 0)
			if wrap and reading > wrap:
				reading -= wrap
			readings.append(reading)
		return readings

	wrapped = replay(wrap=rollover)
	recovered = sum(counters.counter_delta(a, b, rollover) for a, b in pairwise(wrapped))
	checks.append(
		Check(
			"counters/rollover-replay-total",
			_close(recovered, expected_total),
			expected_total,
			recovered,
			"hourly counts as a 16-bit counter",
		)
	)
	reset_at = rng.randrange(1, len(counts)) if len(counts) > 2 else None
	restarted = replay(reset_at=reset_at)
	recovered = sum(counters.counter_delta(a, b) for a, b in pairwise(restarted))
	checks.append(
		Check(
			"counters/reset-replay-total",
			_close(recovered, expected_total),
			expected_total,
			recovered,
			"a controller restart adds nothing",
		)
	)
	# A restart on a counter that also has a rollover value set cannot be told apart from a wrap by
	# the readings alone. Reported, not graded: the size of the gap is the case for a reset signal.
	both = replay(reset_at=reset_at, wrap=rollover)
	metrics["reset_on_rollover_counter_phantom_units"] = (
		sum(counters.counter_delta(a, b, rollover) for a, b in pairwise(both)) - expected_total
	)

	# Availability over the observed span: downtime (merged, clipped) is unplanned Down, the rest
	# Running. Overlapping downtime records are a data-quality finding, not double loss.
	start, end = counts[0][0], counts[-1][0] + timedelta(hours=1)
	clipped = [(max(a, start), min(b, end)) for a, b in downtime if b > start and a < end]
	merged = merge_intervals(clipped)
	planned = (end - start).total_seconds() / 60
	down = sum((b - a).total_seconds() for a, b in merged) / 60
	raw = sum((b - a).total_seconds() for a, b in clipped) / 60
	metrics.update(planned_minutes=planned, downtime_minutes=down, overlapping_downtime_minutes=raw - down)
	ledger = oee.ledger_from_states([(down, "Down", False), (planned - down, "Running", False)], planned)
	res = oee.compute_oee(ledger, good_count=expected_total, scrap_count=0, ideal_cycle_seconds=None)
	exp_av = (planned - down) / planned if planned else 0.0
	checks.append(Check("oee/availability", _close(res.availability, exp_av, 1e-9), exp_av, res.availability))
	checks.append(
		Check(
			"oee/ledger-accounts-every-minute",
			abs(ledger.accounted_minutes - planned) < 1e-6,
			planned,
			ledger.accounted_minutes,
		)
	)
	metrics["availability"] = exp_av

	# Missing signal: drop one in ten hours of state data; the gap must become unknown loss.
	known = planned * 0.9
	gap_ledger = oee.ledger_from_states(
		[(min(down, known), "Down", False), (known - min(down, known), "Running", False)], planned
	)
	checks.append(
		Check(
			"oee/missing-signal-is-loss",
			_close(gap_ledger.unknown_minutes, planned - known, 1e-9) and gap_ledger.coverage <= 0.9 + 1e-9,
			planned - known,
			gap_ledger.unknown_minutes,
		)
	)
	return checks, metrics


# ------------------------------------------------------------------------------- SECOM


def load_secom(folder: Path, ds: dict, max_rows: int | None):
	cols = ds["columns"]
	data = next((p for p in _published_paths(folder, cols["data_file"]) if p.is_file()), None)
	labels = next((p for p in _published_paths(folder, cols["labels_file"]) if p.is_file()), None)
	if not data or not labels:
		raise SchemaMismatch(f"{folder}: missing {cols['data_file']} or {cols['labels_file']}")
	X = [[float(v) for v in line.split()] for line in data.read_text().splitlines() if line.strip()]
	L = []
	for line in labels.read_text().splitlines():
		if not line.strip():
			continue
		label, _, stamp = line.strip().partition(" ")
		L.append((int(float(label)), _ts(stamp, cols.get("timestamp_format"))))
	if len(X) != len(L):
		raise SchemaMismatch(f"SECOM: {len(X)} data rows but {len(L)} labels")
	order = sorted(range(len(X)), key=lambda i: (L[i][1], i))
	rows = [(L[i][1], L[i][0] == cols["label_fail"], X[i]) for i in order]
	return rows[:max_rows] if max_rows else rows


def independent_imr(values, baseline):
	base = values[:baseline]
	mr = [abs(b - a) for a, b in pairwise(base)]
	cl = sum(base) / len(base)
	sigma = (sum(mr) / len(mr)) / D2_N2
	return cl, cl + 3 * sigma, cl - 3 * sigma, sigma


def check_secom(rows, ds: dict, max_features: int, baseline_share: float = 0.3) -> tuple[list[Check], dict]:
	spc = _foames("spc")
	checks, metrics = [], {"samples": len(rows), "fail_rate": sum(r[1] for r in rows) / len(rows)}
	n_feat = len(rows[0][2])
	cut = max(20, int(len(rows) * baseline_share))
	chosen = []
	for j in range(n_feat):
		col = [r[2][j] for r in rows]
		present = [v for v in col if not math.isnan(v)]
		base = [v for v in col[:cut] if not math.isnan(v)]
		if len(present) >= 0.9 * len(col) and len(base) >= 20 and len(set(base)) > 2:
			chosen.append(j)
		if len(chosen) >= max_features:
			break
	metrics["features"] = chosen
	if not chosen:
		raise SchemaMismatch("SECOM: no feature with enough non-missing, varying baseline values")
	worst, signal_mismatch, nan_leaks = 0.0, 0, 0
	flagged = set()
	for j in chosen:
		idx = [i for i, r in enumerate(rows) if not math.isnan(r[2][j])]
		values = [rows[i][2][j] for i in idx]
		b = sum(1 for i in idx if i < cut)
		chart = spc.imr_chart(values, baseline=b, rules=("N1",))
		ind = chart["individuals"]
		cl, ucl, lcl, sigma = independent_imr(values, b)
		for got, exp in (
			(ind["cl"], cl),
			(ind["ucl"], ucl),
			(ind["lcl"], lcl),
			(chart["sigma_within"], sigma),
		):
			worst = max(worst, abs(got - exp) / max(1.0, abs(exp)))
		got_idx = sorted({s["index"] for s in ind["signals"] if s["rule"] == "N1"})
		exp_idx = [k for k, v in enumerate(values) if v > ucl or v < lcl]
		if got_idx != exp_idx:
			signal_mismatch += 1
		nan_leaks += sum(1 for v in ind["points"] if isinstance(v, float) and math.isnan(v))
		flagged.update(idx[k] for k in exp_idx if idx[k] >= cut)
	checks.append(
		Check(
			"spc/imr-limits", worst <= 1e-9, 0.0, worst, "max relative difference in CL, UCL, LCL and sigma"
		)
	)
	checks.append(
		Check(
			"spc/beyond-limit-signals",
			signal_mismatch == 0,
			0,
			signal_mismatch,
			"features whose N1 points differ from an independent test",
		)
	)
	checks.append(Check("spc/no-missing-values-charted", nan_leaks == 0, 0, nan_leaks))

	# Time-aware grading: limits from the earliest samples, flags judged on later ones only. An
	# out-of-control reading is not a confirmed defect, so these are metrics, not checks.
	evaluation = range(cut, len(rows))
	fails = {i for i in evaluation if rows[i][1]}
	tp = len(flagged & fails)
	metrics.update(
		evaluated=len(evaluation),
		flagged=len(flagged),
		fails=len(fails),
		precision=(tp / len(flagged)) if flagged else None,
		recall=(tp / len(fails)) if fails else None,
		base_fail_rate=(len(fails) / len(evaluation)) if evaluation else None,
	)
	return checks, metrics


# ------------------------------------------------------------------------------ synthetic


def synthetic(dataset_id: str, folder: Path, seed: int = 11) -> Path:
	"""Write an invented fixture in the documented shape of a dataset. Not real data."""
	rng = random.Random(seed)
	folder.mkdir(parents=True, exist_ok=True)
	t0 = datetime(2026, 1, 5, 6, 0, 0)
	if dataset_id == "cnc-changeover":
		with (folder / "synthetic_sessions.csv").open("w", newline="") as fh:
			w = csv.writer(fh)
			w.writerow(["timestamp", "session", "phase", "spindle_speed"])
			for s in range(6):
				t = t0 + timedelta(days=s)
				plan = (
					["setup", "production", "interruption", "production"]
					if s % 3 == 0
					else ["setup", "production"]
				)
				if s == 4:
					plan = ["setup", "production", "setup", "production"]
				for phase in plan:
					for _ in range(rng.randint(5, 20)):
						w.writerow([t.isoformat(), f"S{s:02d}", phase, round(rng.uniform(0, 12000), 1)])
						t += timedelta(seconds=rng.randint(10, 60))
	elif dataset_id == "beverage-bottling":
		with (folder / "synthetic_hourly_production.csv").open("w", newline="") as fh:
			w = csv.writer(fh)
			w.writerow(["timestamp", "count"])
			for h in range(72):
				w.writerow([(t0 + timedelta(hours=h)).isoformat(), rng.randint(9000, 14000)])
		with (folder / "synthetic_downtime_events.csv").open("w", newline="") as fh:
			w = csv.writer(fh)
			w.writerow(["start", "end", "reason"])
			for _ in range(15):
				a = t0 + timedelta(minutes=rng.randint(0, 72 * 60 - 60))
				w.writerow(
					[
						a.isoformat(),
						(a + timedelta(minutes=rng.randint(3, 45))).isoformat(),
						rng.choice(["jam", "labeller", "filler"]),
					]
				)
	elif dataset_id == "secom":
		n, f = 300, 12
		with (folder / "secom.data").open("w") as fh, (folder / "secom_labels.data").open("w") as lh:
			for i in range(n):
				drift = 0.0 if i < 200 else 1.5
				row = []
				for j in range(f):
					v = rng.gauss(10 + j, 1) + (drift if j % 4 == 0 else 0)
					row.append("NaN" if rng.random() < 0.03 else f"{v:.4f}")
				fh.write(" ".join(row) + "\n")
				fail = 1 if rng.random() < (0.05 if i < 200 else 0.2) else -1
				lh.write(f'{fail} "{(t0 + timedelta(hours=i)).strftime("%d/%m/%Y %H:%M:%S")}"\n')
	elif dataset_id == "cnc-turning-xquality":
		machining.synthetic_turning(folder, seed)
	elif dataset_id == "cnc-milling-vibration":
		machining.synthetic_milling(folder, seed)
	else:
		raise SystemExit(f"no synthetic fixture for {dataset_id}")
	return folder


# ---------------------------------------------------------------------------------- run


def validate(ds: dict, folder: Path, stage: dict, stage_name: str, synthetic_data: bool) -> Result:
	res = Result(ds["id"], stage_name, synthetic_data)
	try:
		if ds["kind"] == "phase-timeline":
			res.checks, res.metrics = check_phase_timeline(
				load_phase_timeline(folder, ds, stage["max_rows"]), ds
			)
		elif ds["kind"] == "downtime-and-counts":
			res.checks, res.metrics = check_bottling(*load_bottling(folder, ds, stage["max_rows"]), ds)
		elif ds["kind"] == "multivariate-quality":
			res.checks, res.metrics = check_secom(
				load_secom(folder, ds, stage["max_rows"]), ds, stage["max_features"]
			)
		elif ds["kind"] == "machining-parts":
			res.checks, res.metrics, res.notes = machining.check_turning(
				machining.load_turning(folder, ds, stage["max_rows"]), ds, stage["max_features"]
			)
		elif ds["kind"] == "machining-vibration":
			res.checks, res.metrics, res.notes = machining.check_milling(
				machining.load_milling(folder, ds, stage["max_rows"]), ds, stage["max_features"]
			)
		else:
			res.error = f"no checks for kind {ds['kind']!r}"
	except (
		SchemaMismatch,
		machining.SchemaMismatch,
		ValueError,
		KeyError,
		IndexError,
		ZeroDivisionError,
		OSError,
	) as exc:
		res.error = f"{type(exc).__name__}: {exc}"
	return res


def render(results: list[Result]) -> str:
	lines = [
		"# Manufacturing-data validation",
		"",
		"| Dataset | Stage | Data | Result | Checks |",
		"| --- | --- | --- | --- | --- |",
	]
	for r in results:
		ok = sum(c.passed for c in r.checks)
		lines.append(
			f"| {r.dataset} | {r.stage} | {'synthetic' if r.synthetic else 'source'} | {'pass' if r.passed else 'FAIL'} | {ok}/{len(r.checks)} |"
		)
	for r in results:
		lines += ["", f"## {r.dataset}", ""]
		if r.error:
			lines.append(f"Error: {r.error}")
		for c in r.checks:
			lines.append(
				f"- {'pass' if c.passed else 'FAIL'} `{c.id}`: expected {c.expected!r}, observed {c.observed!r}{' (' + c.detail + ')' if c.detail else ''}"
			)
		if r.metrics:
			lines.append("")
			lines.append(
				"Metrics (reported, not graded): " + json.dumps(r.metrics, default=str, sort_keys=True)[:1500]
			)
		if r.notes:
			lines += ["", *r.notes]
	return "\n".join(lines) + "\n"


def cmd_data(opts) -> int:
	manifest = load_manifest()
	if opts.data_command == "list":
		for d in manifest["datasets"]:
			lic = ",".join(d.get("licenses") or ["?"]) + (
				"" if d.get("license_verified") else " (unverified)"
			)
			print(f"{d['id']:30} {d.get('status', ''):8} {d.get('kind', ''):27} {lic}")
		return 0
	chosen = [dataset(manifest, i) for i in opts.datasets] if opts.datasets else enabled(manifest)
	if opts.data_command == "import":
		ds = dataset(manifest, opts.dataset)
		try:
			print(f"{ds['id']}: {import_archive(ds, Path(opts.archive))}")
		except (FetchRefused, OSError) as exc:
			print(f"{ds['id']}: not imported: {exc}", file=sys.stderr)
			return 1
		return 0
	if opts.data_command == "fetch":
		code = 0
		for ds in chosen:
			try:
				print(f"{ds['id']}: {fetch(ds)}")
			except (FetchRefused, OSError) as exc:
				print(f"{ds['id']}: not fetched: {exc}", file=sys.stderr)
				code = 1
		return code
	stage = manifest["stages"][opts.stage]
	results = []
	for ds in chosen:
		if opts.synthetic:
			base = (
				Path(opts.synthetic_dir)
				if opts.synthetic_dir
				else _safe_member_path(cache_root(), "_synthetic", "synthetic fixtures")
			)
			folder = synthetic(ds["id"], _safe_member_path(base, ds["id"], f"dataset {ds['id']!r}"))
		else:
			folder = _safe_member_path(cache_root(), ds["id"], f"dataset {ds['id']!r}")
			if not (folder / "provenance.json").exists():
				results.append(
					Result(
						ds["id"], opts.stage, False, error="not fetched: run `foames-bench data fetch` first"
					)
				)
				continue
		results.append(validate(ds, folder, stage, opts.stage, opts.synthetic))
	text = render(results)
	print(text)
	if opts.out:
		out = Path(opts.out)
		out.mkdir(parents=True, exist_ok=True)
		(out / "manufacturing-data.json").write_text(
			json.dumps([r.as_dict() for r in results], indent=2, default=str) + "\n"
		)
		(out / "manufacturing-data.md").write_text(text)
	return 0 if all(r.passed for r in results) else 1


def add_parser(sub) -> None:
	s = sub.add_parser("data", help="manufacturing-data validation track: public datasets through FoaMES")
	dsub = s.add_subparsers(dest="data_command", required=True)
	d = dsub.add_parser("list", help="datasets in the manifest, with status and license")
	d.set_defaults(fn=cmd_data)
	d = dsub.add_parser("fetch", help="download enabled datasets into the cache ($FOAMES_BENCH_DATA)")
	d.add_argument("--datasets", nargs="*")
	d.set_defaults(fn=cmd_data)
	d = dsub.add_parser("import", help="put a hand-downloaded .zip into the cache (license gate, provenance)")
	d.add_argument("dataset")
	d.add_argument("archive")
	d.set_defaults(fn=cmd_data)
	d = dsub.add_parser("validate", help="replay datasets through FoaMES and compare with independent values")
	d.add_argument("--datasets", nargs="*")
	d.add_argument("--stage", choices=["smoke", "dev", "full"], default="smoke")
	d.add_argument(
		"--synthetic", action="store_true", help="use invented fixtures in each dataset's shape (offline)"
	)
	d.add_argument("--synthetic-dir", default=None)
	d.add_argument("--out", default=None, help="write manufacturing-data.json and .md here")
	d.set_defaults(fn=cmd_data)


def clear_cache(dataset_id: str) -> None:
	root = cache_root()
	target = _safe_member_path(root, dataset_id, f"dataset {dataset_id!r}")
	# Inspect every lexical component: resolution can hide an intermediate link into another
	# dataset inside this cache. Windows junctions are reparse points, not Python symlinks.
	parts = [p for p in re.split(r"[\\/]+", dataset_id) if p not in ("", ".")]
	entry = root
	for part in parts:
		entry = entry / part
		try:
			info = entry.lstat()
		except (FileNotFoundError, NotADirectoryError):
			break
		if (
			stat.S_ISLNK(info.st_mode)
			or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
		):
			raise FetchRefused(f"dataset {dataset_id!r}: refusing to delete through a symlink or junction")
	if target == root.resolve():
		raise FetchRefused(f"dataset {dataset_id!r}: refusing to delete the cache root")
	shutil.rmtree(target, ignore_errors=True)
