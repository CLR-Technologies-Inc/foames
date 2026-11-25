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

"""A read-only Modbus TCP client: read coils, discrete inputs, holding and input registers.
Standard library only.

Written from the public Modbus Application Protocol Specification V1.1b3 and the Modbus Messaging
on TCP/IP Implementation Guide V1.0b (Modbus Organization): an MBAP header (transaction id, protocol
id 0, length, unit id) and a PDU (function code, starting address, quantity). Only the read function
codes 1, 2, 3 and 4 can be sent; the write codes (5, 6, 15, 16, 22, 23) are refused before anything
goes on the wire, and a test checks that.

Register values are decoded as uint16, int16, uint32, int32, float32 or float64, with the word order
the meter documents (big: high word first, the Modbus convention; little: low word first) and an
optional byte swap inside each register, then scaled: value * scale + offset.
"""

from __future__ import annotations

import itertools
import socket
import struct

PORT = 502
READ_COILS = 1
READ_DISCRETE_INPUTS = 2
READ_HOLDING_REGISTERS = 3
READ_INPUT_REGISTERS = 4
READ_FUNCTIONS = frozenset({READ_COILS, READ_DISCRETE_INPUTS, READ_HOLDING_REGISTERS, READ_INPUT_REGISTERS})
TABLES = {
	"coil": READ_COILS,
	"discrete": READ_DISCRETE_INPUTS,
	"holding": READ_HOLDING_REGISTERS,
	"input": READ_INPUT_REGISTERS,
}
DATA_TYPES = {"uint16": 1, "int16": 1, "uint32": 2, "int32": 2, "float32": 2, "float64": 4}
EXCEPTIONS = {
	1: "illegal function",
	2: "illegal data address",
	3: "illegal data value",
	4: "server device failure",
	5: "acknowledge",
	6: "server device busy",
	8: "memory parity error",
	10: "gateway path unavailable",
	11: "gateway target device failed to respond",
}


class ModbusError(RuntimeError):
	pass


def from_reference(reference: int) -> tuple[int, int]:
	"""A conventional 5- or 6-digit reference (00001, 10001, 30001, 40001, or 400001) as
	(function code, zero-based protocol address)."""
	reference = int(reference)
	digits = len(str(reference))
	base = 100000 if digits >= 6 else 10000
	table, number = divmod(reference, base)
	if number < 1:
		raise ModbusError(f"reference {reference} has no register number")
	function = {
		0: READ_COILS,
		1: READ_DISCRETE_INPUTS,
		3: READ_INPUT_REGISTERS,
		4: READ_HOLDING_REGISTERS,
	}.get(table)
	if function is None:
		raise ModbusError(f"reference {reference} is not a coil, input or register reference")
	return function, number - 1


def read_request(transaction_id: int, unit: int, function: int, address: int, quantity: int) -> bytes:
	if function not in READ_FUNCTIONS:
		raise ModbusError("this client only reads (function codes 1 to 4)")
	limit = 2000 if function in (READ_COILS, READ_DISCRETE_INPUTS) else 125
	if not 1 <= quantity <= limit:
		raise ModbusError(f"quantity must be 1 to {limit}")
	if not 0 <= address <= 0xFFFF or address + quantity > 0x10000:
		raise ModbusError("address out of range")
	if not 0 <= unit <= 255:
		raise ModbusError("unit id must be 0 to 255")
	pdu = struct.pack(">BHH", function, address, quantity)
	return struct.pack(">HHHB", transaction_id & 0xFFFF, 0, len(pdu) + 1, unit) + pdu


