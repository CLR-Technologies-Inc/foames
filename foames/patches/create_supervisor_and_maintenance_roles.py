# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Sites installed before the role workspaces need the two new roles before the DocType permissions
that name them are synced."""

from foames.install import before_install


def execute():
	before_install()
