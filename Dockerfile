FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
COPY src/ src/
COPY config/ config/

RUN uv pip install --system --locked .

RUN adduser --disabled-password --gecos '' appuser
USER appuser

HEALTHCHECK --interval=30s --timeout=5s CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "opencompany.main:app", "--host", "0.0.0.0", "--port", "8000"]
