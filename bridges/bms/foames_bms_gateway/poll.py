# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Read every configured point once and turn the values into FoaMES readings."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from foames_bms_gateway import bacnet, modbus
from foames_bms_gateway.config import Config

log = logging.getLogger("foames_bms_gateway")


def _modbus_client(device):
	return modbus.Client(device.host, device.port, device.timeout)


class Readers:
	"""One BACnet client for every BACnet device and one Modbus client per Modbus device. Tests pass
	their own factories."""

	def __init__(self, config: Config, bacnet_factory=None, modbus_factory=None):
		self.config = config
		self._bacnet_factory = bacnet_factory or bacnet.Client
		self._modbus_factory = modbus_factory or _modbus_client
		self._bacnet = None
		self._modbus = {}

	def bacnet(self):
		if self._bacnet is None:
			self._bacnet = self._bacnet_factory()
		return self._bacnet

	def modbus(self, device):
		if device.name not in self._modbus:
			self._modbus[device.name] = self._modbus_factory(device)
		return self._modbus[device.name]

	def close(self):
		if self._bacnet is not None:
			self._bacnet.close()
		for client in self._modbus.values():
			client.close()


def _number(value) -> float:
	if isinstance(value, bool):
		return 1.0 if value else 0.0
	if isinstance(value, int | float):
		return float(value)
	raise ValueError(f"the device answered {value!r}, not a number")


def read_point(readers: Readers, point) -> tuple[float, str]:
	device = readers.config.devices[point.device]
	spec = point.spec
	quality = "Good"
	if device.protocol == "bacnet":
		client = readers.bacnet()
		kwargs = {"port": device.port, "dnet": device.dnet, "dadr": device.dadr}
		raw = client.read_property(
			device.host,
			spec["object_type"],
			spec["instance"],
			spec["property"],
			index=spec["index"],
			**kwargs,
		)
		if spec["status_flags"]:
			flags = client.read_property(
				device.host, spec["object_type"], spec["instance"], "status-flags", **kwargs
			)
			quality = bacnet.quality_from_flags(flags)
	else:
		raw = readers.modbus(device).read_value(
			device.unit,
			spec["table"],
			spec["address"],
			spec["data_type"],
			spec["word_order"],
			spec["byte_swap"],
		)
	return _number(raw) * point.scale + point.offset, quality


def iso(at: datetime) -> str:
	return at.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def poll_once(readers: Readers, clock=time.time) -> tuple[list[dict], list[dict]]:
	"""(readings, errors). A point that cannot be read is reported as an error and skipped: the
	gateway sends nothing for it, and FoaMES raises a stale alarm once it has been silent too long."""
	readings, errors = [], []
	for point in readers.config.points:
		try:
			value, quality = read_point(readers, point)
		except (bacnet.BACnetError, modbus.ModbusError, ValueError, OSError) as e:
			errors.append({"point": point.point, "error": str(e)})
			log.warning("cannot read %s: %s", point.point, e)
			continue
		at = datetime.fromtimestamp(clock(), tz=timezone.utc)
		stamp = iso(at)
		readings.append(
			{
				"point": point.point,
				"value": value,
				"timestamp": stamp,
				"quality": quality,
				"id": f"{point.point}@{stamp}",
			}
		)
	return readings, errors
