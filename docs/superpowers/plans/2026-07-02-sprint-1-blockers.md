# Sprint 1 — Блокеры (CRITICAL + деньги + фиктивная 2FA + сломанный core-UX) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Закрыть все блокеры релиза «Полистата»: CRITICAL path-traversal и alembic-32, денежную refund-логику, фиктивную 2FA, broker-401→logout, сломанные скриншоты, edit-trade 422 и тупик восстановления пароля.

**Architecture:** Точечные фиксы по существующему коду FastAPI-роутеров, SQLAlchemy-моделей и Next.js-компонентов; каждая задача изолирована и имеет собственный тест-цикл. Денежные и security-задачи идут полным TDD (red→green), фронтовые UX-задачи — компактным циклом с реальным кодом и ручной/vitest-проверкой.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Alembic + Pydantic v2 (SQLite dev / PostgreSQL prod); Next.js 16 + React 19 + Tailwind v4 + TanStack Query; pytest / vitest / playwright.

## Global Constraints

- Python: `C:/Python314/python.exe` (зависимости там). Тесты бэка из `backend/`: `C:/Python314/python.exe -m pytest tests/... -q`
- Backend уже запущен на `http://localhost:8000` (GET-смоук можно, мутации прод-данных нельзя).
- Frontend: `cd frontend && npx vitest run --maxWorkers=1` (ТОЛЬКО `maxWorkers=1`) + `npx tsc --noEmit`. E2E: playwright, backend :8000 + `npm run dev -- -p 3001`, при lock-ошибке убить `next dev` + удалить `frontend/.next/dev/lock`.
- Миграции: врем. БД `DATABASE_URL=sqlite:///./_audit_tmp.db`, НИКОГДА не трогать `backend/atom.db`. Перед релизом — Postgres 16.
- Git: новый коммит на задачу (не amend), ветка `feat/rebrand-empirik`, формат `fix(область): что (SN-XX)`. Не пушить/мержить.
- Инварианты: ADR-0007 (P&L), SYNC-08 (курсор после всех стадий), MATH-01 (net_pnl не gross). Читать `docs/PNL_PLAYBOOK.md` для P&L-задач.
- Флейк (не регрессия): `test_debug_warning` + `test_market_service_async::test_get_client_returns_singleton` падают только в полном прогоне.

---

### S1-01 [CRITICAL] Arbitrary file deletion через DELETE /trades/{id}/screenshot (path traversal)

**Files:**
- Modify: `backend/routers/trades.py:1035-1041` (delete_screenshot) и `backend/schemas.py:324-352` (TradeUpdate — убрать `screenshot_url`)
- Test: `backend/tests/test_screenshot_delete_traversal.py` (Create)

**Проблема:** `delete_screenshot` строит путь напрямую из user-settable `trade.screenshot_url` (`Path(trade.screenshot_url.lstrip("/"))`) и вызывает `.unlink()`. Через `PATCH /trades/{id}` с `screenshot_url='../../atom.db'` атакующий удаляет произвольный файл. `get_screenshot` (строки 927-932) уже хардненнут basename+`is_relative_to`, а DELETE забыли.

**Interfaces:**
- Consumes: `UPLOAD_DIR = Path("uploads/screenshots")` (trades.py:895), `import os` (trades.py:891), `from pathlib import Path` (trades.py:893) — уже импортированы в модуле.
- Produces: закрытый DELETE-эндпоинт; `TradeUpdate` без поля `screenshot_url`. S1-03/S1-12 (скриншоты) полагаются на то, что `screenshot_url` задаётся ТОЛЬКО через `upload_screenshot`.

- [ ] **Step 1: Написать падающий тест**

```python
# backend/tests/test_screenshot_delete_traversal.py
"""SEC (CRITICAL): path traversal в DELETE /trades/{id}/screenshot.

update_trade делает слепой setattr для exclude_unset полей, а delete_screenshot
строил путь из user-controlled screenshot_url без containment. Комбинация =
произвольное удаление файла относительно cwd воркера.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from pathlib import Path

import pytest

import models
from routers import trades as trades_router


@pytest.mark.asyncio
async def test_delete_screenshot_does_not_traverse(db_session, tmp_path, monkeypatch):
    # Файл-жертва вне UPLOAD_DIR (эмулируем atom.db в cwd воркера).
    victim = tmp_path / "victim.db"
    victim.write_bytes(b"critical data")

    acc = models.Account(user_id=1, name="A", initial_balance=0, currency="RUB")
    db_session.add(acc)
    db_session.commit()
    db_session.refresh(acc)

    trade = models.Trade(
        account_id=acc.id, symbol="SBER",
        direction=models.TradeDirection.LONG,
        entry_price=300.0, quantity=1, entry_at=datetime.now(),
        # user-controlled traversal-значение
        screenshot_url=f"/../../{victim.name}",
    )
    db_session.add(trade)
    db_session.commit()
    db_session.refresh(trade)

    # Подменяем cwd так, чтобы lstrip('/')-путь указывал на victim.
    monkeypatch.chdir(tmp_path / "uploads" / "screenshots" if False else tmp_path)

    user = models.User(id=1, email="u@e.com", is_active=1, settings={})

    class _FakeAuth:
        @staticmethod
        def get_account_id(db, u):
            return acc.id

    monkeypatch.setattr(trades_router, "auth_service", _FakeAuth)

    await trades_router.delete_screenshot(trade.id, db=db_session, current_user=user)

    # Фикс не должен удалять файл вне UPLOAD_DIR.
    assert victim.exists(), "path traversal: файл вне UPLOAD_DIR был удалён"
```

- [ ] **Step 2: Прогнать тест — ожидать FAIL**

Run: `cd backend && C:/Python314/python.exe -m pytest tests/test_screenshot_delete_traversal.py -q`
Expected: FAIL — `assert victim.exists()` падает (файл удалён traversal-путём).

- [ ] **Step 3: Минимальный фикс**

В `backend/routers/trades.py` заменить тело `if trade.screenshot_url:` в `delete_screenshot`:

Before (`trades.py:1035-1041`):
```python
    if trade.screenshot_url:
        # Удаляем файл
        filepath = Path(trade.screenshot_url.lstrip("/"))
        if filepath.exists():
            filepath.unlink()
        trade.screenshot_url = None
        db.commit()
```

After:
```python
    if trade.screenshot_url:
        # SEC: тот же containment, что в get_screenshot — берём только basename
        # и проверяем, что resolved path внутри UPLOAD_DIR, иначе не трогаем ФС.
        filename = os.path.basename(trade.screenshot_url)
        filepath = UPLOAD_DIR / filename
        if (
            filepath.resolve().is_relative_to(UPLOAD_DIR.resolve())
            and filepath.is_file()
        ):
            filepath.unlink()
        trade.screenshot_url = None
        db.commit()
```

Затем убрать поле из `backend/schemas.py` — удалить строку 339 в классе `TradeUpdate`:

Before (`schemas.py:339`):
```python
    screenshot_url: Optional[str] = None
```

After: (строку удалить целиком — `screenshot_url` больше не user-settable через PATCH; задаётся только `upload_screenshot`).

- [ ] **Step 4: Прогнать тест — ожидать PASS**

Run: `cd backend && C:/Python314/python.exe -m pytest tests/test_screenshot_delete_traversal.py -q`
Expected: PASS. Затем `C:/Python314/python.exe -m pytest tests/test_trades.py -q` — зелёный (регрессия update_trade).

- [ ] **Step 5: Commit**

```bash
git add backend/routers/trades.py backend/schemas.py backend/tests/test_screenshot_delete_traversal.py
git commit -m "fix(trades): containment в delete_screenshot + убрать screenshot_url из TradeUpdate (S1-01)"
```

---

