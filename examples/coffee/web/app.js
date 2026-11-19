// Copyright (c) 2026 CLR Technologies Inc. and contributors
// SPDX-License-Identifier: Apache-2.0

"use strict";

(() => {
	const $ = (id) => document.getElementById(id);
	const state = { data: null, scenario: null, stage: 0, trace: null };
	const number = new Intl.NumberFormat("en", { maximumFractionDigits: 2 });
	const shortTitles = {
		land: "Land & soil",
		nursery: "Seeds & nursery",
		trellis: "Trellis",
		cultivation: "Cultivation",
		harvest: "Harvest",
		processing: "Wet process",
		drying: "Drying",
		green: "Green coffee",
		roasting: "Roasting",
		packaging: "Packaging",
		brewing: "Brewing",
		delivery: "Delivery",
	};
	const ledgerParts = [
		["run_minutes", "Running", "#bdcc9c"],
		["planned_downtime_minutes", "Planned stop", "#d9be80"],
		["unplanned_downtime_minutes", "Unplanned stop", "#ca8e68"],
		["idle_minutes", "Idle", "#96b6a6"],
		["setup_minutes", "Setup", "#d5d2b6"],
		["unknown_minutes", "Unknown", "#788573"],
	];
	function element(tag, text, className) {
		const node = document.createElement(tag);
		if (text !== undefined && text !== null) node.textContent = String(text);
		if (className) node.className = className;
		return node;
	}
	function format(value, unit = "") {
		if (value === null || value === undefined || value === "") return "Not recorded";
		return `${typeof value === "number" ? number.format(value) : value}${
			unit ? ` ${unit}` : ""
		}`;
	}
	function percent(value) {
		return Number.isFinite(value) ? `${(value * 100).toFixed(1)}%` : "Not recorded";
	}
	function date(value) {
		if (!value) return "No event recorded";
		const parsed = new Date(value);
		if (Number.isNaN(parsed.getTime())) return String(value);
		return `${parsed.toISOString().slice(0, 16).replace("T", " ")} UTC`;
	}
	function badge(node, text, status = text) {
		node.textContent = text;
		node.dataset.status = status;
	}
	function safeURL(value) {
		try {
			const url = new URL(value);
			return ["https:", "http:"].includes(url.protocol) ? url.href : null;
		} catch {
			return null;
		}
	}
	function populateList(id, values) {
		$(id).replaceChildren(...(values || []).map((value) => element("li", value)));
	}
	function metric(label, value, unit) {
		const container = element("div");
		const detail = element("dd", format(value));
		if (unit && value !== null && value !== undefined) detail.append(element("small", unit));
		container.append(element("dt", label), detail);
		return container;
	}
	function setStage(index, focus = false) {
		state.stage = Math.max(0, Math.min(state.data.stages.length - 1, index));
		renderStage();
		if (focus) $("stage-title").focus({ preventScroll: true });
	}
	function renderStageNav() {
		const nodes = state.data.stages.map((stage, index) => {
			const item = element("li");
			const button = element("button");
			button.type = "button";
			button.dataset.status = state.scenario.stages[stage.id]?.status || "pending";
			button.setAttribute("aria-label", `${index + 1}. ${stage.title}`);
			if (index === state.stage) button.setAttribute("aria-current", "step");
			button.append(
				element("span", String(index + 1).padStart(2, "0"), "nav-number"),
				element("span", shortTitles[stage.id] || stage.title, "nav-title")
			);
			button.addEventListener("click", () => setStage(index, true));
			item.append(button);
			return item;
		});
		$("stage-list").replaceChildren(...nodes);
	}
	function renderStage() {
		const stage = state.data.stages[state.stage];
		const record = state.scenario.stages[stage.id] || { status: "pending", metrics: [] };
		renderStageNav();
		$("stage-position").textContent = `STEP ${String(state.stage + 1).padStart(
			2,
			"0"
		)} / ${String(state.data.stages.length).padStart(2, "0")}`;
		$("stage-title").textContent = stage.title;
		$("stage-subtitle").textContent = stage.subtitle;
		$("stage-summary").textContent = stage.summary;
		badge(
			$("stage-status"),
			{
				complete: "Recorded",
				held: "Quality hold",
				pending: "Not reached",
				attention: "Review needed",
			}[record.status] || record.status,
			record.status
		);
		$("stage-metrics").replaceChildren(
			...(record.metrics || []).map((row) => metric(row.label, row.value, row.unit))
		);
		$("stage-observation").textContent =
			record.note ||
			"No observation has been recorded for this stage in the selected scenario.";
		$("stage-record-id").textContent = record.record_id || "Not created";
		$("stage-time").textContent = date(record.time);
		if (record.time) $("stage-time").setAttribute("datetime", record.time);
		else $("stage-time").removeAttribute("datetime");
		populateList("stage-controls", stage.controls);
		$("stage-records").replaceChildren(
			...(stage.foames_records || []).map((name) => element("span", name))
		);
		$("paper-status").textContent = stage.paper_status;
		$("previous").disabled = state.stage === 0;
		$("next").disabled = state.stage === state.data.stages.length - 1;
		$("journey-announcement").textContent = `${stage.title}. ${
			$("stage-status").textContent
		}. ${record.note || ""}`;
		renderSources();
	}
	function renderOperations() {
		const oee = state.scenario.oee || {};
		const ledger = oee.ledger || {};
		const hasPackagingPeriod = Number(ledger.planned_minutes) > 0;
		$("oee-value").textContent = hasPackagingPeriod ? percent(oee.oee) : "Not run";
		$("oee-factors").replaceChildren(
			...[
				["Availability", oee.availability],
				["Performance", oee.performance],
				["Quality", oee.quality],
			].map(([label, value]) => {
				const item = element("div");
				item.append(
					element("span", label),
					element("strong", hasPackagingPeriod ? percent(value) : "Not measured")
				);
				return item;
			})
		);
		const chart = [],
			legend = [],
			description = [];
		for (const [key, label, color] of ledgerParts) {
			const minutes = Number(ledger[key]) || 0;
			if (minutes <= 0) continue;
			const segment = element("span");
			segment.style.flexGrow = String(minutes);
			segment.style.backgroundColor = color;
			segment.title = `${label}: ${format(minutes, "min")}`;
			chart.push(segment);
			const entry = element("span");
			const dot = element("i");
			dot.style.backgroundColor = color;
			entry.append(dot, document.createTextNode(`${label} ${format(minutes, "min")}`));
			legend.push(entry);
			description.push(`${label} ${format(minutes, "minutes")}`);
		}
		$("ledger-chart").replaceChildren(...chart);
		$("ledger-chart").hidden = !hasPackagingPeriod;
		$("ledger-chart").setAttribute(
			"aria-label",
			description.join(". ") || "No packaging time recorded"
		);
		$("ledger-legend").replaceChildren(...legend);
		$("oee-counts").textContent = hasPackagingPeriod
			? `${format(oee.good_count)} good packs · ${format(
					oee.scrap_count
			  )} rejected packs · ${format(ledger.planned_minutes, "planned min")}`
			: "Packaging has not run in this scenario. No production or equipment performance has been measured.";
		$("oee-notes").replaceChildren(...(oee.notes || []).map((note) => element("p", note)));
		const suggestions = state.scenario.suggestions || [];
		$("suggestions").replaceChildren(
			...(suggestions.length
				? suggestions
				: [
						{
							title: "Follow the evidence",
							evidence: "This scenario has no open suggestion.",
							action: "Inspect the stage records and source limitations before drawing conclusions.",
						},
				  ]
			).map((suggestion) => {
				const item = element("article", null, "suggestion-item");
				item.append(
					element("h3", suggestion.title),
					element(
						"p",
						typeof suggestion.evidence === "string"
							? suggestion.evidence
							: JSON.stringify(suggestion.evidence)
					),
					element("p", suggestion.action, "action")
				);
				return item;
			})
		);
	}
	function chooseTrace(id) {
		state.trace = id;
		$("trace-select").value = id;
		renderTrace();
	}
	function renderCup() {
		const cup = state.scenario.cup || {};
		$("cup-id").textContent = cup.id || "No cup created";
		badge($("cup-status"), cup.status || "Not reached");
		const values = [
			["Beverage", cup.beverage_g, "g"],
			["Coffee dose", cup.coffee_dose_g, "g"],
			["Dissolved solids (TDS)", cup.tds_percent, "%"],
			["Extraction yield", cup.extraction_percent, "%"],
		];
		$("cup-metrics").replaceChildren(
			...values.map(([label, value, unit]) => {
				const row = element("div");
				row.append(element("dt", label), element("dd", format(value, unit)));
				return row;
			})
		);
		$("cup-handoff").textContent = cup.handoff_at
			? `Recorded handoff: ${date(cup.handoff_at)}`
			: "No completed handoff event. This cup has not been delivered in this scenario.";
		const trace = state.scenario.trace || [];
		const affected = new Set(state.scenario.recall_affected_ids || []);
		const reviewRecords = trace.filter((record) => affected.has(record.id));
		$("recall-review").hidden = reviewRecords.length === 0;
		$("recall-records").replaceChildren(
			...reviewRecords.map((record) => {
				const button = element("button", record.label);
				button.type = "button";
				button.append(element("span", `${record.id} · ${record.status}`));
				button.setAttribute("aria-label", `Trace ${record.label}, ${record.id}`);
				button.addEventListener("click", () => chooseTrace(record.id));
				return button;
			})
		);
		$("trace-select").replaceChildren(
			...trace.map((record) => {
				const option = element("option", `${record.id} · ${record.label}`);
				option.value = record.id;
				return option;
			})
		);
		const cupRecord = trace.find((record) => record.id === cup.id);
		$("trace-cup").disabled = !cupRecord;
		$("trace-cup").textContent = cupRecord ? "Trace this cup ↑" : "No cup to trace";
		$("all-records").replaceChildren(
			...trace.map((record) => {
				const button = element("button", record.id);
				button.type = "button";
				button.addEventListener("click", () => chooseTrace(record.id));
				return button;
			})
		);
		chooseTrace(cupRecord?.id || trace.at(-1)?.id || null);
	}
	function renderTrace() {
		const records = new Map((state.scenario.trace || []).map((record) => [record.id, record]));
		const chain = [],
			seen = new Set();
		function visit(id) {
			if (!id || seen.has(id)) return;
			seen.add(id);
			const record = records.get(id);
			if (!record) return;
			chain.push(record);
			for (const parent of record.parent_ids || []) visit(parent);
		}
		visit(state.trace);
		$("trace-caption").textContent = chain.length
			? `${chain.length} connected records, from selected record back to origin. Quantities at different stages represent different materials.`
			: "No traceable material record exists yet in this scenario.";
		$("trace-chain").replaceChildren(
			...chain.map((record) => {
				const item = element("li");
				item.append(element("span", null, "trace-dot"));
				const body = element("div");
				const row = element("div", null, "trace-row");
				const button = element("button", record.label);
				button.type = "button";
				button.append(
					element("small", `${record.id} · ${shortTitles[record.stage] || record.stage}`)
				);
				button.addEventListener("click", () => {
					const index = state.data.stages.findIndex(
						(stage) => stage.id === record.stage
					);
					if (index >= 0) {
						setStage(index);
						$("journey").scrollIntoView({
							behavior: reducedMotion() ? "instant" : "smooth",
						});
					}
				});
				const quantity = element(
					"div",
					format(record.quantity, record.unit),
					"trace-quantity"
				);
				quantity.append(element("span", record.status));
				row.append(button, quantity);
				body.append(row);
				if (record.parent_ids?.length) {
					const links = element("div", "Parents: ", "parent-links");
					for (const parent of record.parent_ids) {
						const link = element("button", parent);
						link.type = "button";
						link.addEventListener("click", () => chooseTrace(parent));
						links.append(link);
					}
					body.append(links);
				}
				item.append(body);
				return item;
			})
		);
	}
	function renderBalances() {
		$("mass-balance").replaceChildren(
			...(state.scenario.mass_balance || []).map((balance) => {
				const row = element("tr");
				const stage = state.data.stages.find((item) => item.id === balance.stage);
				const useGrams = Number(balance.input_kg) < 1;
				const unit = useGrams ? "g" : "kg";
				const mass = (value) =>
					format(
						value === null || value === undefined
							? value
							: value * (useGrams ? 1000 : 1),
						unit
					);
				const other = element("td", mass(balance.other_kg));
				other.append(element("small", balance.other_label));
				row.append(
					element("td", stage?.title || balance.stage),
					element("td", mass(balance.input_kg)),
					element("td", mass(balance.output_kg)),
					other
				);
				return row;
			})
		);
	}
	function renderSources() {
		const stage = state.data.stages[state.stage];
		const showAll = $("all-sources").checked;
		$("evidence-stage").textContent = showAll ? "all stages" : stage.title;
		const sources = state.data.sources.filter(
			(source) => showAll || (stage.source_ids || []).includes(source.id)
		);
		$("source-list").replaceChildren(
			...sources.map((source) => {
				const card = element("article", null, "source-card");
				const heading = element("h3");
				const url = safeURL(source.url);
				if (url) {
					const link = element("a", `${source.title} ↗`);
					link.href = url;
					link.target = "_blank";
					link.rel = "noopener noreferrer";
					heading.append(link);
				} else heading.textContent = source.title;
				card.append(
					element(
						"p",
						String(source.kind || "Evidence").replaceAll("_", " "),
						"source-kind"
					),
					heading,
					element("p", source.claim),
					element(
						"p",
						source.limitations
							? `Limit: ${source.limitations}`
							: "Review the source for its scope and assumptions.",
						"source-limits"
					),
					element(
						"p",
						[source.publisher, source.locator].filter(Boolean).join(" · "),
						"source-publisher"
					)
				);
				return card;
			})
		);
		if (!sources.length)
			$("source-list").append(
				element(
					"p",
					"No source has been attached to this step yet. Its example values remain simulation assumptions."
				)
			);
	}
	function selectScenario(id) {
		state.scenario =
			state.data.scenarios.find((scenario) => scenario.id === id) || state.data.scenarios[0];
		$("scenario").value = state.scenario.id;
		$("scenario-summary").textContent = state.scenario.summary;
		$("download-ocel").href = `./${encodeURIComponent(state.scenario.id)}.ocel.json`;
		$("download-ocel").setAttribute("download", `${state.scenario.id}.ocel.json`);
		renderStage();
		renderOperations();
		renderCup();
		renderBalances();
	}
	function reducedMotion() {
		return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
	}
	function downloadJSON() {
		const file = {
			disclaimer: state.data.disclaimer,
			engine: state.data.engine,
			scenario: state.scenario,
		};
		downloadFile(file, `foames-coffee-${state.scenario.id}.json`);
	}
	function downloadFile(file, filename) {
		const url = URL.createObjectURL(
			new Blob([JSON.stringify(file, null, 2)], { type: "application/json" })
		);
		const link = element("a");
		link.href = url;
		link.download = filename;
		document.body.append(link);
		link.click();
		link.remove();
		window.setTimeout(() => URL.revokeObjectURL(url), 1000);
	}
	async function downloadOCEL(event) {
		event.preventDefault();
		const scenarioId = state.scenario.id;
		const control = $("download-ocel");
		control.textContent = "Preparing event log…";
		try {
			const response = await fetch(`./${encodeURIComponent(scenarioId)}.ocel.json`);
			if (!response.ok) throw new Error("Event log unavailable");
			downloadFile(await response.json(), `foames-coffee-${scenarioId}.ocel.json`);
			control.textContent = "Download OCEL event log ↓";
		} catch {
			control.textContent = "Download failed. Try again ↓";
		}
	}
	async function load() {
		$("loading").hidden = false;
		$("load-error").hidden = true;
		try {
			const response = await fetch("./data.json", { cache: "no-cache" });
			if (!response.ok) throw new Error(`Data request failed: ${response.status}`);
			const data = await response.json();
			if (!data.stages?.length || !data.scenarios?.length || !Array.isArray(data.sources))
				throw new Error("Incomplete demo data");
			state.data = data;
			$("disclaimer").textContent =
				data.disclaimer ||
				"All records and measurements are simulated. No equipment is controlled.";
			$("scenario").replaceChildren(
				...data.scenarios.map((scenario) => {
					const option = element("option", scenario.title);
					option.value = scenario.id;
					return option;
				})
			);
			const engine = data.engine || {};
			$("engine-details").textContent = [
				engine.name,
				engine.revision ? `revision ${engine.revision}` : null,
				...(engine.modules || []),
			]
				.filter(Boolean)
				.join(" · ");
			selectScenario("normal");
			$("demo").hidden = false;
			$("loading").hidden = true;
		} catch {
			$("loading").hidden = true;
			$("load-error").hidden = false;
		}
	}
	$("scenario").addEventListener("change", (event) => selectScenario(event.target.value));
	$("previous").addEventListener("click", () => setStage(state.stage - 1, true));
	$("next").addEventListener("click", () => setStage(state.stage + 1, true));
	$("replay").addEventListener("click", () => setStage(0, true));
	$("all-sources").addEventListener("change", renderSources);
	$("trace-select").addEventListener("change", (event) => chooseTrace(event.target.value));
	$("trace-cup").addEventListener("click", () => chooseTrace(state.scenario.cup.id));
	$("download-json").addEventListener("click", downloadJSON);
	$("download-ocel").addEventListener("click", downloadOCEL);
	$("retry").addEventListener("click", load);
	void load();
})();
