# Copyright (c) 2026, CLR Technologies Inc. and contributors
# For license information, please see license.txt

"""FoaMES Process Mining.

Turns what FoaMES and its ERP adapters record into event logs, and runs standard process-mining
analyses over them: directly-follows discovery, variant and performance analysis, and conformance
against a reference model. The analyses in `eventlog`, `xes`, `ocel`, `discovery` and `conformance`
have no Frappe dependency; `extractors`, `api` and the DocTypes bind them to a site.
"""
