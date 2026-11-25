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

"""The BMS gateway: BACnet ReadProperty frames, Modbus TCP frames and decoding, the configuration,
polling, and that neither client can send a write."""

import ast
import json
import pathlib
import struct
import unittest

from foames_bms_gateway import bacnet, config, modbus
from foames_bms_gateway.poll import Readers, poll_once
from foames_bms_gateway.sender import INGEST_PATH, WebhookSender, sign

PACKAGE = pathlib.Path(__file__).resolve().parent.parent / "foames_bms_gateway"


def complex_ack(invoke_id, value_bytes, object_id=(0, 3), prop=85):
	apdu = bytes([0x30, invoke_id, 0x0C, 0x0C]) + struct.pack(">I", (object_id[0] << 22) | object_id[1])
	apdu += bytes([0x19, prop]) + b"\x3e" + value_bytes + b"\x3f"
	payload = bytes([0x01, 0x00]) + apdu
	return bytes([0x81, 0x0A]) + struct.pack(">H", len(payload) + 4) + payload


class FakeUDP:
	def __init__(self, answers):
		self.answers = list(answers)
		self.sent = []

	def settimeout(self, _t):
		pass

	def sendto(self, data, addr):
		self.sent.append((data, addr))

	def recvfrom(self, _n):
		if not self.answers:
			raise TimeoutError
		answer = self.answers.pop(0)
		if callable(answer):
			answer = answer(self.sent[-1][0])
		return answer, ("10.0.0.1", 47808)

	def close(self):
		pass


def echo_invoke(value_bytes, **kw):
	"""An answer built for whatever invoke id the last request carried."""
	return lambda request: complex_ack(request[8], value_bytes, **kw)


class TestBACnet(unittest.TestCase):
	def test_read_property_request(self):
		frame = bacnet.read_property_request(7, 0, 3, 85)
		self.assertEqual(frame.hex(), "810a001101040205070c0c000000031955")

	def test_routed_request_carries_dnet_and_dadr(self):
		frame = bacnet.read_property_request(1, 2, 5, 85, dnet=2001, dadr=b"\x0a")
		self.assertEqual(frame[4:12].hex(), "012407d1010aff02")

	def test_large_property_number_takes_two_octets(self):
		apdu = bacnet.read_property_apdu(1, 8, 1234, 300)
		self.assertTrue(apdu.endswith(bytes([0x1A, 0x01, 0x2C])))

	def test_decode_real_enumerated_unsigned_boolean(self):
		real = bacnet.parse_response(complex_ack(9, b"\x44" + struct.pack(">f", 21.5)))
		self.assertEqual((real.invoke_id, real.kind, real.value), (9, "ack", 21.5))
		self.assertEqual(bacnet.parse_response(complex_ack(1, b"\x91\x01")).value, 1)
		self.assertEqual(bacnet.parse_response(complex_ack(1, b"\x21\x03")).value, 3)
		self.assertIs(bacnet.parse_response(complex_ack(1, b"\x11")).value, True)

	def test_status_flags_bitstring_and_quality(self):
		answer = bacnet.parse_response(complex_ack(2, b"\x82\x04\x40", prop=111))
		self.assertEqual(answer.value, [False, True, False, False])
		self.assertEqual(bacnet.quality_from_flags(answer.value), "Bad")
		self.assertEqual(bacnet.quality_from_flags([False, False, False, True]), "Uncertain")
		self.assertEqual(bacnet.quality_from_flags([True, False, False, False]), "Good")

	def test_error_reject_abort(self):
		error = bytes([0x81, 0x0A, 0x00, 0x0D, 0x01, 0x00, 0x50, 0x04, 0x0C, 0x91, 0x02, 0x91, 0x20])
		answer = bacnet.parse_response(error)
		self.assertEqual((answer.kind, answer.invoke_id), ("error", 4))
		self.assertIn("class 2, code 32", answer.detail)
		reject = bytes([0x81, 0x0A, 0x00, 0x09, 0x01, 0x00, 0x60, 0x04, 0x01])
		self.assertEqual(bacnet.parse_response(reject).kind, "reject")

	def test_client_retries_and_matches_invoke_id(self):
		udp = FakeUDP(
			[
				complex_ack(200, b"\x44" + struct.pack(">f", 1.0)),
				echo_invoke(b"\x44" + struct.pack(">f", 7.25)),
			]
		)
		client = bacnet.Client(transport=udp)
		self.assertEqual(client.read_property("10.0.0.1", "analog-input", 3), 7.25)
		self.assertEqual(udp.sent[0][1], ("10.0.0.1", 47808))

	def test_client_times_out(self):
		client = bacnet.Client(transport=FakeUDP([]), retries=1)
		with self.assertRaises(bacnet.BACnetError):
			client.read_property("10.0.0.1", "analog-input", 3)

	def test_only_read_property_can_be_sent(self):
		self.assertEqual(bacnet.ALLOWED_SERVICES, {bacnet.READ_PROPERTY})


