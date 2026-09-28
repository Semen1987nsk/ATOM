# Спринт 4 — Релизная гигиена (CI/миграции/PII/полировка) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (- [ ]) syntax.

**Goal:** Закрыть предрелизную гигиену Полистаты — восстановить CI и прогнать миграции против Postgres, устранить дрейф индексов, дочистить PII/152-ФЗ (файлы скриншотов, totp, PII-сироты), убрать 15с-таймаут на длинных sync-запросах, починить nginx-маршрут лендинг-тикера и довести до конца полировку (тема, валюта, контакты, dead-code, безопасность admin/auth).

**Architecture:** Backend — FastAPI + SQLAlchemy 2.0 + Alembic (guarded-миграции по образцу `_guards.has_index`), SQLite dev / PostgreSQL 16 prod. Frontend — Next.js 16 + React 19 + Tailwind v4, единый `apiClient` поверх `fetchWithTimeout`. Задачи независимы по файлам, кроме явных связок (см. Interfaces): три PII-задачи (S4-01/S4-24/S4-35) правят один `pd_deletion.finalize_deletion`; две support-email задачи (S4-28/S4-31) делят одну константу; две index-drift задачи (S4-18/S4-19) обе трогают `models.py.__table_args__` + миграции.

**Tech Stack:** Python 3.14 (`C:/Python314/python.exe`), pytest, Alembic; Next.js/Vitest/tsc; nginx; T-Bank gRPC; MOEX ISS.

## Global Constraints

- Python: `C:/Python314/python.exe` (зависимости там). Тесты бэка из `backend/`: `C:/Python314/python.exe -m pytest tests/... -q`
- Backend уже запущен на `http://localhost:8000` (GET-смоук можно, мутации прод-данных нельзя).
- Frontend: `cd frontend && npx vitest run --maxWorkers=1` (ТОЛЬКО `maxWorkers=1`) + `npx tsc --noEmit`. E2E: playwright, backend :8000 + `npm run dev -- -p 3001`, при lock-ошибке убить `next dev` + удалить `frontend/.next/dev/lock`.
- Миграции: врем. БД `DATABASE_URL=sqlite:///./_audit_tmp.db`, НИКОГДА не трогать `backend/atom.db`. Перед релизом — Postgres 16.
- Git: новый коммит на задачу (не amend), ветка `feat/rebrand-empirik`, формат `fix(область): что (SN-XX)`. Не пушить/мержить.
- Инварианты: ADR-0007 (P&L), SYNC-08 (курсор после всех стадий), MATH-01 (net_pnl не gross). Читать `docs/PNL_PLAYBOOK.md` для P&L-задач.
- Флейк (не регрессия): `test_debug_warning` + `test_market_service_async::test_get_client_returns_singleton` падают только в полном прогоне.
- ADR-0009 = MVP flat freemium (нет триала/подписочного гейтинга в UI на этот релиз) — релевантно S4-12.

---

## S4-01 [HIGH] Файлы скриншотов не удаляются при анонимизации аккаунта (152-ФЗ)

**Files:**
- Modify: `backend/services/pd_deletion.py` (`finalize_deletion`, строки 135–153, 183)
- Test: `backend/tests/unit/test_pd_deletion_screenshots.py` (Create)

**Проблема:** `finalize_deletion()` зануляет `Trade.screenshot_url` в БД (строка 147), но НЕ удаляет физические файлы под `uploads/screenshots/`. Скриншоты содержат PII/финданные и остаются на диске бессрочно — нарушение 152-ФЗ ст. 21 п. 5.

**Interfaces:** Правит ту же функцию `finalize_deletion`, что S4-24 (totp-поля) и S4-35 (PII-сироты в токен-таблицах). Все три — независимые блоки внутри одной функции; при исполнении подряд не конфликтуют, но каждый добавляет свой тест. `screenshot_url` хранится как `/uploads/screenshots/<filename>` (см. `trades.py:1011`), физический путь = `UPLOAD_DIR / basename` где `UPLOAD_DIR = Path("uploads/screenshots")`.

Шаги:
- [ ] Step 1 — падающий тест. Создать `backend/tests/unit/test_pd_deletion_screenshots.py`:
```python
from pathlib import Path

import models
from services import pd_deletion


def test_finalize_deletion_unlinks_screenshot_files(db_session, tmp_path, monkeypatch):
    # UPLOAD_DIR в trades.py — куда пишутся файлы; переопределяем на tmp.
    upload_dir = tmp_path / "uploads" / "screenshots"
    upload_dir.mkdir(parents=True)
    fname = "abcd-1234.png"
    fpath = upload_dir / fname
    fpath.write_bytes(b"\x89PNG fake screenshot with PII")
    assert fpath.is_file()

    import routers.trades as trades_router
    monkeypatch.setattr(trades_router, "UPLOAD_DIR", upload_dir)

    user = models.User(email="del@example.com", hashed_password="x", is_active=1)
    db_session.add(user)
    db_session.flush()
    acc = models.Account(user_id=user.id, name="acc")
    db_session.add(acc)
    db_session.flush()
    trade = models.Trade(
        account_id=acc.id, symbol="SBER", direction="long",
        entry_price=100, quantity=1, screenshot_url=f"/uploads/screenshots/{fname}",
    )
    db_session.add(trade)
    db_session.commit()

    pd_deletion.finalize_deletion(db_session, user)

    assert not fpath.exists(), "screenshot файл должен быть удалён при анонимизации"
    db_session.refresh(trade)
    assert trade.screenshot_url is None
```
  Проверить фикстуру `db_session`: если её нет — использовать локальную in-memory session (см. соседние `tests/unit/*`, там обычно `conftest` даёт `db_session`). При отсутствии `models.Account(name=...)` подставить реальные обязательные поля Account (открыть `models.py` класс `Account`).
- [ ] Step 2 — запуск, ожидание FAIL:
  `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_pd_deletion_screenshots.py -q`
  Ожидается FAIL: `assert not fpath.exists()` — файл ещё на диске.
- [ ] Step 3 — минимальный фикс. В `finalize_deletion` СОБРАТЬ пути ДО зануления, потом удалить файлы после commit. Before (строки 137–153, только чтение rowcount) → добавить сбор url перед update и unlink после первого commit (строка 183):

  Перед `trades_cleaned = db.execute(` вставить сбор путей:
```python
    # 152-ФЗ ст.21 п.5: физически удаляем файлы скриншотов (PII/финданные),
    # а не только зануляем ссылку в БД.
    from routers.trades import UPLOAD_DIR as _SCREENSHOT_DIR

    screenshot_urls = [
        row[0]
        for row in db.execute(
            select(models.Trade.screenshot_url)
            .where(models.Trade.id.in_(trade_ids_subq))
            .where(models.Trade.screenshot_url.isnot(None))
        ).all()
    ]
```
  После `db.commit()` на строке 183 добавить блок удаления:
```python
    # Удаляем физические файлы скриншотов (после успешного commit анонимизации).
    for url in screenshot_urls:
        try:
            fpath = _SCREENSHOT_DIR / Path(url).name
            fpath.unlink(missing_ok=True)
        except OSError as exc:
            log.warning(f"Failed to unlink screenshot {url}: {exc}")
```
  Добавить в импорты вверху файла `from pathlib import Path` (строка ~25, рядом с `from datetime import timedelta`).
- [ ] Step 4 — запуск, ожидание PASS:
  `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_pd_deletion_screenshots.py -q` → PASS.
- [ ] Step 5 — commit: `fix(152-fz): unlink screenshot files on account anonymization (S4-01)`

---

## S4-02 [HIGH] Глобальный 15с-таймаут apiClient обрубает первый sync и onboarding-reconcile

**Files:**
- Modify: `frontend/src/lib/apiClient.ts` (`ApiRequestOptions` строки 97–104; `request` строки 130–183)
- Modify: `frontend/src/components/BrokerConnectModal.tsx` (`syncConnection` строки 171–187)
- Modify: `frontend/src/components/SyncStatusIndicator.tsx` (`triggerSync` строки 146–159)
- Modify: `frontend/src/app/onboarding/reconcile/page.tsx` (`handleRun` строка 98)
- Test: `frontend/src/lib/__tests__/apiClient.timeout.test.ts` (Create)

**Проблема:** `request()` вызывает `fetchWithTimeout` без передачи таймаута → все запросы капятся `DEFAULT_TIMEOUT_MS=15000`. POST `/broker/connections/{id}/sync` и POST `/onboarding/reconcile` по своему UI идут до 60–90с → первый sync у юзера с историей падает в UI как `ApiError(408)`, хотя backend работает.

Шаги:
- [ ] Step 1 — падающий тест. Создать `frontend/src/lib/__tests__/apiClient.timeout.test.ts`:
```ts
import { describe, it, expect, vi } from 'vitest';
import * as ftw from '../fetchWithTimeout';
import { api } from '../apiClient';

describe('apiClient timeoutMs override', () => {
  it('passes custom timeoutMs through to fetchWithTimeout', async () => {
    const spy = vi
      .spyOn(ftw, 'fetchWithTimeout')
      .mockResolvedValue(new Response('{}', { status: 200 }));
    await api.post('/broker/connections/1/sync', { timeoutMs: 120000 });
    // 3-й аргумент fetchWithTimeout — timeoutMs
    expect(spy).toHaveBeenCalled();
    expect(spy.mock.calls[0][2]).toBe(120000);
    spy.mockRestore();
  });
});
```
- [ ] Step 2 — запуск, ожидание FAIL:
  `cd frontend && npx vitest run --maxWorkers=1 src/lib/__tests__/apiClient.timeout.test.ts`
  Ожидается FAIL: `spy.mock.calls[0][2]` === `undefined` (таймаут не прокидывается).
- [ ] Step 3 — фикс. В `apiClient.ts` добавить поле в интерфейс (строка 103, после `signal?: AbortSignal;`):
```ts
  signal?: AbortSignal;
  /** Переопределение таймаута (мс). Для долгих операций (первый sync/reconcile
   *  до 60–90с) передавать 120000, иначе default 15с обрубит запрос. */
  timeoutMs?: number;
```
  В `request()` — деструктуризация (строка 135) и проброс. Before:
```ts
  const { body, headers: extraHeaders, params, noAuth, rawResponse, signal } = options;
```
  After:
```ts
  const { body, headers: extraHeaders, params, noAuth, rawResponse, signal, timeoutMs } = options;
```
  В `doFetch` (строка 176) передать 3-м аргументом. Before → after:
```ts
      return await fetchWithTimeout(url, fetchOptions, timeoutMs);
```
  (`fetchWithTimeout` уже имеет `timeoutMs = DEFAULT_TIMEOUT_MS` дефолт — `undefined` даст 15с, как было.)

  В `BrokerConnectModal.tsx` `syncConnection` (строка 185) — добавить `timeoutMs`:
```ts
      }>(`/broker/connections/${connectionId}/sync`, {
        params: { full: forceFullSync },
        timeoutMs: 120000,
      });
```
  В `SyncStatusIndicator.tsx` `triggerSync` (строка 149):
```ts
      await api.post(`/broker/trigger-sync/${connectionId}`, { timeoutMs: 120000 });
```
  В `onboarding/reconcile/page.tsx` `handleRun` (строка 98):
```ts
      const data = await api.post<{ runs: Run[] }>(`/onboarding/reconcile?days=30`, { timeoutMs: 120000 });
```
- [ ] Step 4 — запуск, ожидание PASS:
  `cd frontend && npx vitest run --maxWorkers=1 src/lib/__tests__/apiClient.timeout.test.ts` → PASS. Затем `npx tsc --noEmit` (без ошибок).
- [ ] Step 5 — commit: `fix(frontend): allow per-request timeout override for long sync/reconcile (S4-02)`

---

## S4-03 [HIGH] CI мёртв с 2026-05-06 — миграции 0005–0029 не проверялись против PostgreSQL

**Files:**
- Modify: `.github/workflows/ci.yml` (триггеры строки 3–7; job `backend` шаг «Run alembic migrations» строки 64–75)
- Test/Verify: локальный прогон Postgres 16 roundtrip

**Проблема:** `ci.yml` — единственное место, где цепочка миграций гоняется против Postgres, но триггер только `push/PR → main`, а ветка `feat/rebrand-empirik` CI не запускает; последние прогоны на `main` (2026-05-06) все `failure`. 24 из 28 миграций исполнялись только на SQLite; прод = Postgres.

Шаги (MED-стиль сжатие допустимо для CI-конфига, но с реальной локальной верификацией Postgres):
- [ ] Step 1 — воспроизвести проблему локально. Поднять Postgres 16 (docker) и прогнать полный roundtrip:
```bash
docker run -d --name pg16-ci -e POSTGRES_USER=atom -e POSTGRES_PASSWORD=atom -e POSTGRES_DB=atom_test -p 55432:5432 postgres:16-alpine
cd backend
DATABASE_URL=postgresql://atom:atom@localhost:55432/atom_test DEBUG=false \
  SECRET_KEY=ci-test-secret-key-1234567890abcdefghijklmnopqrstuvwxyz \
  REFRESH_SECRET_KEY=ci-test-refresh-key-fedcba0987654321zyxwvutsrqp \
  MASTER_KEY_B64=MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY= \
  C:/Python314/python.exe -m alembic upgrade head
```
  Зафиксировать точную ошибку (ожидаемо — та, что чинит S1-02: revision id 0023 длиной 34 > VARCHAR(32); если S1-02 уже закоммичен, `upgrade head` должен пройти). Затем `alembic downgrade base` и снова `alembic upgrade head`, затем `alembic check`.
- [ ] Step 2 — фикс триггера. В `ci.yml` расширить триггеры (строки 3–7). Before:
```yaml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
```
  After:
```yaml
on:
  push:
    branches: ['**']
  pull_request:
    branches: [main, 'feat/**']
```
  Добавить шаг `alembic check` после `alembic upgrade head` (строка 75), чтобы дрейф моделей (S4-18/S4-19) ловился в CI. Вставить в job `backend` перед `Run pytest`:
```yaml
      - name: Alembic check (schema drift gate)
        working-directory: backend
        env:
          DATABASE_URL: postgresql://atom:atom@localhost:5432/atom_test
          DEBUG: 'false'
          SECRET_KEY: ci-test-secret-key-1234567890abcdefghijklmnopqrstuvwxyz
          REFRESH_SECRET_KEY: ci-test-refresh-key-fedcba0987654321zyxwvutsrqp
          MASTER_KEY_B64: MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=
        run: alembic check
```
  ВАЖНО: этот шаг добавлять ТОЛЬКО после того, как S4-18 и S4-19 закрыты (иначе `alembic check` красный из-за известного дрейфа). Если S4-18/S4-19 ещё не сделаны — оставить шаг с `continue-on-error: true` и снять флаг в задаче S4-19.