### S1-02 [CRITICAL] Revision id 0023 (34 симв.) не влезает в alembic_version VARCHAR(32) — прод-миграция упадёт

**Files:**
- Modify: `backend/alembic/versions/0023_position_authoritative_fields.py:37` (revision), переименование файла
- Modify: `backend/alembic/versions/0024_trade_point_value_snapshot.py:39` (down_revision)
- Modify: `docs/RUNBOOK.md` (рецепт для застампленных dev/stage БД)
- Test: ручная проверка `alembic upgrade head` против врем. SQLite + верификация длины ≤32

**Проблема:** `revision = "0023_position_authoritative_fields"` = 34 символа. Alembic создаёт `alembic_version.version_num` как `String(32)`; PostgreSQL строго enforce'ит длину → `22001 value too long` на шаге 0022→0023, backend не стартует (main.py `_check_alembic_head`). На SQLite не проверяется — потому dev зелёный.

**Interfaces:**
- Consumes: цепочка `0022_trade_fee_breakdown → 0023 → 0024_trade_point_value_snapshot`.
- Produces: revision id `0023_position_auth_fields` (25 символов), на который ссылается `0024.down_revision`.

- [ ] **Step 1: Проверка-репро длины (ожидать FAIL)**

Run:
```bash
cd backend && C:/Python314/python.exe -c "r='0023_position_authoritative_fields'; print(len(r)); assert len(r) <= 32, 'слишком длинно для alembic_version VARCHAR(32)'"
```
Expected: печатает `34`, затем AssertionError — id не влезает.

- [ ] **Step 2: Фикс — переименовать revision в ≤32 символа**

В `backend/alembic/versions/0023_position_authoritative_fields.py`:

Before (`:37`):
```python
revision: str = "0023_position_authoritative_fields"
```
After:
```python
revision: str = "0023_position_auth_fields"
```

В `backend/alembic/versions/0024_trade_point_value_snapshot.py`:

Before (`:39`):
```python
down_revision: Union[str, Sequence[str], None] = "0023_position_authoritative_fields"
```
After:
```python
down_revision: Union[str, Sequence[str], None] = "0023_position_auth_fields"
```

Переименовать файл (имя файла — не revision id, но держим согласованным):
```bash
cd backend && git mv alembic/versions/0023_position_authoritative_fields.py alembic/versions/0023_position_auth_fields.py
```

Добавить в `docs/RUNBOOK.md` (в раздел про alembic/миграции) рецепт для уже застампленных dev/stage БД:
```markdown
### Ре-стамп после переименования 0023 (S1-02)
Если dev/stage БД застамплена на старый id `0023_position_authoritative_fields`
(alembic upgrade head падает "Can't locate revision"):
```sql
UPDATE alembic_version SET version_num='0023_position_auth_fields'
 WHERE version_num='0023_position_authoritative_fields';
```
Затем `alembic upgrade head`.
```

- [ ] **Step 3: Верификация — чистый upgrade head против врем. SQLite + длина ≤32**

Run:
```bash
cd backend && DATABASE_URL=sqlite:///./_audit_tmp.db C:/Python314/python.exe -m alembic upgrade head
DATABASE_URL=sqlite:///./_audit_tmp.db C:/Python314/python.exe -c "import sqlite3; c=sqlite3.connect('_audit_tmp.db'); v=c.execute('SELECT version_num FROM alembic_version').fetchone()[0]; print(v, len(v)); assert len(v)<=32; assert '0023_position_authoritative_fields' not in v"
rm -f _audit_tmp.db
```
Expected: upgrade head без ошибок; печатает head-revision и его длину (≤32); ассерты проходят. Затем убедиться, что `git grep -n "0023_position_authoritative_fields" backend/` пуст.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/ docs/RUNBOOK.md
git commit -m "fix(alembic): revision 0023 <=32 символов для Postgres alembic_version (S1-02)"
```

---

### S1-03 [HIGH] Скриншоты сделок сломаны: static /uploads удалён, фронт грузит старые URL (backend-часть)

**Files:**
- Modify: `backend/routers/trades.py:1011` (upload_screenshot — вернуть путь эндпоинта) ИЛИ оставить хранение как есть и решать на фронте (S1-12)
- Test: `backend/tests/test_screenshot_endpoint_contract.py` (Create)

**Проблема:** IDOR-фикс удалил `app.mount("/uploads", ...)` (main.py:392) и добавил authenticated `GET /trades/{id}/screenshot`, но бэк по-прежнему хранит и отдаёт `screenshot_url='/uploads/screenshots/<file>'` (trades.py:1011), а nginx `/uploads` не проксирует. Итог: 100% скриншотов — 404.

**Interfaces:**
- Consumes: `GET /trades/{trade_id}/screenshot` (trades.py:900, authenticated, ownership-checked, отдаёт FileResponse).
- Produces: контракт — фронт (S1-12) строит URL как `${getApiUrl('')}/trades/${trade.id}/screenshot`. Backend продолжает хранить `screenshot_url` как флаг наличия (`/uploads/screenshots/<file>`) — фронт НЕ использует значение как URL, только проверяет truthiness. Эта задача фиксирует контракт тестом; правка URL — на фронте (S1-12). Зависит от S1-01 (screenshot_url больше не user-settable).

- [ ] **Step 1: Написать тест-контракт (ожидать PASS уже сейчас — фиксируем инвариант)**

```python
# backend/tests/test_screenshot_endpoint_contract.py
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
```

- [ ] **Step 2: Прогнать тест**

Run: `cd backend && C:/Python314/python.exe -m pytest tests/test_screenshot_endpoint_contract.py -q`
Expected: PASS (mount уже удалён, эндпоинт зарегистрирован). Если `test_trade_screenshot_route_registered` даёт 404 — эндпоинт не подключён, разбираться до фронт-правки.

- [ ] **Step 3: Верификация live-смоук + commit**

Run (GET-смоук, backend :8000):
```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/uploads/screenshots/x.png   # ожидаем 404
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/trades/1/screenshot          # ожидаем 401
```

```bash
git add backend/tests/test_screenshot_endpoint_contract.py
git commit -m "test(trades): контракт screenshot-эндпоинта для фронт-миграции (S1-03)"
```

---

### S1-04 [HIGH] Refund больше не деактивирует подписку: idempotency-замок глотает refund.succeeded

**Files:**
- Modify: `backend/routers/payments.py:295-310` (webhook — IntegrityError-ветка)
- Test: `backend/tests/test_webhook_idempotency.py` (добавить refund-сценарий)

**Проблема:** Для `refund.succeeded` `payment_id` мапится на ОРИГИНАЛЬНЫЙ `payment.id` (payments.py:251), по которому строка `payment_attempts` уже есть → `INSERT` бьёт по `UNIQUE(external_id)` → `IntegrityError` → ранний `return {ok, idempotent}` (payments.py:297-300), и `_deactivate_subscription` (payments.py:306) недостижим. Юзеру вернули деньги — Pro остаётся активным.

**Interfaces:**
- Consumes: `PaymentAttemptORM.external_id` UNIQUE (models.py:907), поле `status` (models.py); `_deactivate_subscription(db, user, payment_id)` (payments.py:366). Тест-фикстуры `_make_user`, `test_app` из `tests/test_webhook_idempotency.py`.
- Produces: при IntegrityError — перечитывание существующей строки и, если её `status != target_status`, обновление статуса + выполнение действия. S1-10/S1-11 (refund scoping/lookup) полагаются на то, что после этой правки refund-ветка реально доходит до `_deactivate_subscription`.

- [ ] **Step 1: Написать падающий тест (refund после succeeded деактивирует подписку)**

Добавить в `backend/tests/test_webhook_idempotency.py` в класс `TestWebhookIdempotency`:

```python
    def test_refund_after_succeeded_deactivates_subscription(self, test_app):
        """succeeded-webhook активирует Pro; refund.succeeded по тому же payment_id
        деактивирует подписку. Раньше idempotency-замок глотал refund (IntegrityError
        на уже существующем external_id) и _deactivate_subscription не вызывался.
        """
        db = test_app["db"]
        user, _ = _make_user(db)
        client = test_app["client"]

        # 1. Активация (real YooKassa формат — refund придёт тоже в нём).
        r1 = client.post("/payments/webhook", json={
            "event": "payment.succeeded",
            "object": {
                "id": "pmt-refund-1",
                "status": "succeeded",
                "amount": {"value": "399.00"},
                "metadata": {"user_id": str(user.id), "plan": "pro"},
            },
        })
        assert r1.status_code == 200, r1.text
        sub = db.query(Subscription).filter(Subscription.user_id == user.id).one()
        assert sub.is_active == 1

        # 2. Refund по тому же исходному платежу.
        r2 = client.post("/payments/webhook", json={
            "event": "refund.succeeded",
            "object": {
                "id": "rfnd-1",
                "payment_id": "pmt-refund-1",
                "status": "succeeded",
                "amount": {"value": "399.00"},
                "metadata": {"user_id": str(user.id), "plan": "pro"},
            },
        })
        assert r2.status_code == 200, r2.text

        db.expire_all()
        subs = db.query(Subscription).filter(Subscription.user_id == user.id).all()
        assert all(s.is_active == 0 for s in subs), "refund должен деактивировать подписку"
        pmt = db.query(Payment).filter(Payment.external_id == "pmt-refund-1").one()
        assert pmt.status == PaymentStatus.REFUNDED
