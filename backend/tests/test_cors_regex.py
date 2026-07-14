"""API-02: CORS-origin regex (codespaces) разрешён только в DEBUG.

Заметки по окружению (отличие от наброска в плане):
  - `importlib.reload(config)` повторно грузит `.env.local` с `override=True`,
    а локальный `.env.local` содержит `DEBUG=true`. Поэтому в prod-тесте
    выставляем `ENV=production` — тогда `.env.local` НЕ загружается и
    `DEBUG=false` из monkeypatch реально доходит до Settings.
  - Дефолтное значение regex экранировано (`\.app\.github\.dev`), поэтому
    проверяем подстроку `github` (а не `app.github.dev`, которой в строке
    с бэкслешами нет).
"""

import importlib

import config


def test_cors_regex_empty_in_prod(monkeypatch):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("SECRET_KEY", "x" * 70)
    monkeypatch.setenv("REFRESH_SECRET_KEY", "y" * 70)
    monkeypatch.setenv("MASTER_KEY_B64", "c29tZS1iYXNlNjQta2V5")
    monkeypatch.delenv("CORS_ORIGIN_REGEX", raising=False)
    importlib.reload(config)
    assert config.settings.DEBUG is False
    assert config.settings.CORS_ORIGIN_REGEX == ""


def test_cors_regex_codespaces_in_dev(monkeypatch):
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.delenv("CORS_ORIGIN_REGEX", raising=False)
    importlib.reload(config)
    assert config.settings.DEBUG is True
    assert "github" in config.settings.CORS_ORIGIN_REGEX
