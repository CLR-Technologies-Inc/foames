# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""MQTT gateway: subscribes to `<prefix>/<machine source id>/<event type>` and records events.

Run it as a long-lived process inside the bench, for example with a supervisor entry:

    bench --site <site> execute foames.foames_mes.gateway.mqtt.run

It needs the optional `paho-mqtt` package (pip install paho-mqtt). Payloads are JSON objects
(for example {"value": 1234} for a count, {"state": "Running"} for a state), or a bare value.
"""

import frappe

from foames.foames_mes.gateway.mapping import EventError, mqtt_message_to_raw


def get_settings():
	return frappe.get_single("Machine Data Settings")


def handle_message(topic: str, payload: bytes, prefix: str) -> str | None:
	"""Record one MQTT message. Returns the Machine Event name, or None when it was rejected."""
	from foames.foames_mes.api import record_event

	try:
		raw = mqtt_message_to_raw(topic, payload, prefix)
		name = record_event(raw, source="MQTT")
		frappe.db.commit()
		return name
	except EventError as e:
		frappe.logger("foames.mqtt").warning(f"rejected {topic}: {e}")
		return None
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title="MQTT gateway", message=frappe.get_traceback())
		return None


def run():
	try:
		import paho.mqtt.client as mqtt
	except ImportError:
		raise SystemExit("The MQTT gateway needs paho-mqtt: pip install paho-mqtt")

	settings = get_settings()
	if not settings.mqtt_enabled:
		raise SystemExit("MQTT is not enabled in Machine Data Settings")
	prefix = (settings.mqtt_topic_prefix or "foames").strip("/")

	client = mqtt.Client()
	if settings.mqtt_username:
		client.username_pw_set(
			settings.mqtt_username, settings.get_password("mqtt_password", raise_exception=False)
		)
	if settings.mqtt_tls:
		client.tls_set()

	def on_connect(c, userdata, flags, rc, *args):
		c.subscribe(f"{prefix}/+/+")
		c.subscribe(f"{prefix}/#")

	def on_message(c, userdata, message):
		handle_message(message.topic, message.payload, prefix)

	client.on_connect = on_connect
	client.on_message = on_message
	client.connect(settings.mqtt_broker, settings.mqtt_port or 1883, keepalive=60)
	client.loop_forever()