```

- [ ] **Step 2: Прогнать — ожидать FAIL**

Run: `cd backend && C:/Python314/python.exe -m pytest tests/test_webhook_idempotency.py::TestWebhookIdempotency::test_refund_after_succeeded_deactivates_subscription -q`
Expected: FAIL — `sub.is_active` остаётся 1 (замок проглотил refund).

- [ ] **Step 3: Минимальный фикс IntegrityError-ветки**

В `backend/routers/payments.py` заменить блок `try/except IntegrityError`:

Before (`payments.py:295-300`):
```python
        try:
            db.flush()  # бьёт по UNIQUE(external_id) немедленно — захват замка
        except IntegrityError:
            db.rollback()
            log.info("payment_webhook: idempotent replay payment_id=%s status=%s", payment_id, target_status)
            return {"ok": True, "idempotent": True}
```

After:
```python
        try:
            db.flush()  # бьёт по UNIQUE(external_id) немедленно — захват замка
        except IntegrityError:
            db.rollback()
            # Замок уже взят прошлым webhook'ом. Идемпотентный выход ТОЛЬКО если
            # статус совпадает. Для смены статуса (succeeded→refunded по тому же
            # external_id) — пропускаем действие дальше, замок не перевставляем.
            existing = (
                db.query(attempt_attr)
                .filter(attempt_attr.external_id == payment_id)
                .first()
            )
            if existing is not None and existing.status == target_status:
                log.info("payment_webhook: idempotent replay payment_id=%s status=%s", payment_id, target_status)
                return {"ok": True, "idempotent": True}
            if existing is not None:
                existing.status = target_status
                db.flush()
            log.info("payment_webhook: status transition payment_id=%s -> %s", payment_id, target_status)
```

- [ ] **Step 4: Прогнать — ожидать PASS**

Run: `cd backend && C:/Python314/python.exe -m pytest tests/test_webhook_idempotency.py -q`
Expected: PASS (новый refund-тест + существующие идемпотентность-тесты зелёные).

- [ ] **Step 5: Commit**

```bash
git add backend/routers/payments.py backend/tests/test_webhook_idempotency.py
git commit -m "fix(payments): refund.succeeded не должен глотаться idempotency-замком (S1-04)"
```

---

### S1-05 [HIGH] 401 от broker-эндпоинтов при невалидном T-Bank токене принудительно разлогинивает юзера

**Files:**
- Modify: `backend/routers/broker.py:443`, `backend/routers/broker.py:778`, `backend/routers/real_pnl.py:87`
- Test: `backend/tests/test_broker_token_status_code.py` (Create)

**Проблема:** `broker.py:443/778` и `real_pnl.py:87` отдают `HTTPException(401)` при невалидном БРОКЕРСКОМ токене. `apiClient.ts:194-217` на любой не-auth 401 делает refresh→retry→`clearAuthTokens()`+`dispatchEvent('auth:logout')`, что `AuthContext.tsx:157` превращает в полный logout. `PortfolioCard` дёргает `/broker/portfolio` на дашборде → юзер с протухшим T-Bank токеном выброшен на login.

**Interfaces:**
- Consumes: существующий в этом же файле паттерн `410` («Подключение брокера повреждено», real_pnl.py:80) и `502/424` для внешних сбоев.
- Produces: broker-token ошибки отдают `424 Failed Dependency` (внешняя зависимость — брокер — недоступна/невалидна), НЕ 401. Фронт (apiClient) НЕ разлогинивает на 424. Резервируем 401 только за сессионной аутентификацией.

- [ ] **Step 1: Написать падающий тест**

```python
# backend/tests/test_broker_token_status_code.py
"""401 зарезервирован за сессионной auth. Ошибка БРОКЕРСКОГО токена (TokenInvalid)
не должна отдавать 401 — иначе apiClient разлогинивает юзера из приложения.
Проверяем, что все три места отдают 424 (Failed Dependency), а не 401.
"""
import ast
import os
import re

BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _token_invalid_status_codes(path):
    src = open(path, encoding="utf-8").read()
    codes = []
    # находим except TokenInvalid: ... raise HTTPException(status_code=NNN
    for m in re.finditer(r"except\s+TokenInvalid\s*:(.+?)(?=\n\s*except|\n\s*return|\n@|\Z)", src, re.S):
        block = m.group(1)
        for c in re.finditer(r"status_code=(\d+)", block):
            codes.append(int(c.group(1)))
    return codes


def test_broker_token_invalid_uses_424_not_401():
    for rel in ("routers/broker.py", "routers/real_pnl.py"):
        codes = _token_invalid_status_codes(os.path.join(BASE, rel))
        assert codes, f"не нашёл except TokenInvalid в {rel}"
        assert all(c == 424 for c in codes), f"{rel}: TokenInvalid отдаёт {codes}, ожидался только 424"
```

- [ ] **Step 2: Прогнать — ожидать FAIL**

Run: `cd backend && C:/Python314/python.exe -m pytest tests/test_broker_token_status_code.py -q`
Expected: FAIL — коды `[401]` вместо `[424]`.

- [ ] **Step 3: Заменить 401 на 424 в трёх местах**

`backend/routers/broker.py:443`:
Before:
```python
    except TokenInvalid:
        raise HTTPException(status_code=401, detail="Токен невалиден или отозван")
```
After:
```python
    except TokenInvalid:
        raise HTTPException(status_code=424, detail="Токен брокера невалиден или отозван")
```

`backend/routers/broker.py:777-778`:
Before:
```python
    except TokenInvalid:
        raise HTTPException(status_code=401, detail="Токен невалиден")
```
After:
```python
    except TokenInvalid:
        raise HTTPException(status_code=424, detail="Токен брокера невалиден")
```

`backend/routers/real_pnl.py:86-87`:
Before:
```python
    except TokenInvalid:
        raise HTTPException(status_code=401, detail="Токен невалиден")
```
After:
```python
    except TokenInvalid:
        raise HTTPException(status_code=424, detail="Токен брокера невалиден")
