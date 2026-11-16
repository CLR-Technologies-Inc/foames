# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""A read-only BACnet/IP client: the ReadProperty service, nothing else. Standard library only.

Written from the public structure of the protocol (ANSI/ASHRAE Standard 135, BACnet/IP Annex J):
a BVLC header, an NPDU and a confirmed-request APDU carrying ReadProperty, answered by a Complex-ACK
whose value is application-tagged. No vendor code or SDK is used. The client sends no write service
(WriteProperty, WritePropertyMultiple, a priority-array relinquish or any device command); the
only service choice it can put on the wire is READ_PROPERTY, and a test checks that.

Devices on the same IP subnet, or reached through a BACnet/IP router at a known address, are read
directly by IP and port. A device behind a router on another BACnet network takes that network
number and its MAC address (DNET/DADR).
"""

from __future__ import annotations

import itertools
import socket
import struct
from dataclasses import dataclass

PORT = 47808
BVLC_TYPE = 0x81
ORIGINAL_UNICAST = 0x0A
FORWARDED_NPDU = 0x04
NPDU_VERSION = 0x01

CONFIRMED_REQUEST = 0
COMPLEX_ACK = 3
ERROR_PDU = 5
REJECT_PDU = 6
ABORT_PDU = 7
READ_PROPERTY = 12
# The service choices this client may send. Writes are not among them, on purpose.
ALLOWED_SERVICES = frozenset({READ_PROPERTY})

OBJECT_TYPES = {
	"analog-input": 0,
	"analog-output": 1,
	"analog-value": 2,
	"binary-input": 3,
	"binary-output": 4,
	"binary-value": 5,
	"device": 8,
	"multi-state-input": 13,
	"multi-state-output": 14,
	"multi-state-value": 19,
	"accumulator": 23,
	"pulse-converter": 24,
	"large-analog-value": 46,
	"integer-value": 45,
	"positive-integer-value": 48,
}
PROPERTIES = {"present-value": 85, "status-flags": 111, "units": 117, "object-name": 77, "reliability": 103}
STATUS_FLAGS = ("in-alarm", "fault", "overridden", "out-of-service")


class BACnetError(RuntimeError):
	pass


def object_type_number(value) -> int:
	if isinstance(value, int):
		return value
	text = str(value).strip().lower().replace("_", "-").replace(" ", "-")
	if text.isdigit():
		return int(text)
	if text not in OBJECT_TYPES:
		raise BACnetError(f"unknown object type {value!r}")
	return OBJECT_TYPES[text]


def property_number(value) -> int:
	if isinstance(value, int):
		return value
	text = str(value).strip().lower().replace("_", "-").replace(" ", "-")
	if text.isdigit():
		return int(text)
	if text not in PROPERTIES:
		raise BACnetError(f"unknown property {value!r}")
	return PROPERTIES[text]


# Encoding


def _context_unsigned(tag: int, value: int) -> bytes:
	if value < 0:
		raise BACnetError("an unsigned value cannot be negative")
	length = max(1, (value.bit_length() + 7) // 8)
	if length > 4:
		raise BACnetError("value too large")
	return bytes([(tag << 4) | 0x08 | length]) + value.to_bytes(length, "big")


def object_identifier(object_type: int, instance: int) -> int:
	if not 0 <= object_type < 1024:
		raise BACnetError("object type must be 0 to 1023")
	if not 0 <= instance < 0x400000:
		raise BACnetError("instance must be 0 to 4194303")
	return (object_type << 22) | instance


def read_property_apdu(invoke_id: int, object_type: int, instance: int, prop: int, index=None) -> bytes:
	service = READ_PROPERTY
	if service not in ALLOWED_SERVICES:
		raise BACnetError("this client only reads")
	apdu = bytes(
		[
			(CONFIRMED_REQUEST << 4) | 0x02,  # segmented response accepted
			0x05,  # max segments unspecified, max APDU 1476 octets
			invoke_id & 0xFF,
			service,
		]
	)
	apdu += bytes([0x0C]) + struct.pack(">I", object_identifier(object_type, instance))
	apdu += _context_unsigned(1, prop)
	if index is not None:
		apdu += _context_unsigned(2, int(index))
	return apdu


def npdu(expecting_reply: bool = True, dnet: int | None = None, dadr: bytes | None = None) -> bytes:
	control = 0x04 if expecting_reply else 0x00
	if dnet is None:
		return bytes([NPDU_VERSION, control])
	dadr = dadr or b""
	return (
		bytes([NPDU_VERSION, control | 0x20])
		+ struct.pack(">H", dnet)
		+ bytes([len(dadr)])
		+ dadr
		+ bytes([0xFF])  # hop count
	)


def bvlc(payload: bytes) -> bytes:
	return bytes([BVLC_TYPE, ORIGINAL_UNICAST]) + struct.pack(">H", len(payload) + 4) + payload


def read_property_request(
	invoke_id: int, object_type: int, instance: int, prop: int, index=None, dnet=None, dadr=None
) -> bytes:
	return bvlc(npdu(True, dnet, dadr) + read_property_apdu(invoke_id, object_type, instance, prop, index))


# Decoding


def _tag(data: bytes, at: int) -> tuple[int, bool, int, int]:
	"""(tag number, is context, length-value-type, offset after the tag header)."""
	if at >= len(data):
		raise BACnetError("truncated tag")
	first = data[at]
	at += 1
	number = first >> 4
	if number == 0x0F:
		number = data[at]
		at += 1
	context = bool(first & 0x08)
	lvt = first & 0x07
	if lvt == 5:  # extended length
		length = data[at]
		at += 1
		if length == 254:
			length = struct.unpack(">H", data[at : at + 2])[0]
			at += 2
		elif length == 255:
			length = struct.unpack(">I", data[at : at + 4])[0]
			at += 4
		lvt = length
	return number, context, lvt, at


def _is_opening(data: bytes, at: int) -> bool:
	return at < len(data) and data[at] & 0x0F == 0x0E


def _is_closing(data: bytes, at: int) -> bool:
	return at < len(data) and data[at] & 0x0F == 0x0F


def decode_application(data: bytes, at: int):
	"""One application-tagged value at `at`. Returns (value, offset after it)."""
	first = data[at]
	number, context, lvt, at = _tag(data, at)
	if context:
		raise BACnetError("expected an application tag")
	if number == 1:  # Boolean: the value is in the tag itself
		return bool(first & 0x07), at
	body = data[at : at + lvt]
	if len(body) < lvt:
		raise BACnetError("truncated value")
	end = at + lvt
	if number == 0:
		return None, end
	if number in (2, 9):  # Unsigned, Enumerated
		return int.from_bytes(body, "big"), end
	if number == 3:  # Signed
		return int.from_bytes(body, "big", signed=True), end
	if number == 4:
		return struct.unpack(">f", body)[0], end
	if number == 5:
		return struct.unpack(">d", body)[0], end
	if number == 6:
		return body.hex(), end
	if number == 7:  # CharacterString; 0 is UTF-8 (ANSI X3.4 compatible)
		charset = body[0] if body else 0
		text = body[1:]
		return (text.decode("utf-8", "replace") if charset == 0 else text.decode("latin-1")), end
	if number == 8:  # BitString: first octet is the unused bit count
		unused = body[0] if body else 0
		bits = []
		for octet in body[1:]:
			bits.extend(bool(octet & (0x80 >> i)) for i in range(8))
		return bits[: len(bits) - unused] if unused else bits, end
	if number == 12:
		raw = int.from_bytes(body, "big")
		return {"type": raw >> 22, "instance": raw & 0x3FFFFF}, end
	return body.hex(), end


def _skip_npdu(data: bytes, at: int) -> tuple[int, bool]:
	"""Offset of the APDU and whether the NPDU carries a network-layer message instead."""
	if data[at] != NPDU_VERSION:
		raise BACnetError("not a BACnet NPDU")
	control = data[at + 1]
	at += 2
	if control & 0x20:  # destination specifier
		dlen = data[at + 2]
		at += 3 + dlen
	if control & 0x08:  # source specifier
		slen = data[at + 2]
		at += 3 + slen
	if control & 0x20:
		at += 1  # hop count
	return at, bool(control & 0x80)


@dataclass
class Answer:
	invoke_id: int
	kind: str  # "ack", "error", "reject", "abort", "other"
	value: object = None
	detail: str = ""


def parse_response(data: bytes) -> Answer | None:
	"""Read one BVLC datagram. Returns None for anything that is not an answer to a request."""
	if len(data) < 6 or data[0] != BVLC_TYPE:
		return None
	function = data[1]
	at = 4
	if function == FORWARDED_NPDU:
		at += 6  # original source address and port
	elif function != ORIGINAL_UNICAST:
		return None
	at, network_message = _skip_npdu(data, at)
	if network_message or at >= len(data):
		return None
	pdu_type = data[at] >> 4
	if pdu_type == COMPLEX_ACK:
		invoke_id, service = data[at + 1], data[at + 2]
		if data[at] & 0x08:
			raise BACnetError("segmented answers are not supported; read a smaller property")
		if service != READ_PROPERTY:
			return Answer(invoke_id, "other")
		return Answer(invoke_id, "ack", _read_property_ack(data, at + 3))
	if pdu_type == ERROR_PDU:
		invoke_id = data[at + 1]
		klass, after = decode_application(data, at + 3)
		code, _after = decode_application(data, after)
		return Answer(invoke_id, "error", detail=f"error class {klass}, code {code}")
	if pdu_type == REJECT_PDU:
		return Answer(data[at + 1], "reject", detail=f"reject reason {data[at + 2]}")
	if pdu_type == ABORT_PDU:
		return Answer(data[at + 1], "abort", detail=f"abort reason {data[at + 2]}")
	return None


def _read_property_ack(data: bytes, at: int):
	# [0] object identifier, [1] property identifier, optional [2] array index, then [3] { value }
	while at < len(data) and not _is_opening(data, at):
		_number, context, lvt, at = _tag(data, at)
		if not context:
			raise BACnetError("malformed ReadProperty answer")
		at += lvt
	if not _is_opening(data, at):
		raise BACnetError("ReadProperty answer carries no value")
	at += 1
	values = []
	while at < len(data) and not _is_closing(data, at):
		value, at = decode_application(data, at)
		values.append(value)
	return values[0] if len(values) == 1 else values


# Transport


class Client:
	"""Reads properties from BACnet/IP devices over UDP. `transport` is a socket-like object with
	sendto, recvfrom and settimeout (a real UDP socket by default); tests pass a stand-in.

	By default the socket is not bound: the first sendto picks an ephemeral port on the interface
	that routes to the device, and devices answer ReadProperty to that address. Pass
	`local_address=(ip, port)` only to answer from a specific interface; it never listens on all."""

	def __init__(self, timeout: float = 3.0, retries: int = 2, local_address=None, transport=None):
		self.timeout = timeout
		self.retries = max(int(retries), 0)
		if transport is None:
			transport = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
			if local_address:
				ip, port = local_address
				if not ip or ip == "0.0.0.0":
					raise BACnetError("local_address must name one interface, not all of them")
				transport.bind((ip, int(port)))
		self.transport = transport
		self.transport.settimeout(timeout)
		self._ids = itertools.cycle(range(256))

	def close(self):
		try:
			self.transport.close()
		except Exception:
			pass

	def read_property(
		self,
		host: str,
		object_type,
		instance: int,
		prop="present-value",
		*,
		port: int = PORT,
		index=None,
		dnet=None,
		dadr=None,
	):
		invoke_id = next(self._ids)
		request = read_property_request(
			invoke_id,
			object_type_number(object_type),
			int(instance),
			property_number(prop),
			index,
			dnet,
			dadr,
		)
		for attempt in range(self.retries + 1):
			self.transport.sendto(request, (host, int(port)))
			try:
				answer = self._await(invoke_id)
			except TimeoutError:
				if attempt >= self.retries:
					raise BACnetError(f"no answer from {host}:{port}")
				continue
			if answer.kind == "ack":
				return answer.value
			raise BACnetError(f"{host}:{port} answered {answer.kind}: {answer.detail}")
		raise BACnetError(f"no answer from {host}:{port}")

	def _await(self, invoke_id: int) -> Answer:
		while True:
			try:
				data, _addr = self.transport.recvfrom(1500)
			except TimeoutError as e:
				raise TimeoutError from e
			answer = parse_response(data)
			if answer is not None and answer.invoke_id == invoke_id:
				return answer


def quality_from_flags(flags) -> str:
	"""Status flags (in-alarm, fault, overridden, out-of-service) as a reading quality."""
	if not isinstance(flags, list) or len(flags) < 4:
		return "Good"
	if flags[1]:
		return "Bad"
	if flags[2] or flags[3]:
		return "Uncertain"
	return "Good"
