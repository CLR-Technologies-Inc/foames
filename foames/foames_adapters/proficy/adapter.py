# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

from foames.foames_adapters.mes.adapter import ProfileAdapter
from foames.foames_adapters.proficy.profile import PROFILE


class ProficyAdapter(ProfileAdapter):
	profile = PROFILE
