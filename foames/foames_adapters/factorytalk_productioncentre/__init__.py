# Copyright (c) 2026 CLR Technologies Inc. and contributors
# SPDX-License-Identifier: Apache-2.0

"""Rockwell FactoryTalk ProductionCentre adapter.

Rockwell Automation's on-premise enterprise MES (PharmaSuite for life sciences), tied to Allen-Bradley and ControlLogix automation.
The profile in `profile.py` says how FoaMES reaches it; the shared machinery is in
`foames.foames_adapters.mes`. Setup is in docs/mes-adapters.md (the framework) and
docs/vendors/factorytalk_productioncentre/README.md (this system).
"""

ADAPTER_KEY = "FTPC"