```

- [ ] **Step 4: Прогнать — ожидать PASS**

Run: `cd backend && C:/Python314/python.exe -m pytest tests/test_broker_token_status_code.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/broker.py backend/routers/real_pnl.py backend/tests/test_broker_token_status_code.py
git commit -m "fix(broker): broker-token TokenInvalid -> 424 вместо 401 (не разлогинивать) (S1-05)"
```

---

### S1-06 [HIGH] 2FA (TOTP) включается, но никогда не проверяется при входе — защита фиктивна

**Files:**
- Modify: `backend/schemas.py:118-121` (UserLogin — добавить `totp_code`), `backend/routers/auth.py:108-141` (login — проверка TOTP)
- Test: `backend/tests/test_login_2fa.py` (Create)

**Проблема:** `/2fa/enable|verify|disable` выставляют `user.totp_enabled=True` (auth.py:505), но `login()` (auth.py:116-132) и `authenticate_user()` (auth_service.py:404-442) нигде не читают `totp_enabled`/`totp_secret` и не требуют код. Вход по одному паролю независимо от 2FA.

**Interfaces:**
- Consumes: `models.User.totp_enabled` (Boolean, models.py:44), `models.User.totp_secret` (String, models.py:43), `verify_code(secret, code) -> bool` (services/totp_service.py:50). `authenticate_user(db, email, password) -> Optional[User]` (auth_service.py:404).
- Produces: `UserLogin.totp_code: Optional[str]`. `login()` при `user.totp_enabled` требует валидный `totp_code`, иначе 401 (без выдачи токенов).

- [ ] **Step 1: Написать падающие тесты**

```python
# backend/tests/test_login_2fa.py
"""2FA-enforcement на входе. При totp_enabled логин без валидного кода = 401,
финальная пара токенов не выдаётся. Без 2FA — вход как раньше.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DEBUG", "true")

from main import app
from models import Base, User
from database import get_db
import auth_service


@pytest.fixture()
def app_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TS = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def _override():
        db = TS()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override
    db = TS()
    yield TestClient(app), db
    db.close()
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


def _user(db, enabled, secret=None):
    u = User(
        email="a@b.com", name="A",
        hashed_password=auth_service.get_password_hash("password12345"),
        is_active=1, settings={},
        totp_enabled=enabled, totp_secret=secret,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def test_login_without_2fa_succeeds(app_db):
    client, db = app_db
    _user(db, enabled=False)
    r = client.post("/auth/login", json={"email": "a@b.com", "password": "password12345"})
    assert r.status_code == 200, r.text


def test_login_with_2fa_missing_code_rejected(app_db):
    client, db = app_db
    secret = pyotp.random_base32()
    _user(db, enabled=True, secret=secret)
    r = client.post("/auth/login", json={"email": "a@b.com", "password": "password12345"})
    assert r.status_code == 401, r.text


def test_login_with_2fa_valid_code_succeeds(app_db):
    client, db = app_db
    secret = pyotp.random_base32()
    _user(db, enabled=True, secret=secret)
    code = pyotp.TOTP(secret).now()
    r = client.post("/auth/login", json={"email": "a@b.com", "password": "password12345", "totp_code": code})
    assert r.status_code == 200, r.text
```

- [ ] **Step 2: Прогнать — ожидать FAIL**

Run: `cd backend && C:/Python314/python.exe -m pytest tests/test_login_2fa.py -q`
Expected: FAIL — `test_login_with_2fa_missing_code_rejected` даёт 200 вместо 401 (2FA не проверяется); возможно `test_login_with_2fa_valid_code_succeeds` падает на неизвестном поле `totp_code`.

- [ ] **Step 3: Реализация**

`backend/schemas.py:118-121` — добавить поле:
Before:
```python
class UserLogin(BaseModel):
    """Схема для входа"""
    email: EmailStr
    password: str
```
After:
```python
class UserLogin(BaseModel):
    """Схема для входа"""
    email: EmailStr
    password: str
    totp_code: Optional[str] = None
```

`backend/routers/auth.py` — в `login()` после проверки `is_active` (после строки 128, перед выдачей токенов на строке 131) вставить:
```python
    # 2FA-enforcement: если у юзера включён TOTP, финальную пару токенов не
    # выдаём до проверки 6-значного кода. Резервируем 401 для auth-провала.
    if user.totp_enabled:
        from services.totp_service import verify_code
        if not user_data.totp_code or not verify_code(user.totp_secret, user_data.totp_code):
            raise HTTPException(
                status_code=401,
                detail="Требуется код двухфакторной аутентификации",
            )
```

- [ ] **Step 4: Прогнать — ожидать PASS**

Run: `cd backend && C:/Python314/python.exe -m pytest tests/test_login_2fa.py -q`
Expected: PASS (все три теста).

- [ ] **Step 5: Commit**

```bash
git add backend/schemas.py backend/routers/auth.py backend/tests/test_login_2fa.py
git commit -m "fix(auth): проверять TOTP-код на входе при totp_enabled (S1-06)"
```

---

### S1-07 [HIGH] Восстановление пароля — тупик: нет /auth/reset-password и «Забыли пароль?»

**Files:**
- Create: `frontend/src/app/auth/reset-password/page.tsx`
- Modify: `frontend/src/app/login/page.tsx` (ссылка «Забыли пароль?»)
- Test: `frontend/src/app/auth/reset-password/page.test.tsx` (Create, vitest)

**Проблема:** Backend полностью реализует reset-флоу (`POST /auth/password-reset/request` + `/confirm`, auth.py:613) и шлёт письмо со ссылкой `{PUBLIC_URL}/auth/reset-password?token=...` (auth.py:599). Во фронте страницы `/auth/reset-password` нет (ссылка из письма → 404), а на login нет «Забыли пароль?».

**Interfaces:**
- Consumes: `POST /auth/password-reset/confirm` — тело `{token: string, new_password: string}` (schemas.py:204, `new_password` min 12), ответы 400 при `недействительна/истекла`. `POST /auth/password-reset/request` — тело `{email: string}` (schemas.py:199). `api` из `@/lib/apiClient`, `ApiError`.
- Produces: страница `/auth/reset-password?token=...` (форма нового пароля ×2 + POST confirm + обработка 400) и ссылка на login.

- [ ] **Step 1: Написать vitest на страницу (ожидать FAIL — файла нет)**

```tsx
// frontend/src/app/auth/reset-password/page.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams('token=tok123'),
  useRouter: () => ({ push: vi.fn() }),
}));

const post = vi.fn().mockResolvedValue({});
vi.mock('@/lib/apiClient', () => ({
  api: { post: (...a: unknown[]) => post(...a) },
  ApiError: class ApiError extends Error { constructor(public status: number, message: string) { super(message); } },
}));

import ResetPasswordPage from './page';

describe('ResetPasswordPage', () => {
  it('шлёт new_password и token в /auth/password-reset/confirm', async () => {
    render(<ResetPasswordPage />);
    const inputs = screen.getAllByLabelText(/пароль/i);
    fireEvent.change(inputs[0], { target: { value: 'newpassword1234' } });
    fireEvent.change(inputs[1], { target: { value: 'newpassword1234' } });
    fireEvent.click(screen.getByRole('button', { name: /сохранить|сбросить|обновить/i }));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith('/auth/password-reset/confirm', {
        body: { token: 'tok123', new_password: 'newpassword1234' },
        noAuth: true,
      }),
    );
  });

  it('показывает ошибку при несовпадении паролей', async () => {
    render(<ResetPasswordPage />);
    const inputs = screen.getAllByLabelText(/пароль/i);
    fireEvent.change(inputs[0], { target: { value: 'newpassword1234' } });
    fireEvent.change(inputs[1], { target: { value: 'other12345678' } });
    fireEvent.click(screen.getByRole('button', { name: /сохранить|сбросить|обновить/i }));
    await waitFor(() => expect(screen.getByText(/не совпадают/i)).toBeInTheDocument());
    expect(post).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Прогнать — ожидать FAIL**

Run: `cd frontend && npx vitest run --maxWorkers=1 src/app/auth/reset-password/page.test.tsx`
Expected: FAIL — модуль `./page` не найден.

- [ ] **Step 3: Создать страницу**

```tsx
// frontend/src/app/auth/reset-password/page.tsx
'use client';

import { useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { api, ApiError } from '@/lib/apiClient';
import { Button, Input } from '@/components/ui';

export default function ResetPasswordPage() {
  const router = useRouter();
  const token = useSearchParams().get('token') ?? '';

  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (password !== confirm) {
      setError('Пароли не совпадают');
      return;
    }
    if (password.length < 12) {
      setError('Пароль должен быть минимум 12 символов');
      return;
    }
    setLoading(true);
    try {
      await api.post('/auth/password-reset/confirm', {
        body: { token, new_password: password },
        noAuth: true,
      });
      setDone(true);
      setTimeout(() => router.push('/login'), 1500);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Не удалось сбросить пароль');
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <main className="min-h-screen flex items-center justify-center p-6">
        <div className="cyber-card p-8 max-w-[420px] text-center">
          <p className="text-[var(--danger)]">Ссылка недействительна — токен отсутствует.</p>
          <Link href="/login" className="text-[var(--accent)] mt-4 inline-block">← На страницу входа</Link>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen flex items-center justify-center p-6">
      <div className="cyber-card p-8 w-full max-w-[420px]">
        <h1 className="text-2xl font-bold mb-6">Новый пароль</h1>
        {done ? (
          <p className="text-[var(--success)]">Пароль обновлён. Перенаправляем на вход…</p>
        ) : (
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            {error && (
              <div className="px-3 py-2.5 rounded-[var(--radius-md)] bg-[var(--danger-soft)] text-[var(--danger)] text-sm">
                {error}
              </div>
            )}
            <Input
              label="Новый пароль"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="new-password"
            />
            <Input
              label="Повторите пароль"
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              autoComplete="new-password"
            />
            <Button type="submit" size="lg" fullWidth loading={loading}>
              Сохранить
            </Button>
          </form>
        )}
        <div className="mt-6 text-center">
          <Link href="/login" className="text-sm text-[var(--text-tertiary)] hover:text-[var(--foreground)]">
            ← На страницу входа
          </Link>
        </div>
      </div>
    </main>
  );
}
```

Добавить ссылку «Забыли пароль?» в `frontend/src/app/login/page.tsx` — после блока поля пароля (после закрывающего `/>` Input-пароля на строке 119, перед кнопкой submit на строке 121):
```tsx
            <div className="text-right -mt-1">
              <Link
                href="/auth/reset-password"
                className="text-sm text-[var(--text-tertiary)] hover:text-[var(--accent)] transition-colors"
              >
                Забыли пароль?
              </Link>
            </div>
```

- [ ] **Step 4: Прогнать тест + tsc — ожидать PASS**

Run: `cd frontend && npx vitest run --maxWorkers=1 src/app/auth/reset-password/page.test.tsx && npx tsc --noEmit`
Expected: оба теста PASS, tsc без ошибок.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/auth/reset-password/ frontend/src/app/login/page.tsx
git commit -m "fix(auth-ui): страница /auth/reset-password + ссылка «Забыли пароль?» (S1-07)"
```

---

### S1-08 [HIGH] POST /broker/connections/{id}/reset уничтожает аннотации всех sync-сделок

**Files:**
- Modify: `backend/routers/broker.py:507` (эндпоинт reset — предупреждение/подтверждение)
- Test: `backend/tests/test_broker_reset_confirm.py` (Create)

**Проблема:** Эндпоинт «полная пересинхронизация» вызывает `reset_account` (broker.py:507), который жёстко удаляет все trades `data_source='tinkoff_v2'` (tools/reset_broker_account.py:75-79) вместе с `notes/tags/mood/discipline/confidence/setup_id/screenshot_url`. После reset строк уже нет — DATA-02 перенос аннотаций (читает со старых строк) не срабатывает, re-sync пересоздаёт журнал голым. Тихая потеря дневника трейдера по одному клику.

**Interfaces:**
- Consumes: тело reset-эндпоинта. Существующий query-параметр/тело эндпоинта (broker.py вокруг 500-510).
- Produces: reset требует явного подтверждения `confirm_data_loss=true` в теле/query, иначе `409 Conflict` с текстом о потере аннотаций. Минимальный безопасный барьер до полноценного side-хранилища аннотаций.

- [ ] **Step 1: Прочитать эндпоинт целиком и написать падающий тест**

Сначала прочитать сигнатуру: `sed -n '480,520p' backend/routers/broker.py` — определить имя функции и её параметры.

```python
# backend/tests/test_broker_reset_confirm.py
"""Reset брокер-подключения удаляет sync-сделки с аннотациями (notes/tags/mood/...).
Без явного confirm_data_loss=true эндпоинт должен отвечать 409, а не молча стирать дневник.
Проверяем на уровне исходника: reset-эндпоинт гейтит удаление флагом подтверждения.
"""
import os

BROKER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "routers", "broker.py")


def test_reset_endpoint_requires_confirmation_flag():
    src = open(BROKER, encoding="utf-8").read()
    # Находим блок с вызовом reset_account и проверяем, что рядом есть гейт 409
    # и упоминание confirm_data_loss.
    assert "reset_account(" in src, "эндпоинт reset должен вызывать reset_account"
    assert "confirm_data_loss" in src, "reset должен требовать confirm_data_loss"
    assert "status_code=409" in src, "без подтверждения reset должен отдавать 409"
```

- [ ] **Step 2: Прогнать — ожидать FAIL**

Run: `cd backend && C:/Python314/python.exe -m pytest tests/test_broker_reset_confirm.py -q`
Expected: FAIL — `confirm_data_loss`/`409` отсутствуют.

- [ ] **Step 3: Добавить гейт подтверждения**

В `backend/routers/broker.py` в reset-эндпоинте (вокруг строки 507), добавить query-параметр `confirm_data_loss: bool = False` в сигнатуру и гейт ПЕРЕД вызовом `reset_account`:

Before (`broker.py:507` контекст):
```python
    result = reset_account(account.id, confirmed=True)
```
After:
```python
    if not confirm_data_loss:
        raise HTTPException(
            status_code=409,
            detail=(
                "Полная пересинхронизация безвозвратно удалит заметки, теги, "
                "оценки настроения/дисциплины и скриншоты всех синхронизированных "
                "сделок. Подтвердите: confirm_data_loss=true."
            ),
        )
    result = reset_account(account.id, confirmed=True)
```

И добавить `confirm_data_loss: bool = False` в параметры функции-эндпоинта (в её `def ...(...)` рядом с прочими Query-параметрами).

- [ ] **Step 4: Прогнать — ожидать PASS**

Run: `cd backend && C:/Python314/python.exe -m pytest tests/test_broker_reset_confirm.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/routers/broker.py backend/tests/test_broker_reset_confirm.py
git commit -m "fix(broker): reset требует confirm_data_loss=true (не терять аннотации молча) (S1-08)"
```

---

### S1-09 [HIGH] Редактирование сделки падает 422: confidence='' и слайдер 1-10 против backend le=5

**Files:**
- Modify: `frontend/src/components/EditTradeModal.tsx:120-134` (handleSubmit — явная сборка confidence), `:308-318` (слайдер 1-5)
- Test: `frontend/src/components/EditTradeModal.test.tsx` (Create, vitest)

**Проблема:** `handleSubmit` шлёт `...formData` — `confidence` уходит строкой (EditTradeModal.tsx:122); для sync-сделок это `''`, что pydantic не парсит в `Optional[int]` → 422 на каждой попытке. Слайдер `min=1 max=10` (`:312-313`), а backend `confidence: Optional[int] = Field(None, ge=1, le=5)` (schemas.py:348) → значения 6-10 тоже 422.

**Interfaces:**
- Consumes: backend `TradeUpdate.confidence: Optional[int] = Field(None, ge=1, le=5)` (schemas.py:348). `PATCH /trades/{id}`.
- Produces: `confidence` в body = `formData.confidence ? parseInt(...) : null`, слайдер шкала 1-5.

- [ ] **Step 1: Написать vitest (ожидать FAIL)**

```tsx
// frontend/src/components/EditTradeModal.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const patch = vi.fn().mockResolvedValue({});
vi.mock('@/lib/apiClient', () => ({
  api: { patch: (...a: unknown[]) => patch(...a) },
  ApiError: class ApiError extends Error {},
}));
vi.mock('@/components/ui/Toast', () => ({ useToast: () => ({ success: vi.fn(), error: vi.fn() }) }));

import { EditTradeModal } from './EditTradeModal';

const syncTrade = {
  id: 42, symbol: 'SBER', direction: 'long', entry_price: 300, quantity: 10,
  entry_at: '2026-01-01T10:00:00Z', leverage: 1, commission: 0, swap: 0,
  confidence: null, tags: [], screenshot_url: null,
} as never;

describe('EditTradeModal', () => {
  it('шлёт confidence как null (не пустую строку) для sync-сделки без confidence', async () => {
    render(<EditTradeModal isOpen onClose={() => {}} onSuccess={() => {}} trade={syncTrade} />);
    fireEvent.click(screen.getByRole('button', { name: /сохранить/i }));
    await waitFor(() => expect(patch).toHaveBeenCalled());
    const body = patch.mock.calls[0][1].body;
    expect(body.confidence).toBeNull();
  });
});
```

- [ ] **Step 2: Прогнать — ожидать FAIL**

Run: `cd frontend && npx vitest run --maxWorkers=1 src/components/EditTradeModal.test.tsx`
Expected: FAIL — `body.confidence` = `''`, не `null`.

- [ ] **Step 3: Фикс handleSubmit + слайдер**

`frontend/src/components/EditTradeModal.tsx` — в объекте body (`:121-133`) добавить явную сборку confidence. ВНИМАНИЕ: строка `tags: formData.tags.split(...)` (`:132`) — ПОСЛЕДНЕЕ свойство литерала и НЕ имеет замыкающей запятой (следом идёт `}`). Поэтому нужно и добавить запятую к строке `tags`, и вписать `confidence` новой строкой. Before (`:132`):
```tsx
          tags: formData.tags.split(',').map(t => t.trim()).filter(Boolean)
        };
```
After:
```tsx
          tags: formData.tags.split(',').map(t => t.trim()).filter(Boolean),
          confidence: formData.confidence ? parseInt(formData.confidence, 10) : null,
        };
```
(поле `confidence` из `...formData` перекрывается этим явным ключом, т.к. он идёт позже в литерале объекта. Сверить точный текст строки `tags` перед правкой — `.split(',')`-аргументы могли измениться.)

Слайдер (`:308-318`) — привести к шкале 1-5:
Before:
```tsx
            <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Уверенность (1-10)</label>
            <div className="flex items-center gap-2">
              <input 
                type="range"
                min="1"
                max="10"
```
After:
```tsx
            <label className="block text-[10px] font-mono uppercase opacity-50 mb-1">Уверенность (1-5)</label>
            <div className="flex items-center gap-2">
              <input 
                type="range"
                min="1"
                max="5"
```

- [ ] **Step 4: Прогнать тест + tsc — ожидать PASS**

Run: `cd frontend && npx vitest run --maxWorkers=1 src/components/EditTradeModal.test.tsx && npx tsc --noEmit`
Expected: PASS, tsc чист.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/EditTradeModal.tsx frontend/src/components/EditTradeModal.test.tsx
git commit -m "fix(edit-trade): confidence как int|null + слайдер 1-5 (не 422) (S1-09)"
```

---

### S1-10 [HIGH] Refund-webhook помечает Payment REFUNDED глобально по external_id без скоупинга по user + int(user_id) без обработки

**Files:**
- Modify: `backend/routers/payments.py:270-271` (int(user_id) try/except), `:366-381` (_deactivate_subscription — скоуп по user)
- Test: `backend/tests/test_refund_scoping.py` (Create)

**Проблема:** `_deactivate_subscription` (payments.py:374-376) обновляет `Payment.status` по одному `external_id` без `filter(user_id)` и деактивирует ВСЕ активные подписки найденного user. `int(user_id)` (payments.py:271) без try/except → 500 на кривом (но подписанном) payload.

**Interfaces:**
- Consumes: результат S1-04 (refund-ветка теперь доходит до `_deactivate_subscription`). `_deactivate_subscription(db, user, payment_id)` (payments.py:366). `models.Payment.external_id`, `models.Payment.user_id`.
- Produces: `_deactivate_subscription` скоупит `Payment.update` по `user_id`. `int(user_id)` обёрнут в try/except → 400.

- [ ] **Step 1: Написать падающие тесты**

```python
# backend/tests/test_refund_scoping.py
"""Refund не должен трогать Payment чужого юзера с тем же external_id,
и кривой user_id в подписанном payload не должен ронять 500."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DEBUG", "true")

