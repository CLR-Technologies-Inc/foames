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
