"""The synthetic event log for process-mining-analysis: 60 work orders through a welding cell.
Deterministic (fixed seed), invented, and free of any plant's data."""

import csv
import io
import random
from datetime import datetime, timedelta, timezone

T0 = datetime(2026, 10, 5, 6, 0, tzinfo=timezone.utc)
SERVICE = {
	"Cut": (8, 14),
	"Weld": (20, 35),
	"Inspect": (5, 9),
	"Rework Weld": (15, 25),
	"Paint": (25, 40),
	"Pack": (4, 7),
}
WAIT = {
	"Cut": (0, 5),
	"Weld": (5, 20),
	"Inspect": (30, 90),
	"Rework Weld": (10, 30),
	"Paint": (10, 25),
	"Pack": (2, 10),
}
RESOURCES = {
	"Cut": "SAW-1",
	"Weld": "WELD-2",
	"Inspect": "QC-1",
	"Rework Weld": "WELD-2",
	"Paint": "BOOTH-1",
	"Pack": "PACK-1",
}


def rows(seed: int = 20261105) -> list[dict]:
	rng = random.Random(seed)
	out = []
	for n in range(1, 61):
		case = f"WO-{n:04d}"
		t = T0 + timedelta(minutes=rng.randint(0, 60 * 24 * 4))
		steps = ["Cut", "Weld", "Inspect"]
		# A first rework is likelier than a second.
		chance = 0.3
		while rng.random() < chance:
			steps += ["Rework Weld", "Inspect"]
			chance = 0.15
		if n in (17, 33, 52):
			pass  # stopped after inspection: still open at extraction time
		else:
			if rng.random() > 0.2:
				steps.append("Paint")
			steps.append("Pack")
		for step in steps:
			t += timedelta(minutes=rng.randint(*WAIT[step]))
			out.append(
				{
					"case_id": case,
					"activity": step,
					"lifecycle": "start",
					"timestamp": t,
					"resource": RESOURCES[step],
				}
			)
			t += timedelta(minutes=rng.randint(*SERVICE[step]))
			out.append(
				{
					"case_id": case,
					"activity": step,
					"lifecycle": "complete",
					"timestamp": t,
					"resource": RESOURCES[step],
				}
			)
	# The export is not sorted, as exports from a historian rarely are.
	rng.shuffle(out)
	return out


def to_csv(data: list[dict]) -> str:
	buffer = io.StringIO()
	writer = csv.DictWriter(
		buffer, fieldnames=["case_id", "activity", "lifecycle", "timestamp", "resource"], lineterminator="\n"
	)
	writer.writeheader()
	for row in data:
		writer.writerow({**row, "timestamp": row["timestamp"].strftime("%Y-%m-%dT%H:%M:%SZ")})
	return buffer.getvalue()