from main import app
from models import Base, User, Account, Payment, PaymentStatus
from database import get_db
import auth_service
from utils.datetime_utils import utc_now_naive


@pytest.fixture()
def app_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TS = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def _o():
        db = TS()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _o
    db = TS()
    yield TestClient(app), db
    db.close()
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


def _user(db, email):
    u = User(email=email, name="U", hashed_password=auth_service.get_password_hash("password12345"), is_active=1, settings={})
    db.add(u); db.commit(); db.refresh(u)
    return u


def test_refund_scoped_by_user(app_db):
    client, db = app_db
    victim = _user(db, "victim@e.com")
    attacker = _user(db, "att@e.com")
    # У обоих Payment с одинаковым external_id (коллизия/рассинхрон).
    for u in (victim, attacker):
        db.add(Payment(user_id=u.id, amount=399, currency="RUB",
                       status=PaymentStatus.COMPLETED, external_id="shared-ext",
                       payment_method="yookassa", completed_at=utc_now_naive()))
    db.commit()

    from routers.payments import _deactivate_subscription
    _deactivate_subscription(db, attacker, "shared-ext")
    db.expire_all()

    victim_pmt = db.query(Payment).filter(Payment.user_id == victim.id).one()
    assert victim_pmt.status == PaymentStatus.COMPLETED, "чужой Payment не должен помечаться REFUNDED"


