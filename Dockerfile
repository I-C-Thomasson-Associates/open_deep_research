# =============================================================================
# DOCKERFILE - Open Deep Research (Aegra runtime)
# =============================================================================
# Builds a self-hosted Aegra image. Aegra (Apache 2.0) is a drop-in replacement
# for the LangGraph Platform runtime; it implements the Agent Protocol API,
# manages a Redis-backed job queue with Postgres-checkpointed durability, and
# supports horizontal scaling across pods via lease-based crash recovery.
#
# Required runtime env vars (set by Kubernetes Deployment in
# sobe-aifoundry-infrastructure/dev/kubernetes.tf):
#   DATABASE_URL              -- postgres://user:pwd@host:5432/deep_research?sslmode=require
#   REDIS_URL                 -- redis://redis:6379/3
#   REDIS_BROKER_ENABLED=true -- enables Redis BLPOP dispatch (vs Postgres polling)
#   WORKER_COUNT              -- async workers per pod (we use 2)
#   N_JOBS_PER_WORKER         -- concurrent jobs per worker (we use 6 -> 12/pod)
#   LEASE_DURATION_SECONDS    -- worker heartbeat lease (30)
#   HEARTBEAT_INTERVAL_SECONDS-- heartbeat cadence (10)
#   RUN_MIGRATIONS_ON_STARTUP -- false; an init container runs alembic upgrade
#   VAULT_HOST, AZURE_CLIENT_ID
#                             -- bootstrap for src/open_deep_research/env.py
#   AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_VERSION, SEARCH_API,
#   GET_API_KEYS_FROM_CONFIG  -- non-secret application config
#
# Build:  docker build -t open-deep-research .
# Run:    docker run -p 2024:2024 --env-file .env open-deep-research
# Health: GET http://localhost:2024/live -> {"status":"ok"}
# =============================================================================

FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY src ./src
COPY aegra.json ./aegra.json
COPY langgraph.json ./langgraph.json
COPY README.md ./README.md

RUN pip install --no-cache-dir .

# Patch aegra-api 0.9.17's broken sslmode -> asyncpg translation.
# Upstream maps sslmode=require -> ssl=true (the literal string), but asyncpg
# rejects 'true' as an SSLMode value. The fix is identity-mapping the mode
# name; remove this patch when aegra-api ships a real fix in 0.9.18+.
RUN sed -i \
    -e 's|"disable": "false",|"disable": "disable",|' \
    -e 's|"allow": "false",|"allow": "allow",|' \
    -e 's|"prefer": "false",|"prefer": "prefer",|' \
    -e 's|"require": "true",|"require": "require",|' \
    -e 's|"verify-ca": "true",|"verify-ca": "verify-ca",|' \
    -e 's|"verify-full": "true",|"verify-full": "verify-full",|' \
    /usr/local/lib/python3.12/site-packages/aegra_api/settings.py \
    && python -c "from aegra_api.settings import _SSLMODE_TO_ASYNCPG; assert _SSLMODE_TO_ASYNCPG['require'] == 'require', _SSLMODE_TO_ASYNCPG; print('aegra sslmode patch applied:', _SSLMODE_TO_ASYNCPG)"

# -----------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AEGRA_CONFIG=/app/aegra.json \
    PORT=2024

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

RUN groupadd --system aegra \
    && useradd --system --gid aegra --create-home --shell /bin/bash aegra \
    && chown -R aegra:aegra /app
USER aegra

EXPOSE 2024

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://localhost:2024/live || exit 1

CMD ["aegra", "serve", "--host", "0.0.0.0", "--port", "2024", "--config", "/app/aegra.json"]
