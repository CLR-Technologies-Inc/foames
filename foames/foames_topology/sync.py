# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""Mirror what FoaMES already records into the topology graph, so it stays current by itself.

Runs every 15 minutes (and on demand from the Topology View page). From the site's own records:

physical layer
	Line (from Machine.line) contains Machine.
	P&ID components, when the P&ID module is installed: each component, Part Of its parent
	component or the machine it is linked to, with its process and signal connections as Pipe and
	Wiring links.
data layer, bound to the physical layer
	Each machine data source (Machine Data Settings node map rows, and P&ID components with a
	signal) becomes a Signal, bound to its machine or instrument, flowing into its Connector
	(OPC UA, Sparkplug B, MQTT, Webhook, Historian), then into the machine's event stream, which
	derives the machine's OEE KPI and posts to the ERP record the machine is working on.

The sync writes as the providers in model.SYNC_PROVIDERS, which collectors cannot use, and marks
everything Managed. Anything it wrote before and no longer finds is retired, not deleted.

Other apps add their own records through the `foames_topology_collectors` hook: each dotted path
is called with no arguments and returns a collector report (see ingest.py), which goes through the
same checks as one posted to the API.
"""

import frappe
from frappe.utils import now_datetime

from foames.foames_topology import store

MES = "foames-mes"
PID = "foames-pid"
ERP = "foames-erp"

_CONNECTOR_TITLES = {
	"OPC UA": "OPC UA",
	"Sparkplug B": "Sparkplug B",
	"MQTT": "MQTT",
	"Webhook": "Machine-event webhook",
	"Historian": "Historian bridge",
	"Other": "Other source",
}


class _Batch:
	"""What one provider wrote in this run, so the rest can be retired."""

	def __init__(self, provider, tenant):
		self.provider = provider
		self.tenant = tenant
		self.assets = {}
		self.links = {}
		self.bindings = {}

	def asset(self, asset_id, **values):
		values.update(asset_id=asset_id, provider=self.provider, tenant=self.tenant)
		values.setdefault("title", asset_id)
		# Several sources can describe the same node (two node map rows on one connector); the
		# first wins and later ones only fill gaps.
		current = self.assets.setdefault(asset_id, values)
		for k, v in values.items():
			if current.get(k) in (None, "") and v not in (None, ""):
				current[k] = v
		return asset_id

	def link(self, a, link_type, b, **values):
		key = f"{a}|{link_type}|{b}"
		self.links[key] = {
			"link_key": key,
			"from_asset": a,
			"to_asset": b,
			"link_type": link_type,
			"provider": self.provider,
			"tenant": self.tenant,
			**values,
		}

	def bind(self, signal, physical, direction="Read", **values):
		key = f"{signal}|{direction}|{physical}"
		self.bindings[key] = {
			"binding_key": key,
			"signal": signal,
			"physical_asset": physical,
			"direction": direction,
			"provider": self.provider,
			"tenant": self.tenant,
			**values,
		}


def scheduled_sync():
	if not int(store.settings()["sync_enabled"]):
		return
	sync()


def sync() -> dict:
	"""Run the sync now. Returns counts per provider."""
	settings = store.settings()
	tenant = settings["default_tenant"] or None
	mes, pid, erp = _Batch(MES, tenant), _Batch(PID, tenant), _Batch(ERP, tenant)
	machines = _machines(mes)
	_node_map(mes, machines)
	if _doctype_ready("PID Component"):
		_pid(pid, mes, machines)
	if int(settings["include_kpis"]):
		_kpis(mes, machines)
	if int(settings["include_erp_records"]):
		_erp(erp, machines)

	summary = {}
	# Parents first: assets are sorted so a line is written before the machines in it.
	for batch in (mes, pid, erp):
		counts = {"inserted": 0, "updated": 0, "unchanged": 0, "skipped": 0}
		for values in _parents_first(batch.assets):
			counts[store.upsert_asset(values)] += 1
		for values in batch.links.values():
			counts[store.upsert_keyed("Topology Link", "link_key", values)] += 1
		for values in batch.bindings.values():
			counts[store.upsert_keyed("Signal Binding", "binding_key", values)] += 1
		counts["retired"] = store.retire_missing(
			batch.provider, set(batch.assets), set(batch.links), set(batch.bindings)
		)
		summary[batch.provider] = counts

	for path in frappe.get_hooks("foames_topology_collectors"):
		from foames.foames_topology.api import apply_report

		try:
			summary[path] = apply_report(frappe.get_attr(path)(), writable_tenants=None)
		except Exception:
			frappe.log_error(title=f"Topology collector {path} failed")
			summary[path] = {"error": True}

	frappe.db.set_single_value(
		"Topology Settings",
		{"last_sync_at": now_datetime(), "last_sync_summary": frappe.as_json(summary, indent=None)},
	)
	return summary


def _doctype_ready(doctype):
	return frappe.db.exists("DocType", doctype) and frappe.db.table_exists(doctype)


def _parents_first(assets: dict):
	done, out = set(), []

	def visit(asset_id, stack):
		if asset_id in done or asset_id in stack or asset_id not in assets:
			return
		stack.add(asset_id)
		parent = assets[asset_id].get("parent_asset")
		if parent:
			visit(parent, stack)
		done.add(asset_id)
		out.append(assets[asset_id])

	for asset_id in sorted(assets):
		visit(asset_id, set())
	return out


def machine_asset_id(machine):
	return f"machine:{machine}"


def _machines(mes):
	machines = frappe.get_all(
		"Machine",
		{"disabled": 0},
		["name", "title", "line", "status", "last_seen", "machine_type", "current_job_reference"],
		order_by="name",
	)
	for m in machines:
		parent = None
		if m.line:
			parent = mes.asset(f"line:{m.line}", title=m.line, layer="Physical", kind="Line", status="OK")
		mes.asset(
			machine_asset_id(m.name),
			title=m.title or m.name,
			layer="Physical",
			kind="Machine",
			parent_asset=parent,
			status=m.status or "Unknown",
			last_seen=m.last_seen,
			source_doctype="Machine",
			source_name=m.name,
			attributes={"machine_type": m.machine_type} if m.machine_type else None,
		)
		# Every machine's events land in one stream, whichever connector they came through.
		mes.asset(
			f"events:{m.name}",
			title=f"{m.title or m.name} events",
			layer="Data",
			kind="Event Stream",
			status="OK" if m.last_seen else "Unknown",
			last_seen=m.last_seen,
			source_doctype="Machine",
			source_name=m.name,
		)
	return {m.name: m for m in machines}


def connector_id(batch, source):
	"""Connectors are shared by every source that uses them, so they are always the MES provider's;
	pass the MES batch."""
	source = source or "Other"
	return batch.asset(
		f"connector:{source.lower().replace(' ', '-')}",
		title=_CONNECTOR_TITLES.get(source, source),
		layer="Data",
		kind="Connector",
		status="OK",
	)


def _latest_event(machine, event_type, name):
	filters = {"machine": machine}
	if event_type:
		filters["event_type"] = event_type
	if name and event_type == "Measurement":
		filters["measurement_name"] = name
	elif name and event_type == "Count":
		filters["counter_name"] = name
	return frappe.db.get_value(
		"Machine Event", filters, ["timestamp", "value"], as_dict=True, order_by="timestamp desc"
	)


def _node_map(mes, machines):
	for row in frappe.get_cached_doc("Machine Data Settings").get("node_map") or []:
		if row.machine not in machines or not row.node_id:
			continue
		source = row.source or "Other"
		signal = mes.asset(
			f"signal:{source.lower().replace(' ', '-')}:{row.node_id}",
			title=row.name_or_counter or row.node_id,
			layer="Data",
			kind="Signal",
			attributes={"node_id": row.node_id, "event_type": row.event_type},
		)
		latest = _latest_event(row.machine, row.event_type, row.name_or_counter)
		if latest:
			mes.assets[signal]["last_seen"] = latest.timestamp
		mes.bind(
			signal,
			machine_asset_id(row.machine),
			last_value=latest.value if latest and row.event_type == "Measurement" else None,
			last_value_at=latest.timestamp if latest else None,
		)
		connector = connector_id(mes, source)
		mes.link(signal, "Data Flow", connector)
		mes.link(connector, "Data Flow", f"events:{row.machine}")


_PID_KIND = {"Equipment": "Equipment", "Instrument": "Instrument", "Line": "Piping", "Valve": "Valve", "Actuator": "Equipment"}


def _pid(pid, mes, machines):
	components = frappe.get_all(
		"PID Component",
		{"disabled": 0},
		[
			"name",
			"tag",
			"component_type",
			"description",
			"drawing",
			"parent_component",
			"machine",
			"event_type",
			"signal_name",
			"signal_source",
			"signal_address",
			"historian_tag",
			"engineering_unit",
		],
		order_by="name",
	)
	ids = {c.name: f"pid:{c.name}" for c in components}
	for c in components:
		parent = ids.get(c.parent_component)
		if not parent and c.machine in machines:
			parent = machine_asset_id(c.machine)
		physical = pid.asset(
			ids[c.name],
			title=c.tag or c.name,
			layer="Physical",
			kind=_PID_KIND.get(c.component_type, "Other"),
			parent_asset=parent,
			status="OK",
			source_doctype="PID Component",
			source_name=c.name,
			attributes={k: v for k, v in (("description", c.description), ("drawing", c.drawing)) if v},
		)
		address = c.signal_address or c.historian_tag or c.signal_name
		if not (c.signal_source or address):
			continue
		signal = pid.asset(
			f"signal:pid:{c.name}",
			title=f"{c.tag or c.name} signal",
			layer="Data",
			kind="Historian Point" if c.signal_source == "Historian" or (c.historian_tag and not c.signal_address) else "Signal",
			attributes={"address": address, "historian_tag": c.historian_tag} if address else None,
		)
		latest = _latest_event(c.machine, c.event_type, c.signal_name) if c.machine else None
		if latest:
			pid.assets[signal]["last_seen"] = latest.timestamp
		pid.bind(
			signal,
			physical,
			tag=c.tag,
			unit=c.engineering_unit,
			last_value=latest.value if latest and c.event_type == "Measurement" else None,
			last_value_at=latest.timestamp if latest else None,
		)
		connector = connector_id(mes, c.signal_source)
		pid.link(signal, "Data Flow", connector)
		if c.machine in machines:
			pid.link(connector, "Data Flow", f"events:{c.machine}")
	if _doctype_ready("PID Connection"):
		for conn in frappe.get_all(
			"PID Connection", {"parenttype": "PID Drawing"}, ["kind", "from_component", "to_component"]
		):
			a, b = ids.get(conn.from_component), ids.get(conn.to_component)
			if a and b and a != b:
				pid.link(a, "Wiring" if conn.kind == "Signal" else "Pipe", b)


def _kpis(mes, machines):
	for name, m in machines.items():
		oee = frappe.db.get_value(
			"OEE Period", {"machine": name}, ["oee", "to_time"], as_dict=True, order_by="from_time desc"
		)
		kpi = mes.asset(
			f"kpi:oee:{name}",
			title=f"{m.title or name} OEE",
			layer="Data",
			kind="KPI",
			status="OK" if oee else "Unknown",
			last_seen=oee.to_time if oee else None,
			source_doctype="Machine",
			source_name=name,
			attributes={"oee": oee.oee} if oee else None,
		)
		mes.link(f"events:{name}", "Derives", kpi)


def _erp(erp, machines):
	refs = [m.current_job_reference for m in machines.values() if m.current_job_reference]
	if not refs:
		return
	rows = {
		r.name: r
		for r in frappe.get_all(
			"External Reference",
			{"name": ("in", refs)},
			["name", "erp_system", "reference_type", "external_id", "label", "status"],
		)
	}
	for name, m in machines.items():
		ref = rows.get(m.current_job_reference)
		if not ref:
			continue
		record = erp.asset(
			f"erp:{ref.name}",
			title=f"{ref.reference_type} {ref.external_id}",
			layer="Data",
			kind="ERP Record",
			status={"Resolved": "OK", "Missing": "Down"}.get(ref.status, "Unknown"),
			source_doctype="External Reference",
			source_name=ref.name,
			attributes={"erp_system": ref.erp_system, "label": ref.label},
		)
		# The event stream is the MES provider's; the link from it is the ERP provider's.
		erp.link(f"events:{name}", "Posts To", record)
