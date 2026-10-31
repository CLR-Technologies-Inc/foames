#!/usr/bin/env bash
# Runs the FoaMES test suite inside the bench container, as the GitHub Actions workflow does.
#
#   run-tests.sh                                  # the whole app
#   run-tests.sh --module foames.foames_mes.test_oee_and_rules
#   run-tests.sh --doctype "Machine Event"
#   run-tests.sh --failfast
#
# Every argument is passed to `bench run-tests`. The site's data is rolled back by the test
# runner, so the suite can be run again without recreating the site.
set -euo pipefail

SITE_NAME="${SITE_NAME:-test_site}"
BENCH_DIR="${BENCH_DIR:-$HOME/benches/frappe-bench}"
export CI="${CI:-Yes}"
export TYPE="${TYPE:-server}"

if [ ! -f "$BENCH_DIR/sites/$SITE_NAME/site_config.json" ]; then
	echo "Site $SITE_NAME is missing. Run setup-bench.sh first (./bench.sh up on the host)." >&2
	exit 1
fi

cd "$BENCH_DIR"
bench --site "$SITE_NAME" set-config allow_tests true >/dev/null

args=("$@")
# Default to the whole app when no selector was given.
if ! printf '%s\n' "${args[@]}" | grep -qE '^--(app|module|doctype|test)$'; then
	args=(--app foames "${args[@]}")
fi

exec bench --site "$SITE_NAME" run-tests "${args[@]}"
