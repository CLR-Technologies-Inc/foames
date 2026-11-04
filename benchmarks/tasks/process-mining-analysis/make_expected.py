"""Regenerate hidden/expected.json with FoaMES's own process-mining module. Run from benchmarks/:
PYTHONPATH=..:foames_bench/stubs python tasks/process-mining-analysis/make_expected.py"""

import importlib.util
import json
from pathlib import Path
from statistics import median

from foames.foames_process_mining import discovery
from foames.foames_process_mining.eventlog import Event, EventLog

HERE = Path(__file__).parent
_spec = importlib.util.spec_from_file_location("pm_fixture", HERE / "fixture.py")
fixture = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fixture)


def main():
	log = EventLog(
		Event(r["case_id"], r["activity"], r["timestamp"], r["resource"], r["lifecycle"])
		for r in fixture.rows()
	)
	variants = log.variants()
	top, cases = next(iter(variants.items()))
	durations = discovery.case_durations(log)
	traces = log.traces()
	expected = {
		"cases": len(traces),
		"variants": len(variants),
		"top_variant": {"activities": list(top), "cases": len(cases)},
		"median_cycle_time_minutes": round(median(durations.values()) / 60, 2),
		"rework_cases": discovery.rework(log),
		"bottleneck": discovery.bottlenecks(log, 1)[0]["activity"],
		"incomplete_cases": sorted(
			c for c, ev in traces.items() if not any(e.activity == "Pack" for e in ev)
		),
	}
	(HERE / "hidden" / "expected.json").write_text(json.dumps(expected, indent=1) + "\n", encoding="utf-8")
	print(json.dumps(expected, indent=1))


if __name__ == "__main__":
	main()