- [ ] Step 3 — верификация: `alembic check` локально против Postgres → `No new upgrade operations detected`. Удалить контейнер: `docker rm -f pg16-ci`. Commit: `ci(migrations): run CI on all branches + alembic check gate against postgres (S4-03)`

---

## S4-04 [MED] /broker/portfolio не отдаёт top-level unrealized_pnl и name позиций; ticker=FIGI

**Files:**
- Modify: `backend/routers/broker.py` (сборка позиций строки 759–776; return строки 788–801)
- Test: `backend/tests/unit/test_broker_portfolio_shape.py` (Create)

**Проблема:** Фронтовый `interface Portfolio` (PortfolioCard.tsx:12–25) требует `unrealized_pnl: number` на верхнем уровне и `Position.name: string`; return эндпоинта (broker.py:788) не содержит top-level `unrealized_pnl`, позиции без `name`, а `ticker` берётся из `p.figi` (broker.py:762) → карточка всегда «— нереализ.» и FIGI-коды вместо названий.

Шаги:
- [ ] Step 1 — падающий тест. Создать `backend/tests/unit/test_broker_portfolio_shape.py`:
```python
def test_portfolio_response_shape_has_unrealized_and_name(client_with_broker_portfolio):
    # Фикстура мокает Tinkoff get_portfolio с 1 позицией (instrument_uid известен,
    # expected_yield_fifo=+123.45) и известным instrument в InstrumentORM
    # (uid→ticker=SBER, name="Сбербанк").
    resp = client_with_broker_portfolio.get("/broker/portfolio")
    assert resp.status_code == 200
    body = resp.json()
    assert "unrealized_pnl" in body, "top-level unrealized_pnl обязателен для PortfolioCard"
    assert body["unrealized_pnl"] == 123.45
    pos = body["positions"][0]
    assert pos["ticker"] == "SBER"
    assert pos["name"] == "Сбербанк"
    assert "figi" in pos  # FIGI сохранён отдельным полем
```
  Если готовой фикстуры нет — построить минимальную по образцу существующих broker-тестов (`tests/**/test_*broker*`; открыть и переиспользовать их мок Tinkoff-клиента и seeding `InstrumentORM`).
- [ ] Step 2 — запуск, ожидание FAIL:
  `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_broker_portfolio_shape.py -q`
  Ожидается FAIL: `KeyError: 'unrealized_pnl'` (нет top-level) / `pos["ticker"]` == FIGI.
- [ ] Step 3 — фикс. В цикле сборки позиций (строки 760–776) резолвить ticker+name через `InstrumentORM` и накапливать сумму. Before (строки 759–776):
```python
        positions_raw = list(getattr(raw, "positions", []) or [])
        positions = []
        for p in positions_raw:
            ticker = getattr(p, "figi", None) or ""
            qty = _money_decimal(getattr(p, "quantity", None))
            if ticker == "RUB000UTSTOM":
                continue  # рубли отдельно
            positions.append(
                {
                    "ticker": ticker,
                    "instrument_uid": getattr(p, "instrument_uid", None),
                    "instrument_type": getattr(p, "instrument_type", None),
                    "quantity": qty,
                    "average_price": _money_decimal(getattr(p, "average_position_price", None)),
                    "current_price": _money_decimal(getattr(p, "current_price", None)),
                    "unrealized_pnl": _money_decimal(getattr(p, "expected_yield_fifo", None)),
                }
            )
```
  After:
```python
        positions_raw = list(getattr(raw, "positions", []) or [])
        # Резолв name/ticker пачкой по instrument_uid — FIGI-коды бесполезны в UI.
        uids = [getattr(p, "instrument_uid", None) for p in positions_raw]
        uids = [u for u in uids if u]
        instr_map = {}
        if uids:
            for inst in (
                db.query(models.InstrumentORM)
                .filter(models.InstrumentORM.uid.in_(uids))
                .all()
            ):
                instr_map[inst.uid] = inst
        positions = []
        unrealized_total = 0.0
        for p in positions_raw:
            figi = getattr(p, "figi", None) or ""
            if figi == "RUB000UTSTOM":
                continue  # рубли отдельно
            qty = _money_decimal(getattr(p, "quantity", None))
            uid = getattr(p, "instrument_uid", None)
            inst = instr_map.get(uid)
            upl = _money_decimal(getattr(p, "expected_yield_fifo", None))
            unrealized_total += float(upl or 0)
            positions.append(
                {
                    "ticker": (inst.ticker if inst and inst.ticker else figi),
                    "name": (inst.name if inst and inst.name else figi),
                    "figi": figi,
                    "instrument_uid": uid,
                    "instrument_type": getattr(p, "instrument_type", None),
                    "quantity": qty,
                    "average_price": _money_decimal(getattr(p, "average_position_price", None)),
                    "current_price": _money_decimal(getattr(p, "current_price", None)),
                    "unrealized_pnl": upl,
                }
            )
```
  В return (после строки 796) добавить top-level `unrealized_pnl`:
```python
        "options_value": options_value,
        "unrealized_pnl": unrealized_total,
        "initial_balance": initial,
```
  Проверить, что `db` доступна в области функции (это router-эндпоинт с `db: Session = Depends(get_db)`; если параметр называется иначе — использовать реальное имя) и что `models` импортирован (он используется в broker.py).
- [ ] Step 4 — запуск, ожидание PASS:
  `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_broker_portfolio_shape.py -q` → PASS. Смоук: `curl -s http://localhost:8000/broker/portfolio` (нужен auth-cookie — если 401, достаточно unit-теста).
- [ ] Step 5 — commit: `fix(broker): return top-level unrealized_pnl + resolved name/ticker in portfolio (S4-04)`

---

## S4-05 [MED] Calmar на /stats/ аннуализирует любую, даже недельную, историю (floor 0.1 года)

**Files:**
- Modify: `backend/routers/stats.py` (Calmar-блок строки 575–599)
- Test: `backend/tests/unit/test_stats_calmar_short_history.py` (Create)

**Проблема:** `period_years = max(trading_days/365, 0.1)` (stats.py:580) для аккаунта с неделей торговли раздувает CAGR → взорванный Calmar с рейтингом «Исключительно». `stats_advanced.py:101` уже применяет гейт 90 дней — два эндпоинта противоречат.

Шаги:
- [ ] Step 1 — падающий тест. Создать `backend/tests/unit/test_stats_calmar_short_history.py`:
```python
from routers import stats as stats_router


def test_calmar_gated_on_short_history():
    # Прямой юнит на хелпер-гейт (см. Step 3). trading_days < 90 → None/недостаточно.
    result = stats_router._calmar_with_history_gate(
        pnls_sorted=[1000.0] * 6,
        calmar_initial_balance=100000.0,
        period_years=0.1,
        trading_days=7,
    )
    assert result["calmar_ratio"] is None
    assert result["rating"] == "Недостаточно истории"


def test_calmar_computed_on_long_history():
    result = stats_router._calmar_with_history_gate(
        pnls_sorted=[1000.0] * 6,
        calmar_initial_balance=100000.0,
        period_years=1.0,
        trading_days=200,
    )
    assert result["calmar_ratio"] is not None
```
- [ ] Step 2 — запуск, ожидание FAIL:
  `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_stats_calmar_short_history.py -q`
  Ожидается FAIL: `AttributeError: module has no attribute '_calmar_with_history_gate'`.
- [ ] Step 3 — фикс. Добавить хелпер рядом с импортами `analytics` в stats.py (модульный уровень):
```python
def _calmar_with_history_gate(pnls_sorted, calmar_initial_balance, period_years, trading_days):
    """Calmar с гейтом 90 дней (консистентно со stats_advanced.py:101).
    На короткой истории аннуализированная доходность взрывается → не показываем."""
    if trading_days < 90:
        return {
            "calmar_ratio": None,
            "cagr_pct": None,
            "max_drawdown_pct": None,
            "rating": "Недостаточно истории",
        }
    return analytics.calculate_calmar_ratio(
        pnls_sorted,
        initial_balance=calmar_initial_balance,
        period_years=period_years,
    )
```
  Заменить прямой вызов (строки 595–599). Before:
```python
    calmar_data = analytics.calculate_calmar_ratio(
        pnls_sorted,
        initial_balance=calmar_initial_balance,
        period_years=period_years,
    )
```
  After:
```python
    _calmar_trading_days = (
        (sorted_trades[-1].exit_at or sorted_trades[-1].entry_at) - sorted_trades[0].entry_at
    ).days if len(sorted_trades) >= 2 else 0
    calmar_data = _calmar_with_history_gate(
        pnls_sorted,
        calmar_initial_balance=calmar_initial_balance,
        period_years=period_years,
        trading_days=_calmar_trading_days,
    )
```
- [ ] Step 4 — запуск, ожидание PASS:
  `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_stats_calmar_short_history.py -q` → PASS. Прогнать соседние stats-тесты: `C:/Python314/python.exe -m pytest tests/unit -k calmar -q`.
- [ ] Step 5 — commit: `fix(stats): gate Calmar on 90-day history to stop annualization blowup (S4-05)`

---

## S4-06 [MED] tax_visibility использует устаревшую шкалу НДФЛ (13% до 5 млн; с 2025 порог по ЦБ 2.4 млн)

**Files:**
- Modify: `backend/analytics/advanced.py` (`calculate_tax_visibility` строки 623–652)
- Test: `backend/tests/unit/test_tax_visibility_ndfl_2025.py` (Create)

**Проблема:** С 01.01.2025 (ФЗ-176) для доходов от ЦБ действует 13% до 2.4 млн ₽/год и 15% свыше; код считает 13% до 5 млн → занижает налог в диапазоне 2.4–5 млн (до 52 000 ₽).

Шаги:
- [ ] Step 1 — падающий тест. Создать `backend/tests/unit/test_tax_visibility_ndfl_2025.py`:
```python
from datetime import datetime

from analytics.advanced import calculate_tax_visibility


def test_ndfl_threshold_is_2_4m():
    year = datetime.utcnow().year
    trades = [{"pnl": 3_000_000, "exit_at": datetime(year, 6, 1)}]
    r = calculate_tax_visibility(trades)
    # 2_400_000*0.13 + 600_000*0.15 = 312_000 + 90_000 = 402_000
    assert r["estimated_tax"] == 402_000.0
    assert r["tax_rate_applied"] == 0.15


def test_ndfl_below_threshold_flat_13():
    year = datetime.utcnow().year
    trades = [{"pnl": 1_000_000, "exit_at": datetime(year, 6, 1)}]
    r = calculate_tax_visibility(trades)
    assert r["estimated_tax"] == 130_000.0
    assert r["tax_rate_applied"] == 0.13
```
- [ ] Step 2 — запуск, ожидание FAIL:
  `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_tax_visibility_ndfl_2025.py -q`
  Ожидается FAIL: `estimated_tax` == 390_000 (3_000_000*0.13), а не 402_000.
- [ ] Step 3 — фикс. Ввести константу с годом и заменить порог (строки 638–642, 651). Before:
```python
    realized = sum(float(t.get("pnl") or 0) for t in ytd_trades)
    # Прогрессивная шкала: до 5M ₽ — 13%, выше — 15%
    if realized <= 5_000_000:
        tax = max(realized, 0) * tax_rate
    else:
        tax = 5_000_000 * tax_rate + (realized - 5_000_000) * 0.15
```
  After:
```python
    realized = sum(float(t.get("pnl") or 0) for t in ytd_trades)
    # ФЗ-176 (с 01.01.2025): доход от ЦБ облагается 13% до 2.4 млн ₽/год, 15% свыше.
    NDFL_SECURITIES_THRESHOLD_2025 = 2_400_000
    if realized <= NDFL_SECURITIES_THRESHOLD_2025:
        tax = max(realized, 0) * tax_rate
    else:
        tax = NDFL_SECURITIES_THRESHOLD_2025 * tax_rate + (realized - NDFL_SECURITIES_THRESHOLD_2025) * 0.15
```
  И в return (строка 651). Before:
```python
        "tax_rate_applied": tax_rate if realized <= 5_000_000 else 0.15,
```
  After:
```python
        "tax_rate_applied": tax_rate if realized <= NDFL_SECURITIES_THRESHOLD_2025 else 0.15,
```
- [ ] Step 4 — запуск, ожидание PASS:
  `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_tax_visibility_ndfl_2025.py -q` → PASS.
- [ ] Step 5 — commit: `fix(analytics): update NDFL securities threshold to 2.4M (FZ-176 2025) (S4-06)`

---

## S4-07 [MED] POST /trades/calculate-mae-mfe force_all: неограниченный фан-аут в MOEX ISS

**Files:**
- Modify: `backend/routers/trades.py` (`calculate_mae_mfe_bulk` строки 1303–1332)
- Test: `backend/tests/unit/test_mae_mfe_batch_cap.py` (Create)

**Проблема:** При `force_all=true` грузятся ВСЕ закрытые сделки без капа, для каждой последовательно `await calculate_mae_mfe` → тысячи ISS-запросов в одном HTTP-запросе; nginx `proxy_read_timeout 120s` рвёт клиента, троттлинг ISS бьёт по всем.

Шаги (кап батча — минимальный безопасный фикс; TTL-кэш свечей вынесен из scope):
- [ ] Step 1 — падающий тест. Создать `backend/tests/unit/test_mae_mfe_batch_cap.py`:
```python
from routers import trades as trades_router


def test_batch_cap_constant_exists_and_reasonable():
    assert hasattr(trades_router, "MAE_MFE_BATCH_CAP")
    assert 50 <= trades_router.MAE_MFE_BATCH_CAP <= 500
```
  (Полноценный e2e-тест фан-аута требует мока ISS и БД; для MED достаточно закрепить кап константой + ограничить запрос `.limit()`. Проверка `.limit` — через inspection ниже.)
- [ ] Step 2 — запуск, ожидание FAIL:
  `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_mae_mfe_batch_cap.py -q`
  Ожидается FAIL: `AttributeError: MAE_MFE_BATCH_CAP`.
