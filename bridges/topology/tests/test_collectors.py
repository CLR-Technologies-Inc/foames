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

import io
import json
import os
import unittest
import urllib.error
from contextlib import redirect_stdout
from datetime import datetime

from foames_topology_collectors import __main__ as cli
from foames_topology_collectors import agents, network, sender

EXAMPLES = os.path.join(os.path.dirname(__file__), "..", "examples")
NOW = datetime(2026, 11, 15, 12, 0, 0)


def example(name):
	return os.path.join(EXAMPLES, name)


class TestNetwork(unittest.TestCase):
	def report(self, **kw):
		return network.report_from_status(
			network.read_status(example("tailscale-status.json")), provider="net", now=NOW, **kw
		)

	def test_hosts_and_tailnet(self):
		r = self.report()
		ids = {a["asset_id"]: a for a in r["assets"]}
		self.assertIn("network:example.org", ids)
		self.assertEqual(ids["host:gateway-1"]["status"], "OK")
		self.assertEqual(ids["host:line-2-hmi"]["status"], "Down")
		self.assertEqual(ids["host:line-2-hmi"]["last_seen"], "2026-11-15 08:30:00")
		self.assertEqual(ids["host:gpu-box"]["attributes"]["tags"], ["tag:agents"])
		self.assertEqual(len(r["links"]), 3)
		self.assertTrue(all(link["link_type"] == "Network" for link in r["links"]))
		self.assertTrue(r["retire_missing"])

	def test_site(self):
		r = self.report(site="Plant A")
		ids = {a["asset_id"]: a for a in r["assets"]}
		self.assertEqual(ids["host:gpu-box"]["parent_asset"], "site:plant-a")
		self.assertEqual(ids["site:plant-a"]["kind"], "Site")


class TestAgents(unittest.TestCase):
	def report(self, **kw):
		with open(example("agent-events.jsonl")) as f:
			events, skipped = agents.read_events(f)
		self.assertEqual(skipped, 0)
		return agents.report_from_events(events, provider="agents", now=NOW, **kw)

	def test_latest_event_per_task_wins(self):
		ids = {a["asset_id"]: a for a in self.report()["assets"]}
		self.assertEqual(ids["task:T-11"]["status"], "OK")
		self.assertEqual(ids["task:T-12"]["status"], "Idle")
		self.assertEqual(ids["agent:planner"]["kind"], "Agent")

	def test_delegation_and_hosts(self):
		r = self.report()
		links = {(x["from_asset"], x["link_type"], x["to_asset"]) for x in r["links"]}
		self.assertIn(("agent:orchestrator", "Delegates", "agent:planner"), links)
		self.assertIn(("task:T-10", "Delegates", "task:T-11"), links)
		self.assertIn(("agent:planner", "Delegates", "task:T-11"), links)
		self.assertIn(("agent:planner", "Runs On", "host:gpu-box"), links)
		self.assertEqual(
			r["bindings"], [{"signal": "task:T-12", "physical_asset": "machine:P-201", "direction": "Write"}]
		)

	def test_window(self):
		r = self.report(window_hours=1)
		self.assertEqual(r["assets"], [])

	def test_bad_lines_are_skipped(self):
		events, skipped = agents.read_events(
			["not json", "[]", '{"agent": "a"}', '{"agent": "a", "task": 1}', ""]
		)
		self.assertEqual((len(events), skipped), (1, 3))


class FakeResponse(io.BytesIO):
	def __enter__(self):
		return self

	def __exit__(self, *a):
		return False


class TestSender(unittest.TestCase):
	def test_send_posts_with_token(self):
		seen = {}

		def opener(request, timeout):
			seen["url"] = request.full_url
			seen["auth"] = request.get_header("Authorization")
			seen["body"] = json.loads(request.data)
			return FakeResponse(b'{"message": {"inserted": 2}}')

		out = sender.send({"provider": "p"}, "https://site/", "k", "s", opener=opener)
		self.assertEqual(out, {"inserted": 2})
		self.assertEqual(seen["url"], "https://site" + sender.INGEST_PATH)
		self.assertEqual(seen["auth"], "token k:s")
		self.assertEqual(seen["body"], {"report": {"provider": "p"}})

	def test_retries_then_gives_up(self):
		calls = []

		def opener(request, timeout):
			calls.append(1)
			raise urllib.error.URLError("down")

		with self.assertRaises(sender.SendError):
			sender.send({}, "https://site", "k", "s", opener=opener, retries=2, sleep=lambda s: None)
		self.assertEqual(len(calls), 3)

	def test_4xx_is_not_retried(self):
		calls = []

		def opener(request, timeout):
			calls.append(1)
			raise urllib.error.HTTPError(request.full_url, 403, "no", {}, io.BytesIO(b"denied"))

		with self.assertRaises(sender.SendError):
			sender.send({}, "https://site", "k", "s", opener=opener, sleep=lambda s: None)
		self.assertEqual(len(calls), 1)


class TestCli(unittest.TestCase):
	def test_dry_run(self):
		out = io.StringIO()
		with redirect_stdout(out):
			code = cli.main(
				[
					"network",
					"--provider",
					"net",
					"--status-file",
					example("tailscale-status.json"),
					"--dry-run",
				]
			)
		self.assertEqual(code, 0)
		self.assertEqual(json.loads(out.getvalue())["provider"], "net")


if __name__ == "__main__":
	unittest.main()
