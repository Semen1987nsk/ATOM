# Sprint 2A-2 — API Surface Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use `- [ ]`.

> **NO-COMMIT MODE.** Реализуй + тесты до зелёного, НЕ `git add`/`git commit`. Пользователь ревьюит.

> **Окружение:** dev py3.14 (no Docker), CI/prod py3.11. Python через `PYTHONUTF8=1 python -X utf8 ...`. Ребренд Eqio→Empirik — без «eqio»-строк; искать места по символам, не номерам строк (перепроверять перед правкой).

**Goal:** Закрыть API-surface находки Sprint 2A-2 (API-01/02/03/04/09/12/13/14, SEC-07/13): auth+rate-limit на market-прокси, CORS-regex dev-only, дефолтный read-rate-limit, cap на `limit`, whitelist admin sort, boot-warning на DEBUG, убрать `str(exc)` из тел ответов, убрать `/db-check`, magic-byte+row-cap на импорте, allowlist тикера в MOEX URL.

**Architecture:** Большинство — независимые точечные правки. Один общий CONFIG-блок (новые settings + rate-limit presets) кладётся первым. Два файла с цепочками: `routers/trades.py` (API-04→API-13→SEC-07), `main.py` (API-14→API-12).

**Tech Stack:** FastAPI, slowapi, openpyxl/pandas, pytest.

**Решения (зафиксированы):**
- API-12 → **boot-time `log.warning`** при DEBUG=true (НЕ hard-fail: нет `ENVIRONMENT`-флага; traceback уже gated на DEBUG в handlers).
- API-14 → **удалить `/db-check`** (`/ready`+`/health` покрывают; pre-launch, живого монитора нет).
- API-01 → **добавить auth+rate-limit** (проверено: фронт `/market/*` не вызывает → безопасно).

---

## Verified current locations (audit pre-rebrand → current)
| Finding | Current |
|---|---|
| API-01 | `routers/market.py:17` (get_prices), `:36` (get_futures_specs) |
| API-02 | `config.py:267` (CORS_ORIGIN_REGEX) |
| API-03 | `rate_limiter.py:78-99` (Limiter wiring), presets `:138-158` |
| API-04 | `routers/trades.py:521` (read_trades limit), `:539` (read_position_trades limit) |
| API-09 | `admin_service.py:52` (`getattr(models.User, sort_by, ...)`) |
| API-12 | `main.py:246` (handler `if settings.DEBUG`), lifespan `:96` |
| API-13 | `routers/onboarding.py:91` (`str(exc)`), `routers/trades.py:501` (commit `{exc}`) — `:432` stale |
| API-14 | `main.py:456` (`/db-check`) |
| SEC-07 | `routers/trades.py:45-63` (`_read_upload_with_limit`, size-cap уже есть), `import_service.parse_trade_file:878` |
| SEC-13 | `market_service.py:385` (candle URL f-string), call sites `routers/replay.py:98`, trades MAE/MFE |

---

## Task CONFIG (first — unblocks others)
**Files:** Modify `config.py` (after CORS block ~:267), `rate_limiter.py` (presets ~:158).

- [ ] **Step 1:** Add to `Settings` (`config.py`), env+safe-defaults:
```python
    MAX_TRADES_LIMIT: int = int(os.getenv("MAX_TRADES_LIMIT", "1000"))
    MAX_IMPORT_ROWS: int = int(os.getenv("MAX_IMPORT_ROWS", "20000"))
    READ_RATE_LIMIT: str = os.getenv("READ_RATE_LIMIT", "120/minute")
    MARKET_RATE_LIMIT: str = os.getenv("MARKET_RATE_LIMIT", "30/minute")
```
And API-02 — make CORS regex DEV-only (DEBUG defined at config.py:227, in scope):
```python
    _cors_regex_default = r"https://.*\.app\.github\.dev" if DEBUG else ""
    CORS_ORIGIN_REGEX: str = os.getenv("CORS_ORIGIN_REGEX", _cors_regex_default)
```
- [ ] **Step 2:** Add to `rate_limiter.py` after presets: `READ_LIMIT = settings.READ_RATE_LIMIT`, `MARKET_LIMIT = settings.MARKET_RATE_LIMIT`.
- [ ] **Step 3:** Smoke: `PYTHONUTF8=1 python -X utf8 -c "import config, rate_limiter; print(config.settings.MAX_TRADES_LIMIT, rate_limiter.MARKET_LIMIT)"`.