- [ ] Step 3 — фикс. Добавить константу модульного уровня (рядом с `UPLOAD_DIR`, ~строка 895 или у топа роутера) и ограничить запрос. Добавить:
```python
# Кап на батч MAE/MFE: каждый расчёт = до 6 ISS-запросов на тикер; без капа
# force_all у активного трейдера = тысячи ISS-запросов в одном HTTP-запросе.
MAE_MFE_BATCH_CAP = 200
```
  В `calculate_mae_mfe_bulk` после `query = ...` фильтров, заменить `trades = query.all()` (строка 1332). Before:
```python
    trades = query.all()
```
  After:
```python
    # Ограничиваем батч: остальное юзер добьёт повторным вызовом (курсор — по
    # сделкам без MAE/MFE, force_all обрабатывает по 200 за раз).
    trades = query.order_by(models.Trade.id).limit(MAE_MFE_BATCH_CAP).all()
```
  В return (строки 1386–1392) добавить признак «есть ещё»:
```python
        "errors": errors[:10] if errors else [],
        "has_more": len(trades) == MAE_MFE_BATCH_CAP,
```
- [ ] Step 4 — запуск, ожидание PASS:
  `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_mae_mfe_batch_cap.py -q` → PASS. Импорт-смоук: `C:/Python314/python.exe -c "import main"`.
- [ ] Step 5 — commit: `fix(trades): cap MAE/MFE bulk batch at 200 to bound ISS fan-out (S4-07)`

---

## S4-08 [MED] Новый /api/landing/ticker в проде получает 404 через nginx (location /api/ срезает префикс)

**Files:**
- Modify: `nginx/conf.d/empirik.conf` (location `/api/` строки 107–122)
- Verify: nginx -t + e2e через прокси

**Проблема:** `location /api/ { proxy_pass http://empirik_backend/; }` — trailing slash заменяет `/api/` на `/` → запрос `/api/landing/ticker` уходит на backend как `/landing/ticker`, которого нет → 404 → `LiveTicker` уходит в fallback. Backend-роутер имеет `prefix="/api/landing"` (landing.py:16).

Шаги (nginx-конфиг, ручная верификация):
- [ ] Step 1 — воспроизвести. Проверить текущее поведение прокси-переписывания. Локально (если nginx поднят через docker-compose.prod) — `curl -s http://localhost/api/landing/ticker` вернёт 404. Без nginx — статически: `location /api/` с `proxy_pass .../;` срезает префикс (задокументировано в самой находке).
- [ ] Step 2 — фикс. Добавить exact-location ВЫШЕ `location /api/` (перед строкой 107). Вставить:
```nginx
    # /api/landing/* — backend-роутер имеет prefix=/api/landing. Общий location /api/
    # с trailing-slash proxy_pass срезал бы префикс (/api/landing/ticker → /landing/...),
    # которого на backend нет. Явный proxy_pass БЕЗ слэша сохраняет полный путь.
    location /api/landing/ {
        limit_req zone=api_lim burst=40 nodelay;

        proxy_pass http://empirik_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Request-ID $http_x_request_id;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
    }

```
  (Префиксный `location /api/landing/` длиннее `/api/` → nginx выберет его по правилу самого длинного совпадения. `proxy_pass` без слэша = путь передаётся как есть.)
- [ ] Step 3 — верификация: `docker compose -f docker-compose.prod.yml exec nginx nginx -t` (или `nginx -t -c` на конфиге) → `syntax is ok`. Затем e2e через прокси: `curl -s http://localhost/api/landing/ticker` → 200 с JSON `{stale, tickers}`. Commit: `fix(nginx): route /api/landing/* without prefix strip so ticker returns 200 (S4-08)`

---

## S4-09 [MED] invariants_service обращается к несуществующим колонкам BalanceSnapshot + 'out' вместо 'output'

**Files:**
- Modify: `backend/services/invariants_service.py` (`_cash_invariant`: snapshot-запросы строки 337–358; withdrawals-ветка строка 320)
- Test: `backend/tests/unit/test_invariants_cash.py` (Create)

**Проблема:** `_cash_invariant` фильтрует по `BalanceSnapshot.snapshot_date` (строки 341, 350) и читает `snap.total_value` (358), но модель имеет `date` и `balance` (models.py:257–258) → `AttributeError` при построении запроса. Дополнительно withdrawals-ветка использует `{"out", "pay_out", "withdrawal"}` (строка 320), но каноническая Tinkoff-константа вывода = `"output"` (domain/enums.py:115, capital_service.py:41) → выводы не учитываются.

Шаги:
- [ ] Step 1 — падающий тест. Создать `backend/tests/unit/test_invariants_cash.py`:
```python
from datetime import datetime

import models
from services import invariants_service


def test_cash_invariant_uses_real_snapshot_columns(db_session):
    user = models.User(email="inv@x.com", hashed_password="x", is_active=1)
    db_session.add(user)
    db_session.flush()
    acc = models.Account(user_id=user.id, name="acc")
    db_session.add(acc)
    db_session.flush()
    db_session.add(models.BalanceSnapshot(account_id=acc.id, date=datetime(2025, 1, 1), balance=100000))
    db_session.add(models.BalanceSnapshot(account_id=acc.id, date=datetime(2025, 12, 31), balance=150000))
    # output-операция должна попасть в withdrawals
    db_session.add(models.OperationORM(
        account_id=acc.id, operation_id="op1", operation_type="output",
        executed_at=datetime(2025, 6, 1), state="executed",
        payment_units=-50000, payment_nano=0,
    ))
    db_session.commit()

    # Не должно кидать AttributeError на snapshot_date/total_value.
    check = invariants_service._cash_invariant(
        db_session, acc.id, datetime(2025, 1, 1), datetime(2025, 12, 31)
    )
    assert check.name == "cash"
```
  Подставить реальную сигнатуру `_cash_invariant` (открыть строки 285–300 файла — имя параметров account_id/period_start/period_end) и обязательные поля Account/OperationORM.
- [ ] Step 2 — запуск, ожидание FAIL:
  `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_invariants_cash.py -q`
  Ожидается FAIL: `AttributeError: type object 'BalanceSnapshot' has no attribute 'snapshot_date'`.
- [ ] Step 3 — фикс. Заменить `snapshot_date`→`date` и `total_value`→`balance` (строки 341, 343, 350, 352, 358). Before (snap_start блок 337–344):
```python
    snap_start = (
        db.query(models.BalanceSnapshot)
        .filter(
            models.BalanceSnapshot.account_id == account_id,
            models.BalanceSnapshot.snapshot_date <= period_start,
        )
        .order_by(models.BalanceSnapshot.snapshot_date.desc())
        .first()
    )
```
  After:
```python
    snap_start = (
        db.query(models.BalanceSnapshot)
        .filter(
            models.BalanceSnapshot.account_id == account_id,
            models.BalanceSnapshot.date <= period_start,
        )
        .order_by(models.BalanceSnapshot.date.desc())
        .first()
    )
```
  Аналогично snap_end (строки 346–354): `snapshot_date` → `date` (два вхождения). Строка 358 Before → After:
```python
        rhs = Decimal(str(snap_end.balance or 0)) - Decimal(str(snap_start.balance or 0))
```
  Withdrawals-ветка (строка 320) Before:
```python
        elif op_type in {"out", "pay_out", "withdrawal"}:
```
  After:
```python
        elif op_type in {"output", "out", "pay_out", "withdrawal"}:
```
- [ ] Step 4 — запуск, ожидание PASS:
  `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_invariants_cash.py -q` → PASS.
- [ ] Step 5 — commit: `fix(invariants): use real BalanceSnapshot columns + count 'output' withdrawals (S4-09)`

---

## S4-10 [MED] TOTP-код можно переиспользовать (replay) в пределах окна — нет счётчика last-used

**Files:**
- Modify: `backend/services/totp_service.py` (`verify_code` строки 50–62)
- Modify: `backend/models.py` (User: добавить `totp_last_used_step`, рядом с `totp_secret` строка 43)
- Create: `backend/alembic/versions/0031_totp_last_used_step.py`
- Modify: `backend/routers/auth.py` (`/2fa/verify` строка 502; `/2fa/disable` строка 524)
- Test: `backend/tests/unit/test_totp_replay.py` (Create)

**Проблема:** `verify_code` вызывает `totp.verify(code, valid_window=1)` (±90с), но нигде не сохраняется последний использованный шаг → перехваченный код валиден повторно ~90с. Применимо к `/2fa/disable`, где код — единственная защита.

**Interfaces:** Меняет сигнатуру `verify_code` → все её вызовы в auth.py (строки 502, 524) должны передавать `user` и коммитить обновлённый `totp_last_used_step`.

Шаги:
- [ ] Step 1 — падающий тест. Создать `backend/tests/unit/test_totp_replay.py`:
```python
import pyotp

from services import totp_service


class _FakeUser:
    def __init__(self):
        self.totp_secret = pyotp.random_base32()
        self.totp_last_used_step = None


def test_same_code_rejected_on_replay():
    user = _FakeUser()
    code = pyotp.TOTP(user.totp_secret).now()
    assert totp_service.verify_code_for_user(user, code) is True
    # Повтор того же кода в том же окне — replay, должен быть отклонён.
    assert totp_service.verify_code_for_user(user, code) is False
```
- [ ] Step 2 — запуск, ожидание FAIL:
  `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_totp_replay.py -q`
  Ожидается FAIL: `AttributeError: module has no attribute 'verify_code_for_user'`.
- [ ] Step 3 — фикс. В `totp_service.py` добавить replay-safe обёртку (сохранить старую `verify_code` для обратной совместимости):
```python
def verify_code_for_user(user, code: str) -> bool:
    """Replay-safe проверка: отклоняет повторное использование того же TOTP-шага.
    Требует у user поля totp_secret и totp_last_used_step (int|None)."""
    secret = getattr(user, "totp_secret", None)
    if not secret or not code:
        return False
    if not PYOTP_AVAILABLE:
        log.error("verify_code_for_user called but pyotp not installed")
        return False
    try:
        totp = pyotp.TOTP(secret)
        import time as _time
        for offset in (-1, 0, 1):
            step = int(_time.time()) // 30 + offset
            if totp.verify(code, for_time=step * 30, valid_window=0):
                last = getattr(user, "totp_last_used_step", None)
                if last is not None and step <= last:
                    return False  # replay/старый шаг
                user.totp_last_used_step = step
                return True
        return False
    except Exception:
        log.exception("TOTP verify_code_for_user failed")
        return False
```
  В `models.py` (после строки 44 `totp_enabled`):
```python
    totp_last_used_step = Column(Integer, nullable=True)  # replay-guard: последний принятый TOTP-шаг
```
  Миграция `0031_totp_last_used_step.py` (guarded). **Порядок:** выполнять S4-10 ПОСЛЕ S4-19 — тогда head=`0030_trades_account_entry_exit_index` и down_revision ниже корректен. Если по какой-то причине S4-10 делается раньше S4-19, сначала выполни `C:/Python314/python.exe -m alembic heads` из `backend/` и подставь фактический head (сейчас, до Спринта 4, это `0029_broker_conn_cascade`; S1-02 переименовывает 0023, но НЕ добавляет новых head):
```python
"""S4-10: users.totp_last_used_step — replay-guard для TOTP.

Revision ID: 0031_totp_last_used_step
Revises: 0030_trades_account_entry_exit_index
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0031_totp_last_used_step"
down_revision: Union[str, Sequence[str], None] = "0030_trades_account_entry_exit_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from _guards import has_column
    bind = op.get_bind()
    if not has_column(bind, "users", "totp_last_used_step"):
        with op.batch_alter_table("users") as batch:
            batch.add_column(sa.Column("totp_last_used_step", sa.Integer(), nullable=True))


def downgrade() -> None:
    from _guards import has_column
    bind = op.get_bind()
    if has_column(bind, "users", "totp_last_used_step"):
        with op.batch_alter_table("users") as batch:
            batch.drop_column("totp_last_used_step")
```
  В `auth.py` заменить оба вызова `verify_code(current_user.totp_secret, payload.code)` (строки 502, 524) на `verify_code_for_user(current_user, payload.code)` и убедиться, что после успешной проверки идёт `db.commit()` (в `/2fa/verify` он уже есть после `totp_enabled = True`; в `/2fa/disable` — после `totp_secret = None`). Импорт (строки 497, 519) заменить `from services.totp_service import verify_code` → `from services.totp_service import verify_code_for_user`.
- [ ] Step 4 — запуск, ожидание PASS:
  `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_totp_replay.py -q` → PASS.
  Миграция: `cd backend && DATABASE_URL=sqlite:///./_audit_tmp.db C:/Python314/python.exe -m alembic upgrade head && DATABASE_URL=sqlite:///./_audit_tmp.db C:/Python314/python.exe -m alembic downgrade -1 && DATABASE_URL=sqlite:///./_audit_tmp.db C:/Python314/python.exe -m alembic upgrade head` → чисто. Удалить `_audit_tmp.db`.
- [ ] Step 5 — commit: `fix(auth): reject TOTP code replay via last-used-step guard (S4-10)`

---

## S4-11 [MED] User enumeration на /auth/register: разный ответ для существующего и нового email

**Files:**
- Modify: `backend/routers/auth.py` (`register` строки 51–105)
- Test: `backend/tests/integration/test_register_enumeration.py` (Create)

**Проблема:** При регистрации на существующий email — 400 «Email уже зарегистрирован», на новый — 200 с созданием → перечисление зарегистрированных почт. Помечено как принятый риск с TODO на Phase 3, не закрыто.

Шаги (единообразный ответ; полноценный email-verification-first поток — вне scope, минимально устраняем oracle по коду ответа):
- [ ] Step 1 — падающий тест. Создать `backend/tests/integration/test_register_enumeration.py`:
```python
def test_register_does_not_leak_existing_email(client, seed_user):
    # seed_user создаёт юзера с email exists@example.com
    resp = client.post("/auth/register", json={
        "email": "exists@example.com", "password": "verylongpassword123", "pd_consent": True,
    })
    # Не должно быть отличимого 400 «Email уже зарегистрирован».
    assert resp.status_code in (200, 202)
    assert "уже зарегистрирован" not in resp.text
```
  Использовать реальную register-схему (открыть `schemas.UserCreate` — набор полей: email/password/pd_consent + возможные utm). Если фикстур `client`/`seed_user` нет — построить по образцу `tests/integration/test_pr26_endpoints.py`.
- [ ] Step 2 — запуск, ожидание FAIL:
  `cd backend && C:/Python314/python.exe -m pytest tests/integration/test_register_enumeration.py -q`
  Ожидается FAIL: 400 + текст «Email уже зарегистрирован».