def test_bad_user_id_returns_400_not_500(app_db):
    client, _ = app_db
    r = client.post("/payments/webhook", json={
        "event": "payment.succeeded",
        "object": {"id": "x", "status": "succeeded", "amount": {"value": "1"},
                   "metadata": {"user_id": "not-a-number", "plan": "pro"}},
    })
    assert r.status_code == 400, r.text
```

- [ ] **Step 2: Прогнать — ожидать FAIL**

Run: `cd backend && C:/Python314/python.exe -m pytest tests/test_refund_scoping.py -q`
Expected: FAIL — victim Payment помечен REFUNDED; `int("not-a-number")` даёт 500, не 400.

- [ ] **Step 3: Фикс скоупинга + int guard**

`backend/routers/payments.py:270-271` — обернуть int:
Before:
```python
    if user_id:
        user = db.query(models.User).filter(models.User.id == int(user_id)).first()
```
After:
```python
    if user_id:
        try:
            uid = int(user_id)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="invalid user_id in metadata")
        user = db.query(models.User).filter(models.User.id == uid).first()
```

`_deactivate_subscription` (payments.py:374-376) — скоуп по user:
Before:
```python
    # Помечаем Payment как REFUNDED
    db.query(models.Payment).filter(
        models.Payment.external_id == payment_id
    ).update({"status": models.PaymentStatus.REFUNDED if hasattr(models.PaymentStatus, "REFUNDED") else models.PaymentStatus.FAILED})