---

## Task API-02: CORS regex DEV-only
**Files:** `config.py` (done in CONFIG), Test: `tests/test_cors_regex.py`.

- [ ] **Step 1: Failing test** (reload-based; protected by conftest `restore_config_settings_singleton`):
```python
import importlib, config

def test_cors_regex_empty_in_prod(monkeypatch):
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.delenv("CORS_ORIGIN_REGEX", raising=False)
    importlib.reload(config)
    assert config.settings.CORS_ORIGIN_REGEX == ""

def test_cors_regex_codespaces_in_dev(monkeypatch):
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.delenv("CORS_ORIGIN_REGEX", raising=False)
    importlib.reload(config)
    assert "app.github.dev" in config.settings.CORS_ORIGIN_REGEX
```
- [ ] **Step 2-4:** RED → (CONFIG block implements) → GREEN: `PYTHONUTF8=1 python -X utf8 -m pytest tests/test_cors_regex.py -q`.

---

## Task API-01: Auth + rate-limit on market proxy
**Files:** `routers/market.py`; Test: `tests/integration/test_market_auth.py`.

- [ ] **Step 1: Failing test:**
```python
from tests.integration.test_pr26_endpoints import test_app, _make_user, _auth_headers

def test_prices_requires_auth(test_app):
    r = test_app["client"].get("/market/prices?tickers=SBER")
    assert r.status_code == 401

def test_prices_ok_with_auth(test_app, monkeypatch):
    import market_service
    monkeypatch.setattr(market_service.MarketService, "get_current_prices",
                        lambda self, t: {"SBER": 100.0})
    db = test_app["db"]; user, _ = _make_user(db, "mkt@test.com")
    r = test_app["client"].get("/market/prices?tickers=SBER", headers=_auth_headers(user))
    assert r.status_code == 200
```
> Проверить точное имя метода сервиса (`get_current_prices`?) и форму ответа перед фиксацией ассерта.

- [ ] **Step 2:** RED.
- [ ] **Step 3:** В `routers/market.py`: импорт `auth_service`, `models`, `from fastapi import Request`, `from rate_limiter import limiter, MARKET_LIMIT`. В оба эндпоинта (`get_prices`, `get_futures_specs`) добавить параметры `request: Request`, `current_user: models.User = Depends(auth_service.get_current_user)` и декоратор `@limiter.limit(MARKET_LIMIT)` (slowapi требует `request: Request` в сигнатуре).
- [ ] **Step 4:** GREEN.
- [ ] **Step 5: Fix breaking test** — `tests/test_api.py::TestMarket::test_get_prices` (`:~1239`) зовёт без auth → теперь 401. Обновить: добавить `auth_headers` + monkeypatch `get_current_prices` (избежать живого MOEX), assert 200. Сообщить об изменении.

---

## Task API-03: Default read rate-limit
**Files:** `rate_limiter.py` (Limiter ctor); Test: `tests/test_rate_limit_default.py`.

