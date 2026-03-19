# ── Stage 1: build dependencies ──────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt setup.py pyproject.toml ./
COPY src/ ./src/

RUN pip install --upgrade pip \
 && pip install --prefix=/install -r requirements.txt \
 && pip install --prefix=/install -e . --no-deps


# ── Stage 2: runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install postgresql-client so entrypoint.sh can use pg_isready
# curl is needed for Streamlit healthcheck in docker-compose
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      postgresql-client \
      curl \
 && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd --gid 1001 tracker \
 && useradd  --uid 1001 --gid tracker --no-create-home --shell /bin/bash tracker

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY --from=builder /app/src ./src
COPY transforms/  ./transforms/
COPY dashboard/   ./dashboard/
COPY scripts/     ./scripts/

RUN chmod +x ./scripts/entrypoint.sh \
 && mkdir -p /app/data \
 && chown -R tracker:tracker /app

ENV PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER tracker

ENTRYPOINT ["./scripts/entrypoint.sh"]
CMD ["ingest"]
