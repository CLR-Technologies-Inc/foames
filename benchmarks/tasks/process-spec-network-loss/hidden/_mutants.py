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

"""Small breaks of FoaMES behaviour that the acceptance tests must catch."""

MUTANTS = {
	"counter_reset_invents_output": (
		"foames/foames_mes/counters.py",
		"	# A reset or an out-of-order reading. Nothing is invented.\n	return 0.0\n",
		"	return float(current)\n",
	),
	"unknown_counted_as_run": (
		"foames/foames_mes/oee.py",
		"		else:\n			ledger.unknown_minutes += minutes\n",
		"		else:\n			ledger.run_minutes += minutes\n",
	),
	"erp_5xx_retried_blind": (
		"foames/foames_adapters/s4hana/outbox.py",
		'"Unknown" if e.maybe_applied or verify_first else "Retry"',
		'"Retry"',
	),
}
