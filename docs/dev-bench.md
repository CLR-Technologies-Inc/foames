# Docker dev bench

A disposable Frappe bench in Docker for working on FoaMES and running its whole test suite, including the tests that need a site. It mirrors the GitHub Actions matrix: Frappe v15 or v16 on MariaDB and Redis, with ERPNext optional. Nothing is installed on the host beyond Docker.

Everything lives under [`docker/`](../docker):

| File | Role |
| --- | --- |
| `docker-compose.yml` | MariaDB, two Redis instances (cache and queue) and the `bench` container. The checkout is bind-mounted into the container at `/workspace/foames`. |
| `Dockerfile` | Python, Node, Yarn, a MariaDB client and `frappe-bench`. Python and Node versions are build arguments. |
| `scripts/setup-bench.sh` | Runs inside the container. Creates the bench from the chosen Frappe branch, points it at the compose services, soft-links the checkout in as `apps/foames`, creates the site and installs ERPNext (when asked) and FoaMES. Idempotent. |
| `scripts/run-tests.sh` | Runs inside the container: `bench --site <site> run-tests --app foames`, with any selector passed through. |
| `bench.sh` | Host-side wrapper around the two scripts and `docker compose`. |
| `.env.example` | The knobs: Frappe branch, ERPNext branch, Python, Node, MariaDB image, site name, passwords, port. |

## Requirements

- Docker Engine with the Compose plugin (Docker Desktop on Windows or macOS, or `docker-ce` with `docker-compose-plugin` on Linux).
- About 4 GB of RAM for the containers and 5 GB of disk for the images, the bench and the database. ERPNext roughly doubles the bench.
- A shell that runs bash for `bench.sh`: any Linux or macOS terminal, or Git Bash or WSL on Windows. Without bash, run the `docker compose` commands listed under [Without bench.sh](#without-benchsh).

## First run

```bash
cd docker
cp .env.example .env        # optional: edit to pick v15, ERPNext, another Python or Node
./bench.sh up               # builds the image, starts the services, creates the bench and the site
./bench.sh test             # runs the whole FoaMES suite
```

The first `up` takes a while: it builds the image, clones Frappe (and ERPNext if configured), installs the Python and Node requirements and creates the site. Later runs of `up` skip every step whose result already exists and only refresh the requirements, so they finish in a minute or two.

The site is `test_site` with the Administrator password `admin`. `./bench.sh serve` serves it on <http://localhost:8000> for clicking through the Floor View and the DocTypes.

## Running tests

`./bench.sh test` takes the same selectors as `bench run-tests`:

```bash
./bench.sh test                                                         # everything
./bench.sh test --module foames.foames_mes.doctype.oee_period.test_oee_period
./bench.sh test --doctype "Machine Event"
./bench.sh test --failfast
```

The checkout is soft-linked into the bench, so an edit on the host is what the next test run sees. A change to a DocType JSON needs `./bench.sh bench migrate` before the test, as on any bench. A change to `pyproject.toml` dependencies needs `./bench.sh up` again, which reruns `bench setup requirements`.

The pure-logic tests (OEE, counters, rules, signing, Sparkplug) still run on the host with plain Python, as described in [installation.md](installation.md#development-setup). The bench is for the rest.

## Picking a configuration

Edit `docker/.env` and run `./bench.sh up` again. Changing the Frappe branch or the ERPNext setting on an existing bench is not supported by `bench init`, so run `./bench.sh reset` first (it deletes the bench and database volumes) and then `./bench.sh up`.

| Goal | `.env` |
| --- | --- |
| Frappe v16, no ERP (the default, same as the "Frappe v16" CI job) | `FRAPPE_BRANCH=version-16`, `ERPNEXT_BRANCH=` empty, `MARIADB_IMAGE=mariadb:11.8` |
| Frappe v16 with ERPNext (the "Frappe v16 + ERPNext" CI job) | as above with `ERPNEXT_BRANCH=version-16` |
| Frappe v15, no ERP (the "Frappe v15" CI job) | `FRAPPE_BRANCH=version-15`, `PYTHON_VERSION=3.11`, `NODE_VERSION=20`, `MARIADB_IMAGE=mariadb:10.6` |

Changing `PYTHON_VERSION` or `NODE_VERSION` rebuilds the image on the next `up`; the bench volume keeps the old virtualenv, so `reset` it too when the Python version changes.

## Everyday commands

| Command | Does |
| --- | --- |
| `./bench.sh up` | Start (or restart) everything and bring the bench up to date |
| `./bench.sh test [selectors]` | Run tests |
| `./bench.sh bench <command>` | Any `bench --site <site> <command>`, for example `migrate`, `console`, `mariadb`, `clear-cache` |
| `./bench.sh shell` | A shell in the bench directory, as the `frappe` user |
| `./bench.sh serve` | Serve the site on port 8000 (foreground; Ctrl-C stops it) |
| `./bench.sh logs [service]` | Follow container logs |
| `./bench.sh down` | Stop the containers; the bench and the database survive |
| `./bench.sh reset` | Stop and delete the volumes; the next `up` starts from scratch |

## Without bench.sh

The wrapper only strings `docker compose` calls together:

```bash
cd docker
docker compose up -d --build
docker compose exec bench /usr/local/share/foames-bench/setup-bench.sh
docker compose exec bench /usr/local/share/foames-bench/run-tests.sh --app foames
docker compose exec bench bash -lc 'cd "$BENCH_DIR" && bench --site "$SITE_NAME" migrate'
docker compose down -v      # reset
```

## How it differs from CI

The GitHub Actions workflow in `.github/workflows/ci.yml` copies the checkout into the bench with `bench get-app`; the dev bench soft-links it so edits are live. CI creates a fresh site per run; the dev bench keeps the site between runs and relies on the test runner's rollback, so a test that commits leaves rows behind. `./bench.sh reset` gives a clean slate when that matters. CI also runs Frappe's semgrep rules and pip-audit, which the dev bench does not; `pre-commit run --all-files` on the host covers the formatting and lint checks.

## Troubleshooting

- **`bench new-site` fails with an access-denied error for the site user.** The site's database user must be allowed to connect from the bench container. The script passes `--mariadb-user-host-login-scope='%'` and falls back to `--no-mariadb-socket` for older Frappe releases; check which one your Frappe branch accepts.
- **The MariaDB client refuses to connect over TLS.** The image writes `skip-ssl` into the `frappe` user's `~/.my.cnf`, as CI does. If you run a client elsewhere, pass `--skip-ssl`.
- **Port 8000 is taken.** Set `BENCH_PORT` in `.env`.
- **Windows line endings.** Keep the checkout with LF line endings (`git config core.autocrlf input`), or the scripts inside the container may fail to parse Python files with CRLF.
- **Something is wedged.** `./bench.sh reset` and `./bench.sh up` rebuild everything from the images, which stay cached.
