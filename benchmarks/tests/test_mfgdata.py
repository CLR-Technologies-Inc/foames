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

"""Self-tests for the manufacturing-data track. Offline: synthetic fixtures and a fake downloader."""

import hashlib
import io
import json
import lzma
import os
import stat
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from foames_bench import mfgdata


def _zip(members: dict) -> bytes:
	buf = io.BytesIO()
	with zipfile.ZipFile(buf, "w") as zf:
		for name, data in members.items():
			zf.writestr(name, data)
	return buf.getvalue()


class TestManifest(unittest.TestCase):
	def test_every_dataset_is_described(self):
		m = mfgdata.load_manifest()
		ids = [d["id"] for d in m["datasets"]]
		self.assertEqual(len(ids), len(set(ids)))
		for d in m["datasets"]:
			self.assertIn(d["status"], ("enabled", "planned", "later"), d["id"])
			self.assertIn("source", d)
			if d["status"] == "enabled":
				self.assertTrue(d["licenses"], d["id"])
				self.assertTrue(d.get("citation"), d["id"])
		self.assertEqual({"smoke", "dev", "full"}, set(m["stages"]))


class TestSyntheticRuns(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.TemporaryDirectory()
		self.addCleanup(self.tmp.cleanup)
		self.m = mfgdata.load_manifest()
		mfgdata._foames("oee")  # puts the FoaMES checkout on sys.path

	def run_ds(self, ds_id, stage="dev"):
		ds = mfgdata.dataset(self.m, ds_id)
		folder = mfgdata.synthetic(ds_id, Path(self.tmp.name) / ds_id)
		return mfgdata.validate(ds, folder, self.m["stages"][stage], stage, True)

	def test_enabled_datasets_pass_on_synthetic_data(self):
		for ds in mfgdata.enabled(self.m):
			with self.subTest(ds=ds["id"]):
				res = self.run_ds(ds["id"])
				self.assertIsNone(res.error)
				self.assertTrue(res.passed, mfgdata.render([res]))

	def test_smoke_stage_limits_rows(self):
		res = self.run_ds("secom", "smoke")
		self.assertLessEqual(res.metrics["samples"], 500)
		self.assertLessEqual(len(res.metrics["features"]), 5)

	def test_checks_catch_a_ledger_that_drops_unknown_time(self):
		from foames.foames_mes import oee

		real = oee.ledger_from_states

		def broken(intervals, planned):
			ledger = real(intervals, planned)
			ledger.unknown_minutes = 0.0
			return ledger

		with mock.patch.object(oee, "ledger_from_states", broken):
			res = self.run_ds("beverage-bottling")
		failed = {c.id for c in res.checks if not c.passed}
		self.assertIn("oee/missing-signal-is-loss", failed)

	def test_checks_catch_a_counter_that_counts_resets(self):
		from foames.foames_mes import counters

		with mock.patch.object(counters, "counter_delta", lambda a, b, r=None: abs(b - a)):
			res = self.run_ds("beverage-bottling")
		self.assertIn("counters/reset-replay-total", {c.id for c in res.checks if not c.passed})

	def test_checks_catch_wrong_spc_limits(self):
		from foames.foames_mes import spc

		real = spc.imr_chart

		def wide(values, baseline=None, rules="Nelson"):
			chart = real(values, baseline, rules)
			chart["individuals"]["ucl"] *= 1.01
			return chart

		with mock.patch.object(spc, "imr_chart", wide):
			res = self.run_ds("secom")
		self.assertIn("spc/imr-limits", {c.id for c in res.checks if not c.passed})

	def test_schema_mismatch_names_the_headers(self):
		ds = mfgdata.dataset(self.m, "cnc-changeover")
		folder = Path(self.tmp.name) / "odd"
		folder.mkdir()
		(folder / "x.csv").write_text("when,what\n2026-01-01T00:00:00,a\n")
		res = mfgdata.validate(ds, folder, self.m["stages"]["smoke"], "smoke", False)
		self.assertIn("when", res.error)
		self.assertFalse(res.passed)


class TestCacheDiscovery(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.TemporaryDirectory()
		self.addCleanup(self.tmp.cleanup)
		self.root = Path(self.tmp.name)
		self.folder = self.root / "cnc-changeover"
		self.folder.mkdir()

	def write(self, relative, text):
		path = self.folder / relative
		path.parent.mkdir(parents=True, exist_ok=True)
		path.write_text(text)
		return path

	def test_csv_discovery_and_selection_ignore_abandoned_staging_at_any_depth(self):
		stale = self.write(".fetch-dataset-interrupted/cnc.csv", "stale")
		self.write("nested/.fetch-archive-interrupted/cnc.csv", "stale")
		published = self.write("published/cnc.csv", "published")
		ordinary = self.write(".fetch-results.csv", "ordinary file")
		self.assertEqual(mfgdata._csvs(self.folder), sorted([ordinary, published]))
		self.assertEqual(mfgdata._find_file(self.folder, ["cnc"]), published)
		self.assertEqual(stale.read_text(), "stale")

	def test_secom_data_and_labels_ignore_abandoned_staging(self):
		self.write(".fetch-dataset-interrupted/secom.data", "incomplete")
		self.write(".fetch-dataset-interrupted/secom_labels.data", "incomplete")
		self.write("published/secom.data", "1 2\n")
		self.write("published/secom_labels.data", '-1 "19/07/2008 11:55:00"\n')
		ds = mfgdata.dataset(mfgdata.load_manifest(), "secom")
		rows = mfgdata.load_secom(self.folder, ds, None)
		self.assertEqual(len(rows), 1)
		self.assertEqual(rows[0][2], [1.0, 2.0])

	def test_publication_excludes_nested_staging_payload_and_provenance(self):
		self.write(".fetch-dataset-interrupted/partial.csv", "partial")
		self.write("nested/.fetch-archive-interrupted/provenance.json", "partial provenance")
		self.write("published.csv", "complete")
		self.write("provenance.json", "complete provenance")
		destination = self.root / "published"
		destination.mkdir()
		mfgdata._publish_dataset(self.folder, destination)
		self.assertEqual((destination / "published.csv").read_text(), "complete")
		self.assertEqual((destination / "provenance.json").read_text(), "complete provenance")
		self.assertFalse((destination / ".fetch-dataset-interrupted").exists())
		self.assertFalse((destination / "nested" / ".fetch-archive-interrupted").exists())

	def test_staged_provenance_does_not_mark_an_unpublished_dataset_as_fetched(self):
		self.write(".fetch-dataset-interrupted/provenance.json", "partial provenance")
		opts = mock.Mock(
			data_command="validate", datasets=["cnc-changeover"], stage="smoke", synthetic=False, out=None
		)
		with (
			mock.patch.object(mfgdata, "cache_root", return_value=self.root),
			mock.patch.object(mfgdata, "validate") as validate,
			mock.patch("sys.stdout", new_callable=io.StringIO) as output,
		):
			self.assertEqual(mfgdata.cmd_data(opts), 1)
		validate.assert_not_called()
		self.assertIn("not fetched", output.getvalue())


class TestFetch(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.TemporaryDirectory()
		self.addCleanup(self.tmp.cleanup)
		self.m = mfgdata.load_manifest()

	@staticmethod
	def zenodo(license_id="cc-by-4.0", data=b"timestamp,session,phase\n", checksum=None):
		md5 = checksum or "md5:" + hashlib.md5(data).hexdigest()
		record = {
			"doi": "10.5281/zenodo.0",
			"metadata": {"license": {"id": license_id}, "version": "1", "creators": [{"name": "A"}]},
			"files": [
				{"key": "a.csv", "checksum": md5, "links": {"self": "https://zenodo.example/a.csv"}},
				{"key": "readme.pdf", "checksum": "md5:x", "links": {"self": "https://zenodo.example/r.pdf"}},
			],
			"links": {},
		}

		def getter(url):
			return json.dumps(record).encode() if "/api/records/" in url else data

		return getter

	def test_zenodo_fetch_checks_license_and_md5_and_writes_provenance(self):
		ds = mfgdata.dataset(self.m, "cnc-changeover")
		folder = mfgdata.fetch(ds, Path(self.tmp.name), getter=self.zenodo())
		prov = json.loads((folder / "provenance.json").read_text())
		self.assertEqual("cc-by-4.0", prov["license"])
		self.assertEqual(["a.csv"], [f["name"] for f in prov["files"]])
		self.assertFalse((folder / "readme.pdf").exists())

	def test_other_license_is_refused(self):
		ds = mfgdata.dataset(self.m, "cnc-changeover")
		with self.assertRaises(mfgdata.FetchRefused):
			mfgdata.fetch(ds, Path(self.tmp.name), getter=self.zenodo("cc-by-nc-4.0"))

	@unittest.skipIf(os.name == "nt", "POSIX parent directory permissions")
	def test_writable_cache_does_not_require_writable_parent(self):
		parent = Path(self.tmp.name) / "readonly-parent"
		folder = parent / "writable-cache"
		folder.mkdir(parents=True)
		parent.chmod(0o555)
		try:
			ds = mfgdata.dataset(self.m, "cnc-changeover")
			mfgdata.fetch(ds, folder, getter=self.zenodo())
			self.assertTrue((folder / "a.csv").is_file())
			self.assertTrue((folder / "provenance.json").is_file())
			self.assertFalse(list(folder.glob(".fetch-dataset-*")))
		finally:
			parent.chmod(0o755)

	def test_checksum_mismatch_is_refused(self):
		ds = mfgdata.dataset(self.m, "cnc-changeover")
		with self.assertRaises(mfgdata.FetchRefused):
			mfgdata.fetch(ds, Path(self.tmp.name), getter=self.zenodo(checksum="md5:00"))

	def test_planned_dataset_is_not_fetched(self):
		with self.assertRaises(mfgdata.FetchRefused):
			mfgdata.fetch(mfgdata.dataset(self.m, "noboom"), Path(self.tmp.name), getter=lambda u: b"")

	def test_zip_is_extracted_and_cannot_escape(self):
		ds = mfgdata.dataset(self.m, "secom")
		good = _zip({"secom.data": "1 2\n", "secom_labels.data": '-1 "19/07/2008 11:55:00"\n'})
		folder = mfgdata.fetch(ds, Path(self.tmp.name) / "ok", getter=lambda u: good)
		self.assertTrue((folder / "secom.data").exists())
		bad = _zip({"../evil.txt": "x"})
		with self.assertRaises(mfgdata.FetchRefused):
			mfgdata.fetch(ds, Path(self.tmp.name) / "bad", getter=lambda u: bad)

	def test_pinned_sha256_mismatch_is_refused(self):
		ds = json.loads(json.dumps(mfgdata.dataset(self.m, "secom")))
		ds["source"]["sha256"] = "0" * 64
		with self.assertRaises(mfgdata.FetchRefused):
			mfgdata.fetch(ds, Path(self.tmp.name), getter=lambda u: _zip({"a": "b"}))


class TestArchiveWrites(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.TemporaryDirectory()
		self.addCleanup(self.tmp.cleanup)
		self.folder = Path(self.tmp.name) / "cache"
		self.folder.mkdir()
		(self.folder / "data.zip").write_bytes(b"previous archive")
		(self.folder / "existing.csv").write_bytes(b"previous data")
		(self.folder / "provenance.json").write_bytes(b"previous provenance")

	def snapshot(self):
		return {
			str(path.relative_to(self.folder)): path.read_bytes() if path.is_file() else None
			for path in self.folder.rglob("*")
		}

	def assert_refused_without_changes(self, data):
		before = self.snapshot()
		with self.assertRaises(mfgdata.FetchRefused):
			mfgdata._store(self.folder, "data.zip", data)
		self.assertEqual(self.snapshot(), before)

	def test_late_unsafe_members_preserve_existing_cache_and_publish_no_early_members(self):
		for name in ("../outside.csv", "nested/../../outside.csv", "..\\outside.csv", "nested/C:payload"):
			with self.subTest(name=name):
				self.assert_refused_without_changes(
					_zip({"existing.csv": "replacement", "new/data.csv": "new data", name: "invalid"})
				)

	def test_late_archive_links_including_directory_entries_preserve_existing_cache(self):
		for name in ("link", "link/"):
			member = zipfile.ZipInfo(name)
			member.create_system = 3
			member.external_attr = (stat.S_IFLNK | 0o777) << 16
			with self.subTest(name=name):
				self.assert_refused_without_changes(
					_zip({"existing.csv": "replacement", "new.csv": "new data", member: "../outside"})
				)

	def test_late_corrupt_member_preserves_existing_cache(self):
		data = _zip({"existing.csv": "replacement", "new.csv": "late corrupt payload"})
		data = data.replace(b"late corrupt payload", b"late invalid payload", 1)
		self.assert_refused_without_changes(data)

	def test_corrupt_directory_entry_preserves_existing_cache(self):
		data = _zip({"existing.csv": "replacement", "nested/": "late corrupt payload"})
		data = data.replace(b"late corrupt payload", b"late invalid payload", 1)
		self.assert_refused_without_changes(data)

	def test_truncated_archive_preserves_existing_cache(self):
		self.assert_refused_without_changes(_zip({"existing.csv": "replacement"})[:-15])

	def test_late_destination_conflict_preserves_existing_cache(self):
		self.assert_refused_without_changes(
			_zip({"new.csv": "new data", "existing.csv/nested.csv": "invalid"})
		)

	def test_conflicting_archive_members_preserve_existing_cache(self):
		for members in (
			{"new.csv": "new data", "new.csv/nested.csv": "invalid"},
			{"new.csv/nested.csv": "new data", "new.csv": "invalid"},
		):
			with self.subTest(members=members):
				self.assert_refused_without_changes(_zip(members))

	def test_failed_fetch_preserves_provenance_and_cached_archive(self):
		ds = mfgdata.dataset(mfgdata.load_manifest(), "secom")
		name = ds["source"]["url"].rsplit("/", 1)[-1]
		(self.folder / name).write_bytes(b"previous source archive")
		before = self.snapshot()
		with self.assertRaises(mfgdata.FetchRefused):
			mfgdata.fetch(
				ds, self.folder, getter=lambda url: _zip({"existing.csv": "replacement", "../bad": "x"})
			)
		self.assertEqual(self.snapshot(), before)

	@staticmethod
	def zenodo_files(payloads, *, invalid_checksum=False):
		ds = {
			"id": "multi-file",
			"title": "Multi-file fixture",
			"status": "enabled",
			"licenses": ["cc-by-4.0"],
			"source": {"type": "zenodo", "record": 1},
		}
		record = {
			"metadata": {"license": {"id": "cc-by-4.0"}},
			"files": [
				{
					"key": name,
					"checksum": "md5:"
					+ ("bad" if invalid_checksum and i == 1 else hashlib.md5(data).hexdigest()),
					"links": {"self": f"https://fixture.example/{name}"},
				}
				for i, (name, data) in enumerate(payloads.items())
			],
		}

		def getter(url):
			return json.dumps(record).encode() if "/api/records/" in url else payloads[url.rsplit("/", 1)[-1]]

		return ds, getter

	def test_late_second_zenodo_checksum_failure_preserves_every_cached_byte(self):
		before = self.snapshot()
		ds, getter = self.zenodo_files(
			{"existing.csv": b"replacement", "second.csv": b"second file"}, invalid_checksum=True
		)
		with self.assertRaises(mfgdata.FetchRefused):
			mfgdata.fetch(ds, self.folder, getter=getter)
		self.assertEqual(self.snapshot(), before)

	def test_late_second_zenodo_bad_zip_preserves_first_archive_extraction_and_provenance(self):
		before = self.snapshot()
		ds, getter = self.zenodo_files(
			{"data.zip": _zip({"existing.csv": "replacement", "new.csv": "new"}), "second.zip": b"not a ZIP"}
		)
		with self.assertRaises(mfgdata.FetchRefused):
			mfgdata.fetch(ds, self.folder, getter=getter)
		self.assertEqual(self.snapshot(), before)

	def test_valid_multifile_dataset_publishes_payloads_and_matching_provenance(self):
		payloads = {
			"data.zip": _zip({"existing.csv": "replacement", "nested/new.csv": "new"}),
			"second.csv": b"second file",
		}
		ds, getter = self.zenodo_files(payloads)
		mfgdata.fetch(ds, self.folder, getter=getter)
		self.assertEqual((self.folder / "existing.csv").read_text(), "replacement")
		self.assertEqual((self.folder / "nested/new.csv").read_text(), "new")
		self.assertEqual((self.folder / "second.csv").read_bytes(), payloads["second.csv"])
		self.assertEqual(
			[entry["name"] for entry in json.loads((self.folder / "provenance.json").read_text())["files"]],
			list(payloads),
		)

	def test_invalid_utf8_filename_is_normalized_to_fetch_refused(self):
		data = _zip({"existing.csv": "replacement", "é.csv": "invalid filename"})
		data = data.replace("é.csv".encode(), b"\xff\xff.csv")
		with self.assertRaises(UnicodeDecodeError):
			zipfile.ZipFile(io.BytesIO(data))
		self.assert_refused_without_changes(data)

	def test_corrupt_lzma_options_are_normalized_to_fetch_refused(self):
		buffer = io.BytesIO()
		with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_LZMA) as archive:
			archive.writestr("existing.csv", "replacement")
			archive.writestr("late.csv", "corrupt LZMA payload")
		data = bytearray(buffer.getvalue())
		with zipfile.ZipFile(io.BytesIO(data)) as archive:
			late = archive.getinfo("late.csv")
			payload_offset = late.header_offset + 30 + len(late.filename.encode()) + len(late.extra)
		# ZIP-LZMA stores four bytes of version/size then LZMA filter properties. 0xff is an
		# invalid lc/lp/pb property and makes the real decoder raise LZMAError, before CRC checking.
		data[payload_offset + 4] = 0xFF
		with self.assertRaises(lzma.LZMAError), zipfile.ZipFile(io.BytesIO(data)) as archive:
			archive.read("late.csv")
		self.assert_refused_without_changes(bytes(data))

	def test_valid_nested_archive_replaces_data_after_validation(self):
		data = _zip({"existing.csv": "replacement", "nested/": "", "nested/new.csv": "new data"})
		mfgdata._store(self.folder, "data.ZIP", data)
		self.assertEqual((self.folder / "existing.csv").read_text(), "replacement")
		self.assertEqual((self.folder / "nested" / "new.csv").read_text(), "new data")
		self.assertEqual((self.folder / "data.ZIP").read_bytes(), data)


class TestClearCache(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.TemporaryDirectory()
		self.addCleanup(self.tmp.cleanup)
		self.root = Path(self.tmp.name) / "cache"
		self.root.mkdir()
		patcher = mock.patch.object(mfgdata, "cache_root", return_value=self.root)
		patcher.start()
		self.addCleanup(patcher.stop)

	def test_deletes_only_selected_dataset_and_ignores_missing(self):
		for name in ("selected", "other"):
			folder = self.root / name
			folder.mkdir()
			(folder / "data").write_text("keep")
		mfgdata.clear_cache("selected")
		mfgdata.clear_cache("selected")
		self.assertFalse((self.root / "selected").exists())
		self.assertEqual((self.root / "other" / "data").read_text(), "keep")

	def test_refuses_symlinks_without_deleting_targets(self):
		other = self.root / "other"
		other.mkdir()
		outside = Path(self.tmp.name) / "outside"
		outside.mkdir()
		for target in (other, self.root, outside, self.root / "missing"):
			with self.subTest(target=target):
				entry = self.root / "selected"
				try:
					entry.symlink_to(target, target_is_directory=True)
				except OSError as error:
					self.skipTest(f"symlink creation is unavailable: {error}")
				with self.assertRaises(mfgdata.FetchRefused):
					mfgdata.clear_cache("selected")
				self.assertTrue(entry.is_symlink())
				self.assertTrue(other.is_dir())
				self.assertTrue(outside.is_dir())
				entry.unlink()

	def test_deletes_ordinary_nested_dataset_and_ignores_missing(self):
		selected = self.root / "group" / "selected"
		selected.mkdir(parents=True)
		(selected / "data").write_text("remove")
		other = selected.parent / "other"
		other.mkdir()
		(other / "data").write_text("keep")
		mfgdata.clear_cache("group/selected")
		mfgdata.clear_cache("group/selected")
		mfgdata.clear_cache("missing/selected")
		self.assertFalse(selected.exists())
		self.assertEqual((other / "data").read_text(), "keep")

	def test_refuses_intermediate_symlinks_into_another_dataset(self):
		other = self.root / "other"
		protected = other / "nested" / "selected"
		protected.mkdir(parents=True)
		(protected / "data").write_text("keep")
		entry = self.root / "alias"
		try:
			entry.symlink_to(other, target_is_directory=True)
		except OSError as error:
			self.skipTest(f"symlink creation is unavailable: {error}")
		for name in ("alias/nested/selected", "alias/nested/missing"):
			with self.subTest(name=name), self.assertRaises(mfgdata.FetchRefused):
				mfgdata.clear_cache(name)
		self.assertTrue(entry.is_symlink())
		self.assertEqual((protected / "data").read_text(), "keep")

	@unittest.skipUnless(os.name == "nt", "Windows junction regression")
	def test_refuses_junctions_at_every_dataset_path_component(self):
		other = self.root / "other"
		protected = other / "nested" / "selected"
		protected.mkdir(parents=True)
		(protected / "data").write_text("keep")
		entry = self.root / "alias"
		result = subprocess.run(
			["cmd", "/c", "mklink", "/J", str(entry), str(other)], capture_output=True, text=True
		)
		if result.returncode:
			self.skipTest(f"junction creation is unavailable: {result.stderr}")
		for name in ("alias", "alias/nested/selected", "alias/nested/missing"):
			with self.subTest(name=name), self.assertRaises(mfgdata.FetchRefused):
				mfgdata.clear_cache(name)
		self.assertTrue(entry.is_dir())
		self.assertEqual((protected / "data").read_text(), "keep")

	def test_refuses_unsafe_paths(self):
		for name in ("", ".", "..", "../outside", "nested/../../outside"):
			with self.subTest(name=name), self.assertRaises(mfgdata.FetchRefused):
				mfgdata.clear_cache(name)
		self.assertTrue(self.root.is_dir())


if __name__ == "__main__":
	unittest.main()
