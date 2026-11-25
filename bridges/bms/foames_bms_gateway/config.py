# Copyright 2026 CLR Technologies Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""The gateway's configuration: the devices it reads and the points on them.

	{
	  "devices": {
	    "ahu-controller": {"protocol": "bacnet", "host": "10.0.5.20"},
	    "main-meter":     {"protocol": "modbus", "host": "10.0.6.10", "unit": 1}
	  },
	  "points": [
	    {"point": "AHU-1.SAT", "device": "ahu-controller", "object": "analog-input", "instance": 3},
	    {"point": "MAIN.kWh", "device": "main-meter", "reference": 40001, "data_type": "float32"}
	  ]
	}

`point` is the Building Point id in FoaMES. A BACnet point names `object` (type name or number),
`instance`, and optionally `property` (default present-value), `index` and `status_flags` (true: also
read the status flags and send a fault as Bad quality, overridden or out of service as Uncertain). A
Modbus point names either `reference` (00001, 10001, 30001 or 40001 style) or `table` (coil,
discrete, input, holding) and a zero-based `address`, then `data_type`, `word_order`, `byte_swap`,
`scale` and `offset`. A BACnet device behind a router on another network takes `dnet` and `dadr`
(the MAC address in hex). The file holds no secret; the webhook secret comes from the environment.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from foames_bms_gateway import bacnet, modbus

PROTOCOLS = ("bacnet", "modbus")
_DEVICE_KEYS = {"protocol", "host", "port", "unit", "timeout", "dnet", "dadr"}
_BACNET_KEYS = {
	"point",
	"device",
	"object",
	"instance",
	"property",
	"index",
	"status_flags",
	"scale",
	"offset",
}
_MODBUS_KEYS = {
	"point",
	"device",
	"reference",
	"table",
	"address",
	"data_type",
	"word_order",
	"byte_swap",
	"scale",
	"offset",
}


class ConfigError(ValueError):
	pass


@dataclass
class Device:
	name: str
	protocol: str
	host: str
	port: int
	unit: int = 1
	timeout: float = 3.0
	dnet: int | None = None
	dadr: bytes | None = None


@dataclass
class Point:
	point: str
	device: str
	spec: dict = field(default_factory=dict)
	scale: float = 1.0
	offset: float = 0.0


@dataclass
class Config:
	devices: dict
	points: list


def load(path: str) -> Config:
	try:
		# The path is one the operator named on the command line of a local tool, not request input.
		with open(path, encoding="utf-8") as f:  # nosemgrep
			raw = json.load(f)
	except (OSError, ValueError) as e:
		raise ConfigError(f"cannot read the configuration {path}: {e}") from e
	return from_dict(raw)


def _unknown(spec: dict, allowed: set, what: str):
	extra = sorted(set(spec) - allowed)
	if extra:
		raise ConfigError(f"{what}: unknown keys {', '.join(extra)}")


def _device(name: str, spec: dict) -> Device:
	if not isinstance(spec, dict):
		raise ConfigError(f"device {name} must be an object")
	_unknown(spec, _DEVICE_KEYS, f"device {name}")
	protocol = spec.get("protocol")
	if protocol not in PROTOCOLS:
		raise ConfigError(f"device {name}: protocol must be one of {', '.join(PROTOCOLS)}")
	if not spec.get("host"):
		raise ConfigError(f"device {name}: host is required")
	default_port = bacnet.PORT if protocol == "bacnet" else modbus.PORT
	dadr = spec.get("dadr")
	try:
		return Device(
			name=name,
			protocol=protocol,
			host=str(spec["host"]),
			port=int(spec.get("port") or default_port),
			unit=int(spec.get("unit", 1)),
			timeout=float(spec.get("timeout") or 3.0),
			dnet=int(spec["dnet"]) if spec.get("dnet") is not None else None,
			dadr=bytes.fromhex(dadr) if dadr else None,
		)
	except ValueError as e:
		raise ConfigError(f"device {name}: {e}") from e


def _bacnet_point(spec: dict) -> dict:
	_unknown(spec, _BACNET_KEYS, f"point {spec.get('point')}")
	try:
		object_type = bacnet.object_type_number(spec.get("object"))
		prop = bacnet.property_number(spec.get("property") or "present-value")
		instance = int(spec["instance"])
		bacnet.object_identifier(object_type, instance)
	except (KeyError, ValueError, bacnet.BACnetError) as e:
		raise ConfigError(f"point {spec.get('point')}: {e}") from e
	return {
		"object_type": object_type,
		"instance": instance,
		"property": prop,
		"index": spec.get("index"),
		"status_flags": bool(spec.get("status_flags")),
	}


def _modbus_point(spec: dict) -> dict:
	_unknown(spec, _MODBUS_KEYS, f"point {spec.get('point')}")
	try:
		if spec.get("reference") is not None:
			function, address = modbus.from_reference(spec["reference"])
			table = {v: k for k, v in modbus.TABLES.items()}[function]
		else:
			table = spec.get("table")
			if table not in modbus.TABLES:
				raise ConfigError(f"table must be one of {', '.join(modbus.TABLES)}")
			address = int(spec["address"])
		data_type = spec.get("data_type") or "uint16"
		if data_type not in modbus.DATA_TYPES:
			raise ConfigError(f"data_type must be one of {', '.join(modbus.DATA_TYPES)}")
		word_order = spec.get("word_order") or "big"
		if word_order not in ("big", "little"):
			raise ConfigError("word_order must be big or little")
	except (KeyError, ValueError, modbus.ModbusError) as e:
		raise ConfigError(f"point {spec.get('point')}: {e}") from e
	return {
		"table": table,
		"address": address,
		"data_type": data_type,
		"word_order": word_order,
		"byte_swap": bool(spec.get("byte_swap")),
	}


def from_dict(raw: dict) -> Config:
	if not isinstance(raw, dict) or not isinstance(raw.get("devices"), dict):
		raise ConfigError('the configuration needs a "devices" object and a "points" list')
	devices = {name: _device(name, spec) for name, spec in raw["devices"].items()}
	points, seen = [], set()
	for spec in raw.get("points") or []:
		if not isinstance(spec, dict) or not spec.get("point"):
			raise ConfigError("every point needs a point id")
		if spec["point"] in seen:
			raise ConfigError(f"point {spec['point']} is listed twice")
		seen.add(spec["point"])
		device = devices.get(spec.get("device"))
		if device is None:
			raise ConfigError(f"point {spec['point']}: unknown device {spec.get('device')!r}")
		parsed = _bacnet_point(spec) if device.protocol == "bacnet" else _modbus_point(spec)
		try:
			scale = float(spec.get("scale", 1))
			offset = float(spec.get("offset", 0))
		except (TypeError, ValueError) as e:
			raise ConfigError(f"point {spec['point']}: scale and offset must be numbers") from e
		points.append(Point(str(spec["point"]), device.name, parsed, scale, offset))
	if not points:
		raise ConfigError("the configuration lists no points")
	return Config(devices, points)
