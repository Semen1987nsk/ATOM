"""INFRA-02: /metrics endpoint exposes Prometheus exposition format.

Backend наблюдаемость: prometheus-fastapi-instrumentator регистрирует
`/metrics` для скрейпинга (Prometheus + Grafana stack).

Тесты:
- /metrics возвращает text/plain Prometheus exposition.
- /metrics не попадает под slowapi default_limits (READ_RATE_LIMIT=120/min).
  Если попадёт — Prometheus scraper (15s интервал) пробьёт лимит и упадёт
  на 429-х каждые ~30 минут. Защита идёт через:
    1. `excluded_handlers` в Instrumentator (не считает в свои гистограммы),
    2. `@limiter.exempt`-эквивалент: пропуск через `/metrics` в SlowAPI.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client() -> TestClient:
    """TestClient на основном app — модульный scope для амортизации стоимости старта."""
    # Импорт внутри фикстуры, чтобы reset_rate_limiter_storage отработала ДО
    # того как app соберёт middleware.
    from main import app

    return TestClient(app)


def test_metrics_endpoint_returns_prometheus_format(client: TestClient) -> None:
    """GET /metrics returns text/plain Prometheus exposition."""
    resp = client.get("/metrics")
    assert resp.status_code == 200, f"expected 200, got {resp.status_code}: {resp.text[:300]}"
    assert "text/plain" in resp.headers["content-type"].lower()
    body = resp.text
    # Стандартные метрики из prometheus_fastapi_instrumentator
    assert (
        "http_requests_total" in body or "http_request_duration_seconds" in body
    ), f"prometheus metrics missing from body: {body[:500]}"


def test_metrics_endpoint_not_rate_limited(client: TestClient) -> None:
    """/metrics не должен попадать под slowapi default_limits (120/minute)."""
    for i in range(150):  # 150 > 120/min default rate
        resp = client.get("/metrics")
        if resp.status_code == 429:
            pytest.fail(f"/metrics rate-limited at request #{i + 1} (should be exempt)")
    assert resp.status_code == 200