def parse_response(frame: bytes, transaction_id: int, function: int, quantity: int):
	"""Registers (list of int) or bits (list of bool) from one response frame."""
	if len(frame) < 9:
		raise ModbusError("truncated response")
	tid, protocol, length, _unit = struct.unpack(">HHHB", frame[:7])
	if tid != transaction_id & 0xFFFF or protocol != 0:
		raise ModbusError("response does not answer this request")
	if len(frame) < 6 + length:
		raise ModbusError("truncated response")
	code = frame[7]
	if code == function | 0x80:
		reason = EXCEPTIONS.get(frame[8], f"exception {frame[8]}")
		raise ModbusError(f"device answered {reason}")
	if code != function:
		raise ModbusError(f"unexpected function code {code}")
	count = frame[8]
	data = frame[9 : 9 + count]
	if len(data) < count:
		raise ModbusError("truncated response")
	if function in (READ_COILS, READ_DISCRETE_INPUTS):
		bits = [bool(octet & (1 << i)) for octet in data for i in range(8)]
		return bits[:quantity]
	if count != 2 * quantity:
		raise ModbusError("register count does not match the request")
	return list(struct.unpack(f">{quantity}H", data))


def decode(
	registers: list[int], data_type: str = "uint16", word_order: str = "big", byte_swap: bool = False
) -> float:
	if data_type not in DATA_TYPES:
		raise ModbusError(f"data type must be one of {', '.join(DATA_TYPES)}")
	needed = DATA_TYPES[data_type]
	if len(registers) < needed:
		raise ModbusError(f"{data_type} needs {needed} registers")
	words = list(registers[:needed])
	if word_order == "little":
		words.reverse()
	elif word_order != "big":
		raise ModbusError("word order must be big or little")
	raw = b"".join(struct.pack(">H", w) for w in words)
	if byte_swap:
		raw = b"".join(raw[i + 1 : i + 2] + raw[i : i + 1] for i in range(0, len(raw), 2))
	fmt = {"uint16": ">H", "int16": ">h", "uint32": ">I", "int32": ">i", "float32": ">f", "float64": ">d"}[
		data_type
	]
	return float(struct.unpack(fmt, raw)[0])


class Client:
	"""Reads one Modbus TCP server. `connect` opens the socket (a TCP connection by default); tests
	pass a stand-in that returns a socket-like object with sendall, recv and close."""

	def __init__(self, host: str, port: int = PORT, timeout: float = 3.0, connect=None):
		self.host, self.port, self.timeout = host, int(port), timeout
		self._connect = connect or self._open
		self._sock = None
		self._ids = itertools.cycle(range(1, 0x10000))

	def _open(self):
		return socket.create_connection((self.host, self.port), timeout=self.timeout)

	def close(self):
		if self._sock is not None:
			try:
				self._sock.close()
			finally:
				self._sock = None

	def _recv(self, size: int) -> bytes:
		out = b""
		while len(out) < size:
			chunk = self._sock.recv(size - len(out))
			if not chunk:
				raise ModbusError(f"{self.host}:{self.port} closed the connection")
			out += chunk
		return out

	def read(self, unit: int, function: int, address: int, quantity: int):
		request_id = next(self._ids)
		request = read_request(request_id, unit, function, address, quantity)
		for attempt in range(2):
			try:
				if self._sock is None:
					self._sock = self._connect()
				self._sock.sendall(request)
				header = self._recv(7)
				length = struct.unpack(">H", header[4:6])[0]
				frame = header + self._recv(length - 1)
				return parse_response(frame, request_id, function, quantity)
			except (OSError, ModbusError) as e:
				self.close()
				if isinstance(e, ModbusError) and "device answered" in str(e):
					raise
				if attempt:
					raise ModbusError(f"cannot read {self.host}:{self.port}: {e}") from e
		raise ModbusError(f"cannot read {self.host}:{self.port}")

	def read_value(
		self,
		unit: int,
		table: str,
		address: int,
		data_type: str = "uint16",
		word_order: str = "big",
		byte_swap: bool = False,
	) -> float:
		function = TABLES.get(table)
		if function is None:
			raise ModbusError(f"table must be one of {', '.join(TABLES)}")
		if function in (READ_COILS, READ_DISCRETE_INPUTS):
			return 1.0 if self.read(unit, function, address, 1)[0] else 0.0
		registers = self.read(unit, function, address, DATA_TYPES.get(data_type, 1))
		return decode(registers, data_type, word_order, byte_swap)
