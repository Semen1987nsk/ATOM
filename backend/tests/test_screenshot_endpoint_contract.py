"""Контракт: скриншот отдаётся ТОЛЬКО через authenticated GET /trades/{id}/screenshot,
а публичный static /uploads мёртв. Фронт (S1-12) должен строить URL из этого маршрута,
а не из trade.screenshot_url (тот остаётся флагом наличия '/uploads/screenshots/<file>').
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from main import app


def test_static_uploads_route_absent():
    client = TestClient(app)
    # Публичный static-mount удалён — маршрут не зарегистрирован.
    resp = client.get("/uploads/screenshots/whatever.png")
    assert resp.status_code == 404


def test_trade_screenshot_route_registered():
    # Authenticated-маршрут существует (без токена → 401, не 404).
    client = TestClient(app)
    resp = client.get("/trades/1/screenshot")
    assert resp.status_code in (401, 403), f"ожидался auth-guard, получено {resp.status_code}"