```
After:
```python
    # Помечаем Payment как REFUNDED — ТОЛЬКО платежи этого юзера (защита от
    # коллизии external_id между юзерами).
    db.query(models.Payment).filter(
        models.Payment.external_id == payment_id,
        models.Payment.user_id == user.id,
    ).update({"status": models.PaymentStatus.REFUNDED if hasattr(models.PaymentStatus, "REFUNDED") else models.PaymentStatus.FAILED})
```

- [ ] **Step 4: Прогнать — ожидать PASS**

Run: `cd backend && C:/Python314/python.exe -m pytest tests/test_refund_scoping.py tests/test_webhook_idempotency.py -q`
Expected: PASS (scoping + не сломали S1-04).

- [ ] **Step 5: Commit**

```bash
git add backend/routers/payments.py backend/tests/test_refund_scoping.py
git commit -m "fix(payments): скоуп refund по user_id + guard int(user_id) -> 400 (S1-10)"
```

---

### S1-11 [HIGH] Webhook refund.succeeded блокируется idempotency-замком (дубль S1-04) + lookup юзера

**Files:**
- Modify: `backend/routers/payments.py:249-306` (refund lookup исходного Payment)
- Test: `backend/tests/test_refund_lookup.py` (Create)

**Проблема:** Дублирует корневую причину S1-04 (idempotency-замок глотает refund). Дополнительно: refund-объект YooKassa не наследует metadata платежа → `user_id` пуст → 404 раньше действия. Нужно резолвить user из исходного Payment по `external_id=payment_id`, а не из metadata.

**Interfaces:**
- Consumes: результат S1-04 (замок больше не глотает refund). `models.Payment.external_id`, `models.Payment.user_id`. `payment_id` = `object.payment_id` для refund (payments.py:251).
- Produces: для `refund.succeeded` при отсутствии `user_id` в metadata — user резолвится через `Payment.external_id == payment_id`. Дополняет S1-04 (замок) и S1-10 (скоуп) — вместе refund-ветка полностью рабочая.

- [ ] **Step 1: Написать падающий тест (refund без metadata.user_id находит юзера по исходному Payment)**

```python
# backend/tests/test_refund_lookup.py
"""refund.succeeded без metadata.user_id должен находить юзера по исходному
Payment (external_id == payment_id) и деактивировать его подписку."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DEBUG", "true")

from main import app
from models import Base, User, Subscription, SubscriptionPlan
from database import get_db
import auth_service


@pytest.fixture()
def app_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TS = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def _o():
        db = TS()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _o
    db = TS()
    yield TestClient(app), db
    db.close()
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()


def test_refund_without_metadata_userid_finds_user(app_db):
    client, db = app_db
    u = User(email="p@e.com", name="P", hashed_password=auth_service.get_password_hash("password12345"), is_active=1, settings={})
    db.add(u); db.commit(); db.refresh(u)

    # Активируем через succeeded (создаётся Payment external_id=pmt-9).
    r1 = client.post("/payments/webhook", json={
        "event": "payment.succeeded",
        "object": {"id": "pmt-9", "status": "succeeded", "amount": {"value": "399.00"},
                   "metadata": {"user_id": str(u.id), "plan": "pro"}},
    })
    assert r1.status_code == 200, r1.text

    # Refund БЕЗ metadata.user_id — резолв через исходный Payment.
    r2 = client.post("/payments/webhook", json={
        "event": "refund.succeeded",
        "object": {"id": "rfnd-9", "payment_id": "pmt-9", "status": "succeeded", "amount": {"value": "399.00"}},
    })
    assert r2.status_code == 200, r2.text
    db.expire_all()
    subs = db.query(Subscription).filter(Subscription.user_id == u.id).all()
    assert all(s.is_active == 0 for s in subs)
```

- [ ] **Step 2: Прогнать — ожидать FAIL**

Run: `cd backend && C:/Python314/python.exe -m pytest tests/test_refund_lookup.py -q`
Expected: FAIL — refund без `metadata.user_id` даёт 404 (user not found).

- [ ] **Step 3: Фикс — резолв user для refund по исходному Payment**

В `backend/routers/payments.py` в блоке поиска юзера (после строки 273, перед `if user is None:` на строке 275) добавить fallback для refund:
```python
    # refund.succeeded обычно не несёт metadata платежа → user_id пуст.
    # Резолвим юзера по исходному Payment (external_id == payment_id).
    if user is None and target_status == "refunded" and payment_id:
        orig = db.query(models.Payment).filter(
            models.Payment.external_id == payment_id
        ).first()
        if orig is not None:
            user = db.query(models.User).filter(models.User.id == orig.user_id).first()
```

- [ ] **Step 4: Прогнать — ожидать PASS**

Run: `cd backend && C:/Python314/python.exe -m pytest tests/test_refund_lookup.py tests/test_refund_scoping.py tests/test_webhook_idempotency.py -q`
Expected: PASS (весь refund-кластер зелёный).

- [ ] **Step 5: Commit**

```bash
git add backend/routers/payments.py backend/tests/test_refund_lookup.py
git commit -m "fix(payments): refund резолвит user по исходному Payment (нет metadata.user_id) (S1-11)"
```

---

### S1-12 [HIGH] Удалён static-mount /uploads, фронт не переведён — все скриншоты 404 (frontend-часть)

**Files:**
- Modify: `frontend/src/app/history/_components/TradeRow.tsx:653-669`, `frontend/src/app/journal/screenshots/page.tsx:142-144`, `:214-216`
- Test: `frontend/src/app/journal/screenshots/screenshotUrl.test.tsx` (Create, vitest)

**Проблема:** IDOR-фикс удалил `app.mount("/uploads", ...)`, но фронт строит URL из `trade.screenshot_url` (`/uploads/screenshots/<file>`) и рендерит `<img>`/`<Image>`: TradeRow.tsx:657-663, journal/screenshots/page.tsx:142-144 (GalleryCard) и :214-216 (Lightbox). После деплоя каждый скриншот — 404. Auth cookie-based → `<img>` на same-site эндпоинт аутентифицируется.

**Interfaces:**
- Consumes: контракт S1-03 — `GET /trades/{id}/screenshot` (authenticated, ownership). `getApiUrl(path)` (apiClient.ts:24). `trade.screenshot_url` используется ТОЛЬКО как флаг наличия (truthiness), не как URL.
- Produces: во всех местах отображения URL строится как `getApiUrl('/trades/' + trade.id + '/screenshot')`.

- [ ] **Step 1: Написать vitest на helper построения URL (ожидать FAIL)**

Сначала вынести построение URL в чистую функцию в screenshots/page.tsx:
```tsx
export function screenshotSrc(tradeId: number): string {
  return getApiUrl(`/trades/${tradeId}/screenshot`);
}
```
Тест:
```tsx
// frontend/src/app/journal/screenshots/screenshotUrl.test.tsx
import { describe, it, expect, vi } from 'vitest';

vi.mock('@/lib/apiClient', () => ({
  getApiUrl: (p: string) => `http://api${p}`,
}));

import { screenshotSrc } from './page';

describe('screenshotSrc', () => {
  it('строит URL через authenticated эндпоинт, не через /uploads', () => {
    const src = screenshotSrc(42);
    expect(src).toBe('http://api/trades/42/screenshot');
    expect(src).not.toContain('/uploads/');
  });
});
```

- [ ] **Step 2: Прогнать — ожидать FAIL**

Run: `cd frontend && npx vitest run --maxWorkers=1 src/app/journal/screenshots/screenshotUrl.test.tsx`
Expected: FAIL — `screenshotSrc` не экспортирован.

- [ ] **Step 3: Фикс всех мест отображения**

`frontend/src/app/journal/screenshots/page.tsx` — добавить экспорт-функцию (рядом с импортами) и заменить оба построения URL.

GalleryCard (`:142-144`):
Before:
```tsx
  const url = trade.screenshot_url?.startsWith("http")
    ? trade.screenshot_url
    : getApiUrl(trade.screenshot_url || "");
```
After:
```tsx
  const url = trade.screenshot_url ? screenshotSrc(trade.id) : "";
```

Lightbox (`:214-216`) — идентичная замена:
Before:
```tsx
  const url = trade.screenshot_url?.startsWith("http")
    ? trade.screenshot_url
    : getApiUrl(trade.screenshot_url || "");
```
After:
```tsx
  const url = trade.screenshot_url ? screenshotSrc(trade.id) : "";
```

`frontend/src/app/history/_components/TradeRow.tsx:653-669` — заменить `getApiUrl(trade.screenshot_url)` на построение через id:
Before:
```tsx
                  <a
                    href={getApiUrl(trade.screenshot_url)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block"
                  >
                    <Image
                      src={getApiUrl(trade.screenshot_url)}
```
After:
```tsx
                  <a
                    href={getApiUrl(`/trades/${trade.id}/screenshot`)}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block"
                  >
                    <Image
                      src={getApiUrl(`/trades/${trade.id}/screenshot`)}
```

- [ ] **Step 4: Прогнать тест + tsc + визуальная проверка**

Run: `cd frontend && npx vitest run --maxWorkers=1 src/app/journal/screenshots/screenshotUrl.test.tsx && npx tsc --noEmit`
Expected: PASS, tsc чист.

Визуальная проверка (playwright, backend :8000 + `npm run dev -- -p 3001`): залогиниться, загрузить скриншот к сделке через AddTradeModal, открыть `/journal/screenshots` → картинка рендерится (не битая). При lock-ошибке убить `next dev` + удалить `frontend/.next/dev/lock`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/journal/screenshots/page.tsx frontend/src/app/history/_components/TradeRow.tsx frontend/src/app/journal/screenshots/screenshotUrl.test.tsx
git commit -m "fix(screenshots): строить URL через GET /trades/{id}/screenshot (не /uploads) (S1-12)"
```

---

### S1-13 [MEDIUM] Self-service PD export leaks 2FA secret and verification token

**Files:**
- Modify: `backend/services/pd_export.py:75` (exclude в build_user_export)
- Test: `backend/tests/test_pd_export_secrets.py` (Create)

**Проблема:** `build_user_export` сериализует все колонки User, исключая только `hashed_password` (pd_export.py:75). `totp_secret` (2FA shared secret) и `email_verification_token` попадают в экспорт JSON. При краже сессии/XSS `totp_secret` даёт полный обход 2FA.

**Interfaces:**
- Consumes: `_serialize_columns(user, exclude={...})` (pd_export.py). `models.User` колонки `totp_secret`, `email_verification_token`, `tokens_valid_after`.
- Produces: экспорт без секретных полей.

- [ ] **Step 1: Написать падающий тест**

```python
# backend/tests/test_pd_export_secrets.py
"""PD-экспорт (152-ФЗ) не должен утекать 2FA-секрет и verification-токен."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import models
from services.pd_export import build_user_export


