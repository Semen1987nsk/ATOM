# syntax=docker/dockerfile:1.7
# ============================================================================
#  ATOM Backend — multi-stage Dockerfile
#  Финальный образ: python:3.11-slim, ~150MB, no-root user, gunicorn+uvicorn.
# ============================================================================

# ───────────────── Stage 1: builder ─────────────────
FROM python:3.11-slim AS builder

# Системные зависимости для psycopg2/numpy/pandas/cryptography wheel build
# (часть может быть подтянута wheel'ами; gcc нужен для psycopg2-source)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Сначала только requirements — слой кешируется между билдами кода
COPY requirements.txt .

# Ставим в /opt/venv, скопируем целиком в runtime-образ
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt \
      --extra-index-url https://opensource.tbank.ru/api/v4/projects/238/packages/pypi/simple && \
    pip install --no-cache-dir gunicorn sentry-sdk[fastapi] python-json-logger

# ───────────────── Stage 2: runtime ─────────────────
FROM python:3.11-slim AS runtime

# Только runtime-зависимости (libpq для psycopg2, без build-essential)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
        ca-certificates \
        tini \
    && rm -rf /var/lib/apt/lists/*

# Non-root user — никогда не пускаем uvicorn под root в проде
RUN groupadd --system --gid 1000 atom && \
    useradd --system --uid 1000 --gid atom --home-dir /app atom

WORKDIR /app

# Виртуальное окружение из builder-стадии
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Код приложения. .dockerignore исключает venv/__pycache__/.env/тесты.
COPY --chown=atom:atom . /app/

# Каталоги, в которые будем писать
RUN mkdir -p /app/uploads /var/log/atom && \
    chown -R atom:atom /app /var/log/atom

USER atom

EXPOSE 8000

# tini как PID 1 — корректный signal handling для graceful shutdown
ENTRYPOINT ["/usr/bin/tini", "--"]

# Healthcheck использует /health endpoint (см. main.py)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# В проде запускаем через gunicorn с uvicorn worker для multi-process.
# Workers = 2*CPU+1 — стандартная формула. Override через GUNICORN_CMD_ARGS.
CMD ["gunicorn", "main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "4", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--graceful-timeout", "30", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "--forwarded-allow-ips", "*"]
