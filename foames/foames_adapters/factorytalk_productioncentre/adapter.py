# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

from foames.foames_adapters.factorytalk_productioncentre.profile import PROFILE
from foames.foames_adapters.mes.adapter import ProfileAdapter


class FactoryTalkProductionCentreAdapter(ProfileAdapter):
	profile = PROFILE
