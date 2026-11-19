# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

import base64
import copy
import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch

from foames_topology_collectors import __main__ as cli
from foames_topology_collectors import network, sender, wireguard

NOW = datetime(2026, 11, 18, 12, tzinfo=timezone.utc)
KEY = base64.b64encode(bytes(range(32))).decode()
KEY2 = base64.b64encode(bytes(range(32, 64))).decode()
ROOT = Path(__file__).resolve().parents[3]
EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "wireguard-status.json"


def snapshot():
	return {
		"observed_at": NOW.isoformat(),
		"interfaces": [
			{
				"name": "wg0",
				"peers": [
					{
						"public_key": KEY,
						"endpoint": "[2001:db8::1]:51820",
						"allowed_ips": ["10.10.0.0/24", "2001:db8:1::/64"],
						"latest_handshake": int(NOW.timestamp()) - 60,
						"transfer_rx": 1234,
						"transfer_tx": 5678,
						"persistent_keepalive": 25,
					}
				],
			}
		],
	}


def report(status=None, **kwargs):
	return wireguard.report_from_status(
		status or snapshot(), provider="wg-gateway-1", host="gateway-1", now=NOW, **kwargs
	)


def peer_asset(result):
	return next(asset for asset in result["assets"] if asset["kind"] == "Host")


class TestWireGuardReport(unittest.TestCase):
	def test_recent_peer_and_interface_observation(self):
		result = report(site="Plant A", tenant="Plant A")
		peer = peer_asset(result)
		self.assertEqual(peer["status"], "OK")
		self.assertEqual(peer["last_seen"], "2026-11-18 11:59:00")
		self.assertEqual(peer["attributes"]["handshake_age_seconds"], 60)
		self.assertEqual(peer["attributes"]["transfer_rx"], 1234)
		self.assertEqual(peer["attributes"]["endpoint"], "[2001:db8::1]:51820")
		self.assertEqual(result["links"][0]["status"], "OK")
		self.assertTrue(result["retire_missing"])
		self.assertEqual(result["tenant"], "Plant A")
		interface = next(a for a in result["assets"] if a["kind"] == "Network Device")
		self.assertEqual(interface["status"], "Unknown")
		self.assertEqual(interface["last_seen"], "2026-11-18 12:00:00")

	def test_handshake_boundaries_never_stale_and_future(self):
		for age, expected in (
			(0, "recent"),
			(180, "recent"),
			(181, "stale"),
			(-1, "clock-skew"),
			(None, "never"),
		):
			with self.subTest(age=age):
				status = snapshot()
				status["interfaces"][0]["peers"][0]["latest_handshake"] = (
					int(NOW.timestamp()) - age if age is not None else 0
				)
				result = report(status)
				peer = peer_asset(result)
				self.assertEqual(peer["attributes"]["handshake_health"], expected)
				self.assertEqual(peer["status"], "OK" if expected == "recent" else "Unknown")
				self.assertEqual(result["links"][0]["status"], peer["status"])
				if age is None or age < 0:
					self.assertIsNone(peer["last_seen"])

	def test_stale_and_future_snapshots_cannot_claim_health_or_retire(self):
		for offset in (-181, 1):
			with self.subTest(offset=offset):
				status = snapshot()
				status["observed_at"] = (NOW + timedelta(seconds=offset)).isoformat()
				peer = status["interfaces"][0]["peers"][0]
				peer["latest_handshake"] = int(NOW.timestamp()) + offset - 60
				result = report(status)
				self.assertEqual(peer_asset(result)["status"], "Unknown")
				self.assertFalse(result["retire_missing"])

	def test_handshake_after_observation_is_unknown_even_when_in_the_past(self):
		status = snapshot()
		status["observed_at"] = (NOW - timedelta(seconds=120)).isoformat()
		self.assertEqual(peer_asset(report(status))["attributes"]["handshake_health"], "clock-skew")

	def test_stable_ids_survive_endpoint_roaming_and_order_changes(self):
		before = report()
		status = snapshot()
		status["interfaces"][0]["peers"][0]["endpoint"] = "192.0.2.20:12345"
		self.assertEqual(peer_asset(before)["asset_id"], peer_asset(report(status))["asset_id"])
		for field, value in (("host", "gateway-2"), ("provider", "different-collector")):
			kwargs = {"provider": "wg-gateway-1", "host": "gateway-1", field: value}
			other = wireguard.report_from_status(status, now=NOW, **kwargs)
			self.assertNotEqual(peer_asset(before)["asset_id"], peer_asset(other)["asset_id"])
		status["interfaces"].append(copy.deepcopy(status["interfaces"][0]))
		status["interfaces"][1]["name"] = "wg1"
		ids = [asset["asset_id"] for asset in report(status)["assets"]]
		self.assertEqual(len(ids), len(set(ids)))

	def test_unknown_fields_never_reach_snapshot_or_report(self):
		status = snapshot()
		status["private_key"] = "DO-NOT-EXPORT-ROOT"
		status["interfaces"][0]["private_key"] = "DO-NOT-EXPORT-INTERFACE"
		status["interfaces"][0]["peers"][0]["preshared_key"] = "DO-NOT-EXPORT-PEER"
		self.assertNotIn("DO-NOT-EXPORT", json.dumps(wireguard.clean_status(status)))
		self.assertNotIn("DO-NOT-EXPORT", json.dumps(report(status)))

	def test_malformed_snapshots_are_rejected(self):
		bad = [
			None,
			{},
			{"observed_at": NOW.isoformat(), "interfaces": {}},
			{"observed_at": "2026-11-18T12:00:00", "interfaces": []},
		]
		for field, value in (
			("public_key", "invalid"),
			("latest_handshake", -1),
			("transfer_rx", 1.2),
			("transfer_tx", True),
			("latest_handshake", 2**63),
			("allowed_ips", ["bad"]),
			("persistent_keepalive", 65536),
			("endpoint", {}),
		):
			status = snapshot()
			status["interfaces"][0]["peers"][0][field] = value
			bad.append(status)
		status = snapshot()
		status["interfaces"][0]["peers"].append(copy.deepcopy(status["interfaces"][0]["peers"][0]))
		bad.append(status)
		for status in bad:
			with self.subTest(status=status), self.assertRaises(wireguard.StatusError):
				wireguard.clean_status(status)

	def test_timezone_and_custom_window(self):
		status = snapshot()
		status["observed_at"] = "2026-11-18T04:00:00-08:00"
		self.assertEqual(peer_asset(report(status))["status"], "OK")
		self.assertEqual(peer_asset(report(status, handshake_max_age=30))["status"], "Unknown")

	def test_report_passes_real_ingestion_rules_alongside_tailscale(self):
		if not (ROOT / "foames" / "foames_topology" / "ingest.py").exists():
			self.skipTest("FoaMES checkout is needed for ingestion contract verification")
		with patch.object(sys, "path", [str(ROOT), *sys.path]):
			from foames.foames_topology.ingest import normalize_report
		tailscale = network.report_from_status(
			{"Self": {"HostName": "gateway-1"}}, provider="tailscale", site="Plant A"
		)
		existing = {a["asset_id"]: {"provider": "tailscale", "managed": 1} for a in tailscale["assets"]}
		result = normalize_report(report(site="Plant A"), existing)
		self.assertEqual(result["rejected"], [])
		self.assertEqual(len(result["assets"]), 3)
		self.assertEqual(len(result["links"]), 1)


