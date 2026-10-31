#!/usr/bin/env bash
# Host-side entry point for the FoaMES Docker dev bench.
#
#   ./bench.sh up            build the image, start MariaDB/Redis/bench, create the bench and site
#   ./bench.sh test [args]   run the tests (args go to `bench run-tests`, see scripts/run-tests.sh)
#   ./bench.sh bench <cmd>   run any bench command on the site, e.g. ./bench.sh bench migrate
#   ./bench.sh shell         open a shell in the bench directory
#   ./bench.sh serve         serve the site on http://localhost:8000 (Administrator / admin)
#   ./bench.sh logs          follow the service logs
#   ./bench.sh down          stop the services, keep the bench and the database
#   ./bench.sh reset         stop the services and delete the bench and database volumes
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

# Git Bash on Windows rewrites arguments that look like POSIX paths (the in-container script paths
# below) into Windows paths before Docker sees them. This turns that off for the docker calls.
export MSYS_NO_PATHCONV=1

# SITE_NAME and BENCH_DIR are set in the container's environment by docker-compose.yml.
in_bench() { docker compose exec bench "$@"; }
in_bench_dir() { in_bench bash -lc 'cd "$BENCH_DIR" && exec "$@"' bench "$@"; }

cmd="${1:-help}"
shift || true

case "$cmd" in
	up)
		docker compose up -d --build
		in_bench /usr/local/share/foames-bench/setup-bench.sh
		;;
	test)
		in_bench /usr/local/share/foames-bench/run-tests.sh "$@"
		;;
	bench)
		in_bench bash -lc 'cd "$BENCH_DIR" && exec bench --site "$SITE_NAME" "$@"' bench "$@"
		;;
	shell)
		in_bench_dir bash
		;;
	serve)
		in_bench bash -lc 'cd "$BENCH_DIR" && exec bench --site "$SITE_NAME" serve --port 8000'
		;;
	logs)
		docker compose logs -f "$@"
		;;
	down)
		docker compose down
		;;
	reset)
		docker compose down -v
		;;
	*)
		sed -n '2,12p' "$0"
		;;
esac
