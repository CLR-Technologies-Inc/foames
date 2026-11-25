// Copyright 2026 CLR Technologies Inc.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
// SPDX-License-Identifier: Apache-2.0

"use strict";

(() => {
	const $ = (id) => document.getElementById(id);
	const state = {
		data: null,
		scenario: null,
		stage: 0,
		trace: null,
		ocelRequest: 0,
		mode: "supply",
		npi: false,
		dialogOpener: null,
		espressoCleanup: null,
	};
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
	const modes = {
		supply: {
			label: "Supply chain",
			description:
				"Follow material identity, custody and the handoff to the next operation.",
		},
		manufacturing: {
			label: "Manufacturing",
			description: "Connect recorded work, quality checks and equipment performance.",
		},
		engineering: {
			label: "Engineering",
			description:
				"Inspect equipment definitions, signals and the evidence needed for readiness.",
		},
	};
	const assetPaths = {
		land: ["M8 75 40 42 67 61 92 30 132 75Z", "M12 86 123 86M23 74l25-13 26 13 22-16 25 16"],
		nursery: [
			"M18 67h28l-4 24H22ZM56 67h28l-4 24H60ZM94 67h28l-4 24H98Z",
			"M32 67V47m0 8q-19-1-17-17 18 0 17 17m0-5q18-1 18-18-18 0-18 18M70 67V39m0 9q-17-2-16-18 18 1 16 18m0-5q17-2 18-18-18 0-18 18M108 67V47m0 8q-17-1-17-17 17 0 17 17m0-5q18-1 18-18-18 0-18 18",
		],
		trellis: [
			"M18 91V23m104 68V23M18 43h104M18 64h104",
			"M42 89V56q0-13 28-13m0 46V72q0-8 30-8M48 43q-8-18 4-22 12 7 2 22m30 21q-8-18 4-22 12 7 2 22",
		],
		irrigation: [
			"M16 80h32V50h44v30h32M30 80v14m80-14v14M49 42h43V25H49Z",
			"M70 6v19m-11-10h22M19 98l-6 8m19-8 6 8m66-8-6 8m19-8 6 8",
		],
		harvest: [
			"M22 48h96l-14 43H36ZM41 48l17-27m42 27L83 21",
			"M43 61h53M40 73h62M54 55l6 29m26-29-6 29M61 17q-8-15 5-14 9 4 2 14m7 0q6-15 17-9-1 11-17 9",
		],
		pulper: [
			"M21 25h60L69 45H34ZM28 46h65v35H28ZM93 53h25v21H93ZM38 81v17m43-17v17",
			"M61 46v35m-12-20h24M109 74v17H90M36 18h35",
		],
		dryer: [
			"M17 35h106v48H17ZM17 50h106M17 66h106M29 83v15m82-15v15",
			"M33 43h74M33 58h74M33 74h74M44 25q-10-9 0-17m25 17q-10-9 0-17m25 17q-10-9 0-17",
		],
		huller: [
			"M38 16h57L85 39H49ZM35 39h62v43H35ZM46 82v16m39-16v16M97 62h25v20H97Z",
			"M51 60a15 15 0 1 0 30 0 15 15 0 1 0-30 0M52 60h27M110 82v14H95",
		],
		roaster: [
			"M43 38a27 27 0 1 0 54 0 27 27 0 1 0-54 0M70 65v17M30 83h80v13H30ZM97 38h24V12h-14v26",
			"M57 38a13 13 0 1 0 26 0 13 13 0 1 0-26 0M42 26H22v34h21M64 18l8 7",
		],
		packager: [
			"M32 11h77v81H32ZM46 25h48v31H46ZM51 65h38v26H51ZM13 91h115v10H13Z",
			"M58 34h24M70 56v9M57 71l3 14h20l3-14M115 25v30h12M22 45h10",
		],
		grinder: [
			"M45 9h50l-9 29H54ZM49 38h42v24H49ZM46 62h48v32H46ZM36 94h68",
			"M61 49h18M64 62v11h25M56 77h23v12H56Z",
		],
		brewer: [
			"M31 15h65v76H31ZM41 25h45v18H41ZM42 56h44v29H42ZM22 92h86v8H22Z",
			"M58 44v12M48 65h24v15H48ZM72 67h7v9h-7M104 38h20v43h-20M109 48h10m-10 9h10",
		],
		handoff: [
			"M37 33h51v36q-25 17-51 0ZM88 41h10q19 18-10 23M24 83h83",
			"M51 23q-8-8 0-17m20 17q-8-8 0-17M20 96h102M114 27l7 7 12-16",
		],
	};
	function svgNode(tag, attributes = {}, text) {
		const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
		for (const [key, value] of Object.entries(attributes))
			node.setAttribute(key, String(value));
		if (text !== undefined) node.textContent = String(text);
		return node;
	}
	function assetIllustration(kind) {
		if (kind === "espresso") return espressoIllustration();
		const svg = svgNode("svg", {
			viewBox: "0 0 140 112",
			"aria-hidden": "true",
			focusable: "false",
			class: "asset-illustration",
		});
		const shapes = assetPaths[kind] || assetPaths.packager;
		svg.append(svgNode("ellipse", { cx: 70, cy: 103, rx: 55, ry: 5, fill: "#d9dfc9" }));
		shapes.forEach((path, index) =>
			svg.append(
				svgNode("path", {
					d: path,
					fill: index ? "none" : "#d6ddbf",
					stroke: index ? "#8b5922" : "#38543a",
					"stroke-width": index ? 2.3 : 2.8,
					"stroke-linecap": "round",
					"stroke-linejoin": "round",
				})
			)
		);
		return svg;
	}
	function espressoCup(fill = 0) {
		const cup = svgNode("g", { class: "espresso-cup" });
		cup.append(
			svgNode("ellipse", { cx: 190, cy: 315, rx: 52, ry: 7, fill: "#d8dedb" }),
			svgNode("path", {
				d: "M220 275h12c21 0 18 28-12 27",
				fill: "none",
				stroke: "#A2A342",
				"stroke-width": 9,
			}),
			svgNode("path", {
				d: "M156 268h68l-6 36q-28 18-56 0Z",
				fill: "#A2A342",
				stroke: "#666d35",
				"stroke-width": 2,
			}),
			svgNode("ellipse", {
				cx: 190,
				cy: 269,
				rx: 33,
				ry: 10,
				fill: "#f4f3e9",
				stroke: "#666d35",
				"stroke-width": 2,
			}),
			svgNode("ellipse", {
				cx: 190,
				cy: 269,
				rx: 28,
				ry: 7,
				fill: "#c39658",
				class: "espresso-liquid",
				opacity: fill,
			}),
			svgNode("path", {
				d: "M170 286q17 6 32 0",
				fill: "none",
				stroke: "#c4c78c",
				"stroke-width": 3,
			})
		);
		return cup;
	}
	function espressoIllustration() {
		const svg = svgNode("svg", {
			viewBox: "0 0 400 390",
			"aria-hidden": "true",
			focusable: "false",
			class: "asset-illustration espresso-machine",
		});
		svg.append(
			svgNode("ellipse", { cx: 207, cy: 365, rx: 155, ry: 13, fill: "#dce4e0" }),
			svgNode("path", {
				d: "M93 46 128 28h196v305l-33 20H93Z",
				fill: "#A2A342",
				stroke: "#243943",
				"stroke-width": 2,
			}),
			svgNode("rect", {
				x: 93,
				y: 46,
				width: 198,
				height: 302,
				rx: 7,
				fill: "#3683A4",
				stroke: "#243943",
				"stroke-width": 2,
			}),
			svgNode("path", { d: "M103 47 134 33h180l-29 14Z", fill: "#c6d1d2" }),
			svgNode("path", { d: "M109 37h176m-160-7h175", stroke: "#e9efed", "stroke-width": 4 }),
			svgNode("rect", { x: 105, y: 150, width: 174, height: 164, rx: 3, fill: "#243943" }),
			svgNode("path", { d: "M111 157h162v150H111Z", fill: "#d4dddc" }),
			svgNode("path", { d: "M112 158h18v149h-18Zm144 0h17v149h-17Z", fill: "#a3b5b8" }),
			svgNode(
				"text",
				{ x: 192, y: 79, "text-anchor": "middle", class: "espresso-brand" },
				"GAGGIA"
			),
			svgNode(
				"text",
				{ x: 192, y: 91, "text-anchor": "middle", class: "espresso-model" },
				"CLASSIC PRO"
			),
			svgNode("rect", {
				x: 163,
				y: 164,
				width: 56,
				height: 31,
				rx: 6,
				fill: "#879b9f",
				stroke: "#243943",
				"stroke-width": 2,
			}),
			svgNode("ellipse", {
				cx: 191,
				cy: 196,
				rx: 29,
				ry: 9,
				fill: "#e6eeeb",
				stroke: "#243943",
				"stroke-width": 2,
			}),
			svgNode("path", {
				d: "M178 201v13h11m15-13v13h-8",
				fill: "none",
				stroke: "#788f95",
				"stroke-width": 6,
			}),
			svgNode("path", {
				d: "M173 195 112 212",
				stroke: "#27363d",
				"stroke-width": 17,
				"stroke-linecap": "round",
			}),
			svgNode("path", {
				d: "M299 142v57l-13 42v22l13 9",
				fill: "none",
				stroke: "#d2dddf",
				"stroke-width": 8,
				"stroke-linejoin": "round",
			}),
			svgNode("path", {
				d: "M298 143v55l-13 44",
				fill: "none",
				stroke: "#758e94",
				"stroke-width": 2,
			}),
			svgNode("ellipse", {
				cx: 303,
				cy: 127,
				rx: 20,
				ry: 15,
				fill: "#263a42",
				stroke: "#16272e",
				"stroke-width": 2,
			}),
			svgNode("path", {
				d: "M293 120v14m7-20v25m7-26v26m7-20v16",
				stroke: "#657781",
				"stroke-width": 2,
			}),
			svgNode("rect", {
				x: 104,
				y: 314,
				width: 176,
				height: 26,
				rx: 4,
				fill: "#99aeb1",
				stroke: "#243943",
				"stroke-width": 2,
			}),
			svgNode("path", {
				d: "M111 321h161m-161 9h161M121 316v21m15-21v21m15-21v21m15-21v21m15-21v21m15-21v21m15-21v21m15-21v21m15-21v21m15-21v21",
				stroke: "#e4e9e5",
				"stroke-width": 2,
			}),
			svgNode("path", { d: "M112 349v9h27v-9m109 0v9h27v-9", fill: "#243943" })
		);
		for (const x of [142, 180, 218]) {
			svg.append(
				svgNode("rect", {
					x,
					y: 108,
					width: 24,
					height: 29,
					rx: 3,
					fill: "#21363e",
					stroke: "#adc7cc",
					"stroke-width": 1,
				})
			);
			svg.append(
				svgNode("path", { d: `M${x + 5} 115h14`, stroke: "#a8bdc1", "stroke-width": 2 })
			);
			svg.append(
				svgNode("circle", {
					cx: x + 12,
					cy: 129,
					r: 2,
					fill: x === 142 ? "#bdd98d" : "#dd9b4b",
				})
			);
		}
		svg.append(
			svgNode("path", {
				d: "M91 183H72",
				fill: "none",
				stroke: "#344e58",
				"stroke-width": 4,
			}),
			svgNode("rect", {
				x: 13,
				y: 150,
				width: 66,
				height: 62,
				rx: 5,
				fill: "#263c46",
				stroke: "#839ba2",
				"stroke-width": 2,
			}),
			svgNode(
				"text",
				{ x: 46, y: 166, "text-anchor": "middle", class: "espresso-pid-label" },
				"CUSTOM PID"
			),
			svgNode(
				"text",
				{ x: 46, y: 187, "text-anchor": "middle", class: "espresso-pid-value" },
				"93.0"
			),
			svgNode(
				"text",
				{ x: 46, y: 202, "text-anchor": "middle", class: "espresso-pid-label" },
				"°C · MODEL"
			),
			svgNode("path", {
				d: "M185 219v47m13-47v47",
				fill: "none",
				stroke: "#91602d",
				"stroke-width": 2.5,
				class: "espresso-flow",
				opacity: 0,
			}),
			espressoCup()
		);
		return svg;
	}
	function stopEspressoReplay() {
		const cleanup = state.espressoCleanup;
		state.espressoCleanup = null;
		if (cleanup) cleanup();
	}
	function espressoPlot(model) {
		const svg = svgNode("svg", {
			viewBox: "0 0 660 225",
			role: "img",
			class: "espresso-plot",
			"aria-label":
				"Synthetic boiler temperature and setpoint over elapsed seconds. Readouts show the selected sample; all samples are available under Scenario signals.",
		});
		const values = model.samples.flatMap((sample) => [
			sample.temperature_c,
			sample.setpoint_c,
		]);
		const min = Math.floor(Math.min(...values) - 2),
			max = Math.ceil(Math.max(...values) + 2);
		const x = (elapsed) => 48 + (elapsed / model.duration_seconds) * 590;
		const y = (value) => 178 - ((value - min) / (max - min)) * 148;
		for (let i = 0; i < 4; i++) {
			const value = min + ((max - min) * i) / 3;
			svg.append(svgNode("path", { d: `M48 ${y(value)}H638`, class: "espresso-grid" }));
			svg.append(
				svgNode(
					"text",
					{ x: 40, y: y(value) + 4, "text-anchor": "end", class: "espresso-axis" },
					value.toFixed(0)
				)
			);
		}
		for (const elapsed of [0, model.brew_start_s, model.brew_end_s, model.duration_seconds]) {
			svg.append(
				svgNode(
					"text",
					{ x: x(elapsed), y: 201, "text-anchor": "middle", class: "espresso-axis" },
					`${elapsed}s`
				)
			);
		}
		svg.append(svgNode("text", { x: 48, y: 15, class: "espresso-axis" }, "Boiler °C"));
		svg.append(
			svgNode("rect", {
				x: x(model.brew_start_s),
				y: 27,
				width: x(model.brew_end_s) - x(model.brew_start_s),
				height: 151,
				class: "espresso-brew-window",
			})
		);
		for (const [key, className] of [
			["setpoint_c", "espresso-setpoint"],
			["temperature_c", "espresso-temperature"],
		]) {
			const d = model.samples
				.map((sample, i) => `${i ? "L" : "M"}${x(sample.elapsed_s)} ${y(sample[key])}`)
				.join(" ");
			svg.append(svgNode("path", { d, class: className }));
		}
		const cursor = svgNode("path", { class: "espresso-cursor" });
		const point = svgNode("circle", { r: 4, class: "espresso-point" });
		svg.append(cursor, point);
		return {
			node: svg,
			update(sample) {
				cursor.setAttribute("d", `M${x(sample.elapsed_s)} 27V178`);
				point.setAttribute("cx", x(sample.elapsed_s));
				point.setAttribute("cy", y(sample.temperature_c));
			},
		};
	}
	function espressoReplay(model) {
		const section = element("section", null, "espresso-replay");
		section.append(
			element("p", "Synthetic PID model · custom finish/retrofit concept", "espresso-kicker")
		);
		const layout = element("div", null, "espresso-layout");
		const figure = element("figure", null, "espresso-figure");
		const machine = espressoIllustration();
		figure.append(
			machine,
			element("figcaption", "Gaggia Classic Pro · CLR powder-coat concept")
		);
		const panel = element("div", null, "espresso-panel");
		panel.append(
			element("h3", "One espresso, sample by sample."),
			element(
				"p",
				`${format(model.dose_g, "g")} coffee → ${format(
					model.yield_g,
					"g"
				)} beverage · ${format(model.water_g, "g")} brew water`,
				"espresso-recipe"
			)
		);
		const phase = element("p", null, "espresso-phase");
		const readouts = element("dl", null, "espresso-readouts");
		const fields = {};
		for (const [key, label] of [
			["temperature_c", "Boiler"],
			["setpoint_c", "Setpoint"],
			["heater_percent", "Heater output"],
			["beverage_g", "In the cup"],
		]) {
			const cell = element("div");
			fields[key] = element("dd");
			cell.append(element("dt", label), fields[key]);
			readouts.append(cell);
		}
		const controls = element("div", null, "espresso-controls");
		const play = actionButton("Play replay", toggle, "button espresso-play");
		const restart = actionButton(
			"Restart",
			() => {
				stop();
				seek(0);
			},
			"button secondary"
		);
		controls.append(play, restart);
		const label = element("label", "Replay position", "espresso-scrub-label");
		const scrub = element("input");
		scrub.type = "range";
		scrub.id = "espresso-position";
		scrub.min = "0";
		scrub.max = String(model.duration_seconds);
		scrub.step = "1";
		label.htmlFor = scrub.id;
		const elapsed = element("output", null, "espresso-elapsed");
		elapsed.htmlFor = scrub.id;
		const plot = espressoPlot(model);
		panel.append(phase, readouts, controls, label, scrub, elapsed);
		layout.append(figure, panel);
		section.append(
			layout,
			plot.node,
			element(
				"p",
				"Blue: synthetic boiler temperature · dashed: setpoint · shaded: brew window. The cursor follows recorded model samples.",
				"espresso-chart-note"
			),
			element("p", model.model_note, "sample-note"),
			element(
				"p",
				"Replay only: no physical control. Moving time does not create a cup or record a delivery.",
				"sample-note"
			)
		);
		let timer = null,
			position = 0,
			started = 0,
			startPosition = 0;
		function stop() {
			if (timer !== null) window.clearInterval(timer);
			timer = null;
			play.textContent = "Play replay";
		}
		function seek(seconds) {
			position = Math.min(model.duration_seconds, Math.max(0, seconds));
			const sample =
				model.samples.findLast((row) => row.elapsed_s <= position) || model.samples[0];
			scrub.value = String(position);
			elapsed.textContent = `${position} / ${model.duration_seconds} s · sample at ${sample.elapsed_s} s`;
			scrub.setAttribute(
				"aria-valuetext",
				`${position} seconds, ${String(sample.phase).replaceAll("_", " ")}`
			);
			phase.textContent = String(sample.phase).replaceAll("_", " ");
			fields.temperature_c.textContent = format(sample.temperature_c, "°C");
			fields.setpoint_c.textContent = format(sample.setpoint_c, "°C");
			fields.heater_percent.textContent = format(sample.heater_percent, "%");
			fields.beverage_g.textContent = format(sample.beverage_g, "g");
			const fill = Math.min(1, Math.max(0, sample.beverage_g / model.yield_g));
			const liquid = machine.querySelector(".espresso-liquid");
			liquid.setAttribute("opacity", fill > 0 ? "1" : "0");
			liquid.setAttribute("rx", 23 + fill * 5);
			liquid.setAttribute("cy", 274 - fill * 5);
			machine.querySelector(".espresso-pid-value").textContent =
				sample.temperature_c.toFixed(1);
			machine
				.querySelector(".espresso-flow")
				.setAttribute(
					"opacity",
					position >= model.brew_start_s && position < model.brew_end_s ? "1" : "0"
				);
			plot.update(sample);
		}
		function toggle() {
			if (timer !== null) {
				stop();
				return;
			}
			if (position >= model.duration_seconds) seek(0);
			started = performance.now();
			startPosition = position;
			play.textContent = "Pause replay";
			timer = window.setInterval(() => {
				seek(Math.floor(startPosition + (performance.now() - started) / 1000));
				if (position >= model.duration_seconds) stop();
			}, 100);
		}
		scrub.addEventListener("input", () => {
			stop();
			seek(Number(scrub.value));
		});
		seek(0);
		return { node: section, stop };
	}
	function actionButton(label, action, className = "sample-link") {
		const button = element("button", label, className);
		button.type = "button";
		button.addEventListener("click", action);
		return button;
	}
	function repositoryLink(label, path) {
		const wrapper = element("span", null, "definition-source");
		if (
			typeof path !== "string" ||
			!path ||
			path.split("/").some((part) => ["", ".", ".."].includes(part))
		)
			return wrapper;
		const revision = /^[a-f0-9]{40}$/i.test(state.data.engine?.revision)
			? state.data.engine.revision
			: "main";
		const url = safeURL(
			`https://github.com/CLR-Technologies-Inc/foames/blob/${revision}/${path
				.split("/")
				.map(encodeURIComponent)
				.join("/")}`
		);
		if (!url) return wrapper;
		const link = element("a", label, "sample-link");
		link.href = url;
		link.target = "_blank";
		link.rel = "noopener noreferrer";
		wrapper.append(link);
		return wrapper;
	}
	function explorer() {
		return state.data?.explorer || {};
	}
	function stageName(id) {
		return state.data.stages.find((stage) => stage.id === id)?.title || id;
	}
	function selectedAssets() {
		const stage = state.data.stages[state.stage].id;
		return (explorer().assets || []).filter((asset) => asset.stage_ids.includes(stage));
	}
	function relatedInstructions(stageId) {
		return (explorer().work_instructions || []).filter((instruction) =>
			instruction.stage_ids.includes(stageId)
		);
	}
	function renderViewContext() {
		if (!state.data?.explorer) return;
		$("perspective-context").textContent = `${stageName(
			state.data.stages[state.stage].id
		)} · ${state.scenario.title}`;
		$("asset-context").textContent = `Shared selection: ${
			state.trace || "no trace record"
		}. Changing perspective keeps the stage, scenario and trace selection.`;
	}
	function setMode(mode) {
		if (!modes[mode]) return;
		state.mode = mode;
		renderExplorer();
		$(
			"journey-announcement"
		).textContent = `${modes[mode].label} view. Stage, scenario and trace selection preserved.`;
	}
	function renderExplorer() {
		const config = explorer();
		const enabled = Array.isArray(config.assets) && config.assets.length > 0;
		$("perspective-bar").hidden = !enabled;
		$("asset-explorer").hidden = !enabled;
		if (!enabled) return;
		const stageId = state.data.stages[state.stage].id;
		const record = state.scenario.stages[stageId] || {};
		const assets = selectedAssets();
		for (const button of document.querySelectorAll("[data-perspective]"))
			button.setAttribute("aria-pressed", String(button.dataset.perspective === state.mode));
		$("asset-eyebrow").textContent = `${modes[
			state.mode
		].label.toUpperCase()} / SHARED ASSETS`;
		$("asset-heading").textContent = `${stageName(stageId)}, connected to the operation`;
		$("mode-description").textContent = modes[state.mode].description;
		const notes =
			config.stage_views?.[stageId]?.[state.mode] ||
			assets.flatMap((asset) => asset[state.mode] || []).slice(0, 3);
		const overview = element("div", null, "perspective-overview");
		overview.append(
			element(
				"p",
				{
					supply: "Material & custody",
					manufacturing: "Work & quality",
					engineering: "Definition & readiness",
				}[state.mode],
				"eyebrow"
			)
		);
		const list = element("ul");
		(notes || []).forEach((note) => list.append(element("li", note)));
		overview.append(list);
		const facts = element("div", null, "perspective-facts");
		if (state.mode === "supply") {
			facts.append(element("p", "RECORDED MATERIAL AT THIS STEP", "eyebrow"));
			const nodes = state.scenario.trace.filter((node) => node.stage === stageId);
			if (!nodes.length)
				facts.append(
					element(
						"p",
						"No material was produced at this step in the selected scenario.",
						"sample-empty"
					)
				);
			nodes.forEach((node) => {
				const button = actionButton(
					node.label,
					() => {
						chooseTrace(node.id);
						openMaterial(node);
					},
					"material-button"
				);
				button.append(
					element("span", `${node.id} · ${format(node.quantity, node.unit)}`),
					element(
						"small",
						node.parent_ids.length
							? `From ${node.parent_ids.join(", ")}`
							: "Origin record"
					)
				);
				facts.append(button);
			});
		} else if (state.mode === "manufacturing") {
			facts.append(
				element("p", "RECORDED WORK", "eyebrow"),
				element(
					"strong",
					{
						complete: "Stage recorded",
						held: "Quality hold",
						pending: "Not reached",
						attention: "Review needed",
					}[record.status] || "No work recorded"
				),
				element("p", record.note || "No observation for this stage.")
			);
			relatedInstructions(stageId).forEach((instruction) =>
				facts.append(
					actionButton(`Open ${instruction.title}`, () =>
						openInstruction(instruction.id)
					)
				)
			);
			if (stageId === "packaging")
				facts.append(
					element(
						"p",
						Number(state.scenario.oee?.ledger?.planned_minutes) > 0
							? `Packaging OEE ${percent(
									state.scenario.oee.oee
							  )}. The full time ledger appears below.`
							: "Packaging has not run. No OEE measurement is shown.",
						"small-copy"
					)
				);
		} else {
			facts.append(element("p", "SCHEMA & SIGNALS", "eyebrow"));
			assets.forEach((asset) =>
				facts.append(
					actionButton(
						`${asset.doctype} · ${asset.name || asset.id}`,
						() => openAsset(asset.id),
						"schema-button"
					)
				)
			);
			facts.append(
				element(
					"p",
					`${assets.reduce(
						(count, asset) => count + (asset.signals?.length || 0),
						0
					)} named sample signals. Open an asset to inspect its definition and scenario readings.`,
					"small-copy"
				)
			);
			if (config.npi)
				facts.append(
					actionButton("Review Arabica introduction evidence", () => {
						state.npi = true;
						$("npi-toggle").checked = true;
						renderNPI();
						$("npi-route").scrollIntoView({
							behavior: reducedMotion() ? "instant" : "smooth",
							block: "nearest",
						});
					})
				);
		}
		$("mode-details").replaceChildren(overview, facts);
		$("asset-cards").replaceChildren(
			...assets.map((asset) => {
				const button = actionButton(null, () => openAsset(asset.id), "asset-card");
				button.setAttribute(
					"aria-label",
					`${asset.label}. Open ${asset.doctype} sample and graphs`
				);
				const copy = element("div", null, "asset-copy");
				copy.append(
					element("span", `${asset.doctype} · ${asset.kind}`, "asset-type"),
					element("strong", asset.label),
					element("code", asset.name || asset.id),
					element("p", (asset[state.mode] || [asset.description])[0]),
					element(
						"span",
						`${
							{
								supply: "View material & handoffs",
								manufacturing: "View work & signals",
								engineering: "Inspect definition & signals",
							}[state.mode]
						}`,
						"asset-action"
					)
				);
				button.append(assetIllustration(asset.kind), copy);
				return button;
			})
		);
		$("instruction-links").replaceChildren(
			...relatedInstructions(stageId).map((instruction) =>
				actionButton(
					`▤ ${instruction.title}`,
					() => openInstruction(instruction.id),
					"instruction-link"
				)
			)
		);
		renderViewContext();
		renderNPI();
	}
	function renderNPI() {
		const npi = explorer().npi;
		$("npi-route").hidden = !npi || !state.npi;
		if (!npi) return;
		$("npi-title").textContent = npi.title;
		$("npi-summary").textContent = npi.summary;
		const stageId = state.data.stages[state.stage].id;
		$("npi-gates").replaceChildren(
			...(npi.gates || []).map((gate, index) => {
				const item = element("li");
				const button = actionButton(null, () => openGate(gate.id), "npi-gate");
				if (gate.stage_ids.includes(stageId)) button.dataset.current = "true";
				button.append(
					element("span", `0${index + 1}`, "gate-number"),
					element("strong", gate.title),
					element(
						"small",
						gate.stage_ids.map((id) => shortTitles[id] || id).join(" · ")
					),
					element("span", gate.status || "Proposed", "gate-status")
				);
				item.append(button);
				return item;
			})
		);
	}
	function openSample(title, kind, contents) {
		stopEspressoReplay();
		const dialog = $("sample-dialog");
		if (!dialog.open) state.dialogOpener = document.activeElement;
		$("sample-title").textContent = title;
		$("sample-kind").textContent = kind;
		$("sample-content").replaceChildren(...contents);
		if (!dialog.open) dialog.showModal();
		$("sample-title").focus();
	}
	function sampleSection(title, ...nodes) {
		const section = element("section", null, "sample-section");
		section.append(element("h3", title), ...nodes);
		return section;
	}
	function bullets(values) {
		const list = element("ul", null, "sample-bullets");
		for (const value of values || [])
			list.append(element("li", typeof value === "string" ? value : JSON.stringify(value)));
		return list;
	}
	function definitionTable(document) {
		const dl = element("dl", null, "definition-grid");
		for (const [key, value] of Object.entries(document || {})) {
			const row = element("div");
			row.append(element("dt", key));
			const rendered =
				typeof value === "object" && value !== null
					? JSON.stringify(value, null, 2)
					: format(value);
			row.append(element("dd", rendered));
			dl.append(row);
		}
		return dl;
	}
	function stageButtons(stageIds) {
		const links = element("div", null, "sample-actions");
		for (const stageId of stageIds || [])
			links.append(
				actionButton(`Go to ${stageName(stageId)}`, () => {
					const index = state.data.stages.findIndex((stage) => stage.id === stageId);
					if (index < 0) return;
					setStage(index);
					state.dialogOpener = $("stage-title");
					$("sample-dialog").close();
					$("journey").scrollIntoView({
						behavior: reducedMotion() ? "instant" : "smooth",
					});
				})
			);
		return links;
	}
	function definitionDetails(title, document, sourcePath) {
		const details = element("details", null, "sample-record-definition");
		details.append(
			element("summary", `Full ${title} sample definition`),
			definitionTable(document || {}),
			repositoryLink(`View ${title} schema`, sourcePath)
		);
		return details;
	}
	function openMaterial(node) {
		const record = state.scenario.stages[node.stage] || {};
		const related = state.scenario.events.filter(
			(event) => event.record_id === node.id || event.related_record_ids?.includes(node.id)
		);
		const events = element("ol", null, "sample-events");
		related.forEach((event) => {
			const item = element("li");
			item.append(element("strong", event.activity), element("span", date(event.timestamp)));
			events.append(item);
		});
		openSample(node.label, "SIMULATED MATERIAL / CUSTODY RECORD", [
			definitionTable({
				record_id: node.id,
				status: node.status,
				quantity: format(node.quantity, node.unit),
				parents: node.parent_ids.join(", ") || "Origin",
				scenario: state.scenario.title,
			}),
			element("p", record.note, "sample-note"),
			sampleSection(
				"Recorded handoffs",
				related.length
					? events
					: element("p", "No handoff event is recorded for this object.")
			),
			stageButtons([node.stage]),
		]);
	}
	function openAsset(id) {
		const asset = (explorer().assets || []).find((item) => item.id === id);
		if (!asset) return;
		const intro = element("div", null, "sample-asset-intro");
		intro.append(assetIllustration(asset.kind), element("p", asset.description));
		const contents = [
			intro,
			signalPanel(asset),
			sampleSection(modes[state.mode].label, bullets(asset[state.mode] || [])),
		];
		const model = state.scenario.espresso;
		const replay =
			model?.asset_id === asset.id && model.samples?.length ? espressoReplay(model) : null;
		if (replay) contents.splice(0, 1, replay.node);
		const instructions = element("div", null, "sample-actions");
		for (const instructionId of asset.work_instruction_ids || []) {
			const instruction = explorer().work_instructions?.find(
				(row) => row.id === instructionId
			);
			if (instruction)
				instructions.append(
					actionButton(`Open ${instruction.title}`, () =>
						openInstruction(instruction.id)
					)
				);
		}
		if (instructions.children.length)
			contents.push(sampleSection("Work instructions", instructions));
		contents.push(
			definitionDetails(
				asset.doctype,
				asset.document || { name: asset.name },
				asset.source_definition
			),
			stageButtons(asset.stage_ids)
		);
		openSample(
			asset.label,
			`${asset.doctype.toUpperCase()} / ${asset.name || asset.id}`,
			contents
		);
		if (replay) state.espressoCleanup = replay.stop;
	}
	function signalPanel(asset) {
		const section = sampleSection("Scenario signals");
		const signals = asset.signals || [];
		if (!signals.length) {
			section.append(
				element(
					"p",
					"No sample signal is defined for this asset. Its work and inspection records remain available.",
					"sample-empty"
				)
			);
			return section;
		}
		const label = element("label", "Select a signal", "signal-label");
		const select = element("select");
		select.id = "sample-signal";
		label.htmlFor = select.id;
		select.setAttribute("aria-label", `${asset.label} signal`);
		signals.forEach((signal) => {
			const option = element(
				"option",
				`${signal.label}${signal.unit ? ` (${signal.unit})` : ""}`
			);
			option.value = signal.id;
			select.append(option);
		});
		const chart = element("div", null, "signal-content");
		function showSignal() {
			const signal = signals.find((item) => item.id === select.value) || signals[0];
			const samples = signal.scenarios?.[state.scenario.id] || [];
			chart.replaceChildren(
				element("p", `Selected scenario: ${state.scenario.title}`, "signal-scenario"),
				element(
					"p",
					signal.source_note || "Illustrative scenario readings, not live telemetry.",
					"sample-note"
				)
			);
			if (signal.scenario_notes?.[state.scenario.id])
				chart.append(
					element("p", signal.scenario_notes[state.scenario.id], "sample-note")
				);
			const hasReachedStage = asset.stage_ids.some(
				(id) =>
					state.scenario.stages[id]?.status &&
					state.scenario.stages[id].status !== "pending"
			);
			if (!samples.length || !hasReachedStage) {
				chart.append(
					element(
						"p",
						`No sample readings for this asset in “${state.scenario.title}”. The definition remains available for planning.`,
						"sample-empty"
					)
				);
				return;
			}
			chart.append(signalChart(signal, samples), signalTable(signal, samples));
		}
		select.addEventListener("change", showSignal);
		section.append(label, select, chart);
		showSignal();
		return section;
	}
	function isTimedSignal(signal, samples) {
		return (
			signal.kind !== "categorical" &&
			samples.every(
				(sample) =>
					/^\d{4}-\d{2}-\d{2}T/.test(sample.time) &&
					Number.isFinite(Date.parse(sample.time))
			)
		);
	}
	function signalChart(signal, samples) {
		const valid = samples.filter(
			(sample) => typeof sample.value === "number" && Number.isFinite(sample.value)
		);
		if (!valid.length)
			return element(
				"p",
				"No observed values. Missing samples remain gaps.",
				"sample-empty"
			);
		const width = 640,
			height = 250,
			left = 62,
			right = 20,
			top = 25,
			bottom = 52;
		const categorical = signal.kind === "categorical";
		const timed = isTimedSignal(signal, samples);
		const svg = svgNode("svg", {
			viewBox: `0 0 ${width} ${height}`,
			class: "signal-chart",
			role: "img",
			"aria-label": `${signal.label}, ${signal.unit || "value"}. ${
				categorical
					? "Separate mass-balance categories."
					: "Individual observations only; no interpolation."
			} Exact readings follow in a table.`,
		});
		const values = valid.map((sample) => sample.value);
		let min = Math.min(...values),
			max = Math.max(...values);
		const pad = Math.max((max - min) * 0.12, Math.abs(max) * 0.025, 0.1);
		min = categorical ? Math.min(0, min) : min - pad;
		max += pad;
		const parsed = timed ? samples.map((sample) => Date.parse(sample.time)) : [];
		const span = timed ? parsed.at(-1) - parsed[0] : 0;
		const plotWidth = width - left - right;
		const x = (index) =>
			left +
			(categorical
				? (index + 0.5) / samples.length
				: samples.length === 1 || (timed && span === 0)
				? 0.5
				: timed
				? (parsed[index] - parsed[0]) / span
				: index / (samples.length - 1)) *
				plotWidth;
		const y = (value) => top + ((max - value) / (max - min)) * (height - top - bottom);
		for (let tick = 0; tick <= 4; tick++) {
			const value = min + ((max - min) * tick) / 4;
			svg.append(
				svgNode("line", {
					x1: left,
					x2: width - right,
					y1: y(value),
					y2: y(value),
					class: "chart-grid",
				}),
				svgNode(
					"text",
					{ x: left - 9, y: y(value) + 4, "text-anchor": "end", class: "chart-label" },
					number.format(value)
				)
			);
		}
		svg.append(
			svgNode(
				"text",
				{ x: left, y: 14, class: "chart-unit" },
				signal.y_axis || signal.unit || "Value"
			)
		);
		samples.forEach((sample, index) => {
			if (typeof sample.value !== "number" || !Number.isFinite(sample.value)) {
				svg.append(
					svgNode("line", {
						x1: x(index),
						x2: x(index),
						y1: top,
						y2: height - bottom,
						class: "chart-missing",
					}),
					svgNode(
						"text",
						{
							x: x(index),
							y: top + 15,
							"text-anchor": "middle",
							class: "chart-label",
						},
						"Missing"
					)
				);
			} else if (categorical) {
				const barWidth = Math.min(76, (plotWidth / samples.length) * 0.48);
				svg.append(
					svgNode("rect", {
						x: x(index) - barWidth / 2,
						y: Math.min(y(sample.value), y(0)),
						width: barWidth,
						height: Math.max(1, Math.abs(y(0) - y(sample.value))),
						rx: 3,
						class: "chart-bar",
					}),
					svgNode(
						"text",
						{
							x: x(index),
							y: y(sample.value) - 8,
							"text-anchor": "middle",
							class: "chart-label",
						},
						String(sample.value)
					)
				);
			} else
				svg.append(
					svgNode("circle", {
						cx: x(index),
						cy: y(sample.value),
						r: 4.5,
						class: "chart-dot",
					})
				);
		});
		const label = (sample) =>
			timed
				? new Date(sample.time).toISOString().slice(5, 16).replace("T", " ")
				: String(sample.time);
		if (categorical || samples.length === 1)
			samples.forEach((sample, index) =>
				svg.append(
					svgNode(
						"text",
						{
							x: x(index),
							y: height - 28,
							"text-anchor": "middle",
							class: "chart-label",
						},
						label(sample)
					)
				)
			);
		else
			svg.append(
				svgNode(
					"text",
					{ x: left, y: height - 28, class: "chart-label" },
					label(samples[0])
				),
				svgNode(
					"text",
					{
						x: width - right,
						y: height - 28,
						"text-anchor": "end",
						class: "chart-label",
					},
					label(samples.at(-1))
				)
			);
		svg.append(
			svgNode(
				"text",
				{ x: width / 2, y: height - 8, "text-anchor": "middle", class: "chart-label" },
				timed ? "Observation time (UTC)" : "Checkpoint"
			)
		);
		return svg;
	}
	function signalTable(signal, samples) {
		const details = element("details", null, "sample-readings");
		details.append(element("summary", `View ${samples.length} sample readings`));
		const timed = isTimedSignal(signal, samples);
		const table = element("table");
		table.append(element("caption", `${signal.label} · ${state.scenario.title}`));
		const head = element("thead"),
			headers = element("tr");
		for (const name of [
			timed ? "Observation time (UTC)" : "Checkpoint",
			`${signal.label}${signal.unit ? ` (${signal.unit})` : ""}`,
		]) {
			const th = element("th", name);
			th.scope = "col";
			headers.append(th);
		}
		head.append(headers);
		const body = element("tbody");
		samples.forEach((sample) => {
			const row = element("tr");
			row.append(
				element("td", timed ? date(sample.time) : sample.time),
				element(
					"td",
					sample.value === null || sample.value === undefined
						? "Missing reading"
						: String(sample.value)
				)
			);
			body.append(row);
		});
		table.append(head, body);
		const scroll = element("div", null, "table-scroll");
		scroll.append(table);
		details.append(scroll);
		return details;
	}
	function openInstruction(id) {
		const instruction = explorer().work_instructions?.find((item) => item.id === id);
		if (!instruction) return;
		const steps = element("ol", null, "instruction-steps");
		for (const [index, step] of (instruction.steps || []).entries()) {
			const item = element("li");
			item.append(element("span", String(index + 1).padStart(2, "0"), "instruction-number"));
			const body = element("div");
			body.append(element("h4", step.title), element("p", step.instruction));
			if (step.acceptance)
				body.append(
					element("p", `Acceptance: ${step.acceptance}`, "instruction-acceptance")
				);
			if (step.evidence)
				body.append(element("p", `Evidence to capture: ${step.evidence}`, "small-copy"));
			if (step.document) {
				const details = element("details", null, "step-definition");
				details.append(
					element("summary", "Step field mapping"),
					definitionTable(step.document)
				);
				body.append(details);
			}
			item.append(body);
			steps.append(item);
		}
		const linkedAssets = element("div", null, "sample-actions");
		for (const assetId of instruction.asset_ids || []) {
			const asset = explorer().assets.find((row) => row.id === assetId);
			if (asset)
				linkedAssets.append(actionButton(`${asset.label}`, () => openAsset(assetId)));
		}
		const evaluation = instruction.sample_evaluations?.[state.scenario.id];
		const evaluationBody = element("div", null, "instruction-evaluation");
		evaluationBody.append(
			element("p", `Selected scenario: ${state.scenario.title}`, "signal-scenario")
		);
		if (evaluation) {
			evaluationBody.append(
				element("strong", `Pure-rule result: ${evaluation.result}`),
				definitionTable({
					value: evaluation.value_number ?? evaluation.value_text,
					record_id: evaluation.record_id,
				}),
				element(
					"p",
					evaluation.note ||
						"Illustration only. No Work Instruction Run or approval was created.",
					"sample-note"
				)
			);
			if (evaluation.result === "Fail")
				evaluationBody.append(
					element(
						"p",
						"The sample check fails its fictional acceptance limits. The scenario remains on hold pending human review; viewing this sample does not release it.",
						"sample-empty"
					)
				);
		} else
			evaluationBody.append(
				element(
					"p",
					"No value was recorded at this stage in the selected scenario. No rule result or executed Work Instruction Run is implied.",
					"sample-empty"
				)
			);
		openSample(instruction.title, `WORK INSTRUCTION SAMPLE / ${instruction.id}`, [
			element(
				"p",
				`Revision ${instruction.revision} · ${instruction.status}. An example for review; it is not an approved operating procedure.`,
				"sample-note"
			),
			sampleSection("Execution steps", steps),
			sampleSection("Example check using FoaMES rules", evaluationBody),
			sampleSection("Linked assets", linkedAssets),
			definitionDetails(
				"Work Instruction",
				instruction.document,
				instruction.source_definition
			),
			stageButtons(instruction.stage_ids),
		]);
	}
	function openGate(id) {
		const npi = explorer().npi;
		const gate = npi?.gates?.find((item) => item.id === id);
		if (!gate) return;
		const assets = element("div", null, "sample-actions");
		for (const assetId of gate.asset_ids || []) {
			const asset = explorer().assets.find((row) => row.id === assetId);
			if (asset) assets.append(actionButton(`${asset.label}`, () => openAsset(asset.id)));
		}
		const linked = element("div", null, "sample-actions");
		for (const [key, title] of [
			["program", "NPI Program"],
			["requirements", "Product Requirements"],
			["transfer", "Tech Transfer Package"],
			["validation", "Validation Protocol"],
		]) {
			if (npi[key])
				linked.append(
					actionButton(`Inspect ${title} sample`, () =>
						openSample(title, "ARABICA INTRODUCTION / PROPOSED SAMPLE", [
							element(
								"p",
								"A proposed coffee-specific record. No approval, qualification or trial outcome is implied.",
								"sample-note"
							),
							definitionTable(npi[key]),
							repositoryLink(`View ${title} schema`, npi.source_definitions?.[key]),
							actionButton(`Back to ${gate.title}`, () => openGate(id)),
						])
					)
				);
		}
		openSample(gate.title, `ARABICA NPI / ${gate.status || "PROPOSED"}`, [
			element(
				"p",
				"This gate is a proposal layered onto the same asset framework. It does not change the recorded scenario or certify the product.",
				"sample-note"
			),
			sampleSection("Proposed deliverables", bullets(gate.deliverables)),
			sampleSection(
				"Acceptance evidence",
				Array.isArray(gate.acceptance)
					? bullets(gate.acceptance)
					: element("p", gate.acceptance)
			),
			sampleSection("Shared equipment", assets),
			sampleSection("Sample FoaMES records", linked),
			stageButtons(gate.stage_ids),
		]);
	}
	function renderCoverage() {
		const coverage = explorer().coverage || [];
		$("coverage-section").hidden = !coverage.length;
		$("coverage-list").replaceChildren(
			...coverage.map((item) => {
				const card = element("article", null, "coverage-card");
				card.append(
					element("span", item.status || "Example", "coverage-status"),
					element("h3", item.feature),
					element("p", item.summary)
				);
				const links = element("div", null, "sample-actions");
				if (item.guide_path)
					links.append(repositoryLink("Read the guide", item.guide_path));
				const instructionLinks = element("div", null, "sample-actions");
				for (const id of item.work_instruction_ids || []) {
					const instruction = explorer().work_instructions?.find((row) => row.id === id);
					if (instruction)
						instructionLinks.append(
							actionButton(instruction.title, () => openInstruction(id))
						);
				}
				if (instructionLinks.children.length) {
					const samples = element("details", null, "sample-record-definition");
					samples.append(
						element(
							"summary",
							`Browse ${instructionLinks.children.length} sample instructions`
						),
						instructionLinks
					);
					card.append(samples);
				}
				for (const id of (item.asset_ids || []).slice(0, 2)) {
					const asset = explorer().assets?.find((row) => row.id === id);
					if (asset) links.append(actionButton(`${asset.label}`, () => openAsset(id)));
				}
				if (item.stage_ids?.length)
					links.append(
						actionButton(`Explore ${shortTitles[item.stage_ids[0]]}`, () => {
							const index = state.data.stages.findIndex(
								(stage) => stage.id === item.stage_ids[0]
							);
							if (index >= 0) {
								setStage(index, true);
								$("journey").scrollIntoView({
									behavior: reducedMotion() ? "instant" : "smooth",
								});
							}
						})
					);
				card.append(links);
				return card;
			})
		);
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
		renderExplorer();
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
	function chooseTrace(id, focus = false) {
		state.trace = id;
		$("trace-select").value = id;
		renderTrace();
		renderViewContext();
		if (focus) $("trace-selected-title").focus({ preventScroll: true });
	}
	function renderCup() {
		const cup = state.scenario.cup || {};
		const espresso = state.scenario.espresso;
		$("espresso-cup-drawing").hidden = !espresso;
		$("filter-cup-drawing").hidden = Boolean(espresso);
		if (espresso) {
			const drawing = svgNode("svg", {
				viewBox: "130 247 130 83",
				"aria-hidden": "true",
				focusable: "false",
			});
			drawing.append(espressoCup(cup.beverage_g > 0 ? 1 : 0));
			$("espresso-cup-drawing").replaceChildren(drawing);
		}
		const trace = state.scenario.trace || [];
		const cupRecord = trace.find((record) => record.id === cup.id);
		$("cup-id").textContent = cupRecord ? cup.id : "No cup created";
		badge($("cup-status"), cupRecord ? cup.status : "Not reached");
		const values = cupRecord
			? [
					["Beverage", cup.beverage_g, "g"],
					["Coffee dose", cup.coffee_dose_g, "g"],
					["Dissolved solids (TDS)", cup.tds_percent, "%"],
					["Extraction yield", cup.extraction_percent, "%"],
			  ]
			: [];
		$("cup-metrics").replaceChildren(
			...values.map(([label, value, unit]) => {
				const row = element("div");
				row.append(element("dt", label), element("dd", format(value, unit)));
				return row;
			})
		);
		$("cup-handoff").textContent = !cupRecord
			? "The journey stopped before brewing. No cup was produced or delivered."
			: cup.handoff_at
			? `Recorded handoff: ${date(cup.handoff_at)}`
			: "No completed handoff event. This cup has not been delivered in this scenario.";
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
		let selectedTitle = $("trace-selected-title");
		if (!selectedTitle) {
			selectedTitle = element("h3", null, "trace-selected-title");
			selectedTitle.id = "trace-selected-title";
			selectedTitle.tabIndex = -1;
			$("trace-chain").before(selectedTitle);
		}
		selectedTitle.textContent = chain.length
			? `${chain[0].label} · ${chain[0].id}`
			: "No selected record";
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
						link.addEventListener("click", () => chooseTrace(parent, true));
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
		stopEspressoReplay();
		if ($("sample-dialog").open) $("sample-dialog").close();
		state.ocelRequest += 1;
		state.scenario =
			state.data.scenarios.find((scenario) => scenario.id === id) || state.data.scenarios[0];
		$("scenario").value = state.scenario.id;
		$("scenario-summary").textContent = state.scenario.summary;
		$("download-ocel").href = `./${encodeURIComponent(state.scenario.id)}.ocel.json`;
		$("download-ocel").setAttribute("download", `${state.scenario.id}.ocel.json`);
		$("download-ocel").textContent = "Download OCEL event log ↓";
		$("download-ocel").removeAttribute("aria-busy");
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
			explorer: state.data.explorer || null,
			view: {
				perspective: state.mode,
				stage: state.data.stages[state.stage].id,
				trace: state.trace,
				npi_proposal_visible: state.npi,
			},
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
		const request = ++state.ocelRequest;
		const control = $("download-ocel");
		control.textContent = "Preparing event log…";
		control.setAttribute("aria-busy", "true");
		try {
			const response = await fetch(`./${encodeURIComponent(scenarioId)}.ocel.json`);
			if (!response.ok) throw new Error("Event log unavailable");
			const eventLog = await response.json();
			if (request !== state.ocelRequest) return;
			downloadFile(eventLog, `foames-coffee-${scenarioId}.ocel.json`);
			control.textContent = "Download OCEL event log ↓";
		} catch {
			if (request === state.ocelRequest)
				control.textContent = "Download failed. Try again ↓";
		} finally {
			if (request === state.ocelRequest) control.removeAttribute("aria-busy");
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
			$("explore-espresso").hidden = !data.scenarios.some(
				(scenario) => scenario.id === "espresso_pid"
			);
			renderCoverage();
			$("demo").hidden = false;
			$("loading").hidden = true;
		} catch {
			$("loading").hidden = true;
			$("load-error").hidden = false;
		}
	}
	$("scenario").addEventListener("change", (event) => selectScenario(event.target.value));
	$("explore-espresso").addEventListener("click", () => {
		selectScenario("espresso_pid");
		const stage = state.data.stages.findIndex((item) => item.id === "brewing");
		if (stage >= 0) setStage(stage);
		openAsset(state.scenario.espresso.asset_id);
	});
	$("previous").addEventListener("click", () => setStage(state.stage - 1, true));
	$("next").addEventListener("click", () => setStage(state.stage + 1, true));
	$("replay").addEventListener("click", () => setStage(0, true));
	$("all-sources").addEventListener("change", renderSources);
	$("trace-select").addEventListener("change", (event) => chooseTrace(event.target.value));
	$("trace-cup").addEventListener("click", () => chooseTrace(state.scenario.cup.id));
	$("download-json").addEventListener("click", downloadJSON);
	$("download-ocel").addEventListener("click", downloadOCEL);
	$("retry").addEventListener("click", load);
	for (const button of document.querySelectorAll("[data-perspective]"))
		button.addEventListener("click", () => setMode(button.dataset.perspective));
	$("npi-toggle").addEventListener("change", (event) => {
		state.npi = event.target.checked;
		renderNPI();
	});
	$("sample-close").addEventListener("click", () => $("sample-dialog").close());
	$("sample-dialog").addEventListener("close", () => {
		stopEspressoReplay();
		const opener = state.dialogOpener;
		state.dialogOpener = null;
		(opener?.isConnected ? opener : $("stage-title")).focus({ preventScroll: true });
	});
	window.addEventListener("pagehide", stopEspressoReplay);
	void load();
})();