- [ ] Step 3 — фикс. Для существующего email — вместо 400 вернуть тот же успешный «нейтральный» ответ, а факт дубля залогировать + (best-effort) уведомить владельца письмом. Before (строки 56–62):
```python
    existing_user = auth_service.get_user_by_email(db, user_data.email)
    if existing_user:
        log.info("register: email already exists email=%s", mask_email(user_data.email))
        raise HTTPException(
            status_code=400,
            detail="Email уже зарегистрирован"
        )

    user = auth_service.create_user(db, user_data)
```
  After:
```python
    existing_user = auth_service.get_user_by_email(db, user_data.email)
    if existing_user:
        # SEC: не раскрываем факт существования email (enumeration). Отвечаем
        # нейтрально 202 и best-effort уведомляем реального владельца письмом.
        log.info("register: duplicate email attempt email=%s", mask_email(user_data.email))
        try:
            from services.email_service import send_duplicate_registration_notice
            send_duplicate_registration_notice(existing_user.email)
        except Exception:
            log.exception("register: duplicate-notice email send failed (non-blocking)")
        return JSONResponse(
            status_code=202,
            content={"message": "Если email свободен — аккаунт создан. Проверьте почту."},
        )

    user = auth_service.create_user(db, user_data)
```
  Добавить импорт `from fastapi.responses import JSONResponse` (если ещё нет вверху auth.py). `send_duplicate_registration_notice` — тонкая обёртка в `email_service.py`; если её создание раздувает задачу, допустимо в первом проходе просто `pass`-логировать (тест проверяет только отсутствие oracle). НЕ трогать успешную ветку — новый юзер по-прежнему получает 200 с cookies. Замечание: нейтральный ответ 202 без cookies для дубля означает, что фронт register-формы должен трактовать 202 как «проверьте почту», а не как логин — сверить `frontend/src/app/register` обработку (если он ждёт строго 200 authenticated — оставить 200 с тем же телом-заглушкой, но БЕЗ установки cookies; в тесте проверять именно отсутствие текста-oracle).
- [ ] Step 4 — запуск, ожидание PASS:
  `cd backend && C:/Python314/python.exe -m pytest tests/integration/test_register_enumeration.py -q` → PASS. Проверить, что happy-path регистрации не сломан: `C:/Python314/python.exe -m pytest tests/ -k register -q`.
- [ ] Step 5 — commit: `fix(auth): neutralize register response to prevent email enumeration (S4-11)`

---

## S4-12 [MED] Весь триал-UI — мёртвый код (ADR-0009 = flat freemium): удалить

**Files:**
- Delete: `frontend/src/components/TrialEndedDialog.tsx`, `frontend/src/components/TrialCountdownBanner.tsx`, `frontend/src/components/FrozenFeatureBadge.tsx`, `frontend/src/contexts/SubscriptionContext.tsx`, `frontend/src/app/pricing/page-v2.tsx`
- Verify: grep + tsc

**Проблема:** `TrialEndedDialog`, `TrialCountdownBanner`, `SubscriptionProvider`, `FrozenFeatureBadge` не смонтированы (grep — только определения + неиспользуемый `pricing/page-v2.tsx`); `GET /subscription/status` → 404. По ADR-0009 (MVP flat freemium) триала нет — это осознанно мёртвый код, его нельзя тащить в релиз.

Шаги (dead-code removal; верификация — grep+tsc):
- [ ] Step 1 — подтвердить, что ничего живое не импортирует эти модули:
```bash
cd frontend/src && grep -rn "TrialEndedDialog\|TrialCountdownBanner\|FrozenFeatureBadge\|SubscriptionProvider\|useSubscription\|SubscriptionContext" --include=*.tsx --include=*.ts | grep -v "TrialEndedDialog.tsx\|TrialCountdownBanner.tsx\|FrozenFeatureBadge.tsx\|SubscriptionContext.tsx\|pricing/page-v2.tsx"
```
  Ожидается: пусто (единственный внешний потребитель `useSubscription` — сам `pricing/page-v2.tsx`, тоже неиспользуемый роут-файл `page-v2` не является Next-страницей). Если найдётся живой импорт — СТОП, эскалировать (значит фича частично подключена).
- [ ] Step 2 — удалить файлы:
```bash
cd frontend/src && rm components/TrialEndedDialog.tsx components/TrialCountdownBanner.tsx components/FrozenFeatureBadge.tsx contexts/SubscriptionContext.tsx app/pricing/page-v2.tsx
```
- [ ] Step 3 — верификация: `cd frontend && npx tsc --noEmit` (без ошибок «cannot find module») + `npx vitest run --maxWorkers=1` (зелёно). Commit: `chore(frontend): remove dead trial/subscription UI per ADR-0009 flat freemium (S4-12)`

---

## S4-13 [MED] Onboarding-визард /onboarding/reconcile недостижим из UI: ReconciliationBanner не смонтирован

**Files:**
- Modify: `frontend/src/app/DashboardHome.tsx` (рядом с `ReconnectBanner` строки 655–662)
- Test: `frontend/src/app/__tests__/DashboardHome.reconbanner.test.tsx` (Create) ИЛИ ручная проверка

**Проблема:** Единственный `href="/onboarding/reconcile"` живёт в `ReconciliationBanner.tsx:74`, но сам баннер не рендерится нигде (grep — 0 использований) → фича сверки с брокерским отчётом отрезана от юзера.

**Interfaces:** `ReconciliationBanner` (S4-31 правит его support-mailto). Монтирование здесь не конфликтует — S4-31 меняет только href внутри компонента.

Шаги:
- [ ] Step 1 — проверка (ручная или тест). Убедиться, что `ReconciliationBanner` не в дереве: `grep -rn "ReconciliationBanner" frontend/src/app` → пусто. Смонтируем рядом с `ReconnectBanner` (DashboardHome.tsx:658).
- [ ] Step 2 — фикс. Импортировать и смонтировать. Добавить импорт вверху `DashboardHome.tsx` (рядом с импортом `ReconnectBanner`):
```tsx
import { ReconciliationBanner } from '@/components/ReconciliationBanner';
```
  После блока `ReconnectBanner` (строки 658–662) добавить:
```tsx
      {user && <ReconciliationBanner />}
```
  (`ReconciliationBanner` сам делает GET `/onboarding/reconciliation-banner` и рендерит null если `!show` — безопасно всегда монтировать под auth.)
- [ ] Step 3 — верификация: `cd frontend && npx tsc --noEmit` + ручной проход: залогиниться, если есть unresolved reconciliation breaks — баннер виден, ссылка «подробнее» ведёт на `/onboarding/reconcile`. Commit: `fix(frontend): mount ReconciliationBanner in DashboardHome so reconcile is reachable (S4-13)`

---

## S4-14 [MED] Флоу верификации email оборван: /auth/me не отдаёт email_verified

**Files:**
- Modify: `backend/schemas.py` (`UserResponse` строки 123–136)
- Modify: `frontend/src/app/profile/page.tsx` (добавить блок resend)
- Modify: `frontend/src/app/auth/verify-email/page.tsx` (текст строка 89)
- Test: `backend/tests/unit/test_user_response_email_verified.py` (Create)

**Проблема:** `UserResponse` (schemas.py:123–136) не содержит `email_verified`, хотя backend прямо говорит «решается на frontend через user.email_verified» (auth.py:80). Фронт не может узнать статус; resend-эндпоинт (auth.py:432) без потребителя; verify-email:89 отправляет на несуществующую кнопку в профиле.

Шаги (core-фикс backend + минимальные фронт-правки):
- [ ] Step 1 — падающий тест. Создать `backend/tests/unit/test_user_response_email_verified.py`:
```python
from schemas import UserResponse


def test_user_response_exposes_email_verified():
    assert "email_verified" in UserResponse.model_fields
```
- [ ] Step 2 — запуск, ожидание FAIL:
  `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_user_response_email_verified.py -q`
  Ожидается FAIL: `email_verified` не в полях.
- [ ] Step 3 — фикс. В `schemas.py` `UserResponse` (после строки 134 `registration_source`):
```python
    registration_source: Optional[str] = None
    email_verified: bool = False
```
  (`User.email_verified` уже существует, models.py:52; `from_attributes=True` подхватит.)
  В `frontend/src/app/profile/page.tsx` добавить блок «Email не подтверждён» с кнопкой resend. Найти секцию профиля и добавить (после блока с email пользователя):
```tsx
      {user && user.email_verified === false && (
        <div className="rounded-lg border border-orange-500/30 bg-orange-500/10 p-4 text-sm">
          <p className="mb-2 text-orange-200">Email не подтверждён.</p>
          <button
            onClick={async () => {
              try {
                await api.post('/auth/resend-verification');
                setMessage({ type: 'success', text: 'Письмо отправлено повторно' });
              } catch (err) {
                setMessage({ type: 'error', text: err instanceof Error ? err.message : 'Не удалось отправить' });
              }
            }}
            className="btn-secondary text-sm"
          >
            Отправить письмо повторно
          </button>
        </div>
      )}
```
  Убедиться, что тип `user` в AuthContext содержит `email_verified` (открыть тип `User` в `AuthContext.tsx` — добавить `email_verified?: boolean` если нет).
  В `verify-email/page.tsx` строка 89 — привести текст в соответствие. Before:
```tsx
                  Войдите в аккаунт и нажмите «Отправить повторно» на странице профиля.
```
  After:
```tsx
                  Войдите в аккаунт — на странице профиля будет кнопка «Отправить письмо повторно».
```
- [ ] Step 4 — запуск, ожидание PASS:
  `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_user_response_email_verified.py -q` → PASS. `cd frontend && npx tsc --noEmit`.
- [ ] Step 5 — commit: `fix(auth): expose email_verified + wire resend-verification UI (S4-14)`

---

## S4-15 [MED] Logout со страницы профиля — гонка: window.location.href абортирует POST /auth/logout

**Files:**
- Modify: `frontend/src/contexts/AuthContext.tsx` (`logout` строки 105–115)
- Modify: `frontend/src/app/profile/page.tsx` (`handleLogout` строки 87–90; `handleDeleteAccount` строки 132–133)
- Test: `frontend/src/contexts/__tests__/authLogout.test.tsx` (Create)

**Проблема:** `handleLogout` вызывает `logout()` (внутри `void api.post('/auth/logout')` не awaited) и синхронно делает `window.location.href='/'` → навигация абортирует in-flight fetch: сервер не отзывает jti, cookies не очищены. Тот же паттерн в `handleDeleteAccount`.

Шаги:
- [ ] Step 1 — падающий тест (РЕАЛЬНОЕ поведение, red→green). Создать `frontend/src/contexts/__tests__/authLogout.test.tsx`. Тест проверяет главную гарантию: `logout()` резолвится ТОЛЬКО после того, как `api.post('/auth/logout')` завершился (у текущей fire-and-forget реализации promise резолвится сразу → тест красный):
```tsx
import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

// Управляемый deferred на api.post: держим сеть «в полёте», пока сами не резолвим.
let resolvePost: () => void;
const postSpy = vi.fn(
  () => new Promise<void>((r) => { resolvePost = r; }),
);
// ВАЖНО: путь/экспорты подогнать под фактический модуль (apiClient экспортирует `api` и `clearAuthTokens`).
vi.mock('@/lib/apiClient', () => ({
  api: { post: postSpy, get: vi.fn(async () => null) },
  clearAuthTokens: vi.fn(),
}));

import { AuthProvider, useAuth } from '@/contexts/AuthContext';

const wrapper = ({ children }: { children: ReactNode }) => (
  <QueryClientProvider client={new QueryClient()}>
    <AuthProvider>{children}</AuthProvider>
  </QueryClientProvider>
);

describe('logout awaitable', () => {
  it('resolves only after api.post(/auth/logout) settles', async () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    let settled = false;
    await act(async () => {
      const p = Promise.resolve(result.current.logout()).then(() => { settled = true; });
      await Promise.resolve();            // дать микротаскам прокрутиться
      expect(settled).toBe(false);        // сеть ещё «в полёте» → logout НЕ завершён
      resolvePost();                      // отпускаем api.post
      await p;
    });
    expect(settled).toBe(true);
    expect(postSpy).toHaveBeenCalledWith('/auth/logout', { noAuth: true });
  });
});
```
  (Если `renderHook`/`@testing-library/react` в проекте недоступен — заменить на рендер `<AuthProvider>` с тест-кнопкой, вызывающей `logout`, и `fireEvent.click`; суть теста — порядок `settled` относительно `resolvePost`, а не механика рендера.)
- [ ] Step 2 — запуск: `cd frontend && npx vitest run --maxWorkers=1 src/contexts/__tests__/authLogout.test.tsx`. Ожидается FAIL: у текущей fire-and-forget реализации `logout()` возвращает `undefined`, `Promise.resolve(undefined)` резолвится немедленно → `settled` станет `true` ДО `resolvePost()`, `expect(settled).toBe(false)` упадёт.
- [ ] Step 3 — фикс. Сделать `logout` возвращающим Promise. В `AuthContext.tsx` (строки 105–115). Before:
```tsx
  const logout = useCallback(() => {
    void api.post('/auth/logout', { noAuth: true }).catch(() => undefined).finally(() => {
      clearAuthTokens();
      queryClient.setQueryData(queryKeys.auth.me(), null);
      queryClient.removeQueries({ queryKey: ['trades'] });
      queryClient.removeQueries({ queryKey: ['stats'] });
    });
  }, [queryClient]);
```
  After:
```tsx
  const logout = useCallback(async (): Promise<void> => {
    await api.post('/auth/logout', { noAuth: true }).catch(() => undefined);
    clearAuthTokens();
    queryClient.setQueryData(queryKeys.auth.me(), null);
    queryClient.removeQueries({ queryKey: ['trades'] });
    queryClient.removeQueries({ queryKey: ['stats'] });
  }, [queryClient]);
```
  Обновить тип в интерфейсе контекста (`logout: () => Promise<void>`). В `profile/page.tsx` `handleLogout` (строки 87–90). Before:
```tsx
  const handleLogout = () => {
    logout();
    window.location.href = '/';
  };
```
  After:
```tsx
  const handleLogout = async () => {
    await logout();
    window.location.href = '/';
  };
```
  В `handleDeleteAccount` (строки 132–133). Before:
```tsx
      await api.delete('/auth/me', { body: { password: deletePassword } });
      logout();
      window.location.href = '/';
```
  After:
```tsx
      await api.delete('/auth/me', { body: { password: deletePassword } });
      await logout();
      window.location.href = '/';
```
  Проверить всех остальных потребителей `logout()` (grep `logout()` по frontend/src) — с async-возвратом «fire-and-forget» вызовы (без await) продолжат работать, но если где-то результат использовался как void в JSX — tsc укажет.
