# Copyright 2026 CLR Technologies Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

import frappe


def check_requalification(today=None) -> list[str]:
	"""Scheduled daily: raise an Agent Suggestion for each qualification that is Due Soon or Expired.
	Returns the suggestions created or reopened."""
	from foames.foames_mes.doctype.agent_suggestion.agent_suggestion import raise_suggestions
	from foames.foames_validation.api import qualification_rows
	from foames.foames_validation.qualification import findings

	if not frappe.db.table_exists("Validation Execution"):
		return []
	return raise_suggestions(findings(qualification_rows(today=today)), agent="foames-validation")
