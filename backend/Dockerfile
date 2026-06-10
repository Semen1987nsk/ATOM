# syntax=docker/dockerfile:1.7
# ============================================================================
#  ATOM Backend — multi-stage Dockerfile
#  Финальный образ: python:3.11-slim, ~150MB, no-root user, gunicorn+uvicorn.
# ============================================================================

# ───────────────── Stage 1: builder ─────────────────
# INFRA-14: base-image pin по digest — pending.
# Локально docker недоступен; вставлять fake digest опасно (CD упадёт на pull).
# TODO(INFRA-14): получить реальный digest и зафиксировать до production rollout:
#   docker manifest inspect python:3.11-slim --verbose | jq -r '.Descriptor.digest'
# Затем заменить обе строки на:
#   FROM python:3.11-slim@sha256:<digest> AS builder
#   FROM python:3.11-slim@sha256:<digest> AS runtime
# Рекомендуется автоматизация через Dependabot/Renovate (docker updates).
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

# INFRA-11: forwarded-allow-ips — кто имеет право устанавливать X-Forwarded-*.
# По умолчанию доверяем loopback + Docker bridge range (nginx внутри сети).
# Override через env при необходимости (например, behind external LB).
ENV FORWARDED_ALLOW_IPS="127.0.0.1,172.16.0.0/12"

# В проде запускаем через gunicorn с uvicorn worker для multi-process.
# Workers = 2*CPU+1 — стандартная формула. Override через GUNICORN_CMD_ARGS.
# sh -c обязательно для substitution ${FORWARDED_ALLOW_IPS} в exec form.
CMD ["sh", "-c", "exec gunicorn main:app \
     --worker-class uvicorn.workers.UvicornWorker \
     --workers 4 \
     --bind 0.0.0.0:8000 \
     --timeout 120 \
     --graceful-timeout 30 \
     --access-logfile - \
     --error-logfile - \
     --forwarded-allow-ips \"${FORWARDED_ALLOW_IPS}\""]