def test_export_excludes_secrets(db_session):
    user = models.User(
        email="s@e.com", name="S", hashed_password="x", is_active=1, settings={},
        totp_secret="SUPERSECRET32", totp_enabled=True,
        email_verification_token="verif-token-abc",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    export = build_user_export(db_session, user)
    ud = export["user"] if "user" in export else export.get("user_data", export)
    # Секреты не должны присутствовать ни под каким ключом верхнего user-объекта.
    flat = str(export)
    assert "SUPERSECRET32" not in flat, "totp_secret утёк в экспорт"
    assert "verif-token-abc" not in flat, "email_verification_token утёк в экспорт"
```

- [ ] **Step 2: Прогнать — ожидать FAIL**

Run: `cd backend && C:/Python314/python.exe -m pytest tests/test_pd_export_secrets.py -q`
Expected: FAIL — `SUPERSECRET32`/`verif-token-abc` присутствуют в экспорте.

Примечание: если ключ user-объекта в export не `user`/`user_data`, тест использует `str(export)` — это устойчиво к имени ключа.

- [ ] **Step 3: Расширить exclude**

`backend/services/pd_export.py:75`:
Before:
```python
    user_data = _serialize_columns(user, exclude={"hashed_password"})
```
After:
```python
    user_data = _serialize_columns(
        user,
        exclude={"hashed_password", "totp_secret", "email_verification_token", "tokens_valid_after"},
    )
```

- [ ] **Step 4: Прогнать — ожидать PASS**

Run: `cd backend && C:/Python314/python.exe -m pytest tests/test_pd_export_secrets.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/pd_export.py backend/tests/test_pd_export_secrets.py
git commit -m "fix(pd-export): исключить totp_secret/verification token из PD-экспорта (S1-13)"
```

---

## Проверка спринта

Полный гейт после всех 13 задач:

```bash
# Backend — весь набор (кроме известного флейка в полном прогоне)
cd backend && C:/Python314/python.exe -m pytest tests/ -q
# Ожидается зелёный; допустимые флейки только в ПОЛНОМ прогоне:
#   test_debug_warning, test_market_service_async::test_get_client_returns_singleton
# (перепроверить изолированно — должны проходить).

# Backend импортится
C:/Python314/python.exe -c "from main import app; print('import OK')"

# Alembic против врем. SQLite (никогда не atom.db)
DATABASE_URL=sqlite:///./_audit_tmp.db C:/Python314/python.exe -m alembic upgrade head && rm -f _audit_tmp.db

# Frontend
cd ../frontend && npx vitest run --maxWorkers=1 && npx tsc --noEmit
```

Зелёным должно быть:
- [ ] `test_screenshot_delete_traversal.py` (S1-01) + `test_trades.py` (регрессия) PASS.
- [ ] Alembic `upgrade head` без ошибок, head-revision ≤32 символов, `git grep 0023_position_authoritative_fields backend/` пуст (S1-02).
- [ ] `test_screenshot_endpoint_contract.py` (S1-03) PASS; live-смоук `/uploads/...`→404, `/trades/1/screenshot`→401.
- [ ] `test_webhook_idempotency.py` (включая новый refund-тест, S1-04) PASS.
- [ ] `test_broker_token_status_code.py` (S1-05) PASS — все TokenInvalid→424.
- [ ] `test_login_2fa.py` (S1-06) — 3/3 PASS.
- [ ] `reset-password/page.test.tsx` (S1-07) — 2/2 PASS; tsc чист.
- [ ] `test_broker_reset_confirm.py` (S1-08) PASS.
- [ ] `EditTradeModal.test.tsx` (S1-09) PASS.
- [ ] `test_refund_scoping.py` (S1-10) + `test_refund_lookup.py` (S1-11) PASS.
- [ ] `screenshotUrl.test.tsx` (S1-12) PASS + визуальная проверка галереи скриншотов (playwright).
- [ ] `test_pd_export_secrets.py` (S1-13) PASS.
- [ ] `from main import app` без ошибок.
- [ ] 13 отдельных коммитов на ветке `feat/rebrand-empirik` (формат `fix(область): … (S1-XX)`), не запушены.