- [ ] **Step 1:** Перед реализацией проверить через context7, что установленная версия slowapi поддерживает `default_limits=` в `Limiter(...)`. (Должна; pin-check на py3.14.)
- [ ] **Step 2: Failing test** (лёгкий unit — проверка что default_limits заполнен, чтобы не гонять 121 запрос):
```python
def test_limiter_has_default_read_limit():
    from rate_limiter import limiter
    from config import settings
    assert settings.READ_RATE_LIMIT in (limiter._default_limits and [str(l) for l in limiter._default_limits] or [])
```
> Если внутренний атрибут отличается — адаптировать к реальному API slowapi (проверить как хранятся default_limits). Альтернатива — интеграционный тест с маленьким лимитом через отдельное приложение.
- [ ] **Step 3:** В `rate_limiter.py` обе ветки `Limiter(...)` (Redis и in-memory) — добавить `default_limits=[settings.READ_RATE_LIMIT]`. Per-route `@limiter.limit` override'ит (не стэкается).
- [ ] **Step 4:** GREEN. Затем **полный прогон** (global default влияет на все роуты под нагрузочными тестами).

**RISK:** генеральный лимит может троттлить легитимный dashboard-polling. 120/min/IP щедро (~2/s). Per-IP ключ → ложняки за корп-NAT; реальный слой защиты — nginx (INFRA-05, отд. спринт). Самая регресс-рискованная задача — после неё полный suite.

---

## Task API-04: Cap on `limit` (trades.py — FIRST in trades chain)
**Files:** `routers/trades.py`; Test: `tests/test_trades_limit_cap.py`.

- [ ] **Step 1: Failing test:**
```python
from tests.integration.test_pr26_endpoints import test_app, _make_user, _auth_headers

def test_trades_limit_capped(test_app):
    db = test_app["db"]; u,_ = _make_user(db, "lim@test.com")
    r = test_app["client"].get("/trades/?limit=10000000", headers=_auth_headers(u))
    assert r.status_code == 422

def test_positions_limit_capped(test_app):
    db = test_app["db"]; u,_ = _make_user(db, "lim2@test.com")
    r = test_app["client"].get("/trades/positions?limit=10000000", headers=_auth_headers(u))
    assert r.status_code == 422
```
- [ ] **Step 2:** RED.
- [ ] **Step 3:** `read_trades` и `read_position_trades`: `limit: int = Query(500, ge=1, le=settings.MAX_TRADES_LIMIT)`, `skip: int = Query(0, ge=0)`. (`settings` уже импортирован.)
- [ ] **Step 4:** GREEN. Проверить, что нет существующих тестов с `limit>1000`.

---

## Task API-13: Stop `str(exc)` leak (trades.py + onboarding.py — onboarding independent)
**Files:** `routers/onboarding.py:91`, `routers/trades.py:501`; Test: `tests/test_error_no_leak.py`.

- [ ] **Step 1: Failing test:**
```python
from tests.integration.test_pr26_endpoints import test_app, _make_user, _auth_headers

def test_onboarding_error_no_internal_detail(test_app, monkeypatch):
    db = test_app["db"]; u,_ = _make_user(db, "leak@test.com")
    import services.reconciliation_service as rs
    async def boom(*a, **k): raise RuntimeError("secret dsn leaked")
    monkeypatch.setattr(rs, "reconcile_account", boom)
    r = test_app["client"].post("/onboarding/reconcile", headers=_auth_headers(u))
    assert "secret dsn leaked" not in r.text
```
> Проверить реальный путь/метод onboarding reconcile + что `reconcile_account` — то место.
- [ ] **Step 2:** RED.
- [ ] **Step 3:** `onboarding.py:91`: `"error": str(exc)` → `"error": "reconciliation_failed"` (детали уже в `log.exception`). `trades.py:501`: убрать `{exc}` из `detail`, generic «Не удалось сохранить импорт, повторите попытку» (детали в `log.error`).
- [ ] **Step 4:** GREEN.

---

## Task SEC-07: Excel magic-byte + row-cap (trades.py chain — LAST)
**Files:** `routers/trades.py` (`_read_upload_with_limit`/validate), `import_service.py` (`parse_trade_file`); Test: `tests/test_import_security.py`.

