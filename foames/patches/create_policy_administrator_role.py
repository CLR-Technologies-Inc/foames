# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Sites installed before authorization hardening need the FoaMES Policy Administrator role before
the Connector Write Policy permissions that name it are synced."""

from foames.install import before_install


def execute():
	before_install()
