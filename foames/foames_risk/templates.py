# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""The starting categories and risk templates FoaMES installs. Pure data, no Frappe dependency.

They are examples for a manufacturing site, written from general public practice. Every site
should set its own tolerances and edit, add or disable templates; installing again never
overwrites a category or template that already exists.
"""

from __future__ import annotations

# (name, tolerance, apply hierarchy of controls, description)
CATEGORIES = (
	("Safety and Health", "Low", 1, "Harm to people: injury, illness, exposure"),
	("Environmental", "Low", 1, "Releases, emissions, waste, permit limits"),
	("Product Quality", "Moderate", 0, "Defects, contamination, mix-ups, recalls"),
	("Process and Equipment", "Moderate", 1, "Equipment failure, process upsets, loss of capability"),
	("Supply Chain", "Moderate", 0, "Suppliers, materials, logistics"),
	("Cybersecurity and OT", "Low", 0, "Attacks on or failures of plant networks and control systems"),
	("IT Infrastructure", "Moderate", 0, "Business systems, data, hosting"),
	("Regulatory Compliance", "Low", 0, "Laws, permits, licences, certifications"),
	("Financial", "Moderate", 0, "Cost, cash, financial reporting"),
	("Fraud", "Low", 0, "Fraud, waste and abuse, financial or not"),
	("Human Capital", "Moderate", 0, "Skills, staffing, key people, training"),
	("Physical Infrastructure", "Moderate", 1, "Buildings, utilities, site services"),
	("Continuity of Operations", "Moderate", 0, "Keeping essential work going through a disruption"),
	("Reputational", "Moderate", 0, "Trust of customers, regulators, the community"),
	("Strategic", "High", 0, "Markets, products, partners, long-range plans"),
	("Other", "Moderate", 0, "Anything that fits no other category"),
)

# A template's controls: (control, level, function, verification method).
TEMPLATES = (
	{
		"title": "Exposure to a hazardous chemical in a process area",
		"category": "Safety and Health",
		"objective": "Operations",
		"risk_statement": (
			"If workers are exposed to a hazardous chemical above its exposure limit while charging, sampling "
			"or cleaning, then they may suffer acute or long-term illness, the area may be shut down and "
			"the site may face regulatory action."
		),
		"inherent_impact": 5,
		"inherent_likelihood": 3,
		"controls": (
			(
				"Use a less hazardous grade or a pre-mixed form where the process allows",
				"Substitution",
				"Preventive",
				"Document Review",
			),
			(
				"Closed transfer or local exhaust ventilation at the point of release, with airflow checked",
				"Engineering Controls",
				"Preventive",
				"Measurement",
			),
			(
				"Charging and cleaning follow the written procedure; no open handling outside the hood",
				"Work Practices",
				"Preventive",
				"Observation",
			),
			(
				"Exposure monitoring against the action level",
				"Administrative Controls",
				"Detective",
				"Measurement",
			),
			(
				"Chemical-resistant gloves, eye protection and fit-tested respirators where required",
				"PPE",
				"Preventive",
				"Inspection",
			),
		),
	},
	{
		"title": "Contact with moving machine parts",
		"category": "Safety and Health",
		"objective": "Operations",
		"risk_statement": (
			"If a person reaches into a machine's danger zone while it can move, then they may be seriously "
			"injured and the line will stop for the investigation."
		),
		"inherent_impact": 5,
		"inherent_likelihood": 3,
		"controls": (
			(
				"Fixed guards and interlocked doors that stop motion when opened, tested",
				"Engineering Controls",
				"Preventive",
				"Test",
			),
			(
				"Lockout/tagout program with a permit for servicing",
				"Administrative Controls",
				"Preventive",
				"Audit",
			),
			(
				"No clearing jams by hand; use the tool and the procedure",
				"Work Practices",
				"Preventive",
				"Observation",
			),
			(
				"Cut-resistant gloves where the task assessment calls for them",
				"PPE",
				"Preventive",
				"Inspection",
			),
		),
	},
	{
		"title": "Release of a stored liquid to the environment",
		"category": "Environmental",
		"objective": "Compliance",
		"risk_statement": (
			"If a tank, drum or transfer line leaks, then the liquid may reach drains, soil or water, the "
			"site may breach its permit and clean-up costs and penalties may follow."
		),
		"inherent_impact": 4,
		"inherent_likelihood": 3,
		"controls": (
			(
				"Secondary containment sized for the largest container",
				"Engineering Controls",
				"Preventive",
				"Inspection",
			),
			(
				"Transfers attended and done to the written procedure",
				"Work Practices",
				"Preventive",
				"Observation",
			),
			("Weekly containment and tank inspection", "Administrative Controls", "Detective", "Inspection"),
			("Spill kit and response plan, exercised", "Administrative Controls", "Contingency", "Test"),
		),
	},
	{
		"title": "Loss of a critical utility",
		"category": "Physical Infrastructure",
		"objective": "Operations",
		"risk_statement": (
			"If power, compressed air or cooling water is lost during production, then batches in process "
			"may be lost, equipment may be damaged and deliveries may be late."
		),
		"inherent_impact": 4,
		"inherent_likelihood": 3,
		"controls": (
			(
				"Redundant supply or backup for the critical loads",
				"Engineering Controls",
				"Preventive",
				"Test",
			),
			(
				"Preventive maintenance on the utility equipment",
				"Administrative Controls",
				"Preventive",
				"Document Review",
			),
			("Safe shutdown and restart procedure", "Work Practices", "Contingency", "Test"),
		),
	},
	{
		"title": "Critical equipment failure",
		"category": "Process and Equipment",
		"objective": "Operations",
		"risk_statement": (
			"If a bottleneck machine fails, then output stops on that line, orders are late and repair "
			"costs rise."
		),
		"inherent_impact": 4,
		"inherent_likelihood": 3,
		"controls": (
			(
				"Condition monitoring with alarms on the failure modes that matter",
				"Engineering Controls",
				"Detective",
				"Test",
			),
			(
				"Preventive maintenance plan on the machine",
				"Administrative Controls",
				"Preventive",
				"Document Review",
			),
			("Critical spares held on site", "Other Management Control", "Contingency", "Inspection"),
		),
	},
	{
		"title": "Single source for a critical material",
		"category": "Supply Chain",
		"objective": "Operations",
		"risk_statement": (
			"If the only qualified supplier of a critical material cannot deliver, then production stops "
			"once stock runs out and customers are not supplied."
		),
		"inherent_impact": 4,
		"inherent_likelihood": 2,
		"controls": (
			("Qualify a second supplier", "Other Management Control", "Preventive", "Document Review"),
			(
				"Safety stock sized to the requalification lead time",
				"Other Management Control",
				"Contingency",
				"Measurement",
			),
			(
				"Supplier performance and financial health reviewed",
				"Administrative Controls",
				"Detective",
				"Audit",
			),
		),
	},
	{
		"title": "Ransomware on the plant network",
		"category": "Cybersecurity and OT",
		"objective": "Operations",
		"risk_statement": (
			"If ransomware reaches the plant network, then control and MES systems may be unavailable, "
			"production stops, and records may be lost or disclosed."
		),
		"inherent_impact": 5,
		"inherent_likelihood": 3,
		"controls": (
			(
				"Network segmentation between business and plant networks, rules reviewed",
				"Engineering Controls",
				"Preventive",
				"Audit",
			),
			("Patching and account review on a schedule", "Administrative Controls", "Preventive", "Audit"),
			(
				"Offline backups of control and MES systems, restore tested",
				"Other Management Control",
				"Contingency",
				"Test",
			),
		),
	},
	{
		"title": "Unapproved write from FoaMES into another system",
		"category": "Cybersecurity and OT",
		"objective": "Operations",
		"risk_statement": (
			"If a connector, agent or misconfigured adapter writes to an ERP, MES or control system without a "
			"person approving it, then orders, stock or settings may be changed wrongly and production or "
			"records may be affected."
		),
		"inherent_impact": 4,
		"inherent_likelihood": 3,
		"controls": (
			(
				"Connectors run read-only; each write waits for an authorised sign-off and is logged",
				"Engineering Controls",
				"Preventive",
				"Test",
			),
			(
				"Each connector's write path approved before it is enabled",
				"Administrative Controls",
				"Preventive",
				"Document Review",
			),
			("Write audit log reviewed", "Administrative Controls", "Detective", "Audit"),
		),
	},
	{
		"title": "Product contamination or mix-up",
		"category": "Product Quality",
		"objective": "Operations",
		"risk_statement": (
			"If material from one product or batch gets into another, then product may be scrapped or "
			"recalled and customers may be harmed."
		),
		"inherent_impact": 4,
		"inherent_likelihood": 3,
		"controls": (
			(
				"Dedicated or error-proofed equipment and connections",
				"Engineering Controls",
				"Preventive",
				"Test",
			),
			("Line clearance before every changeover", "Work Practices", "Preventive", "Observation"),
			(
				"Release testing against the specification",
				"Administrative Controls",
				"Detective",
				"Document Review",
			),
		),
	},
	{
		"title": "Loss of key technical knowledge",
		"category": "Human Capital",
		"objective": "Operations",
		"risk_statement": (
			"If a person who alone knows how to run or repair a process leaves or is absent, then the "
			"process cannot run to standard and problems take longer to fix."
		),
		"inherent_impact": 3,
		"inherent_likelihood": 3,
		"controls": (
			(
				"Written SOPs and work instructions for the process",
				"Administrative Controls",
				"Preventive",
				"Document Review",
			),
			(
				"Cross-training matrix with at least two qualified people",
				"Administrative Controls",
				"Preventive",
				"Audit",
			),
		),
	},
	{
		"title": "Lapse of a permit, licence or certification",
		"category": "Regulatory Compliance",
		"objective": "Compliance",
		"risk_statement": (
			"If an operating permit, licence or certification lapses or its conditions are not met, then "
			"the site may have to stop the activity and may face penalties."
		),
		"inherent_impact": 4,
		"inherent_likelihood": 2,
		"controls": (
			(
				"Register of permits with renewal dates and owners",
				"Administrative Controls",
				"Preventive",
				"Audit",
			),
			(
				"Periodic compliance check against permit conditions",
				"Administrative Controls",
				"Detective",
				"Audit",
			),
		),
	},
	{
		"title": "Unreliable production or quality records",
		"category": "Product Quality",
		"objective": "Reporting",
		"risk_statement": (
			"If production or quality records are incomplete, altered or wrong, then products may be "
			"released on false data and audits and reports may fail."
		),
		"inherent_impact": 4,
		"inherent_likelihood": 2,
		"controls": (
			(
				"Audit trail and electronic signatures on the records",
				"Engineering Controls",
				"Preventive",
				"Test",
			),
			("Second-person review of critical entries", "Work Practices", "Detective", "Audit"),
		),
	},
	{
		"title": "Change made without assessing its risk",
		"category": "Process and Equipment",
		"objective": "Operations",
		"risk_statement": (
			"If a process, equipment or material change is made without a risk review, then new hazards "
			"or failure modes may go uncontrolled."
		),
		"inherent_impact": 4,
		"inherent_likelihood": 3,
		"controls": (
			(
				"Management of change: review and approval before a change is made",
				"Administrative Controls",
				"Preventive",
				"Audit",
			),
			("Pre-start review after the change", "Work Practices", "Detective", "Document Review"),
		),
	},
)
