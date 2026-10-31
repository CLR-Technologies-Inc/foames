# Development bench for FoaMES tests.
#
# One image with Python, Node, Yarn, a MariaDB client and frappe-bench. The bench itself is created
# at first start by scripts/setup-bench.sh into the bench-data volume, so this image never has to be
# rebuilt when Frappe, ERPNext or FoaMES change. Rebuild it only to change the Python or Node version.
ARG PYTHON_VERSION=3.12
ARG NODE_VERSION=24

FROM node:${NODE_VERSION}-bookworm-slim AS node

FROM python:${PYTHON_VERSION}-bookworm

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    LANG=C.UTF-8

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        cron \
        curl \
        default-libmysqlclient-dev \
        git \
        libffi-dev \
        mariadb-client \
        pkg-config \
        redis-tools \
        rsync \
        sudo \
    && rm -rf /var/lib/apt/lists/*

# Node and Yarn, copied from the official Node image so the version is a plain build argument.
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && npm install -g yarn@1 \
    && node --version && npm --version && yarn --version

RUN pip install --upgrade pip frappe-bench

# bench prefers not to run as root. The bench lives in a volume mounted at /home/frappe/benches.
RUN useradd --create-home --shell /bin/bash --uid 1000 frappe \
    && echo "frappe ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/frappe \
    && mkdir -p /home/frappe/benches /workspace \
    && chown -R frappe:frappe /home/frappe /workspace \
    # The MariaDB 11.x client wants TLS by default; the compose service offers none.
    && printf '[client]\nskip-ssl\n' > /home/frappe/.my.cnf \
    && chown frappe:frappe /home/frappe/.my.cnf

COPY --chmod=755 scripts/ /usr/local/share/foames-bench/

USER frappe
WORKDIR /home/frappe/benches

ENV PATH="/home/frappe/.local/bin:${PATH}" \
    BENCH_DIR=/home/frappe/benches/frappe-bench \
    FOAMES_SRC=/workspace/foames

CMD ["sleep", "infinity"]