class TestWireGuardRead(unittest.TestCase):
	@staticmethod
	def outputs():
		return {
			("interfaces",): "wg0 wg1\n",
			("wg0", "endpoints"): f"{KEY}\t[2001:db8::1]:51820\n{KEY2}\t(none)\n",
			("wg0", "allowed-ips"): f"{KEY}\t10.10.0.0/24 2001:db8:1::/64\n{KEY2}\t(none)\n",
			("wg0", "latest-handshakes"): f"{KEY}\t1795003140\n{KEY2}\t0\n",
			("wg0", "transfer"): f"{KEY}\t1234\t5678\n{KEY2}\t0\t0\n",
			("wg0", "persistent-keepalive"): f"{KEY}\t25\n{KEY2}\toff\n",
			**{("wg1", field): "" for field in wireguard.FIELDS},
		}

	def test_live_collection_uses_only_safe_fields_and_keeps_empty_interfaces(self):
		outputs = self.outputs()

		def run(command, **kwargs):
			self.assertEqual(command[:2], ["wg", "show"])
			self.assertEqual(kwargs, {"check": True, "capture_output": True, "text": True, "timeout": 10})
			return subprocess.CompletedProcess(command, 0, stdout=outputs[tuple(command[2:])], stderr="")

		with patch.object(wireguard.subprocess, "run", side_effect=run) as invoked:
			status = wireguard.read_status()
		self.assertEqual(len(invoked.call_args_list), 12)
		peer = status["interfaces"][0]["peers"][1]
		self.assertIsNone(peer["endpoint"])
		self.assertEqual(peer["allowed_ips"], [])
		self.assertEqual(peer["persistent_keepalive"], 0)
		self.assertEqual(status["interfaces"][1], {"name": "wg1", "peers": []})
		self.assertEqual(
			status["interfaces"][0]["peers"][0]["allowed_ips"],
			snapshot()["interfaces"][0]["peers"][0]["allowed_ips"],
		)

	def test_failed_reads_hide_subprocess_details(self):
		for error in (
			FileNotFoundError("sensitive-detail"),
			PermissionError("sensitive-detail"),
			subprocess.CalledProcessError(1, "wg", stderr="sensitive-detail"),
			subprocess.TimeoutExpired("wg", 10, output="sensitive-detail"),
		):
			with (
				patch.object(wireguard.subprocess, "run", side_effect=error),
				self.assertRaises(wireguard.StatusError) as caught,
			):
				wireguard.read_status()
			self.assertNotIn("sensitive-detail", str(caught.exception))

	def test_stderr_alongside_success_is_refused(self):
		with (
			patch.object(
				wireguard.subprocess,
				"run",
				return_value=subprocess.CompletedProcess([], 0, "wg0", "failure"),
			),
			self.assertRaises(wireguard.StatusError),
		):
			wireguard.read_status()

	def test_peer_changes_and_malformed_rows_are_refused(self):
		for value in ("", f"{KEY}\t1\n", f"{KEY}\t1\t2\n{KEY}\t1\t2\n"):
			outputs = self.outputs()
			outputs[("wg0", "transfer")] = value
			with (
				patch.object(wireguard, "_show", side_effect=lambda *args: outputs[args]),
				self.assertRaises(wireguard.StatusError),
			):
				wireguard.read_status()

	def test_interface_changes_are_refused(self):
		outputs = self.outputs()
		calls = []

		def show(*args):
			calls.append(args)
			return "wg0" if len(calls) == 12 else outputs[args]

		with patch.object(wireguard, "_show", side_effect=show), self.assertRaises(wireguard.StatusError):
			wireguard.read_status()

	def test_no_interfaces_is_a_valid_empty_report(self):
		with patch.object(wireguard, "_show", return_value=""):
			status = wireguard.read_status()
		result = wireguard.report_from_status(status, provider="p", host="h")
		self.assertEqual(result["assets"], [])
		self.assertTrue(result["retire_missing"])


