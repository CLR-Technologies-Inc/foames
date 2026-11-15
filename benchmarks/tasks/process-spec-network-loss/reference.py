"""Reference solution for process-spec-network-loss: a specification and acceptance tests."""

from pathlib import Path

PLAN = """# Reconstructing Line 7 performance after network outages

## Requirements

- R1. Reported output never exceeds what the line made. Output is taken only from counter deltas (`foames/foames_mes/counters.py`); nothing is interpolated or estimated for an outage.
- R2. Availability is never overstated. Time without a machine signal is Unknown and counts as loss in OEE (`oee.py`), until real state events for that time arrive.
- R3. Every ERP posting for Line 7 is made exactly once, through the idempotent S/4HANA outbox, whether or not an outage interrupted it.
- R4. Data that arrives late (buffered at the gateway or the PLC) is accepted, deduplicated by the source event id, and the affected OEE Periods are recomputed.
- R5. Every reconstructed figure is traceable to the Machine Events that produced it.

## Ambiguities and questions

- Does the PLC or gateway buffer events during an outage (store-and-forward), and for how long? If not, no reconstruction of state is possible; only the counter delta across the gap is.
- Are PLC timestamps trustworthy (NTP-synchronised clock, time zone)? Late events are placed by their source timestamp.
- Should a period already posted to the ERP be restated when late data arrives, or does the correction go in the next posting? This is a business decision for the plant and the ERP owner.
- Is the counter's rollover value known for Line 7? Without it, a wrap during an outage reads as a reset.

## Invariants at risk

- Counters never invent production (AGENTS.md invariant 3): a reset or first reading after an outage must yield zero.
- Unknown time is loss (invariant 4): the outage must not be read as run time.
- Agents suggest; people act (invariant 5): a reconstruction is raised as an Agent Suggestion with evidence, not posted automatically.
- Postings are idempotent and sequenced (invariant 6): a timeout or 5xx during an outage is Unknown and verified by marker before a retry.

## Design

1. Gateway buffering: enable store-and-forward on the gateway (Sparkplug B or MQTT with persistent sessions, or the Ignition store-and-forward engine), sending source event ids so `Machine Event` ingest deduplicates retries.
2. Ingest: late events are stored with their source timestamps; out-of-order counter readings yield zero by the existing rules, so the delta is taken across the gap on the first reading after it.
3. Staleness: the scheduler's staleness check writes an Unknown state when Line 7 stops reporting. When buffered state events arrive, they cover part of that time; anything still uncovered stays Unknown.
4. Recompute: a job recomputes the OEE Periods that overlap late events and raises an Agent Suggestion listing old and new values with the events as evidence.
5. ERP: confirmations go through the S/4HANA outbox with an idempotency key per order and period. A restatement is a new business event with its own key, approved by a person.

## Acceptance criteria

- AC1 (R1): a counter reset or a drop after an outage counts zero (`acceptance/test_reconstruction.py::test_reset_after_outage_counts_nothing`).
- AC2 (R2): uncovered time in a period is Unknown and lowers availability (`test_gap_is_unknown_and_lowers_availability`).
- AC3 (R3): a 504 on a posting is Unknown, and the retry verifies first and posts nothing new (`test_gateway_timeout_is_verified_not_reposted`).
- AC4 (R4): a duplicate source event id is stored once (needs a Frappe site; to be added to the integration suite).
- AC5 (R5): each recomputed OEE Period links its evidence (Frappe site; integration suite).

## Risks

- Gateway buffers that overflow lose data silently; monitor buffer depth.
- Clock drift on the PLC misplaces late events across period boundaries.
- Restating posted periods can confuse planners; the change must be visible and approved.

## What cannot be inferred

- What the line did during an outage with no buffered events: only the total counted across the gap is known, not when the parts were made, nor run, idle or down time. That time stays Unknown.
- Whether a drop in the counter was a reset or a wrap, when the rollover value is not configured.
- Scrap made during the outage, unless the scrap counter was buffered too.
"""

TESTS = '''"""Acceptance criteria for the Line 7 reconstruction design, against current FoaMES behaviour."""

import unittest

from foames.foames_adapters.s4hana import outbox
from foames.foames_adapters.s4hana.fake import FakeS4HANA, csrf, ok, sap_error
from foames.foames_adapters.s4hana.odata import Connection, ODataClient
from foames.foames_mes.counters import counter_delta
from foames.foames_mes.oee import compute_oee, ledger_from_states


class TestReconstruction(unittest.TestCase):
	def test_reset_after_outage_counts_nothing(self):
		self.assertEqual(counter_delta(48112, 120), 0.0)
		self.assertEqual(counter_delta(None, 48112), 0.0)

	def test_gap_is_unknown_and_lowers_availability(self):
		ledger = ledger_from_states([(240, "Running", False), (120, "Unknown", False)], 480)
		self.assertEqual(ledger.unknown_minutes, 240)
		self.assertEqual(ledger.run_minutes, 240)
		self.assertAlmostEqual(compute_oee(ledger, 100, 0, None).availability, 0.5)

	def test_gateway_timeout_is_verified_not_reposted(self):
		op = outbox.OPERATIONS["Production Order Confirmation"]
		payload = outbox.prepare(op, {"OrderID": "1"}, "line7-conf-1")
		created = {"ConfirmationGroup": "9", "ConfirmationCount": "1"}
		fake = (
			FakeS4HANA()
			.on("FETCH", "API_PROD_ORDER_CONFIRMATION_2_SRV", csrf())
			.on("POST", "ProdnOrdConf2", sap_error(504, "GW", "timeout"), once=True)
			.on("GET", "ProdnOrdConf2", ok({"results": [created]}))
		)
		client = ODataClient(Connection(base_url="https://s4"), transport=fake)
		first = outbox.send(client, op, payload, verify_first=False)
		self.assertEqual(first.status, "Unknown")
		second = outbox.send(client, op, payload, verify_first=first.status == "Unknown")
		self.assertEqual(second.status, "Posted")
		self.assertEqual(sum(r["method"] == "POST" for r in fake.requests), 1)
'''


def apply(workspace: Path):
	(workspace / "PLAN.md").write_text(PLAN, encoding="utf-8")
	(workspace / "acceptance").mkdir(exist_ok=True)
	(workspace / "acceptance" / "test_reconstruction.py").write_text(TESTS, encoding="utf-8")
	(workspace / "BENCH_NOTES.md").write_text(
		"Reference solution. PLAN.md sets out requirements, the questions only the plant can answer, the "
		"invariants at risk and a design built on existing FoaMES behaviour; the acceptance tests pin that "
		"behaviour so a regression in counters, unknown time or outbox verification fails them. Two criteria "
		"need a Frappe site and are listed for the integration suite.\n",
		encoding="utf-8",
	)