- [ ] **Step 1: Failing tests:**
```python
import pytest, import_service

def test_rejects_non_xlsx_magic():
    fake = b"<html>not xlsx</html>" + b"\x00"*100
    with pytest.raises(ValueError):
        import_service.parse_trade_file(fake, "evil.xlsx")

def test_row_cap_enforced(monkeypatch):
    import config, io, pandas as pd
    monkeypatch.setattr(config.settings, "MAX_IMPORT_ROWS", 5)
    df = pd.DataFrame({"symbol":["X"]*50,"side":["buy"]*50,"price":[1]*50,"quantity":[1]*50,"date":["2025-01-01"]*50})
    buf = io.BytesIO(); df.to_excel(buf, index=False); buf.seek(0)
    with pytest.raises(ValueError):
        import_service.parse_trade_file(buf.read(), "big.xlsx")
```
> Проверить сигнатуру `parse_trade_file(content, filename)` и что для .xlsx путь идёт через pandas/openpyxl. CSV-путь не трогать magic-чеком.
- [ ] **Step 2:** RED.
- [ ] **Step 3:**
  - Magic-bytes: для `.xlsx` заголовок ZIP (`PK\x03\x04`/`PK\x05\x06`/`PK\x07\x08`), для `.xls` OLE2 (`\xd0\xcf\x11\xe0`); mismatch → `ValueError`/400 «Файл повреждён или не Excel/CSV». CSV → пропустить бинарный чек.
  - Row-cap в `parse_trade_file`: после чтения `df`/workbook, `if len(df) > settings.MAX_IMPORT_ROWS: raise ValueError(...)` (маппится в 400). Где `load_workbook` — `read_only=True` + проверка `ws.max_row` до итерации (подтвердить что `parse_tinkoff_excel`/`parse_account_balance` совместимы; сейчас `wb.active` full-load).
- [ ] **Step 4:** GREEN. Проверить `tests/test_import_service.py`/`test_import_phase1.py` — фикстуры с настоящими `df.to_excel` байтами (валидный ZIP) проходят magic-чек; hand-built не-ZIP под `.xlsx` — поправить.

**Right-size:** 10MB upload-cap уже есть; magic+row-cap+`read_only` достаточно (не городить полный decompression-ratio policing).

---

## Task API-09: Whitelist admin sort_by
**Files:** `admin_service.py`; Test: `tests/test_admin_sort_whitelist.py`.

- [ ] **Step 1: Failing test** (unit, `db_session` fixture):
```python
import admin_service

def test_sort_by_whitelist_constant():
    assert "hashed_password" not in admin_service._ALLOWED_SORT_COLUMNS
    assert "created_at" in admin_service._ALLOWED_SORT_COLUMNS
```
- [ ] **Step 2:** RED.
- [ ] **Step 3:** Модульный `_ALLOWED_SORT_COLUMNS = {"created_at","last_login","email","name","registration_source"}`; заменить `getattr(models.User, sort_by, models.User.created_at)` на:
```python
col_name = sort_by if sort_by in _ALLOWED_SORT_COLUMNS else "created_at"
sort_column = getattr(models.User, col_name)
```
> Проверить реальные имена колонок User (registration_source существует?). Скорректировать набор под реальные mapped columns.
- [ ] **Step 4:** GREEN.

---

## Task SEC-13: Ticker allowlist before MOEX URL
**Files:** `market_service.py` (`get_candles`); Test: extend `tests/test_market_service.py`.

- [ ] **Step 1: Failing test:**
```python
def test_get_candles_rejects_path_injection(self, service):
    from datetime import datetime
    assert service.get_candles("SBER/../secret", datetime(2025,1,1), datetime(2025,1,2)) == []
```
- [ ] **Step 2:** RED.
- [ ] **Step 3:** Модульный `_TICKER_RE = re.compile(r"^[A-Za-z0-9._-]{1,20}$")`; в начале `get_candles`: `if not _TICKER_RE.match(ticker or ""): log.warning(...); return []`. Реальные тикеры (`SBER`,`SiH6`,`RU000A...`,`BRZ5`) проходят. Возврат `[]` (callers уже терпят пустые свечи), не raise.
- [ ] **Step 4:** GREEN. Проверить существующий `service` fixture в test_market_service.py.