class TestWireGuardCli(unittest.TestCase):
	args = ("wireguard", "--provider", "wg-gateway-1", "--host-name", "gateway-1")

	def test_failure_does_not_send_or_print_partial_report(self):
		out, err = io.StringIO(), io.StringIO()
		with (
			patch.object(wireguard, "read_status", side_effect=wireguard.StatusError("Cannot read status")),
			patch.object(sender, "send") as send,
			redirect_stdout(out),
			redirect_stderr(err),
		):
			code = cli.main([*self.args, "--url", "https://foames.example.com"])
		self.assertEqual(code, 2)
		self.assertEqual(out.getvalue(), "")
		send.assert_not_called()

	def test_invalid_options_fail_before_reading(self):
		for args in (["--handshake-max-age", "0"], ["--snapshot", "--url", "https://foames.example.com"]):
			with (
				patch.object(wireguard, "read_status") as read,
				redirect_stderr(io.StringIO()),
				self.assertRaises(SystemExit),
			):
				cli.main([*self.args, *args])
			read.assert_not_called()

	def test_snapshot_and_dry_run_as_real_cli_processes(self):
		with tempfile.TemporaryDirectory() as folder:
			path = Path(folder) / "status.json"
			result = subprocess.run(
				[
					sys.executable,
					"-m",
					"foames_topology_collectors",
					*self.args,
					"--status-file",
					str(EXAMPLE),
					"--snapshot",
				],
				capture_output=True,
				text=True,
				check=True,
			)
			path.write_text(result.stdout, encoding="utf-8")
			result = subprocess.run(
				[
					sys.executable,
					"-m",
					"foames_topology_collectors",
					*self.args,
					"--status-file",
					str(path),
					"--dry-run",
				],
				capture_output=True,
				text=True,
				check=True,
			)
			self.assertEqual(json.loads(result.stdout)["provider"], "wg-gateway-1")
			self.assertTrue(any(a["kind"] == "Host" for a in json.loads(result.stdout)["assets"]))

	def test_cli_posts_report_to_http_endpoint(self):
		seen = {}

		class Handler(BaseHTTPRequestHandler):
			def do_POST(self):
				seen["path"] = self.path
				seen["auth"] = self.headers["Authorization"]
				seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
				self.send_response(200)
				self.end_headers()
				self.wfile.write(b'{"message":{"inserted":2}}')

			def log_message(self, *args):
				# silenced: request logs are noise in tests
				pass

		with HTTPServer(("127.0.0.1", 0), Handler) as server:
			thread = threading.Thread(target=server.serve_forever, daemon=True)
			thread.start()
			try:
				with (
					patch.object(wireguard, "read_status", return_value=snapshot()),
					patch.dict(
						os.environ, {"FOAMES_API_KEY": "test-key", "FOAMES_API_SECRET": "test-secret"}
					),
					redirect_stdout(io.StringIO()),
				):
					code = cli.main([*self.args, "--url", f"http://127.0.0.1:{server.server_port}"])
			finally:
				server.shutdown()
				thread.join(timeout=5)
		self.assertEqual(code, 0)
		self.assertEqual(seen["path"], sender.INGEST_PATH)
		self.assertEqual(seen["auth"], "token test-key:test-secret")
		self.assertEqual(seen["body"]["report"]["provider"], "wg-gateway-1")


if __name__ == "__main__":
	unittest.main()
