# ── Build stage ─────────────────────────────────────────────────────────────
FROM python:3.14-slim AS builder

# Pin uv version for reproducible builds
COPY --from=ghcr.io/astral-sh/uv:0.6 /uv /usr/local/bin/uv

WORKDIR /app

# Copy all build inputs (pyproject needs src/ to build the local package wheel)
COPY pyproject.toml uv.lock alembic.ini ./
COPY src/ src/

RUN uv sync --frozen --no-dev --no-cache --compile-bytecode

# ── Runtime stage ────────────────────────────────────────────────────────────
FROM python:3.14-slim AS runtime

# Python tuning: no .pyc rewrites, unbuffered stdout for clean Docker logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Only runtime system dep: curl (used by HEALTHCHECK)
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user — consistent UID for file permission predictability
RUN adduser --disabled-password --gecos '' --uid 1001 appuser

# Copy virtualenv from builder — no build tools in the final image
COPY --from=builder --chown=appuser:appuser /app/.venv .venv

# Copy application files (owned by appuser)
COPY --chown=appuser:appuser alembic.ini ./
COPY --chown=appuser:appuser src/ src/
COPY --chown=appuser:appuser config/ config/
COPY --chown=appuser:appuser migrations/ migrations/
COPY --chown=appuser:appuser soul.md ./
COPY --chown=appuser:appuser sops/ sops/

# Persistent workspace volume — agent working directories
RUN mkdir -p workspaces && chown appuser:appuser workspaces
VOLUME ["/app/workspaces"]

# OpenTelemetry: set OTEL_ENABLED=true to wrap uvicorn with OTEL auto-instrumentation
# Requires opentelemetry-distro + opentelemetry-exporter-otlp in dependencies
ENV OTEL_ENABLED=false \
    OTEL_SERVICE_NAME=opencompany \
    OTEL_EXPORTER_OTLP_ENDPOINT=""

USER appuser

# Health check — start-period covers the full lifespan startup (DB migrations,
# persona seeding, etc.) which can take up to 90s on cold start.
# Returns 200 when both DB and Redis are reachable, 503 otherwise.
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Use entrypoint script to conditionally wrap with OTEL
COPY --chown=appuser:appuser docker-entrypoint.sh ./
RUN chmod +x docker-entrypoint.sh
ENTRYPOINT ["./docker-entrypoint.sh"]
