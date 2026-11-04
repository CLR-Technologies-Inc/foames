# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

from foames.foames_adapters.delmia_apriso.profile import PROFILE
from foames.foames_adapters.mes.adapter import ProfileAdapter


class DelmiaAprisoAdapter(ProfileAdapter):
	profile = PROFILE
