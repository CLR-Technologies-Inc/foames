# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""A process development (PD) simulation study.

The engineer lists the factors (with their studied range and, for what-if, how they vary in
operation) and the responses (with limits), generates a design, runs the experiments and enters
the results in the run grid. The study then fits a response-surface model per response, runs a
Monte Carlo what-if around the nominal settings and maps the design space over any two factors.
The arithmetic is in foames.foames_life_sciences.doe; this class only moves data between the record and
those functions. Nothing here reads production data or changes a process.
"""

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from foames.foames_life_sciences import doe

RESULT_COLUMNS = tuple(f"y{i}" for i in range(1, doe.MAX_RESPONSES + 1))
FACTOR_COLUMNS = tuple(f"x{i}" for i in range(1, doe.MAX_FACTORS + 1))


def parse_number(value):
	"""A response or nominal typed as text: a float, or None when blank."""
	if value is None or str(value).strip() == "":
		return None
	try:
		return float(str(value).strip())
	except ValueError:
		frappe.throw(_("{0} is not a number").format(frappe.bold(value)))


class PDSimulationStudy(Document):
	def validate(self):
		if not self.factors:
			frappe.throw(_("A study needs at least one factor"))
		if len(self.factors) > doe.MAX_FACTORS:
			frappe.throw(_("A study takes at most {0} factors").format(doe.MAX_FACTORS))
		if len(self.responses) > doe.MAX_RESPONSES:
			frappe.throw(_("A study takes at most {0} responses").format(doe.MAX_RESPONSES))
		for kind, rows, key, prefix in (
			("factor", self.factors, "factor", "x"),
			("response", self.responses, "response", "y"),
		):
			names = [r.get(key) for r in rows]
			if len(names) != len(set(names)):
				frappe.throw(_("Each {0} name can appear only once").format(_(kind)))
			for i, row in enumerate(rows, start=1):
				row.symbol = f"{prefix}{i}"
		for f in self.factors:
			if flt(f.low) >= flt(f.high):
				frappe.throw(_("{0}: low must be below high").format(f.factor))
			nominal = parse_number(f.nominal)
			if nominal is not None and not flt(f.low) <= nominal <= flt(f.high):
				frappe.throw(_("{0}: the nominal must lie in the studied range").format(f.factor))
			if f.distribution == "Normal" and flt(f.sd) <= 0:
				frappe.throw(
					_("{0}: a normal distribution needs a positive standard deviation").format(f.factor)
				)
		for r in self.responses:
			if r.limits == "Lower and Upper" and flt(r.lower) > flt(r.upper):
				frappe.throw(_("{0}: the lower limit is above the upper limit").format(r.response))
		for run in self.runs:
			for column in RESULT_COLUMNS:
				parse_number(run.get(column))
		self.status = self.current_status()

	def current_status(self):
		if self.model_results:
			return "Modelled"
		return "Runs Pending" if self.runs else "Planning"

	# -- data in the shapes doe expects ---------------------------------------------------------
	def factor_specs(self):
		specs = []
		for f in self.factors:
			low, high = flt(f.low), flt(f.high)
			nominal = parse_number(f.nominal)
			nominal = (low + high) / 2.0 if nominal is None else nominal
			spec = {
				"name": f.factor,
				"low": low,
				"high": high,
				"nominal": nominal,
				"distribution": f.distribution or "Fixed",
				"sd": flt(f.sd),
				"dist_low": None,
				"dist_high": None,
			}
			if flt(f.spread) > 0:
				spec["dist_low"], spec["dist_high"] = nominal - flt(f.spread), nominal + flt(f.spread)
			specs.append(spec)
		return specs

	def response_specs(self):
		return [
			{"name": r.response, "limits": r.limits or "None", "lower": flt(r.lower), "upper": flt(r.upper)}
			for r in self.responses
		]

	def models(self):
		if not self.model_results:
			frappe.throw(_("Fit the models first"))
		return json.loads(self.model_results)["models"]

	# -- actions -----------------------------------------------------------------------------
	@frappe.whitelist()
	def generate_design(self, overwrite=0):
		"""Replace the run grid with the chosen design, in actual units."""
		self.check_permission("write")
		if any(run.get(c) not in (None, "") for run in self.runs for c in RESULT_COLUMNS) and not cint(
			overwrite
		):
			frappe.throw(_("Some runs already have results; confirm to overwrite them"))
		factors = self.factor_specs()
		design = doe.build_design(
			self.design_type,
			len(factors),
			levels=cint(self.levels) or 2,
			fraction=cint(self.fraction),
			center_points=cint(self.center_points),
			replicates=cint(self.replicates) or 1,
			randomise=bool(cint(self.randomise)),
			seed=cint(self.seed),
		)
		self.set("runs", [])
		for run in design["runs"]:
			row = {"run_no": run["run_no"], "std_order": run["std_order"], "point_type": run["point_type"]}
			for i, code in enumerate(run["coded"]):
				row[FACTOR_COLUMNS[i]] = round(doe.actual(code, factors[i]["low"], factors[i]["high"]), 9)
			self.append("runs", row)
		self.design_factors = json.dumps([f["name"] for f in factors])
		notes = [f"{len(design['runs'])} runs, {design['design']}"]
		if design["resolution"]:
			notes.append(f"resolution {design['resolution']}")
		if design["alpha"] and design["alpha"] > 1:
			notes.append(
				f"axial points at +/-{design['alpha']:.3f} coded units lie outside the low-high range; check they are safe to run"
			)
		self.design_summary = "; ".join(notes)
		self.model_results = None
		self.model_summary = None
		self.what_if_results = None
		self.what_if_summary = None
		self.probability_all_in_limits = 0
		self.save()
		return self.design_summary

	@frappe.whitelist()
	def fit_models(self):
		"""Fit the chosen model to each response that has results."""
		self.check_permission("write")
		factors = self.factor_specs()
		if self.design_factors and json.loads(self.design_factors) != [f["name"] for f in factors]:
			frappe.throw(_("The factors changed since the design was generated; generate it again"))
		symbols = [f["name"] for f in factors]
		models, lines = {}, []
		for j, response in enumerate(self.responses):
			column = RESULT_COLUMNS[j]
			points, ys = [], []
			for run in self.runs:
				y = parse_number(run.get(column))
				if run.excluded or y is None:
					continue
				points.append(
					[
						doe.coded(flt(run.get(FACTOR_COLUMNS[i])), f["low"], f["high"])
						for i, f in enumerate(factors)
					]
				)
				ys.append(y)
			if not ys:
				lines.append(f"{response.response}: no results yet")
				continue
			try:
				fit = doe.fit(points, ys, self.model_type, symbols)
			except ValueError as e:
				lines.append(f"{response.response}: {e}")
				continue
			fit.pop("residuals")
			models[response.response] = fit
			adj = fit["adj_r_squared"]
			lines.append(
				f"{response.response}: R2 {fit['r_squared']:.3f}"
				+ (f", adjusted {adj:.3f}" if adj is not None else "")
				+ (
					f", RMSE {fit['rmse']:.4g}"
					if fit["rmse"] is not None
					else ", no residual degrees of freedom"
				)
				+ f", {fit['runs']} runs"
			)
		if not models:
			frappe.throw("<br>".join(lines) or _("No response has results"))
		self.model_results = json.dumps({"coded": True, "factors": factors, "models": models}, indent=1)
		self.model_summary = "\n".join(lines)
		self.save()
		return self.model_summary

	@frappe.whitelist()
	def run_what_if(self):
		"""Monte Carlo of the fitted models around the factors' nominal settings."""
		self.check_permission("write")
		result = doe.what_if(
			self.factor_specs(),
			self.response_specs(),
			self.models(),
			iterations=cint(self.iterations) or 5000,
			seed=cint(self.seed),
			include_model_error=bool(cint(self.include_model_error)),
		)
		self.what_if_results = json.dumps(result, indent=1)
		self.probability_all_in_limits = 100.0 * result["probability_all_in_limits"]
		lines = [
			f"{r['response']}: mean {r['mean']:.4g}, 90% of runs in [{r['p05']:.4g}, {r['p95']:.4g}], "
			f"{100 * r['probability_in_limits']:.1f}% within limits"
			+ (f", predicted Ppk {r['predicted_ppk']:.2f}" if r["predicted_ppk"] is not None else "")
			for r in result["responses"]
		]
		if result["percent_draws_outside_studied_range"]:
			lines.append(
				f"{result['percent_draws_outside_studied_range']:.1f}% of draws fell outside the studied range; "
				"the model is extrapolating there"
			)
		self.what_if_summary = "\n".join(lines)
		self.save()
		return result

	@frappe.whitelist()
	def get_design_space(self, x_factor, y_factor, steps=21):
		"""The design-space grid over two factors, the others at nominal. Not stored."""
		self.check_permission("read")
		names = [f.factor for f in self.factors]
		if x_factor not in names or y_factor not in names:
			frappe.throw(_("Choose two factors of this study"))
		return doe.design_space(
			self.factor_specs(),
			self.response_specs(),
			self.models(),
			names.index(x_factor),
			names.index(y_factor),
			cint(steps) or 21,
		)