class FakeTCP:
	def __init__(self, respond):
		self.respond = respond
		self.buffer = b""
		self.requests = []

	def sendall(self, data):
		self.requests.append(data)
		self.buffer += self.respond(data)

	def recv(self, n):
		out, self.buffer = self.buffer[:n], self.buffer[n:]
		return out

	def close(self):
		pass


def register_answer(registers):
	def respond(request):
		tid, _p, _l, unit, function = struct.unpack(">HHHBB", request[:8])
		data = b"".join(struct.pack(">H", r) for r in registers)
		pdu = bytes([function, len(data)]) + data
		return struct.pack(">HHHB", tid, 0, len(pdu) + 1, unit) + pdu

	return respond


class TestModbus(unittest.TestCase):
	def test_read_request(self):
		self.assertEqual(modbus.read_request(1, 17, 3, 107, 3).hex(), "0001000000061103006b0003")

	def test_write_function_codes_are_refused(self):
		for code in (5, 6, 15, 16, 22, 23):
			with self.assertRaises(modbus.ModbusError):
				modbus.read_request(1, 1, code, 0, 1)

	def test_references(self):
		self.assertEqual(modbus.from_reference(40001), (3, 0))
		self.assertEqual(modbus.from_reference(30010), (4, 9))
		self.assertEqual(modbus.from_reference(10001), (2, 0))
		self.assertEqual(modbus.from_reference(1), (1, 0))
		self.assertEqual(modbus.from_reference(400101), (3, 100))

	def test_decode(self):
		hi, lo = struct.unpack(">HH", struct.pack(">f", 1234.5))
		self.assertEqual(modbus.decode([hi, lo], "float32"), 1234.5)
		self.assertEqual(modbus.decode([lo, hi], "float32", "little"), 1234.5)
		self.assertEqual(modbus.decode([0xFFFF], "int16"), -1)
		self.assertEqual(modbus.decode([0x0001, 0x0000], "uint32"), 65536)
		self.assertEqual(modbus.decode([0x3412], "uint16", byte_swap=True), 0x1234)

	def test_client_reads_and_scales_through_poll(self):
		hi, lo = struct.unpack(">HH", struct.pack(">f", 5000.0))
		cfg = config.from_dict(
			{
				"devices": {"meter": {"protocol": "modbus", "host": "10.0.6.10", "unit": 2}},
				"points": [
					{
						"point": "MAIN.KW",
						"device": "meter",
						"reference": 40003,
						"data_type": "float32",
						"scale": 0.001,
					}
				],
			}
		)
		sock = FakeTCP(register_answer([hi, lo]))
		readers = Readers(cfg, modbus_factory=lambda d: modbus.Client(d.host, d.port, connect=lambda: sock))
		readings, errors = poll_once(readers, clock=lambda: 1_763_280_000.0)
		self.assertEqual(errors, [])
		self.assertEqual(readings[0]["point"], "MAIN.KW")
		self.assertAlmostEqual(readings[0]["value"], 5.0)
		self.assertEqual(readings[0]["timestamp"], "2025-11-16T08:00:00.000Z")
		self.assertEqual(readings[0]["id"], "MAIN.KW@2025-11-16T08:00:00.000Z")
		self.assertEqual(sock.requests[0][6:], bytes([2, 3, 0, 2, 0, 2]))

	def test_exception_response(self):
		def respond(request):
			tid = struct.unpack(">H", request[:2])[0]
			return struct.pack(">HHHB", tid, 0, 3, 1) + bytes([0x83, 0x02])

		client = modbus.Client("h", connect=lambda: FakeTCP(respond))
		with self.assertRaisesRegex(modbus.ModbusError, "illegal data address"):
			client.read(1, 3, 0, 1)