- [ ] Step 4 — запуск, ожидание PASS: `cd frontend && npx tsc --noEmit` (без ошибок) + `npx vitest run --maxWorkers=1 src/contexts/__tests__/authLogout.test.tsx`.
- [ ] Step 5 — commit: `fix(frontend): await logout before navigation to avoid aborting POST /auth/logout (S4-15)`

---

## S4-16 [MED] impersonate-токен: нет запрета имперсонации админов, нет отзыва, нет ограничения действий

**Files:**
- Modify: `backend/routers/admin.py` (`admin_impersonate` строки 746–783)
- Modify: `backend/auth_service.py` (`get_current_user` — блок destructive-операций под impersonation)
- Test: `backend/tests/integration/test_admin_impersonate.py` (Create)

**Проблема:** `admin_impersonate` выпускает 15-мин JWT, но (1) не проверяет `target.is_admin`; (2) токен не пишется в `revoked_tokens`; (3) `get_current_user` не ограничивает действия под `impersonated_by`.

Шаги (закрываем п.1 запрет + п.3 блок деструктивных операций; полноценный отзыв jti — расширяемо, но минимум = запрет + guard):
- [ ] Step 1 — падающий тест. Создать `backend/tests/integration/test_admin_impersonate.py`:
```python
def test_cannot_impersonate_admin(admin_client, seed_admin_target):
    # seed_admin_target — второй пользователь с is_admin=True
    resp = admin_client.post(f"/admin/users/{seed_admin_target.id}/impersonate")
    assert resp.status_code == 403
    assert "admin" in resp.json()["detail"].lower()
```
  Построить фикстуры по образцу `tests/integration/test_pr26_endpoints.py` (admin-клиент + seeding пользователей).
- [ ] Step 2 — запуск, ожидание FAIL:
  `cd backend && C:/Python314/python.exe -m pytest tests/integration/test_admin_impersonate.py -q`
  Ожидается FAIL: 200 вместо 403.
- [ ] Step 3 — фикс. В `admin_impersonate` после проверки self (строка 764) добавить запрет админов:
```python
    if target.id == admin.id:
        raise HTTPException(status_code=400, detail="cannot impersonate yourself")
    if target.is_admin:
        raise HTTPException(status_code=403, detail="cannot impersonate an admin user")
```
  Блокировка деструктивных операций под impersonation — в `get_current_user` (auth_service.py). Найти, где декодируется JWT и извлекается payload; добавить проброс флага. Минимально: в `auth_service.get_current_user` после декода токена сохранить `request.state.is_impersonation = bool(payload.get("impersonated_by"))` (если у get_current_user есть доступ к `request`; если нет — вернуть на объекте user транзиентное поле). Затем в чувствительных эндпоинтах (смена пароля `/auth/change-password`, удаление `/auth/me`, платежи) добавить гвард. Для scope этой задачи — реализовать хелпер и применить к DELETE `/auth/me`:
```python
# auth_service.py
def assert_not_impersonation(request) -> None:
    """Блокирует деструктивные операции под impersonation-сессией (non-repudiation)."""
    if getattr(request.state, "is_impersonation", False):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Операция недоступна в режиме имперсонации")
```
  Установку `request.state.is_impersonation` сделать в `get_current_user` при наличии claim `impersonated_by`. Применить `assert_not_impersonation(request)` в DELETE `/auth/me` (открыть роут в auth.py) — это единственная точка в scope; остальные (платежи/смена пароля) отметить как follow-up в commit-описании.
- [ ] Step 4 — запуск, ожидание PASS:
  `cd backend && C:/Python314/python.exe -m pytest tests/integration/test_admin_impersonate.py -q` → PASS.
- [ ] Step 5 — commit: `fix(admin): forbid impersonating admins + guard destructive ops under impersonation (S4-16)`

---

## S4-17 [MED] Один глобальный ErrorBoundary — упавший виджет роняет весь дашборд

**Files:**
- Modify: `frontend/src/components/ErrorBoundary.tsx` (добавить `fallback` prop)
- Modify: `frontend/src/app/DashboardHome.tsx` (обернуть тяжёлые виджеты)
- Test: `frontend/src/components/__tests__/ErrorBoundary.fallback.test.tsx` (Create)

**Проблема:** `ErrorBoundary` существует один — вокруг всего дерева в root layout (layout.tsx:105). Виджеты (EquityCurveCard/Recharts, PortfolioCard, AdvancedMetricsGrid) не обёрнуты → исключение в одном заменяет ВЕСЬ дашборд на глобальный fallback.

Шаги:
- [ ] Step 1 — падающий тест. Создать `frontend/src/components/__tests__/ErrorBoundary.fallback.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ErrorBoundary } from '../ErrorBoundary';

function Boom(): never {
  throw new Error('widget crashed');
}

describe('ErrorBoundary custom fallback', () => {
  it('renders provided fallback instead of global UI', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    render(
      <ErrorBoundary fallback={<div>виджет недоступен</div>}>
        <Boom />
      </ErrorBoundary>
    );
    expect(screen.getByText('виджет недоступен')).toBeInTheDocument();
    spy.mockRestore();
  });
});
```
- [ ] Step 2 — запуск, ожидание FAIL:
  `cd frontend && npx vitest run --maxWorkers=1 src/components/__tests__/ErrorBoundary.fallback.test.tsx`
  Ожидается FAIL: рендерится глобальный «Что-то пошло не так», а не «виджет недоступен» (нет prop `fallback`).
- [ ] Step 3 — фикс. В `ErrorBoundary.tsx` добавить опциональный `fallback`. Before (строки 11–13):
```tsx
interface ErrorBoundaryProps {
  children: React.ReactNode;
}
```
  After:
```tsx
interface ErrorBoundaryProps {
  children: React.ReactNode;
  fallback?: React.ReactNode;
}
```
  В `render()` (строка 42) — при наличии `fallback` вернуть его:
```tsx
    if (this.state.hasError) {
      if (this.props.fallback !== undefined) {
        return this.props.fallback;
      }
      return (
        <div className="min-h-screen bg-background flex items-center justify-center p-4">
```
  В `DashboardHome.tsx` обернуть рисковые виджеты. Пример для EquityCurveCard (строки 679–689):
```tsx
          <ErrorBoundary fallback={<div className="card p-6 text-sm text-[var(--text-secondary)]">График недоступен</div>}>
            <EquityCurveCard
              data={settings.pnlDisplayMode === 'gross' ? stats?.equity_curve_gross : stats?.equity_curve}
              benchmark={stats?.imoex_curve}
              benchmarkLabel="IMOEX"
              initialBalance={effectiveInitialDeposit ?? undefined}
              formatCurrency={formatCurrency}
              isBrokerCumulative={isBrokerUser}
              pctBaseline={(stats as { drawdown_baseline?: number })?.drawdown_baseline ?? 0}
              peakDate={stats?.max_drawdown_peak_date ?? null}
              troughDate={stats?.max_drawdown_trough_date ?? null}
            />
          </ErrorBoundary>
```
  Аналогично обернуть `PortfolioCard`, `AdvancedMetricsGrid`, `BenchmarkingView` (найти их рендер в DashboardHome по имени компонента) в `<ErrorBoundary fallback={<div className="card p-6 text-sm text-[var(--text-secondary)]">Виджет недоступен</div>}>`. Импорт `ErrorBoundary` в DashboardHome (если ещё нет): `import { ErrorBoundary } from '@/components/ErrorBoundary';`.
- [ ] Step 4 — запуск, ожидание PASS:
  `cd frontend && npx vitest run --maxWorkers=1 src/components/__tests__/ErrorBoundary.fallback.test.tsx` → PASS. `npx tsc --noEmit`.
- [ ] Step 5 — commit: `fix(frontend): per-widget ErrorBoundary fallback so one crash doesn't kill dashboard (S4-17)`

---

## S4-18 [MED] Дрейф: индексы ix_operations_state_type_executed и ix_access_log_status_created отсутствуют в models.py

**Files:**
- Modify: `backend/models.py` (`OperationORM.__table_args__` строки 956–964; `AccessLogORM.__table_args__` строки 807–810)
- Verify: `alembic check`

**Проблема:** Миграция 0027 создаёт два composite-индекса, но в `__table_args__` `OperationORM` и `AccessLogORM` они не объявлены → `alembic check` падает `New upgrade operations detected: remove_index ...` → следующая autogenerate молча дропнет прод-перф-индексы; БД через `create_all` их не имеют.

**Interfaces:** Обе index-drift задачи (S4-18, S4-19) правят `models.py.__table_args__` + связаны с `alembic check`-гейтом в S4-03. S4-18 = добавить в модели уже существующие в 0027 индексы; S4-19 = добавить недостающую миграцию для индекса, который уже в модели.

Шаги:
- [ ] Step 1 — воспроизвести. На чистой врем. БД:
```bash
cd backend
DATABASE_URL=sqlite:///./_audit_tmp.db C:/Python314/python.exe -m alembic upgrade head
DATABASE_URL=sqlite:///./_audit_tmp.db C:/Python314/python.exe -m alembic check
```
  Ожидается FAIL: `New upgrade operations detected: [('remove_index', ...ix_access_log_status_created...), ('remove_index', ...ix_operations_state_type_executed...)]`.
- [ ] Step 2 — фикс. В `OperationORM.__table_args__` (после строки 963 `Index("ix_operations_type", ...)`) добавить:
```python
        Index("ix_operations_type", "operation_type"),
        # 0027_perf_indexes: composite под варм-маржу (state, operation_type, executed_at).
        Index("ix_operations_state_type_executed", "state", "operation_type", "executed_at"),
    )
```
  В `AccessLogORM.__table_args__` (после строки 809 `Index("ix_access_log_status", ...)`):
```python
        Index("ix_access_log_status", "status_code"),
        # 0027_perf_indexes: composite под /admin/errors/recent (status_code, created_at).
        Index("ix_access_log_status_created", "status_code", "created_at"),
    )
```
- [ ] Step 3 — верификация. Пересоздать врем. БД и проверить:
```bash
cd backend && rm -f _audit_tmp.db
DATABASE_URL=sqlite:///./_audit_tmp.db C:/Python314/python.exe -m alembic upgrade head
DATABASE_URL=sqlite:///./_audit_tmp.db C:/Python314/python.exe -m alembic check
```
  Ожидается: `remove_index` этих двух индексов больше НЕ появляется (может остаться дрейф S4-19 — закрывается там). `C:/Python314/python.exe -c "import models"` без ошибок. Удалить `_audit_tmp.db`. Commit: `fix(models): declare 0027 perf indexes in ORM to fix alembic drift (S4-18)`

---

## S4-19 [MED] Обратный дрейф: ix_trades_account_entry_exit в models.py без миграции

**Files:**
- Create: `backend/alembic/versions/0030_trades_account_entry_exit_index.py`
- Verify: `alembic check` clean + snap CI-гейта в S4-03

**Проблема:** Индекс `ix_trades_account_entry_exit(account_id, entry_at, exit_at)` добавлен в models.py (строка 338) коммитом 8aece9e (после 0029), но миграции нет → существующие БД (и прод после первого деплоя) его не получат. `create_all` даёт его только свежим БД.

**Interfaces:** Дополняет S4-18 — вместе делают `alembic check` полностью clean, после чего в S4-03 снимается `continue-on-error` с CI-шага `alembic check`. down_revision миграции = актуальный head (на момент плана 0029; если S1-02 переименовал 0023 или добавились миграции — взять `alembic heads`; S4-10 создаёт 0031 после этой, поэтому эта = 0030).

Шаги:
- [ ] Step 1 — воспроизвести. На чистой врем. БД после S4-18:
```bash
cd backend && rm -f _audit_tmp.db
DATABASE_URL=sqlite:///./_audit_tmp.db C:/Python314/python.exe -m alembic upgrade head
DATABASE_URL=sqlite:///./_audit_tmp.db C:/Python314/python.exe -m alembic check
```
  Если индекс уже создаётся `create_all` в 0001 — на SQLite дрейфа может не быть; но на прод-Postgres (миграции с нуля, без create_all) индекса нет. Подтвердить, что `grep -rn ix_trades_account_entry_exit alembic/versions/` → пусто.
- [ ] Step 2 — фикс. Создать `backend/alembic/versions/0030_trades_account_entry_exit_index.py` (guarded, по образцу 0027):
```python
"""S4-19: ix_trades_account_entry_exit — недостающая миграция под индекс из models.py.

Revision ID: 0030_trades_account_entry_exit_index
Revises: 0029_broker_conn_cascade
Create Date: 2026-07-02 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0030_trades_account_entry_exit_index"
down_revision: Union[str, Sequence[str], None] = "0029_broker_conn_cascade"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX = "ix_trades_account_entry_exit"


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if _is_postgres():
        with op.get_context().autocommit_block():
            op.execute(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {_INDEX} "
                "ON trades (account_id, entry_at, exit_at)"
            )
    else:
        from _guards import has_index
        bind = op.get_bind()
        if not has_index(bind, "trades", _INDEX):
            op.create_index(
                _INDEX, "trades", ["account_id", "entry_at", "exit_at"], unique=False
            )


def downgrade() -> None:
    if _is_postgres():
        with op.get_context().autocommit_block():
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {_INDEX}")
    else:
        from _guards import has_index
        bind = op.get_bind()
        if has_index(bind, "trades", _INDEX):
            op.drop_index(_INDEX, table_name="trades")
```
  ВАЖНО: сверить, что `down_revision` = реальный текущий head (`cd backend && C:/Python314/python.exe -m alembic heads`). Если head изменился из-за S1-02 (переименование 0023) — обновить.
- [ ] Step 3 — верификация:
```bash
cd backend && rm -f _audit_tmp.db
DATABASE_URL=sqlite:///./_audit_tmp.db C:/Python314/python.exe -m alembic upgrade head
DATABASE_URL=sqlite:///./_audit_tmp.db C:/Python314/python.exe -m alembic downgrade -1
DATABASE_URL=sqlite:///./_audit_tmp.db C:/Python314/python.exe -m alembic upgrade head
DATABASE_URL=sqlite:///./_audit_tmp.db C:/Python314/python.exe -m alembic check
```
  Ожидается: `alembic check` → `No new upgrade operations detected` (clean, вместе с S4-18). Удалить `_audit_tmp.db`. Затем снять `continue-on-error` с шага `alembic check` в `ci.yml` (добавленного в S4-03). Commit: `fix(migrations): add 0030 for ix_trades_account_entry_exit + make alembic check clean (S4-19)`

