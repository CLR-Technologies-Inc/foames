# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Self-tests for the CNC equipment study (lathe and milling fleet). Offline: synthetic fixtures,
a fake Kaggle downloader, and planted FoaMES defects the checks must catch."""

import base64
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from foames_bench import machining, mfgdata


def _zip_folder(folder: Path) -> bytes:
	buf = io.BytesIO()
	with zipfile.ZipFile(buf, "w") as zf:
		for p in sorted(folder.rglob("*")):
			if p.is_file():
				zf.write(p, p.relative_to(folder).as_posix())
	return buf.getvalue()


class StudyBase(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.TemporaryDirectory()
		self.addCleanup(self.tmp.cleanup)
		self.root = Path(self.tmp.name)
		self.m = mfgdata.load_manifest()
		mfgdata._foames("oee")

	def run_ds(self, ds_id, stage="dev"):
		ds = mfgdata.dataset(self.m, ds_id)
		folder = mfgdata.synthetic(ds_id, self.root / ds_id)
		return mfgdata.validate(ds, folder, self.m["stages"][stage], stage, True)

	def failed(self, res):
		return {c.id for c in res.checks if not c.passed}


class TestLathe(StudyBase):
	def test_passes_and_reports_the_study(self):
		res = self.run_ds("cnc-turning-xquality")
		self.assertTrue(res.passed, mfgdata.render([res]))
		m = res.metrics
		self.assertEqual(62, m["parts"])
		self.assertEqual(20, len(m["baseline_parts"]))
		self.assertEqual({"test 2", "test 3", "test 4"}, set(m["sensors_by_deviation"]))
		self.assertEqual(3, m["fleet_ecl"])
		self.assertIn("### Equipment study: CNC lathe", "\n".join(res.notes))
		# The synthetic wrong-tool batch is planted on vibration: the study must say so.
		self.assertIn("VIB_1_RMS", m["sensors_by_deviation"]["test 4"][0]["feature"])

	def test_features_spread_over_both_operations(self):
		res = self.run_ds("cnc-turning-xquality", "smoke")
		self.assertTrue(res.passed, mfgdata.render([res]))
		self.assertEqual(5, res.metrics["features_charted"])
		top = [r["feature"] for rows in res.metrics["sensors_by_deviation"].values() for r in rows]
		self.assertTrue(any(f.startswith("OP120/") for f in top) and any(f.startswith("OP130/") for f in top))

	def test_catches_wrong_spc_limits(self):
		from foames.foames_mes import spc

		real = spc.imr_chart

		def wide(values, baseline=None, rules="Nelson"):
			chart = real(values, baseline, rules)
			chart["individuals"]["lcl"] -= 1.0
			return chart

		with mock.patch.object(spc, "imr_chart", wide):
			res = self.run_ds("cnc-turning-xquality", "smoke")
		self.assertIn("spc/imr-limits", self.failed(res))

	def test_catches_energy_kpi_that_divides_by_zero_output(self):
		from foames.foames_mes import kpi

		with mock.patch.object(kpi, "specific_consumption", lambda r, o: float(r) / max(float(o), 1e-9)):
			res = self.run_ds("cnc-turning-xquality", "smoke")
		self.assertIn("kpi/energy-per-part", self.failed(res))

	def test_catches_ecl_profile_that_drifts_from_the_recommended_floors(self):
		from foames.foames_mes import ecl

		levels = {k: dict(v) for k, v in ecl.LEVELS.items()}
		levels[3]["min_tier"] = "oss"
		with mock.patch.object(ecl, "LEVELS", levels):
			res = self.run_ds("cnc-turning-xquality", "smoke")
		self.assertIn("ecl/profile-matches-recommended-floors", self.failed(res))

	def test_crv_reader_skips_header_and_reads_semicolons(self):
		f = self.root / "a.crv"
		f.write_text("Time (s);AI1 (W)\n0.001;126.95\n0.002;122.43\n")
		self.assertEqual(([0.001, 0.002], [126.95, 122.43]), machining.read_crv(f))

	def test_missing_label_column_names_the_headers(self):
		folder = self.root / "odd"
		folder.mkdir()
		(folder / "labels.csv").write_text("part,status\npart_020,ok\n")
		ds = mfgdata.dataset(self.m, "cnc-turning-xquality")
		res = mfgdata.validate(ds, folder, self.m["stages"]["smoke"], "smoke", False)
		self.assertIn("status", res.error)


class TestMillingFleet(StudyBase):
	def test_passes_and_reports_transfer(self):
		res = self.run_ds("cnc-milling-vibration")
		self.assertTrue(res.passed, mfgdata.render([res]))
		m = res.metrics
		self.assertEqual(["M01", "M02", "M03"], m["machines"])
		self.assertEqual(18, m["transfer_pairs"])
		self.assertEqual({"M01", "M02", "M03"}, set(m["per_machine"]))
		self.assertIn("### Equipment study: CNC milling fleet", "\n".join(res.notes))

	def test_stage_budget_spreads_over_groups(self):
		ds = mfgdata.dataset(self.m, "cnc-milling-vibration")
		folder = mfgdata.synthetic("cnc-milling-vibration", self.root / "mill")
		full = machining.load_milling(folder, ds, None)["files"]
		data = machining.load_milling(folder, ds, 54)
		groups = {(r["machine"], r["op"]) for r in data["files"]}
		self.assertEqual(9, len(groups))
		self.assertLess(len(data["files"]), len(full))
		for key in groups:
			# A budget keeps each group's baseline: its earliest good recordings, not a sample of them.
			def base(rs, key=key):
				return [r["file"] for r in rs if (r["machine"], r["op"]) == key and r["baseline"]]

			self.assertEqual(base(full), base(data["files"]))
			self.assertGreaterEqual(len(base(full)), 8)

	def test_headerless_and_unnamed_columns(self):
		ds = mfgdata.dataset(self.m, "cnc-milling-vibration")
		f = self.root / "M01_Aug_2019_OP00_000.csv"
		f.write_text("1,2,3\n4,5,6\n")
		self.assertEqual([(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)], machining._mill_rows(f, ds["columns"]))
		f.write_text("idx,a,b,c\n0,1,2,3\n1,4,5,6\n")
		self.assertEqual([(1.0, 2.0, 3.0), (4.0, 5.0, 6.0)], machining._mill_rows(f, ds["columns"]))
		f.write_text("0,1,2\n7,8,9\n")
		self.assertEqual([(7.0, 8.0, 9.0)], machining._mill_rows(f, {"axes": [["0", "1", "2"]]}))
		f.write_text("Z,Y,X,t\n3,2,1,0\n")
		self.assertEqual([(1.0, 2.0, 3.0)], machining._mill_rows(f, ds["columns"]))

	def test_catches_wrong_signals(self):
		from foames.foames_mes import spc

		real = spc.imr_chart

		def quiet(values, baseline=None, rules="Nelson"):
			chart = real(values, baseline, rules)
			chart["individuals"]["signals"] = []
			return chart

		with mock.patch.object(spc, "imr_chart", quiet):
			res = self.run_ds("cnc-milling-vibration", "smoke")
		self.assertIn("spc/beyond-limit-signals", self.failed(res))

	def test_no_files_names_the_expected_layout(self):
		folder = self.root / "empty"
		folder.mkdir()
		ds = mfgdata.dataset(self.m, "cnc-milling-vibration")
		res = mfgdata.validate(ds, folder, self.m["stages"]["smoke"], "smoke", False)
		self.assertIn("M01_Aug_2019_OP00_000.csv", res.error)


class TestKaggle(unittest.TestCase):
	def setUp(self):
		self.tmp = tempfile.TemporaryDirectory()
		self.addCleanup(self.tmp.cleanup)
		self.root = Path(self.tmp.name)
		self.m = mfgdata.load_manifest()

	def test_license_normalisation(self):
		lic = mfgdata.kaggle_license
		self.assertEqual("cc-by-4.0", lic({"licenseName": "Attribution 4.0 International (CC BY 4.0)"}))
		self.assertEqual("cc-by-4.0", lic({"licenses": [{"name": "CC-BY-4.0"}]}))
		self.assertEqual("cc0-1.0", lic({"licenses": [{"name": "CC0-1.0"}]}))
		self.assertEqual("apache-2.0", lic({"licenseName": "Apache 2.0"}))
		for refused in (
			"CC BY-SA 4.0",
			"Attribution-NonCommercial 4.0 International (CC BY-NC 4.0)",
			"CC-BY-NC-SA-4.0",
		):
			self.assertNotEqual("cc-by-4.0", lic({"licenseName": refused}), refused)
		self.assertEqual("", lic({}))

	def test_credentials(self):
		self.assertEqual("Bearer t", mfgdata.kaggle_auth({"KAGGLE_API_TOKEN": "t"}))
		basic = mfgdata.kaggle_auth({"KAGGLE_USERNAME": "u", "KAGGLE_KEY": "k"})
		self.assertEqual("u:k", base64.b64decode(basic.split()[1]).decode())
		cfg = self.root / "cfg"
		cfg.mkdir()
		(cfg / "kaggle.json").write_text('{"username": "a", "key": "b"}')
		self.assertTrue(mfgdata.kaggle_auth({"KAGGLE_CONFIG_DIR": str(cfg)}).startswith("Basic "))
		self.assertIsNone(mfgdata.kaggle_auth({"KAGGLE_CONFIG_DIR": str(self.root / "none")}))

	def fake(self, license_name, archive):
		calls = []

		def getter(url):
			calls.append(url)
			if "/datasets/view/" in url:
				return json.dumps({"licenseName": license_name, "currentVersionNumber": 2}).encode()
			return archive

		return getter, calls

	def test_fetch_checks_license_and_extracts(self):
		ds = mfgdata.dataset(self.m, "cnc-turning-xquality")
		src = mfgdata.synthetic("cnc-turning-xquality", self.root / "src")
		getter, calls = self.fake("Attribution 4.0 International (CC BY 4.0)", _zip_folder(src))
		folder = mfgdata.fetch(ds, self.root / "cache", getter=getter)
		prov = json.loads((folder / "provenance.json").read_text())
		self.assertEqual("cc-by-4.0", prov["license"])
		self.assertEqual(2, prov["version"])
		self.assertTrue(any("/datasets/download/cetimai/xquality-cnc-turning-data" in c for c in calls))
		res = mfgdata.validate(ds, folder, self.m["stages"]["smoke"], "smoke", False)
		self.assertTrue(res.passed, mfgdata.render([res]))

	def test_fetch_refuses_another_license_before_downloading(self):
		ds = mfgdata.dataset(self.m, "cnc-milling-vibration")
		getter, calls = self.fake("CC BY-NC-SA 4.0", b"")
		with self.assertRaises(mfgdata.FetchRefused):
			mfgdata.fetch(ds, self.root / "cache", getter=getter)
		self.assertFalse(any("/download/" in c for c in calls))

	def test_fetch_without_credentials_points_to_import(self):
		ds = mfgdata.dataset(self.m, "cnc-turning-xquality")
		with mock.patch.object(mfgdata, "kaggle_auth", return_value=None):
			with self.assertRaisesRegex(mfgdata.FetchRefused, "data import cnc-turning-xquality"):
				mfgdata.fetch(ds, self.root / "cache")

	def test_credentials_are_not_sent_on_redirect(self):
		seen = {}

		class Resp(io.BytesIO):
			def __enter__(self):
				return self

			def __exit__(self, *a):
				return False

		def urlopen(req, timeout=None):
			seen["redirected"] = req.headers
			seen["unredirected"] = req.unredirected_hdrs
			return Resp(b"ok")

		with mock.patch("urllib.request.urlopen", urlopen):
			mfgdata._get("https://www.kaggle.com/api/v1/x", auth="Basic abc")
		self.assertNotIn("Authorization", seen["redirected"])
		self.assertEqual("Basic abc", seen["unredirected"]["Authorization"])

	def test_import_a_hand_downloaded_archive(self):
		ds = mfgdata.dataset(self.m, "cnc-milling-vibration")
		src = mfgdata.synthetic("cnc-milling-vibration", self.root / "src")
		archive = self.root / "cnc-machining-data.zip"
		archive.write_bytes(_zip_folder(src))
		folder = mfgdata.import_archive(ds, archive, self.root / "cache")
		prov = json.loads((folder / "provenance.json").read_text())
		self.assertEqual("manual download", prov["imported_from"])
		self.assertEqual("cc-by-4.0", prov["license"])
		res = mfgdata.validate(ds, folder, self.m["stages"]["smoke"], "smoke", False)
		self.assertTrue(res.passed, mfgdata.render([res]))

	def test_import_reads_the_cache_inbox(self):
		ds = mfgdata.dataset(self.m, "cnc-turning-xquality")
		src = mfgdata.synthetic("cnc-turning-xquality", self.root / "src")
		with mock.patch.object(mfgdata, "cache_root", return_value=self.root / "cache"):
			with self.assertRaisesRegex(mfgdata.FetchRefused, "_inbox"):
				mfgdata.import_archive(ds)
			inbox = mfgdata.inbox_path(ds)
			inbox.parent.mkdir(parents=True)
			inbox.write_bytes(_zip_folder(src))
			folder = mfgdata.import_archive(ds)
		self.assertEqual(self.root / "cache" / "cnc-turning-xquality", folder)
		self.assertTrue((folder / "provenance.json").is_file())

	def test_import_command_line(self):
		from foames_bench import cli

		ds = mfgdata.dataset(self.m, "cnc-turning-xquality")
		src = mfgdata.synthetic("cnc-turning-xquality", self.root / "src")
		with mock.patch.object(mfgdata, "cache_root", return_value=self.root / "cache"):
			inbox = mfgdata.inbox_path(ds)
			inbox.parent.mkdir(parents=True)
			inbox.write_bytes(_zip_folder(src))
			with mock.patch("sys.stdout", new_callable=io.StringIO):
				code = cli.main(["data", "import", "cnc-turning-xquality"])
		self.assertEqual(0, code)
		self.assertTrue((self.root / "cache" / "cnc-turning-xquality" / "provenance.json").is_file())

	def test_import_refuses_unverified_license(self):
		ds = json.loads(json.dumps(mfgdata.dataset(self.m, "cnc-milling-vibration")))
		ds["license_verified"] = False
		archive = self.root / "a.zip"
		archive.write_bytes(b"PK")
		with self.assertRaises(mfgdata.FetchRefused):
			mfgdata.import_archive(ds, archive, self.root / "cache")


if __name__ == "__main__":
	unittest.main()
