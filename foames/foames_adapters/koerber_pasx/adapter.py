# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

from foames.foames_adapters.koerber_pasx.profile import PROFILE
from foames.foames_adapters.mes.adapter import ProfileAdapter


class KoerberPASXAdapter(ProfileAdapter):
	profile = PROFILE
