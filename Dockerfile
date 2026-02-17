FROM python:3.13-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml .
COPY src/ src/
COPY config/ config/

RUN uv pip install --system .

CMD ["uvicorn", "opencompany.main:app", "--host", "0.0.0.0", "--port", "8000"]