---

## Task API-14: Remove /db-check (main.py chain — FIRST)
**Files:** `main.py`; Test: update `tests/test_api.py::TestRoot`.

- [ ] **Step 1: Update test** `test_db_check` (`:132`) → assert removal:
```python
def test_db_check_removed(self, test_app):
    """API-14: /db-check удалён; используйте /ready."""
    assert test_app["client"].get("/db-check").status_code == 404
```
- [ ] **Step 2:** RED (роут ещё есть → 200≠404).
- [ ] **Step 3:** Удалить `@app.get("/db-check")` хэндлер (`main.py:456`) целиком.
- [ ] **Step 4:** GREEN. Grep что ничто внутри backend не ссылается на `/db-check`.

---

## Task API-12: Boot-warning on DEBUG (main.py chain — LAST)
**Files:** `main.py`; Test: `tests/test_debug_warning.py`.

- [ ] **Step 1: Failing test:**
```python
def test_debug_true_logs_warning(monkeypatch, caplog):
    import main
    monkeypatch.setattr(main.settings, "DEBUG", True)
    with caplog.at_level("WARNING"):
        main._warn_if_debug()
    assert any("DEBUG" in r.message for r in caplog.records)
```
> caplog + `propagate=False` (logger.py) — привязать к `logging.getLogger("atom")` если не ловит.
- [ ] **Step 2:** RED (`_warn_if_debug` не существует).
- [ ] **Step 3:** Маленький helper `def _warn_if_debug(): if settings.DEBUG: log.warning("⚠️ DEBUG=true — НЕ для продакшна (traceback'и gated, но проверь окружение)")`. Вызвать в `lifespan` startup (~:99).
- [ ] **Step 4:** GREEN.

---

## Final verification
- [ ] Full suite: `PYTHONUTF8=1 python -X utf8 -m pytest tests/unit tests/integration tests/test_api.py tests/test_auth_hardening.py -q` — зелёное (711+ baseline, минус удалённый db-check + новые).
- [ ] App import smoke: `PYTHONUTF8=1 python -X utf8 -c "import main; print(len(main.app.routes))"`.
- [ ] `security-reviewer` по всему диффу: API-01 auth-gate, API-09 whitelist, SEC-07 magic+row-cap, SEC-13 ticker-regex (path-injection), API-02 prod-CORS, API-13 нет leak в телах, API-03 limit не отключаем глобально случайно.

## Existing tests to fix (consolidated)
- `tests/test_api.py::TestRoot::test_db_check` → `test_db_check_removed` (404). [API-14]
- `tests/test_api.py::TestMarket::test_get_prices` → +auth_headers +monkeypatch service. [API-01]
- `tests/test_import_service.py`/`test_import_phase1.py` — убедиться фикстуры = реальные xlsx-байты. [SEC-07]
- Полный прогон под API-03 (global default limit).

## Self-Review
1. Spec coverage: API-01/02/03/04/09/12/13/14, SEC-07/13 — все 10 имеют task. API-12 сведён к warning (решение). SEC-07 size-cap уже был — добавляем magic+row-cap.
2. Placeholders: тест-код приведён; «проверить реальное имя/сигнатуру» — verify-инструкции.
3. Type consistency: `MAX_TRADES_LIMIT`/`MAX_IMPORT_ROWS`/`READ_RATE_LIMIT`/`MARKET_RATE_LIMIT`, `READ_LIMIT`/`MARKET_LIMIT`, `_ALLOWED_SORT_COLUMNS`, `_TICKER_RE`, `_warn_if_debug` — согласованы.
