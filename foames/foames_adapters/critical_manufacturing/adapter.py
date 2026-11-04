# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

from foames.foames_adapters.critical_manufacturing.profile import PROFILE
from foames.foames_adapters.mes.adapter import ProfileAdapter


class CriticalManufacturingAdapter(ProfileAdapter):
	profile = PROFILE