class TestConfigAndPoll(unittest.TestCase):
	def test_example_config_loads(self):
		cfg = config.load(str(pathlib.Path(__file__).resolve().parent.parent / "examples" / "bms.json"))
		self.assertEqual(len(cfg.points), 5)
		self.assertEqual(cfg.devices["chiller-plant"].dadr, b"\x0a")

	def test_bad_configs(self):
		with self.assertRaises(config.ConfigError):
			config.from_dict({"devices": {"d": {"protocol": "knx", "host": "h"}}, "points": []})
		with self.assertRaises(config.ConfigError):
			config.from_dict(
				{
					"devices": {"d": {"protocol": "bacnet", "host": "h"}},
					"points": [
						{"point": "p", "device": "d", "object": "analog-input", "instance": 1, "write": 5}
					],
				}
			)

	def test_bacnet_poll_with_status_flags(self):
		cfg = config.from_dict(
			{
				"devices": {"ahu": {"protocol": "bacnet", "host": "10.0.5.20"}},
				"points": [
					{
						"point": "AHU-1.SAT",
						"device": "ahu",
						"object": "analog-input",
						"instance": 3,
						"status_flags": True,
					}
				],
			}
		)
		udp = FakeUDP(
			[echo_invoke(b"\x44" + struct.pack(">f", 13.5)), echo_invoke(b"\x82\x04\x10", prop=111)]
		)
		readers = Readers(cfg, bacnet_factory=lambda: bacnet.Client(transport=udp))
		readings, errors = poll_once(readers, clock=lambda: 0.0)
		self.assertEqual(errors, [])
		self.assertEqual((readings[0]["value"], readings[0]["quality"]), (13.5, "Uncertain"))

	def test_unreadable_point_is_an_error_not_a_reading(self):
		cfg = config.from_dict(
			{
				"devices": {"ahu": {"protocol": "bacnet", "host": "10.0.5.20"}},
				"points": [{"point": "AHU-1.SAT", "device": "ahu", "object": "analog-input", "instance": 3}],
			}
		)
		readers = Readers(cfg, bacnet_factory=lambda: bacnet.Client(transport=FakeUDP([]), retries=0))
		readings, errors = poll_once(readers)
		self.assertEqual(readings, [])
		self.assertEqual(errors[0]["point"], "AHU-1.SAT")


class FakeResponse:
	def __init__(self, body):
		self.body = body

	def read(self):
		return self.body

	def __enter__(self):
		return self

	def __exit__(self, *a):
		return False


class TestSender(unittest.TestCase):
	def test_posts_signed_readings(self):
		seen = []

		def opener(request, timeout):
			seen.append(request)
			return FakeResponse(json.dumps({"message": {"accepted": ["a"], "rejected": []}}).encode())

		sender = WebhookSender(
			"https://foames.example.com", "s3cret", opener=opener, clock=lambda: 1700000000
		)
		answer = sender.send([{"point": "P", "value": 1}])
		self.assertEqual(answer["accepted"], ["a"])
		request = seen[0]
		self.assertTrue(request.full_url.endswith(INGEST_PATH))
		self.assertEqual(json.loads(request.data), {"readings": [{"point": "P", "value": 1}]})
		self.assertEqual(request.get_header("X-foames-signature"), sign("s3cret", "1700000000", request.data))


class TestReadOnly(unittest.TestCase):
	"""No write service or write function code appears anywhere in the package."""

	def test_no_write_services_in_the_code(self):
		forbidden = ("WriteProperty", "write_property", "WRITE_", "relinquish")
		for path in PACKAGE.glob("*.py"):
			tree = ast.parse(path.read_text())
			names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
			names |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
			names |= {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef | ast.ClassDef)}
			for name in names:
				for word in forbidden:
					self.assertNotIn(word, name, f"{path.name} names {name}")


if __name__ == "__main__":
	unittest.main()
