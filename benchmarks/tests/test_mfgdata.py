# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Self-tests for the manufacturing-data track. Offline: synthetic fixtures and a fake downloader."""

import hashlib
import io
import json
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


class TestFetch(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.TemporaryDirectory()
		self.addCleanup(self.tmp.cleanup)
		self.m = mfgdata.load_manifest()

	def zenodo(self, license_id="cc-by-4.0", data=b"timestamp,session,phase\n", checksum=None):
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


if __name__ == "__main__":
	unittest.main()
