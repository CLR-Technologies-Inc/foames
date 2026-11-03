# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class MachineDataSettings(Document):
	def validate(self):
		from foames.foames_mes.gateway.opcua import security_config

		# Catch a missing certificate or a public private key when the settings are saved, not when
		# the gateway starts.
		security_config(self)