---

## S4-20 [LOW] api.generated.ts не перегенерирован — отсутствует /api/landing/ticker

**Files:**
- Modify: `frontend/src/types/api.generated.ts` (регенерация)
- Verify: grep + tsc

**Проблема:** Живой `/openapi.json` содержит `/api/landing/ticker`, в `api.generated.ts` его нет (141 vs 142 пути) → дрейф генерата обесценивает типизированный контракт.

Шаги (регенерация; ПОСЛЕ всех backend-контрактных правок S4-04/S4-14):
- [ ] Step 1 — проверка: `grep -c '"/api/landing' frontend/src/types/api.generated.ts` → 0.
- [ ] Step 2 — регенерация (backend :8000 должен отражать все правки С1–С4). Выполнить проектную команду:
```bash
cd frontend && npm run gen:api-types
```
  (Если скрипта нет в package.json — `npx openapi-typescript http://localhost:8000/openapi.json -o src/types/api.generated.ts`. НЕ трогать вручную бренд-строки — регенерация их перезапишет; при необходимости сохранить «Полистата»-комментарий шапки.)
- [ ] Step 3 — верификация: `grep -c '"/api/landing' frontend/src/types/api.generated.ts` → ≥1; `cd frontend && npx tsc --noEmit` (без ошибок). Commit: `chore(frontend): regenerate api.generated.ts (adds /api/landing/ticker) (S4-20)`

---

## S4-21 [LOW] Raw fetch без таймаута в обход apiClient/fetchWithTimeout (4 места)

**Files:**
- Modify: `frontend/src/components/OAuthButtons.tsx` (строки 107, 140)
- Modify: `frontend/src/app/status/page.tsx` (строка ~36), `frontend/src/components/StatusBadge.tsx` (строка ~23)
- Modify: `frontend/src/components/landing/parts/LiveTicker.tsx` (строка 8)
- Test: не требуется (грубая замена) — tsc + ручная проверка

**Проблема:** Все запросы должны идти через `fetchWithTimeout(15s)`. Мимо неё: `OAuthButtons` (обмен OAuth-кода — юзер зависнет на логине при мёртвом бэке), status/StatusBadge (/ready), LiveTicker. Все — прямой `fetch()` без AbortController.

Шаги (приоритет — OAuthButtons):
- [ ] Step 1 — проверка: `grep -rn "await fetch(" frontend/src/components/OAuthButtons.tsx frontend/src/app/status/page.tsx frontend/src/components/StatusBadge.tsx frontend/src/components/landing/parts/LiveTicker.tsx`.
- [ ] Step 2 — фикс. В каждом файле импортировать `import { fetchWithTimeout } from '@/lib/fetchWithTimeout';` и заменить `fetch(` → `fetchWithTimeout(`. Пример OAuthButtons.tsx (строка 107). Before:
```tsx
          const response = await fetch(
            getApiUrl(`/auth/oauth/${provider}/callback?code=${code}&state=${state}&redirect_uri=${encodeURIComponent(redirectUri)}`),
            { method: 'POST', credentials: 'include' }
          );
```
  After:
```tsx
          const response = await fetchWithTimeout(
            getApiUrl(`/auth/oauth/${provider}/callback?code=${code}&state=${state}&redirect_uri=${encodeURIComponent(redirectUri)}`),
            { method: 'POST', credentials: 'include' }
          );
```
  Аналогично строка 140 (authorize) и LiveTicker.tsx строка 8. Для `LiveTicker` (relative URL `/api/landing/ticker`) — `fetchWithTimeout("/api/landing/ticker")` (сигнатура допускает вызов с одним аргументом, дефолт 15с). Для status/page.tsx и StatusBadge.tsx (/ready) — то же.
- [ ] Step 3 — верификация: `grep -rn "await fetch(" frontend/src/components/OAuthButtons.tsx ...` → пусто; `cd frontend && npx tsc --noEmit` + `npx vitest run --maxWorkers=1`. Commit: `fix(frontend): route 4 raw fetch calls through fetchWithTimeout (S4-21)`

---

## S4-22 [LOW] _index_cache в MoexService — неограниченный рост словаря

**Files:**
- Modify: `backend/moex_service.py` (`__init__` строки 98–103; запись кэша строка 413)
- Test: `backend/tests/unit/test_moex_index_cache_evict.py` (Create)

**Проблема:** Кэш истории IMOEX ключуется `(ticker, start_iso, end_iso)` — почти уникален на юзера и дрейфует с каждой сделкой. TTL проверяется только на чтение; протухшие записи не удаляются, `max_size` нет → медленная утечка до OOM.

Шаги:
- [ ] Step 1 — падающий тест. Создать `backend/tests/unit/test_moex_index_cache_evict.py`:
```python
from datetime import datetime, timedelta

from moex_service import MoexService


def test_index_cache_evicts_expired_on_write():
    svc = MoexService()
    old = datetime.utcnow() - timedelta(hours=2)  # старше TTL (1ч)
    svc._index_cache[("IMOEX", "2020-01-01", "2020-12-31")] = ([], old)
    svc._store_index_cache(("IMOEX", "2025-01-01", "2025-12-31"), [{"date": "2025-01-01", "value": 1.0}])
    # Протухшая запись должна быть удалена при записи новой.
    assert ("IMOEX", "2020-01-01", "2020-12-31") not in svc._index_cache


def test_index_cache_bounded_size():
    svc = MoexService()
    for i in range(300):
        svc._store_index_cache(("IMOEX", f"2025-{i:03d}", "x"), [])
    assert len(svc._index_cache) <= svc._INDEX_CACHE_MAX
```
- [ ] Step 2 — запуск, ожидание FAIL:
  `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_moex_index_cache_evict.py -q`
  Ожидается FAIL: `AttributeError: '_store_index_cache'`.
- [ ] Step 3 — фикс. В `__init__` (строка 103) добавить лимит:
```python
        self._index_cache_ttl = timedelta(hours=1)
        self._INDEX_CACHE_MAX = 256
```
  Добавить метод записи с эвикцией и заменить прямую запись на строке 413. Метод:
```python
    def _store_index_cache(self, cache_key, rows) -> None:
        now = datetime.utcnow()
        # Чистим протухшие записи.
        expired = [k for k, (_, ts) in self._index_cache.items() if now - ts >= self._index_cache_ttl]
        for k in expired:
            self._index_cache.pop(k, None)
        # Жёсткий кап: если всё ещё переполнено — выкидываем самые старые.
        if len(self._index_cache) >= self._INDEX_CACHE_MAX:
            for k in sorted(self._index_cache, key=lambda kk: self._index_cache[kk][1])[
                : len(self._index_cache) - self._INDEX_CACHE_MAX + 1
            ]:
                self._index_cache.pop(k, None)
        self._index_cache[cache_key] = (rows, now)
```
  Строка 413 Before:
```python
        self._index_cache[cache_key] = (all_rows, datetime.utcnow())
```
  After:
```python
        self._store_index_cache(cache_key, all_rows)
```
- [ ] Step 4 — запуск, ожидание PASS:
  `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_moex_index_cache_evict.py -q` → PASS.
- [ ] Step 5 — commit: `fix(moex): bound _index_cache with TTL eviction + max size (S4-22)`

---

## S4-23 [LOW] GET /stats/benchmark без кэша и без rate-limit — full-scan на каждый вызов

**Files:**
- Modify: `backend/routers/stats_advanced.py` (`get_benchmark` строки 165–179)
- Test: `backend/tests/unit/test_benchmark_rate_limited.py` (Create) ИЛИ smoke

**Проблема:** `/stats/benchmark` не имеет ни кэша, ни отдельного лимита (только дефолт 120/min), на каждый запрос `load_filtered_trades` (.all()) + полный набор метрик. `/advanced` уже имеет `@limiter.limit(API_LIMIT)` (строка 44).

Шаги (минимум — добавить rate-limit по образцу `/advanced`; кэш опционален):
- [ ] Step 1 — проверка/тест. Создать `backend/tests/unit/test_benchmark_rate_limited.py`:
```python
import inspect

from routers import stats_advanced


def test_benchmark_has_rate_limit_decorator():
    src = inspect.getsource(stats_advanced.get_benchmark)
    # Декоратор limiter применяется к обёртке; проверяем что endpoint принимает Request
    # (необходим для slowapi limiter) — контракт наличия лимита.
    sig = inspect.signature(stats_advanced.get_benchmark)
    assert "request" in sig.parameters
```
- [ ] Step 2 — запуск, ожидание FAIL:
  `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_benchmark_rate_limited.py -q`
  Ожидается FAIL: у `get_benchmark` нет параметра `request`.
- [ ] Step 3 — фикс. Добавить декоратор и `request: Request` по образцу `/advanced` (строки 43–46). Before (строки 165–172):
```python
@router.get("/benchmark")
async def get_benchmark(
    period: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user),
):
```
  After:
```python
@router.get("/benchmark")
@limiter.limit(API_LIMIT)
async def get_benchmark(
    request: Request,
    period: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user),
):
```
  (`limiter`, `API_LIMIT`, `Request` уже импортированы в файле — используются `/advanced`.)
- [ ] Step 4 — запуск, ожидание PASS:
  `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_benchmark_rate_limited.py -q` → PASS. Импорт-смоук `C:/Python314/python.exe -c "import main"`.
- [ ] Step 5 — commit: `fix(stats): rate-limit /stats/benchmark like /advanced (S4-23)`

---

## S4-24 [LOW] Anonymization не чистит totp_secret и email_verification_token

**Files:**
- Modify: `backend/services/pd_deletion.py` (`finalize_deletion` анонимизация User строки 170–180)
- Test: `backend/tests/unit/test_pd_deletion_totp.py` (Create)

**Проблема:** `finalize_deletion` зануляет email/name/oauth/utm/settings, но оставляет `totp_secret` и `email_verification_token` на анонимизированной записи.

**Interfaces:** Та же функция, что S4-01 и S4-35. Правит блок анонимизации User (строки 170–180).

Шаги:
- [ ] Step 1 — падающий тест. Создать `backend/tests/unit/test_pd_deletion_totp.py`:
```python
import models
from services import pd_deletion


def test_finalize_clears_totp_and_verification(db_session):
    user = models.User(
        email="t@x.com", hashed_password="x", is_active=1,
        totp_secret="SECRET32", totp_enabled=True, email_verification_token="tok123",
    )
    db_session.add(user)
    db_session.commit()

    pd_deletion.finalize_deletion(db_session, user)

    assert user.totp_secret is None
    assert user.totp_enabled is False
    assert user.email_verification_token is None
```
- [ ] Step 2 — запуск, ожидание FAIL:
  `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_pd_deletion_totp.py -q`
  Ожидается FAIL: `totp_secret` == "SECRET32".
- [ ] Step 3 — фикс. В блоке анонимизации (после строки 179 `user.settings = {}`):
```python
    user.settings = {}
    user.last_login = None
    # 152-ФЗ: секреты 2FA и токен верификации — тоже подлежат уничтожению.
    user.totp_secret = None
    user.totp_enabled = False
    user.email_verification_token = None
```
- [ ] Step 4 — запуск, ожидание PASS:
  `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_pd_deletion_totp.py -q` → PASS.
- [ ] Step 5 — commit: `fix(152-fz): clear totp_secret and email_verification_token on anonymization (S4-24)`

---

## S4-25 [LOW] Timing-enumeration на /password-reset/request (синхронный SMTP только для существующих)

**Files:**
- Modify: `backend/routers/auth.py` (`password_reset_request` строки 538–610)
- Test: не требуется строгий (timing) — smoke + code review

**Проблема:** Эндпоинт всегда 202 (закрывает enumeration по коду), но письмо отправляется синхронно (`send_password_reset_email`, smtplib timeout=15) ТОЛЬКО для существующего активного юзера; для несуществующего — ранний return без SMTP → разница во времени ответа = timing-oracle.

Шаги (вынести отправку в BackgroundTasks — response уходит одинаково быстро в обоих ветках):
- [ ] Step 1 — проверка: подтвердить, что отправка синхронна в теле запроса (строки 600–607) и для несуществующего юзера её нет (строки 562–564 ранний return).
- [ ] Step 2 — фикс. Добавить `BackgroundTasks` в сигнатуру и выносить отправку в фон. Сигнатура (строки 538–542). Before:
```python
def password_reset_request(
    request: Request,
    payload: schemas.PasswordResetRequest,
    db: Session = Depends(database.get_db),
):
```
  After:
```python
def password_reset_request(
    request: Request,
    payload: schemas.PasswordResetRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(database.get_db),
):
```
  Заменить синхронную отправку (строки 600–607). Before:
```python
    try:
        send_password_reset_email(
            to_email=user.email,
            reset_url=reset_url,
            user_name=getattr(user, "name", None),
        )
    except Exception:
        log.exception("password_reset email send failed for user_id=%s", user.id)
```
  After:
```python
    # Отправка в фоне: response не должен зависеть от времени SMTP-round-trip
    # (иначе timing-oracle отличает существующий email от несуществующего).
    background_tasks.add_task(
        send_password_reset_email,
        to_email=user.email,
        reset_url=reset_url,
        user_name=getattr(user, "name", None),
    )
```
  Добавить `BackgroundTasks` в импорт из fastapi вверху auth.py.
- [ ] Step 3 — верификация: `cd backend && C:/Python314/python.exe -c "import main"` (импортится) + прогон password-reset тестов `C:/Python314/python.exe -m pytest tests/ -k password_reset -q`. Commit: `fix(auth): send password-reset email in background to close timing oracle (S4-25)`

---

## S4-26 [LOW] Тема сбрасывается на тёмную при логине/логауте (theme в user-scoped tradingSettings)

**Files:**
- Modify: `frontend/src/contexts/SettingsContext.tsx` (`getInitialSettings` строки 54–85; `updateSettings` строки 107–123)
- Test: `frontend/src/contexts/__tests__/themePersist.test.tsx` (Create)

**Проблема:** `USER_SCOPED_STORAGE_KEYS` включает `'tradingSettings'` целиком, а `SettingsContext` хранит там же `theme` → тема чистится при смене владельца (logout/login). ThemeToggle-персистентность не работает: светлая тема после re-login → тёмная.

