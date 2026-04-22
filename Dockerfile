# =============================================================================
# DOCKERFILE - Open Deep Research (LangGraph API)
# =============================================================================
# Inherits from the official LangGraph Platform API image, which ships the Go
# gRPC persistence binary required for the Postgres runtime. When POSTGRES_URI
# is set at runtime the container automatically selects the Postgres runtime
# (multi-worker + multi-pod safe via shared state); otherwise it falls back to
# the in-memory runtime for local single-process use.
#
# The base image already provides:
#   - Non-root runtime user
#   - Healthcheck on http://localhost:2024/ok
#   - Entrypoint that honors POSTGRES_URI, REDIS_URI, WEB_CONCURRENCY,
#     N_JOBS_PER_WORKER, LANGSERVE_GRAPHS, BG_JOB_TIMEOUT_SECS, and the
#     LANGSMITH_* / LANGGRAPH_* air-gap toggles.
#
# Build:  docker build -t open-deep-research .
# Run:    docker run -p 2024:2024 --env-file .env open-deep-research
# Health: GET http://localhost:2024/ok -> {"ok": true}
# =============================================================================

FROM langchain/langgraph-api:3.11

# Copy project sources into the standard LangGraph Platform deps path so that
# `pip install -e` keeps the graph module importable under the path declared in
# LANGSERVE_GRAPHS below.
ADD ./pyproject.toml /deps/open-deep-research/pyproject.toml
ADD ./uv.lock /deps/open-deep-research/uv.lock
ADD ./langgraph.json /deps/open-deep-research/langgraph.json
ADD ./src /deps/open-deep-research/src
ADD ./README.md /deps/open-deep-research/README.md

# Install the project against the base image's pinned constraints. The
# constraints file ensures langgraph / langgraph-api / langsmith stay aligned
# with the Go runtime in the base image and avoids accidental upgrades from
# our own pyproject pins.
RUN PYTHONDONTWRITEBYTECODE=1 \
    pip install --no-cache-dir -c /api/constraints.txt -e /deps/open-deep-research

# Advertise the graph to the platform entrypoint. Key is the user-facing graph
# name ("Deep Researcher"); value is the import path.
ENV LANGSERVE_GRAPHS='{"Deep Researcher": "/deps/open-deep-research/src/open_deep_research/deep_researcher.py:deep_researcher"}'

# Keep long-running research jobs from being culled by the default timeout.
# Can be overridden at deploy time via the Kubernetes env var of the same name.
ENV BG_JOB_TIMEOUT_SECS=1800

WORKDIR /deps/open-deep-research

EXPOSE 2024
