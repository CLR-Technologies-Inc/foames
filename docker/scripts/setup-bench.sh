#!/usr/bin/env bash
# Creates the Frappe bench and the test site inside the bench container. Safe to run again: every
# step is skipped when its result already exists, so a second run only refreshes requirements.
#
# Environment (set by docker-compose.yml): FRAPPE_BRANCH, ERPNEXT_BRANCH, SITE_NAME, DB_HOST,
# DB_ROOT_PASSWORD, ADMIN_PASSWORD, REDIS_CACHE, REDIS_QUEUE, BENCH_DIR, FOAMES_SRC.
set -euo pipefail

FRAPPE_BRANCH="${FRAPPE_BRANCH:-version-16}"
ERPNEXT_BRANCH="${ERPNEXT_BRANCH:-}"
SITE_NAME="${SITE_NAME:-test_site}"
DB_HOST="${DB_HOST:-mariadb}"
DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD:-root}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-admin}"
REDIS_CACHE="${REDIS_CACHE:-redis://redis-cache:6379}"
REDIS_QUEUE="${REDIS_QUEUE:-redis://redis-queue:6379}"
BENCH_DIR="${BENCH_DIR:-$HOME/benches/frappe-bench}"
FOAMES_SRC="${FOAMES_SRC:-/workspace/foames}"

log() { printf '\n==> %s\n' "$*"; }

wait_for_db() {
	log "Waiting for MariaDB at $DB_HOST"
	for _ in $(seq 1 60); do
		if mariadb --host "$DB_HOST" --user root --password="$DB_ROOT_PASSWORD" -e "select 1" >/dev/null 2>&1; then
			return 0
		fi
		sleep 2
	done
	echo "MariaDB did not answer at $DB_HOST" >&2
	return 1
}

# Written only after `bench init` returns, so a bench that failed half-way is not mistaken for one.
INIT_MARKER=".foames-bench-initialised"

init_bench() {
	if [ -f "$BENCH_DIR/$INIT_MARKER" ]; then
		log "Bench exists at $BENCH_DIR (Frappe $(cd "$BENCH_DIR/apps/frappe" && git rev-parse --abbrev-ref HEAD))"
		return 0
	fi
	if [ -d "$BENCH_DIR" ]; then
		log "Removing the incomplete bench at $BENCH_DIR from an earlier failed init"
		rm -rf "$BENCH_DIR"
	fi
	log "Creating the bench from Frappe $FRAPPE_BRANCH"
	mkdir -p "$(dirname "$BENCH_DIR")"
	bench init \
		--frappe-branch "$FRAPPE_BRANCH" \
		--python "$(command -v python3)" \
		--skip-redis-config-generation \
		--skip-assets \
		--no-backups \
		"$BENCH_DIR"
	echo "$FRAPPE_BRANCH" > "$BENCH_DIR/$INIT_MARKER"
}

configure_bench() {
	log "Pointing the bench at the compose services"
	cd "$BENCH_DIR"
	bench set-config -g db_host "$DB_HOST"
	bench set-config -g redis_cache "$REDIS_CACHE"
	bench set-config -g redis_queue "$REDIS_QUEUE"
	# Frappe v15 still reads redis_socketio; v16 reuses the queue.
	bench set-config -g redis_socketio "$REDIS_QUEUE"
	bench set-config -g socketio_port 9000
	bench set-config -g developer_mode 1
	bench set-config -g allow_tests true
}

get_erpnext() {
	[ -n "$ERPNEXT_BRANCH" ] || return 0
	cd "$BENCH_DIR"
	if [ -d apps/erpnext ]; then
		log "ERPNext is already in the bench"
		return 0
	fi
	log "Fetching ERPNext $ERPNEXT_BRANCH"
	bench get-app --branch "$ERPNEXT_BRANCH" --skip-assets erpnext
}

get_foames() {
	cd "$BENCH_DIR"
	if [ -e apps/foames ]; then
		log "foames is already in the bench ($(readlink -f apps/foames))"
	elif bench get-app --soft-link --skip-assets foames "$FOAMES_SRC"; then
		log "Soft-linked $FOAMES_SRC as apps/foames"
	else
		# Older bench releases have no --soft-link; link by hand and register the app.
		log "bench get-app --soft-link failed, linking apps/foames by hand"
		ln -s "$FOAMES_SRC" apps/foames
		grep -qx foames sites/apps.txt 2>/dev/null || echo foames >> sites/apps.txt
	fi
	log "Installing requirements"
	bench setup requirements --dev
	# The soft link keeps the host checkout live, so make sure the editable install points at it.
	./env/bin/pip install --quiet --no-deps -e apps/foames
}

create_site() {
	cd "$BENCH_DIR"
	if [ -f "sites/$SITE_NAME/site_config.json" ]; then
		log "Site $SITE_NAME exists"
		return 0
	fi
	log "Creating site $SITE_NAME"
	# The site's database user must be allowed to log in from the bench container, not only from
	# localhost on the database host. Frappe v15.x and v16 call the option --mariadb-user-host-login-scope.
	bench new-site \
		--db-root-password "$DB_ROOT_PASSWORD" \
		--admin-password "$ADMIN_PASSWORD" \
		--mariadb-user-host-login-scope='%' \
		"$SITE_NAME" \
	|| bench new-site \
		--db-root-password "$DB_ROOT_PASSWORD" \
		--admin-password "$ADMIN_PASSWORD" \
		--no-mariadb-socket \
		"$SITE_NAME"
	bench use "$SITE_NAME"
}

install_apps() {
	cd "$BENCH_DIR"
	local installed
	installed="$(bench --site "$SITE_NAME" list-apps 2>/dev/null || true)"
	if [ -n "$ERPNEXT_BRANCH" ] && ! grep -qw erpnext <<<"$installed"; then
		log "Installing ERPNext on $SITE_NAME"
		bench --site "$SITE_NAME" install-app erpnext
	fi
	if ! grep -qw foames <<<"$installed"; then
		log "Installing foames on $SITE_NAME"
		bench --site "$SITE_NAME" install-app foames
	else
		log "foames is installed on $SITE_NAME, migrating"
		bench --site "$SITE_NAME" migrate
	fi
	bench --site "$SITE_NAME" set-config allow_tests true
	log "Building foames assets"
	bench build --app foames
}

wait_for_db
init_bench
configure_bench
get_erpnext
get_foames
create_site
install_apps

log "Ready. Run the tests with: bench --site $SITE_NAME run-tests --app foames"
