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

"""The pure rules of read-only mode: no site needed.

python -m unittest foames.foames_kernel.test_write_policy
"""

import unittest

from foames.foames_kernel import write_policy as p


class TestDecide(unittest.TestCase):
	def test_read_write_only_when_both_are_off(self):
		self.assertEqual(p.decide(False, False), p.ALLOW)
		self.assertEqual(p.decide(True, False), p.QUEUE)
		self.assertEqual(p.decide(False, True), p.QUEUE)

	def test_site_switch_overrides_a_writable_policy(self):
		self.assertEqual(p.decide(True, False, p.SITE_DEFAULT, p.BLOCK), p.BLOCK)

	def test_policy_action_wins_over_site_action(self):
		self.assertEqual(p.decide(False, True, p.BLOCK, p.QUEUE), p.BLOCK)
		self.assertEqual(p.decide(False, True, p.QUEUE, p.BLOCK), p.QUEUE)
		self.assertEqual(p.decide(False, True, p.SITE_DEFAULT, p.BLOCK), p.BLOCK)

	def test_unknown_actions_fall_back_to_queue(self):
		self.assertEqual(p.decide(True, True, "nonsense", None), p.QUEUE)


class TestContext(unittest.TestCase):
	def test_reads_common_spellings(self):
		ctx = p.context_of({"workOrder": "WO-1", "jobCard": "JC-7", "batch": "B-3", "machineId": "M-2"})
		self.assertEqual(
			ctx, {"work_order": "WO-1", "job_card": "JC-7", "process_run": "B-3", "machine": "M-2"}
		)

	def test_explicit_values_win_and_nested_values_are_found(self):
		ctx = p.context_of({"body": {"work_order": "WO-9"}, "job_card": "JC-1"}, {"job_card": "JC-2"})
		self.assertEqual(ctx["work_order"], "WO-9")
		self.assertEqual(ctx["job_card"], "JC-2")

	def test_ignores_non_scalars_and_cuts_long_values(self):
		ctx = p.context_of({"order": {"id": 1}, "work_order": ["x"], "machine": "M" * 500, "job": True})
		self.assertEqual(ctx["work_order"], "")
		self.assertEqual(ctx["job_card"], "")
		self.assertEqual(len(ctx["machine"]), 140)

	def test_non_dict_payload(self):
		self.assertEqual(p.context_of(None), {k: "" for k in p.CONTEXT_FIELDS})


class TestHashes(unittest.TestCase):
	def test_payload_hash_is_stable_and_order_free(self):
		a = p.payload_hash("ERPNext", p.KIND_OUTBOX, "Manufacture", {"qty": 5, "work_order": "WO"})
		b = p.payload_hash("ERPNext", p.KIND_OUTBOX, "Manufacture", {"work_order": "WO", "qty": 5})
		self.assertEqual(a, b)
		self.assertEqual(len(a), 64)
		self.assertNotEqual(
			a, p.payload_hash("ERPNext", p.KIND_OUTBOX, "Manufacture", {"work_order": "WO", "qty": 6})
		)
		self.assertNotEqual(
			a, p.payload_hash("S4HANA", p.KIND_OUTBOX, "Manufacture", {"work_order": "WO", "qty": 5})
		)

	def test_signature_hash_binds_every_part(self):
		base = ("PW-1", "abc", "qa@example.com", p.APPROVE, "checked", "2026-11-15 10:00:00")
		seal = p.signature_hash(*base)
		for i in range(len(base)):
			changed = list(base)
			changed[i] = changed[i] + "x"
			self.assertNotEqual(seal, p.signature_hash(*changed), i)

	def test_chain_detects_edits_removals_and_reordering(self):
		entries = []
		previous = ""
		for n in range(4):
			content = {"event": p.EVENT_HELD, "reason": f"r{n}"}
			digest = p.entry_hash(previous, content)
			entries.append(
				{"name": f"WAL-{n}", "previous_hash": previous, "entry_hash": digest, "content": content}
			)
			previous = digest
		self.assertEqual(p.verify_chain(entries), [])
		edited = [dict(e) for e in entries]
		edited[1] = {**edited[1], "content": {"event": p.EVENT_HELD, "reason": "changed"}}
		self.assertEqual(p.verify_chain(edited), ["WAL-1"])
		self.assertEqual(p.verify_chain([entries[0], entries[2], entries[3]]), ["WAL-2"])
		self.assertIn("WAL-0", p.verify_chain([entries[1], entries[0], entries[2], entries[3]]))


class TestSignature(unittest.TestCase):
	def rules(self, **overrides):
		values = {
			"signer": "qa@example.com",
			"requester": "agent@example.com",
			"meaning": p.APPROVE,
			"reason": "Checked against the batch record",
			"signer_roles": ["FoaMES Supervisor"],
			"required_role": "FoaMES Supervisor",
			"require_second_person": True,
			"status": p.AWAITING,
		}
		values.update(overrides)
		return values

	def test_a_valid_signature_passes(self):
		p.check_signature(**self.rules())
		p.check_signature(**self.rules(meaning=p.REJECT))

	def test_each_rule(self):
		for overrides, message in (
			({"status": p.EXECUTED}, "awaiting sign-off"),
			({"meaning": "Maybe"}, "meaning"),
			({"reason": " "}, "reason"),
			({"signer_roles": ["FoaMES Operator"]}, "role"),
			({"signer": "agent@example.com"}, "cannot also sign"),
		):
			with self.assertRaisesRegex(p.SignatureError, message):
				p.check_signature(**self.rules(**overrides))

	def test_same_person_allowed_when_the_site_allows_it(self):
		p.check_signature(**self.rules(signer="agent@example.com", require_second_person=False))


if __name__ == "__main__":
	unittest.main()