Шаги (вынести theme в отдельный device-ключ вне user-scoped):
- [ ] Step 1 — падающий тест (детерминированный red). Создать `frontend/src/contexts/__tests__/themePersist.test.tsx`. Тест фиксирует два инварианта: (1) `updateSettings({theme})` пишет device-ключ `empirik.theme`; (2) он переживает `clearUserScopedState()`. Сейчас theme уходит ТОЛЬКО в `tradingSettings` (user-scoped) → первый assert красный (`empirik.theme` === null):
```tsx
import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import type { ReactNode } from 'react';
import { SettingsProvider, useSettings } from '@/contexts/SettingsContext';
import { clearUserScopedState } from '@/lib/userScopedStorage';

const wrapper = ({ children }: { children: ReactNode }) => (
  <SettingsProvider>{children}</SettingsProvider>
);

describe('theme persistence (device-scoped)', () => {
  beforeEach(() => localStorage.clear());

  it('updateSettings пишет theme в device-ключ empirik.theme и он переживает logout', () => {
    const { result } = renderHook(() => useSettings(), { wrapper });
    act(() => { result.current.updateSettings({ theme: 'light' }); });
    // (1) тема ушла в device-ключ, а не только в user-scoped tradingSettings
    expect(localStorage.getItem('empirik.theme')).toBe('light');
    // (2) logout (смена владельца) её не стирает
    clearUserScopedState();
    expect(localStorage.getItem('empirik.theme')).toBe('light');
  });
});
```
  (Если `useSettings`/`updateSettings` называются иначе — сверить с `SettingsContext.tsx` в Step 1 перед запуском и подставить фактические имена.)
- [ ] Step 2 — запуск, ожидание FAIL: `cd frontend && npx vitest run --maxWorkers=1 src/contexts/__tests__/themePersist.test.tsx` → `expect(localStorage.getItem('empirik.theme')).toBe('light')` падает (получено `null`), т.к. theme пишется только в `tradingSettings`.
- [ ] Step 3 — фикс. В `SettingsContext.tsx` читать/писать theme из device-ключа. Константа вверху файла:
```tsx
const THEME_DEVICE_KEY = 'empirik.theme';
```
  В `getInitialSettings` (строка 80) при сборке — переопределять theme device-значением:
```tsx
      theme: (typeof window !== 'undefined' && (localStorage.getItem(THEME_DEVICE_KEY) as Theme))
        || parsed.theme || defaultSettings.theme,
```
  В `updateSettings` (после `localStorage.setItem('tradingSettings', ...)` строка 117) — дублировать theme в device-ключ:
```tsx
        localStorage.setItem('tradingSettings', JSON.stringify(updated));
        if (newSettings.theme) {
          localStorage.setItem(THEME_DEVICE_KEY, newSettings.theme);
        }
```
  (Оставляем theme и в tradingSettings для обратной совместимости, но истина — в device-ключе; при logout `clearUserScopedState` чистит только `tradingSettings`, device-ключ уцелеет.)
- [ ] Step 4 — запуск, ожидание PASS: подправить тест под контракт (после `updateSettings` `empirik.theme` установлен и переживает `clearUserScopedState`):
  `cd frontend && npx vitest run --maxWorkers=1 src/contexts/__tests__/themePersist.test.tsx` → PASS. `npx tsc --noEmit`.
- [ ] Step 5 — commit: `fix(frontend): persist theme in device-scoped key so it survives login/logout (S4-26)`

---

## S4-27 [LOW] global-error.tsx без CSS + кнопка reset() вместо reload

**Files:**
- Modify: `frontend/src/app/global-error.tsx` (строки 26–43)
- Verify: ручная проверка рендера

**Проблема:** `global-error` замещает root layout, но не подключает стили (нет `import './globals.css'`, нет inline-стилей) → Tailwind-утилиты и `btn-primary` не применятся: голый текст, невидимая кнопка. Плюс `onClick={reset}` при детерминированной ошибке провайдеров зациклит — честнее `window.location.reload()`.

Шаги (inline-стили — надёжнее, т.к. globals.css в global-error может не примениться при сломанном билд-графе):
- [ ] Step 1 — проверка: подтвердить отсутствие импорта CSS (grep `import.*css` в файле — пусто).
- [ ] Step 2 — фикс. Заменить блок рендера (строки 26–43) на inline-стилизованный + reload. Before:
```tsx
  return (
    <html lang="ru">
      <body>
        <div className="min-h-screen flex items-center justify-center p-8">
          <div className="max-w-md text-center">
            <h2 className="text-2xl font-bold mb-2">Критическая ошибка</h2>
            <p className="mb-4">Перезагрузите страницу.</p>
            {error.digest && (
              <p className="text-xs mb-4">ID: {error.digest}</p>
            )}
            <button onClick={reset} className="btn-primary">
              Перезагрузить
            </button>
          </div>
        </div>
      </body>
    </html>
  );
```
  After:
```tsx
  return (
    <html lang="ru">
      <body style={{ margin: 0, background: '#0b0b0d', color: '#f5f5f5', fontFamily: 'system-ui, sans-serif' }}>
        <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 32 }}>
          <div style={{ maxWidth: 420, textAlign: 'center' }}>
            <h2 style={{ fontSize: 24, fontWeight: 700, marginBottom: 8 }}>Критическая ошибка</h2>
            <p style={{ marginBottom: 16, opacity: 0.85 }}>Перезагрузите страницу.</p>
            {error.digest && (
              <p style={{ fontSize: 12, marginBottom: 16, opacity: 0.6 }}>ID: {error.digest}</p>
            )}
            <button
              onClick={() => window.location.reload()}
              style={{
                background: '#E2521C', color: '#fff', border: 'none', borderRadius: 8,
                padding: '10px 20px', fontSize: 14, cursor: 'pointer',
              }}
            >
              Перезагрузить
            </button>
          </div>
        </div>
      </body>
    </html>
  );
```
  (`reset` больше не используется — убрать из деструктуризации props или оставить с eslint-disable; проще оставить в сигнатуре и не вызывать, tsc не ругается на неиспользуемый destructured prop если он объявлен в типе. Если lint строг — переименовать в `_reset` или убрать из деструктуризации.)
