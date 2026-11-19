# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0
"""Fictional espresso balances and a deterministic, lumped thermal PID illustration.

No measurements, device commands, calibration or Gaggia operating recipe are provided.
The thermal coefficients and controller gains exist only to make control feedback visible.
The assumed beverage flow is independent of the thermal model, not a predicted extraction.
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from datetime import datetime, timedelta

DURATION_SECONDS = 90
BREW_START_S = 45
BREW_END_S = 75
SETPOINT_C = 93.0
INITIAL_TEMPERATURE_C = 90.0
DOSE_G = 18.0
YIELD_G = 36.0
WATER_G = 54.0
TDS_PERCENT = 10.0
ESPRESSO_ID = "DEMO-ESPRESSO-01"
CUP_ID = "DEMO-ESPRESSO-CUP-01"
MODEL_NOTE = (
	"Synthetic PID teaching model, not measured Gaggia dynamics, hardware tuning or a brewing recipe. "
	"It starts at an assumed 90 C and controls toward a fictional 93 C setpoint using proportional, "
	"integral and derivative feedback, heater clamping and anti-windup. Heat loss, heater response "
	"and the brew thermal load are illustrative assumptions. Beverage flow is a separately assumed "
	"36 g shot over seconds 45-75; the final 15 seconds show recovery. No equipment is connected."
)


def _clamp(value, low=0.0, high=1.0):
	return max(low, min(high, value))


@dataclass
class PIDController:
	"""Normalized fictional heater control; derivative is taken on temperature.

	The integral contribution is bounded and only accepted when it does not wind the
	controller further into saturation. These gains are not settings for real equipment.
	"""

	kp: float = 0.65
	ki: float = 0.025
	kd: float = 0.8
	integral: float = 0.0
	previous_temperature: float | None = None

	def step(self, temperature: float, setpoint: float, dt: float = 1.0) -> float:
		values = (temperature, setpoint, dt, self.kp, self.ki, self.kd, self.integral)
		if not all(math.isfinite(v) for v in values) or dt <= 0:
			raise ValueError("PID inputs must be finite and the time step positive")
		if min(self.kp, self.ki, self.kd) < 0 or not 0 <= self.integral <= 1:
			raise ValueError("PID gains must be nonnegative and the integral contribution within 0..1")
		error = setpoint - temperature
		derivative = 0.0
		if self.previous_temperature is not None:
			if not math.isfinite(self.previous_temperature):
				raise ValueError("Previous temperature must be finite")
			derivative = -(temperature - self.previous_temperature) / dt
		candidate = _clamp(self.integral + self.ki * error * dt)
		raw = self.kp * error + candidate + self.kd * derivative
		if 0 <= raw <= 1 or (raw > 1 and error < 0) or (raw < 0 and error > 0):
			self.integral = candidate
		output = _clamp(self.kp * error + self.integral + self.kd * derivative)
		self.previous_temperature = temperature
		return output


def simulate_espresso(
	end_time: str, *, brew_load_c_per_s: float = 0.10, heater_rise_c_per_s: float = 0.32
) -> dict:
	"""One-second samples of a toy closed loop and independently assumed shot flow.

	A normalized heater adds at most 0.32 C per second, ambient loss is 0.001 times
	(temperature - 22 C) per second, and brewing subtracts 0.10 C per second by default.
	These are synthetic lumped-model coefficients, not measured machine properties.
	"""
	for value in (brew_load_c_per_s, heater_rise_c_per_s):
		if not math.isfinite(value) or value < 0:
			raise ValueError("Thermal coefficients must be finite and nonnegative")
	end = datetime.fromisoformat(end_time)
	if end.utcoffset() is None:
		raise ValueError("The espresso replay needs a timezone-aware end time")
	start = end - timedelta(seconds=DURATION_SECONDS)
	controller = PIDController()
	temperature = INITIAL_TEMPERATURE_C
	samples = []
	for elapsed in range(DURATION_SECONDS + 1):
		brewing = BREW_START_S <= elapsed < BREW_END_S
		phase = "Warming" if elapsed < BREW_START_S else "Brewing" if brewing else "Recovering"
		heater = controller.step(temperature, SETPOINT_C)
		beverage = YIELD_G * _clamp((elapsed - BREW_START_S) / (BREW_END_S - BREW_START_S))
		samples.append(
			{
				"elapsed_s": elapsed,
				"time": (start + timedelta(seconds=elapsed)).isoformat(),
				"temperature_c": round(temperature, 4),
				"setpoint_c": SETPOINT_C,
				"heater_percent": round(heater * 100, 3),
				"beverage_g": round(beverage, 3),
				"phase": phase,
			}
		)
		# The sample's heater output affects the next one-second interval.
		if elapsed < DURATION_SECONDS:
			temperature += heater_rise_c_per_s * heater - 0.001 * (temperature - 22.0)
			if brewing:
				temperature -= brew_load_c_per_s
	return {
		"asset_id": "DEMO-ASSET-ESPRESSO",
		"duration_seconds": DURATION_SECONDS,
		"brew_start_s": BREW_START_S,
		"brew_end_s": BREW_END_S,
		"setpoint_c": SETPOINT_C,
		"dose_g": DOSE_G,
		"yield_g": YIELD_G,
		"water_g": WATER_G,
		"model_note": MODEL_NOTE,
		"samples": samples,
	}


def make_espresso_scenario(normal: dict) -> dict:
	"""Copy the normal upstream material path and replace only its brew and handoff.

	The caller rebuilds the process graph and validates genealogy using FoaMES's pure
	modules. This transformation never changes its input or claims a filter brew is espresso.
	"""
	if normal.get("id") != "normal":
		raise ValueError("The espresso route must start from the normal upstream scenario")
	result = copy.deepcopy(normal)
	result.update(
		id="espresso_pid",
		title="PID espresso and cup handoff",
		summary="Follow the same fictional coffee lot into a custom PID espresso demonstration and an explicitly recorded cup handoff.",
	)
	# This derived value must be recomputed from the replacement event records.
	result.pop("process_graph", None)
	extraction = YIELD_G * (TDS_PERCENT / 100) / DOSE_G * 100
	brew_stage = result["stages"]["brewing"]
	brew_stage.update(
		record_id=ESPRESSO_ID,
		metrics=[
			{"label": "Dose", "value": DOSE_G, "unit": "g"},
			{"label": "Beverage", "value": YIELD_G, "unit": "g"},
			{"label": "TDS", "value": TDS_PERCENT, "unit": "%"},
			{"label": "Extraction", "value": extraction, "unit": "%"},
			{"label": "Assumed water", "value": WATER_G, "unit": "g"},
		],
		note="Illustrative espresso assumptions: a 250 g bag supplies 18 g, leaving 232 g. 18 g coffee + 54 g water becomes 36 g beverage and 36 g wet puck/retention. 10% TDS gives 20% extraction. This is not a Gaggia recipe or measured machine performance.",
	)
	result["stages"]["delivery"].update(
		record_id=CUP_ID,
		note="Only the explicit simulated espresso-cup handoff marks delivery; neither PID recovery nor shot completion implies handoff.",
	)
	for record in result["trace"]:
		if record["id"] == "DEMO-BREW-01":
			record.update(
				id=ESPRESSO_ID, label="Illustrative PID espresso", quantity=YIELD_G, unit="g beverage"
			)
		elif record["id"] == "DEMO-CUP-01":
			record.update(
				id=CUP_ID, label="Delivered espresso cup", parent_ids=[ESPRESSO_ID, "DEMO-ORDER-01"]
			)
	for flow in result["mass_balance"]:
		if flow["stage"] == "brewing":
			flow.update(
				input_kg=(DOSE_G + WATER_G) / 1000,
				output_kg=YIELD_G / 1000,
				other_kg=(DOSE_G + WATER_G - YIELD_G) / 1000,
				other_label="Illustrative 36 g wet puck and retained water; includes 54 g added water",
			)
	for event in result["events"]:
		if event["stage"] == "brewing":
			event.update(record_id=ESPRESSO_ID, activity="Complete illustrative PID espresso cycle")
		elif event["stage"] == "delivery":
			event.update(record_id=CUP_ID, activity="Confirm espresso cup handoff")
	result["cup"] = {
		"id": CUP_ID,
		"status": "Delivered",
		"beverage_g": YIELD_G,
		"coffee_dose_g": DOSE_G,
		"tds_percent": TDS_PERCENT,
		"extraction_percent": extraction,
		"handoff_at": result["stages"]["delivery"]["time"],
	}
	result["espresso"] = simulate_espresso(brew_stage["time"])
	return result
