# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Metric collection: percentiles, peak RSS, device description. Stdlib only."""

from __future__ import annotations

import os
import platform


def percentile(values: list[float], pct: float) -> float | None:
	"""Nearest-rank percentile; None for an empty list."""
	if not values:
		return None
	sorted_v = sorted(values)
	idx = min(len(sorted_v) - 1, max(0, int(round((pct / 100.0) * (len(sorted_v) - 1)))))
	return sorted_v[idx]


def latency_stats(samples_ms: list[float]) -> dict:
	total = sum(samples_ms)
	return {
		"p50": percentile(samples_ms, 50),
		"p95": percentile(samples_ms, 95),
		"p99": percentile(samples_ms, 99),
		"mean": total / len(samples_ms) if samples_ms else None,
		"min": min(samples_ms) if samples_ms else None,
		"max": max(samples_ms) if samples_ms else None,
	}


def peak_rss_mb() -> float | None:
	"""Peak resident set size in MB, best effort across platforms."""
	try:
		import resource

		# Linux reports kilobytes, macOS reports bytes.
		rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
		return rss / (1024 * 1024) if rss > 1 << 30 else rss / 1024
	except (ImportError, AttributeError, OSError):
		pass
	try:
		with open("/proc/self/status", encoding="utf-8") as f:
			for line in f:
				if line.startswith("VmHWM:"):
					return float(line.split()[1]) / 1024
	except OSError:
		pass
	return None


def device_info() -> dict:
	info = {
		"arch": platform.machine(),
		"os": platform.system().lower(),
		"cpu_model": platform.processor() or None,
		"cpu_count": os.cpu_count(),
		"mem_total_mb": _mem_total_mb(),
	}
	return {k: v for k, v in info.items() if v is not None}


def _mem_total_mb() -> float | None:
	try:
		with open("/proc/meminfo", encoding="utf-8") as f:
			for line in f:
				if line.startswith("MemTotal:"):
					return float(line.split()[1]) / 1024
	except OSError:
		pass
	return None