- [ ] Step 3 — верификация: `cd frontend && npx tsc --noEmit`. Ручная: временно бросить ошибку в root layout (или довериться визуальному ревью inline-стилей — кнопка оранжевая #E2521C по бренду видна). Commit: `fix(frontend): inline-style global-error + use window.reload (S4-27)`

---

## S4-28 [LOW] Контакты поддержки разъезжаются: support@empirik.app vs empirik.io vs t.me/atom_support_bot

**Files:**
- Create: `frontend/src/lib/contact.ts` (константа `SUPPORT_EMAIL`)
- Modify: `frontend/src/app/help/page.tsx` (строки 72, 89, 167, 176, 183, 194, 280, 287), `frontend/src/app/status/page.tsx` (строка 120)
- Test: не требуется — grep + tsc

**Проблема:** Четыре разных адресата: `support@empirik.app` (5 вхождений), `support@empirik.io`, `hello@empirik.io`, Telegram `t.me/atom_support_bot` со старым кодовым именем ATOM. Зона `.app` вероятно не обслуживается.

**Interfaces:** Создаёт `SUPPORT_EMAIL`-константу, которую переиспользует S4-31 (ReconciliationBanner + Landing + onboarding/reconcile). S4-28 создаёт константу и правит help/status; S4-31 подключает её в остальных файлах.

Шаги:
- [ ] Step 1 — проверка: `grep -rn "empirik.app\|atom_support_bot" frontend/src/app/help frontend/src/app/status`.
- [ ] Step 2 — фикс. Создать `frontend/src/lib/contact.ts`:
```ts
// Единый обслуживаемый адрес поддержки. Домен согласован с бизнес-решением
// (empirik.io оставлен осознанно до регистрации polistata.ru). ENV-override для прод.
export const SUPPORT_EMAIL = process.env.NEXT_PUBLIC_SUPPORT_EMAIL || 'support@empirik.io';
export const SUPPORT_TELEGRAM = 'https://t.me/empirik_support_bot';
```
  В `help/page.tsx` импортировать и заменить все `support@empirik.app` → `{SUPPORT_EMAIL}` (в JSX-тексте) и `mailto:support@empirik.app` → `` `mailto:${SUPPORT_EMAIL}` ``. Telegram-ссылку `https://t.me/atom_support_bot` → `{SUPPORT_TELEGRAM}` и текст `@atom_support_bot` → `@empirik_support_bot`. В `status/page.tsx` строка 120 — то же для mailto.
  (ВАЖНО: реальный обслуживаемый ящик и имя Telegram-бота должен подтвердить владелец; в коде — константа, значение легко поменять через ENV. Если владелец не подтвердил — оставить `empirik.io` как в privacy/pricing, где уже используется рабочий домен.)
- [ ] Step 3 — верификация: `grep -rn "empirik.app\|atom_support_bot" frontend/src/app/help frontend/src/app/status` → пусто; `cd frontend && npx tsc --noEmit`. Commit: `fix(frontend): unify support contact into SUPPORT_EMAIL constant (help/status) (S4-28)`

---

## S4-29 [LOW] admin feature-flags PATCH принимает произвольные имена флагов без whitelist

**Files:**
- Modify: `backend/routers/admin.py` (`admin_set_feature_flags` строки 1531–1567)
- Test: `backend/tests/integration/test_feature_flags_whitelist.py` (Create)

**Проблема:** `admin_set_feature_flags` принимает произвольный `dict[str,bool]` и создаёт любую строку-флаг (`flag_name[:64]`) без валидации → опечатка/будущий код-путь молча активирует/деактивирует гейтинг.

Шаги:
- [ ] Step 1 — падающий тест. Создать `backend/tests/integration/test_feature_flags_whitelist.py`:
```python
def test_unknown_flag_rejected(admin_client, seed_user):
    resp = admin_client.patch(
        f"/admin/users/{seed_user.id}/feature-flags",
        json={"totally-unknown-flag": True},
    )
    assert resp.status_code == 400


def test_known_flag_accepted(admin_client, seed_user):
    from routers.admin import ALLOWED_FEATURE_FLAGS
    known = next(iter(ALLOWED_FEATURE_FLAGS))
    resp = admin_client.patch(
        f"/admin/users/{seed_user.id}/feature-flags",
        json={known: True},
    )
    assert resp.status_code == 200
```
- [ ] Step 2 — запуск, ожидание FAIL:
  `cd backend && C:/Python314/python.exe -m pytest tests/integration/test_feature_flags_whitelist.py -q`
  Ожидается FAIL: неизвестный флаг возвращает 200 (или `ALLOWED_FEATURE_FLAGS` не существует).
- [ ] Step 3 — фикс. Ввести whitelist модульного уровня в admin.py (значения сверить с реальными флагами — открыть `feature_flags.py`; если нет чёткого списка, включить известные из моделей/тестов, напр. `mae-mfe-beta`):
```python
# Допустимый набор feature-flag имён. Неизвестные отклоняются, чтобы опечатка
# или будущий код-путь не активировал гейтинг платных фич молча.
ALLOWED_FEATURE_FLAGS = frozenset({"mae-mfe-beta", "trade-replay-beta", "ai-insights-beta"})
```
  В `admin_set_feature_flags` перед циклом (строка 1544) добавить валидацию:
```python
    unknown = set(flags) - ALLOWED_FEATURE_FLAGS
    if unknown:
        log.warning("admin_set_feature_flags: unknown flags rejected: %s", unknown)
        raise HTTPException(
            status_code=400,
            detail=f"Неизвестные feature-флаги: {', '.join(sorted(unknown))}",
        )

    for flag_name, enabled in flags.items():
```
- [ ] Step 4 — запуск, ожидание PASS:
  `cd backend && C:/Python314/python.exe -m pytest tests/integration/test_feature_flags_whitelist.py -q` → PASS.
- [ ] Step 5 — commit: `fix(admin): whitelist feature-flag names, reject unknown (S4-29)`

---

## S4-30 [LOW] Мёртвый дубликат PeriodSelector.tsx с hardcoded русскими строками

**Files:**
- Delete: `frontend/src/components/PeriodSelector.tsx`
- Verify: grep + tsc

**Проблема:** `PeriodSelector.tsx` нигде не импортируется (grep — только собственное определение); реальный селектор живёт в `FilterPanel.tsx`. Дубликат с захардкоженными строками мимо i18n — ловушка.

Шаги:
- [ ] Step 1 — подтвердить мёртвость: `grep -rn "PeriodSelector" frontend/src --include=*.tsx --include=*.ts | grep -v "components/PeriodSelector.tsx"` → пусто. Если найдётся импорт — СТОП.
- [ ] Step 2 — удалить: `rm frontend/src/components/PeriodSelector.tsx`.
- [ ] Step 3 — верификация: `cd frontend && npx tsc --noEmit` (без «cannot find module»). Commit: `chore(frontend): remove dead duplicate PeriodSelector (S4-30)`

---

## S4-31 [LOW] Три разных саппорт-адреса: empirik.app, empirik.io, бренд «Полистата»

**Files:**
- Modify: `frontend/src/components/ReconciliationBanner.tsx` (строка 81), `frontend/src/app/onboarding/reconcile/page.tsx` (строки 171, 174), `frontend/src/components/landing/Landing.tsx` (строки 579–580)
- Verify: grep + tsc

**Проблема:** Баннер расхождений/onboarding/reconcile шлют на `support@empirik.app`, лендинг — на `support@empirik.io`. Если `@empirik.app` не читается — юзеры с реальными reconciliation-расхождениями пишут в никуда.

**Interfaces:** Использует `SUPPORT_EMAIL` из `frontend/src/lib/contact.ts`, созданный в S4-28. Выполнять ПОСЛЕ S4-28.

Шаги:
- [ ] Step 1 — проверка: `grep -rn "empirik.app\|empirik.io" frontend/src/components/ReconciliationBanner.tsx frontend/src/app/onboarding/reconcile/page.tsx frontend/src/components/landing/Landing.tsx`.
- [ ] Step 2 — фикс. Импортировать `import { SUPPORT_EMAIL } from '@/lib/contact';` в каждый файл. В `ReconciliationBanner.tsx` строка 81. Before:
```tsx
            href="mailto:support@empirik.app?subject=Расхождение%20в%20reconciliation"
```
  After:
```tsx
            href={`mailto:${SUPPORT_EMAIL}?subject=Расхождение%20в%20reconciliation`}
```
  В `onboarding/reconcile/page.tsx` строки 171, 174 — mailto → `` `mailto:${SUPPORT_EMAIL}...` `` и текст ` support@empirik.app` → `{SUPPORT_EMAIL}`. В `Landing.tsx` строки 579–580 — `hello@empirik.io`/`support@empirik.io` привести к единому: оставить `hello@` для общих, `support@` заменить на `{SUPPORT_EMAIL}` (или оставить empirik.io если он и есть выбранный домен — в этом случае значение константы `support@empirik.io` совпадёт, замена косметическая, но централизует источник).
- [ ] Step 3 — верификация: `grep -rn "empirik.app" frontend/src` → пусто; `cd frontend && npx tsc --noEmit` + `npx vitest run --maxWorkers=1`. Commit: `fix(frontend): route reconciliation/landing support links through SUPPORT_EMAIL (S4-31)`

---

## S4-32 [LOW] Часть виджетов хардкодит «₽» и ru-RU-формат в обход настройки валюты

**Files:**
- Modify: `frontend/src/components/dashboard/RecentTrades.tsx` (строка 116) + StreakIndicator/ActivityCalendar/SetupPerformance/AdvancedMetricsGrid/PnLHealthBadge (хардкод `₽`), `frontend/src/components/dashboard/StatsGrid.tsx` (строка 435 — символ перед числом)
- Test: не требуется строгий — tsc + ручная проверка смены валюты

**Проблема:** `RecentTrades`, `StreakIndicator`, `ActivityCalendar`, `SetupPerformance`, `AdvancedMetricsGrid`, `PnLHealthBadge` хардкодят `toLocaleString('ru-RU') + ' ₽'` → при смене валюты дашборд показывает два знака сразу. `StatsGrid:435` ставит символ ПЕРЕД числом.

Шаги (прокинуть `formatCurrency` из useSettings; фокус — RecentTrades + StatsGrid как в evidence, остальные по тому же паттерну):
- [ ] Step 1 — проверка: `grep -rn "' ₽'\|\" ₽\"\|ru-RU" frontend/src/components/dashboard/RecentTrades.tsx frontend/src/components/dashboard/StatsGrid.tsx`.
- [ ] Step 2 — фикс. В `RecentTrades.tsx` — получить `formatCurrency` из `useSettings()` (если компонент ещё не в контексте — добавить `const { formatCurrency } = useSettings();`) и заменить строку 116. Before:
```tsx
                    {isWin ? '+' : ''}
                    {pnl.toLocaleString('ru-RU', { maximumFractionDigits: 0 })} ₽
```
  After:
```tsx
                    {isWin ? '+' : ''}
                    {formatCurrency(pnl)}
```
  (Убрать ручной `'+'` если `formatCurrency` уже даёт знак; сверить: `formatCurrency` даёт `-` для отрицательных, но не `+` для положительных — оставить `{isWin ? '+' : ''}` перед `{formatCurrency(Math.abs(pnl))}` для win, либо просто `{formatCurrency(pnl)}` и убрать префикс.)
  В `StatsGrid.tsx` строка 435. Before:
```tsx
description={hasData ? `${settings.currencySymbol}${Math.abs(stats?.avg_loss || 0).toFixed(0)}` : ''}
```
  After:
```tsx
description={hasData ? formatCurrency(Math.abs(stats?.avg_loss || 0)) : ''}
```
  Для остальных виджетов (StreakIndicator/ActivityCalendar/SetupPerformance/AdvancedMetricsGrid/PnLHealthBadge) — тем же приёмом заменить хардкод `... ₽` на `formatCurrency(...)`, прокинув его из `useSettings()`. (ActivityCalendar-суммы в клетках оставляют `к`-формат для компактности — там можно оставить число, но заменить `₽` на `settings.currencySymbol`.)
- [ ] Step 3 — верификация: `cd frontend && npx tsc --noEmit` + `npx vitest run --maxWorkers=1`; ручная — сменить валюту в настройках на USD, проверить что дашборд не показывает `₽` и `$` одновременно. Commit: `fix(frontend): use formatCurrency in dashboard widgets instead of hardcoded ₽ (S4-32)`

---

## S4-33 [LOW] Остатки dark-hardcode в светлой теме: text-green-300/red-300 и белые rgba в Heatmap

**Files:**
- Modify: `frontend/src/components/dashboard/ActivityCalendar.tsx` (строка 154), `frontend/src/components/dashboard/AdvancedMetricsGrid.tsx` (строка ~456)
- Verify: ручная в светлой теме

**Проблема:** Light-override в globals.css не покрывает `green-300/red-300` (суммы PnL в клетках календаря) и inline `rgba(255,255,255,0.03)` пустых клеток Heatmap → в светлой теме низкий контраст/невидимые клетки.

Шаги (заменить на CSS-переменные):
- [ ] Step 1 — проверка: `grep -rn "text-green-300\|text-red-300" frontend/src/components/dashboard/ActivityCalendar.tsx` и `grep -rn "rgba(255,255,255" frontend/src/components/dashboard/AdvancedMetricsGrid.tsx`.
- [ ] Step 2 — фикс. В `ActivityCalendar.tsx` строка 154. Before:
```tsx
                  className={`text-[8px] font-mono leading-none mt-0.5 ${
                    b.pnl >= 0 ? 'text-green-300' : 'text-red-300'
                  }`}
```
  After:
```tsx
                  className="text-[8px] font-mono leading-none mt-0.5"
                  style={{ color: b.pnl >= 0 ? 'var(--success)' : 'var(--danger)' }}
```
  (Проверить, что CSS-переменные `--success`/`--danger` определены в globals.css для обеих тем; если имена другие — использовать реальные, напр. `--positive`/`--negative`.)
  В `AdvancedMetricsGrid.tsx` строка ~456. Before:
```tsx
const bg = cell.count === 0 ? "rgba(255,255,255,0.03)" : ...
```
  After:
```tsx
const bg = cell.count === 0 ? "var(--surface-2)" : ...
```
  (Сверить наличие `--surface-2`; если нет — добавить в override-блок globals.css `:root[data-theme=light]` правило для green-300/red-300 как альтернативу.)
- [ ] Step 3 — верификация: `cd frontend && npx tsc --noEmit`; ручная — переключить на светлую тему, календарь: подписи PnL читаемы, пустые клетки heatmap видны. Commit: `fix(frontend): use theme CSS vars for calendar PnL text and empty heatmap cells (S4-33)`

---

## S4-34 [LOW] Любой IntegrityError при создании сделки маскируется под 409 «дубликат»

**Files:**
- Modify: `backend/routers/trades.py` (`create_trade` commit-пути строки 212–216, 228–232)
- Test: `backend/tests/unit/test_trade_integrity_narrow.py` (Create)

**Проблема:** Оба commit-пути ловят `IntegrityError` целиком и отвечают 409 «Такая сделка уже существует». Кроме `uq_trades_dedup_v2` это накроет FK/NOT NULL/CHECK — реальный баг выглядит как «дубликат», в логах нет stacktrace.

Шаги (сузить до имени констрейнта дедупа):
- [ ] Step 1 — падающий тест. Создать `backend/tests/unit/test_trade_integrity_narrow.py`:
```python
import pytest
from sqlalchemy.exc import IntegrityError

from routers import trades as trades_router


def test_non_dedup_integrity_reraised():
    # Хелпер-классификатор: только uq_trades_dedup_v2 → 409, остальное re-raise.
    class _Orig(Exception):
        def __str__(self):
            return 'NOT NULL constraint failed: trades.account_id'
    exc = IntegrityError("stmt", {}, _Orig())
    assert trades_router._is_duplicate_trade_error(exc) is False


def test_dedup_integrity_is_duplicate():
    class _Orig(Exception):
        def __str__(self):
            return 'UNIQUE constraint failed: uq_trades_dedup_v2'
    exc = IntegrityError("stmt", {}, _Orig())
    assert trades_router._is_duplicate_trade_error(exc) is True
```
- [ ] Step 2 — запуск, ожидание FAIL:
  `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_trade_integrity_narrow.py -q`
  Ожидается FAIL: `AttributeError: _is_duplicate_trade_error`.
- [ ] Step 3 — фикс. Добавить классификатор модульного уровня в trades.py:
```python
def _is_duplicate_trade_error(exc) -> bool:
    """True только для dedup-констрейнта — прочие IntegrityError не маскируем под 409."""
    return "uq_trades_dedup_v2" in str(getattr(exc, "orig", exc))
```
  Заменить оба except-блока (строки 214–216 и 230–232). Before (обе):
```python
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="Такая сделка уже существует")
```
  After (обе):
```python
        except IntegrityError as exc:
            db.rollback()
            if _is_duplicate_trade_error(exc):
                raise HTTPException(status_code=409, detail="Такая сделка уже существует")
            log.exception("create_trade: unexpected IntegrityError")
            raise HTTPException(status_code=500, detail="Ошибка сохранения сделки")
```
  Убедиться, что `log` доступен в trades.py (используется в других местах — да).
- [ ] Step 4 — запуск, ожидание PASS:
  `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_trade_integrity_narrow.py -q` → PASS. Прогнать существующий дедуп-тест: `C:/Python314/python.exe -m pytest tests/ -k duplicate -q` (должен остаться зелёным).
- [ ] Step 5 — commit: `fix(trades): narrow duplicate-409 to dedup constraint, re-raise other IntegrityErrors (S4-34)`

---

## S4-35 [LOW] password_reset_tokens / feature_flags / revoked_tokens.user_id без FK — PII-сироты переживают удаление

**Files:**
- Modify: `backend/services/pd_deletion.py` (`finalize_deletion` — добавить чистку токен-таблиц)
- Modify: `backend/models.py` (комментарий-обоснование у трёх таблиц: строки 763, 790, 932)
- Test: `backend/tests/unit/test_pd_deletion_orphans.py` (Create)

**Проблема:** `password_reset_tokens.user_id` (936), `feature_flags.user_id` (790), `revoked_tokens.user_id` (763) — просто `Integer` без FK/ondelete → после удаления юзера остаются строки с `user_id` и `requester_ip` (PII) в `password_reset_tokens`.

**Interfaces:** Та же функция `finalize_deletion`, что S4-01 и S4-24. Выбран путь «чистка при 152-ФЗ-удалении» (без миграции FK — безопаснее перед релизом), как предлагает сам finding.

Шаги:
- [ ] Step 1 — падающий тест. Создать `backend/tests/unit/test_pd_deletion_orphans.py`:
```python
from datetime import datetime, timedelta

import models
from services import pd_deletion


def test_finalize_deletes_token_orphans(db_session):
    user = models.User(email="orph@x.com", hashed_password="x", is_active=1)
    db_session.add(user)
    db_session.flush()
    db_session.add(models.PasswordResetTokenORM(
        token="t1", user_id=user.id, created_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=1), requester_ip="1.2.3.4",
    ))
    db_session.add(models.FeatureFlagORM(user_id=user.id, flag_name="mae-mfe-beta", enabled=True))
    db_session.add(models.RevokedTokenORM(
        jti="j1", user_id=user.id, revoked_at=datetime.utcnow(),
        expires_at=datetime.utcnow() + timedelta(hours=1),
    ))
    db_session.commit()

    pd_deletion.finalize_deletion(db_session, user)

    assert db_session.query(models.PasswordResetTokenORM).filter_by(user_id=user.id).count() == 0
    assert db_session.query(models.FeatureFlagORM).filter_by(user_id=user.id).count() == 0
    assert db_session.query(models.RevokedTokenORM).filter_by(user_id=user.id).count() == 0
```
  Сверить реальные имена ORM-классов (`RevokedTokenORM`? — открыть models.py класс `revoked_tokens`, использовать фактическое имя класса).
- [ ] Step 2 — запуск, ожидание FAIL:
  `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_pd_deletion_orphans.py -q`
  Ожидается FAIL: строки остаются (count != 0).
- [ ] Step 3 — фикс. В `finalize_deletion` перед финальным `db.commit()` (перед строкой 201 `user.is_active = 0`) добавить чистку сирот:
```python
    # 152-ФЗ: удаляем PII-сироты в таблицах без FK на users (user_id/requester_ip).
    db.query(models.PasswordResetTokenORM).filter(
        models.PasswordResetTokenORM.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(models.FeatureFlagORM).filter(
        models.FeatureFlagORM.user_id == user_id
    ).delete(synchronize_session=False)
    db.query(models.RevokedTokenORM).filter(
        models.RevokedTokenORM.user_id == user_id
    ).delete(synchronize_session=False)
```
  (Использовать реальные имена классов из models.py.) В `models.py` добавить комментарий-обоснование намеренного отсутствия FK у трёх таблиц (строки 763, 790, 932), например у `revoked_tokens.user_id`:
```python
    user_id = Column(Integer, nullable=False, index=True)  # без FK: чистится в pd_deletion.finalize_deletion (152-ФЗ)
```
- [ ] Step 4 — запуск, ожидание PASS:
  `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_pd_deletion_orphans.py -q` → PASS.
- [ ] Step 5 — commit: `fix(152-fz): purge password_reset/feature_flag/revoked_token orphans on deletion (S4-35)`

---

## Проверка спринта

Полный релиз-гейт (запускать после закрытия всех 35 задач):

1. **Backend unit + integration** (из `backend/`):
   `C:/Python314/python.exe -m pytest tests/unit tests/integration -q`
   Зелёно, кроме известного флейка `test_debug_warning` + `test_market_service_async::test_get_client_returns_singleton` (падают только в полном прогоне).

2. **Импорт backend:** `C:/Python314/python.exe -c "import main"` — без ошибок.

3. **Миграции против Postgres 16** (реальный контейнер, не SQLite):
   `DATABASE_URL=postgresql://... alembic upgrade head` → `alembic downgrade base` → `alembic upgrade head` → `alembic check` = `No new upgrade operations detected` (S4-18 + S4-19 закрыты).

4. **Frontend:** `cd frontend && npx tsc --noEmit` (0 ошибок) + `npx vitest run --maxWorkers=1` (зелёно).

5. **CI-конфиг:** `ci.yml` триггерится на `feat/rebrand-empirik`, шаг `alembic check` без `continue-on-error` (после S4-19).

6. **nginx:** `nginx -t` ok; `curl http://localhost/api/landing/ticker` через прокси → 200 (S4-08).

7. **Grep-чистота dead-code:** `grep -rn "TrialEndedDialog\|SubscriptionProvider\|PeriodSelector\|empirik.app\|atom_support_bot" frontend/src` → пусто (S4-12/S4-30/S4-28/S4-31).

8. **Ручной сквозной проход** (playwright, backend :8000 + `npm run dev -- -p 3001`): register → verify-email UI → login → onboarding → broker connect → первый sync (не обрывается на 15с, S4-02) → тема переживает re-login (S4-26) → logout (POST /auth/logout завершается, S4-15).
