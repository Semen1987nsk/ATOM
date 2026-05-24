# Sprint 0 — Stop-the-bleeding + правдивый CI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Убрать критичные foot-gun’ы (утечка секретов, дубль gRPC-стримов под мульти-воркером, нешифрованные токены в проде) и сделать CI честным (собирает брокерский слой, реально гоняет фронт-тесты и типы), чтобы последующие спринты были верифицируемы.

**Architecture:** Точечные правки в `backend/` (config fail-fast, worker-guard, deprecation fix), `.gitignore`, и `.github/workflows/`. Новый shared-util `worker_role.py` (DRY для IS_SCHEDULER_WORKER). Регенерация `requirements.lock` через одноразовый CI-workflow (на хосте нет Docker и стоит Python 3.14 вместо целевого 3.11).

**Tech Stack:** FastAPI / SQLAlchemy 2.0 / pytest (backend), Next.js 16 / vitest / tsc / eslint (frontend), GitHub Actions (CI), ruff + mypy (вводим non-blocking).

**Покрывает находки спеки:** SEC-04, SEC-06, SYNC-01, INFRA-01, INFRA-10, INFRA-13, INFRA-15, API-15. (См. `docs/superpowers/specs/2026-05-23-production-readiness-design.md`.)

**Режим коммитов:** no-commit — каждый «Commit»-шаг это *предложенная* команда; основатель ревьюит и коммитит сам. Шаги оставлены для полноты, но не выполняются агентом без явного разрешения.

**Глобальное правило проверки backend:** все `python` запускать как `PYTHONUTF8=1 python -X utf8` (Windows cp1251 ломает чтение Unicode-строк в config).

---

## File Structure

- Modify: `.gitignore` — добавить `*.bak`.
- Modify: `backend/routers/trades.py:537`, `backend/routers/admin.py:1471` — `regex=` → `pattern=`.
- Create: `backend/worker_role.py` — единый `is_scheduler_worker()`.
- Modify: `backend/main.py:126-132` — гард стримов через `is_scheduler_worker()`.
- Modify: `backend/config.py` — `_resolve_master_key_b64()` + строка 298.
- Modify: `backend/Dockerfile` (если нужно) и `.github/workflows/ci.yml` — `--extra-index-url`, убрать `AUTO_INIT_DB`, фронт-гейты, backend-lint.
- Modify: `frontend/src/app/layout.tsx:21-29`, `frontend/package.json` (script `typecheck`).
- Create: `backend/pyproject.toml` — минимальные ruff + mypy конфиги.
- Create: `.github/workflows/regenerate-lock.yml` — одноразовая регенерация lock.
- Create tests: `backend/tests/unit/test_worker_role.py`, `backend/tests/unit/test_config_master_key.py`, `backend/tests/unit/test_no_deprecated_query_regex.py`.

---

## Task 1: SEC-04 — `*.bak` в `.gitignore` (стоп-утечка секретов)

**Files:**
- Modify: `.gitignore`
- Verify: `backend/.env.local.bak`

- [ ] **Step 1: Подтвердить, что бэкап-файл с секретами НЕ в трекинге**

Run:
```bash
cd /c/Users/Administrator/Eqio/ATOM
git ls-files "backend/.env.local.bak" "*.bak"
```
Expected: пусто (файл untracked). Если что-то вывелось — СТОП, файл уже в индексе/истории: сообщить основателю (нужен `git rm --cached` + ротация секретов), не продолжать молча.

- [ ] **Step 2: Добавить правило в `.gitignore`**

В секцию «Environment variables» (после строки `.env.production`) добавить:
```gitignore
# Backups of env/secret files (e.g. .env.local.bak) — НИКОГДА не коммитим
*.bak
*.env.local.bak
```

- [ ] **Step 3: Проверить, что игнор работает**

Run:
```bash
git check-ignore backend/.env.local.bak
```
Expected: вывод `backend/.env.local.bak` (т.е. игнорируется).

- [ ] **Step 4 (suggested commit):**
```bash
git add .gitignore
git commit -m "chore(security): gitignore *.bak to prevent secret-file leak (SEC-04)"
```

---

## Task 2: API-15 — `regex=` → `pattern=` в Query (+ регресс-тест)

**Files:**
- Test: `backend/tests/unit/test_no_deprecated_query_regex.py`
- Modify: `backend/routers/trades.py:537`, `backend/routers/admin.py:1471`

- [ ] **Step 1: Падающий тест-страж**

Create `backend/tests/unit/test_no_deprecated_query_regex.py`:
```python
"""Guard: в Pydantic v2 `Query(regex=...)` deprecated и может молча не
валидировать. Должно использоваться `pattern=`. Тест ловит регрессию."""
from __future__ import annotations

import pathlib


def test_no_deprecated_query_regex():
    routers_dir = pathlib.Path(__file__).resolve().parents[2] / "routers"
    offenders: list[str] = []
    for f in sorted(routers_dir.glob("*.py")):
        for i, line in enumerate(f.read_text(encoding="utf-8").splitlines(), start=1):
            if "Query(" in line and "regex=" in line:
                offenders.append(f"{f.name}:{i}")
    assert offenders == [], (
        "Использован устаревший Query(regex=...) — заменить на pattern=:\n  "
        + "\n  ".join(offenders)
    )
```

- [ ] **Step 2: Запустить — убедиться, что падает**

Run:
```bash
cd /c/Users/Administrator/Eqio/ATOM/backend
PYTHONUTF8=1 python -X utf8 -m pytest tests/unit/test_no_deprecated_query_regex.py -q
```
Expected: FAIL — offenders содержит `trades.py:537` и `admin.py:1471`.

- [ ] **Step 3: Починить trades.py:537**

Заменить:
```python
    status: str = Query("all", regex="^(all|open|closed)$"),
```
на:
```python
    status: str = Query("all", pattern="^(all|open|closed)$"),
```

- [ ] **Step 4: Починить admin.py:1471**

Заменить:
```python
    status_filter: Optional[str] = Query(None, regex="^(pending|overdue|finalized)$"),
```
на:
```python
    status_filter: Optional[str] = Query(None, pattern="^(pending|overdue|finalized)$"),
```

- [ ] **Step 5: Запустить — убедиться, что зелёный + app импортится**

Run:
```bash
cd /c/Users/Administrator/Eqio/ATOM/backend
PYTHONUTF8=1 python -X utf8 -m pytest tests/unit/test_no_deprecated_query_regex.py -q
PYTHONUTF8=1 python -X utf8 -c "from main import app; print('IMPORT-OK', len(app.routes))"
```
Expected: PASS; `IMPORT-OK <N>`.

- [ ] **Step 6 (suggested commit):**
```bash
git add backend/routers/trades.py backend/routers/admin.py backend/tests/unit/test_no_deprecated_query_regex.py
git commit -m "fix(api): Query pattern= instead of deprecated regex= + guard test (API-15)"
```

---

## Task 3: SYNC-01 — гард стримов по `IS_SCHEDULER_WORKER` (стоп IP-cooldown T-Bank)

**Files:**
- Create: `backend/worker_role.py`
- Test: `backend/tests/unit/test_worker_role.py`
- Modify: `backend/main.py:126-132`

- [ ] **Step 1: Падающий тест на util**

Create `backend/tests/unit/test_worker_role.py`:
```python
"""is_scheduler_worker(): singleton-фоновые задачи (scheduler + streams)
должны идти ровно на одном воркере. Default true (одиночный деплой)."""
from __future__ import annotations

import importlib


def _fresh(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("IS_SCHEDULER_WORKER", raising=False)
    else:
        monkeypatch.setenv("IS_SCHEDULER_WORKER", value)
    import worker_role
    importlib.reload(worker_role)
    return worker_role.is_scheduler_worker()


def test_default_is_true(monkeypatch):
    assert _fresh(monkeypatch, None) is True


def test_false_when_disabled(monkeypatch):
    assert _fresh(monkeypatch, "false") is False
    assert _fresh(monkeypatch, "FALSE") is False


def test_true_when_enabled(monkeypatch):
    assert _fresh(monkeypatch, "true") is True
```

- [ ] **Step 2: Запустить — падает (модуля нет)**

Run:
```bash
cd /c/Users/Administrator/Eqio/ATOM/backend
PYTHONUTF8=1 python -X utf8 -m pytest tests/unit/test_worker_role.py -q
```
Expected: FAIL — `ModuleNotFoundError: No module named 'worker_role'`.

- [ ] **Step 3: Создать util**

Create `backend/worker_role.py`:
```python
"""Единая точка определения «singleton-воркера» для фоновых задач.

На multi-worker деплое (gunicorn --workers N) фоновые синглтоны — sync
scheduler И stream consumers — должны крутиться ровно на ОДНОМ воркере,
иначе N×gRPC-стримов мгновенно ловят IP-cooldown T-Bank. Поставьте
IS_SCHEDULER_WORKER=false на всех воркерах кроме одного.
"""
from __future__ import annotations

import os


def is_scheduler_worker() -> bool:
    return os.getenv("IS_SCHEDULER_WORKER", "true").lower() == "true"
```

- [ ] **Step 4: Запустить — зелёный**

Run:
```bash
cd /c/Users/Administrator/Eqio/ATOM/backend
PYTHONUTF8=1 python -X utf8 -m pytest tests/unit/test_worker_role.py -q
```
Expected: PASS (3 passed).

- [ ] **Step 5: Применить гард в `main.py`**

В `backend/main.py` заменить блок (строки ~126-132):
```python
    try:
        from application.sync.stream_manager import stream_manager
        started = await stream_manager.start_all_enabled()
        if started > 0:
            log.info("📡 Stream consumers started: %d", started)
    except Exception:
        log.exception("Failed to start stream_manager (non-blocking)")
```
на:
```python
    # SYNC-01: stream-consumers — singleton-фоновая работа. Без этого гарда
    # они стартуют на КАЖДОМ gunicorn-воркере → N×500 gRPC-стримов →
    # IP-cooldown T-Bank в первую минуту мульти-воркер деплоя.
    from worker_role import is_scheduler_worker
    if is_scheduler_worker():
        try:
            from application.sync.stream_manager import stream_manager
            started = await stream_manager.start_all_enabled()
            if started > 0:
                log.info("📡 Stream consumers started: %d", started)
        except Exception:
            log.exception("Failed to start stream_manager (non-blocking)")
    else:
        log.info("⏭️ Stream consumers skipped on this worker (IS_SCHEDULER_WORKER=false)")
```

- [ ] **Step 6: Проверить импорт приложения**

Run:
```bash
cd /c/Users/Administrator/Eqio/ATOM/backend
PYTHONUTF8=1 python -X utf8 -c "from main import app; print('IMPORT-OK', len(app.routes))"
```
Expected: `IMPORT-OK <N>` без ошибок.

- [ ] **Step 7 (suggested commit):**
```bash
git add backend/worker_role.py backend/tests/unit/test_worker_role.py backend/main.py
git commit -m "fix(sync): gate stream_manager behind IS_SCHEDULER_WORKER (SYNC-01)"
```

---

## Task 4: INFRA-15 — fail-fast `MASTER_KEY_B64` в проде

**Files:**
- Test: `backend/tests/unit/test_config_master_key.py`
- Modify: `backend/config.py` (новая функция ~после строки 174; строка 298)

- [ ] **Step 1: Падающий тест**

Create `backend/tests/unit/test_config_master_key.py`:
```python
"""MASTER_KEY_B64 (AES-256-GCM мастер-ключ брокерских токенов):
в проде (DEBUG=false) ОБЯЗАТЕЛЕН, иначе токены лягут нешифрованными."""
from __future__ import annotations

import pytest


def test_raises_in_prod_when_missing(monkeypatch):
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.delenv("MASTER_KEY_B64", raising=False)
    from config import _resolve_master_key_b64
    with pytest.raises(RuntimeError):
        _resolve_master_key_b64()


def test_empty_ok_in_debug(monkeypatch):
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.delenv("MASTER_KEY_B64", raising=False)
    from config import _resolve_master_key_b64
    assert _resolve_master_key_b64() == ""


def test_returns_value_when_set(monkeypatch):
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("MASTER_KEY_B64", "c29tZS1iYXNlNjQta2V5")
    from config import _resolve_master_key_b64
    assert _resolve_master_key_b64() == "c29tZS1iYXNlNjQta2V5"
```

- [ ] **Step 2: Запустить — падает (функции нет)**

Run:
```bash
cd /c/Users/Administrator/Eqio/ATOM/backend
PYTHONUTF8=1 python -X utf8 -m pytest tests/unit/test_config_master_key.py -q
```
Expected: FAIL — `ImportError: cannot import name '_resolve_master_key_b64'`.

- [ ] **Step 3: Добавить функцию в `config.py`**

Сразу после `_resolve_auto_init_db()` (перед `class Settings:`, ~строка 175) вставить (стиль зеркалит `_resolve_secret_key`; `os`, `warnings` уже импортированы):
```python
def _resolve_master_key_b64() -> str:
    """MASTER_KEY_B64 — AES-256-GCM мастер-ключ для шифрования брокерских токенов.

    - prod (DEBUG=false): ОБЯЗАТЕЛЕН — иначе токены сохранятся нешифрованными.
    - dev (DEBUG=true): пустая строка допустима (encryption-сервис подменит
      на ephemeral dev-ключ с громким warning).
    """
    key = os.getenv("MASTER_KEY_B64", "")
    if key:
        return key

    is_debug = os.getenv("DEBUG", "false").lower() == "true"
    if not is_debug:
        raise RuntimeError(
            "\n🚨 FATAL: MASTER_KEY_B64 is not set!\n"
            "   In production (DEBUG != true) MASTER_KEY_B64 MUST be set "
            "(AES-256-GCM master key for broker tokens).\n"
            "   Generate one with: "
            "python -c 'import os,base64; print(base64.b64encode(os.urandom(32)).decode())'\n"
            "   Then set: export MASTER_KEY_B64='your-generated-key'"
        )

    warnings.warn(
        "\n⚠️  MASTER_KEY_B64 not set — broker-token encryption will use an "
        "ephemeral dev key.\n"
        "   This key changes on every restart; stored tokens become undecryptable.\n"
        "   Set MASTER_KEY_B64 for persistent encryption in development.",
        UserWarning,
        stacklevel=2,
    )
    return ""
```

- [ ] **Step 4: Подключить в `Settings`**

Заменить строку 298:
```python
    MASTER_KEY_B64: str = os.getenv("MASTER_KEY_B64", "")
```
на:
```python
    MASTER_KEY_B64: str = _resolve_master_key_b64()
```

- [ ] **Step 5: Запустить — зелёный + app импортится (под DEBUG=true)**

Run:
```bash
cd /c/Users/Administrator/Eqio/ATOM/backend
PYTHONUTF8=1 python -X utf8 -m pytest tests/unit/test_config_master_key.py -q
DEBUG=true PYTHONUTF8=1 python -X utf8 -c "from main import app; print('IMPORT-OK', len(app.routes))"
```
Expected: PASS (3 passed); `IMPORT-OK <N>`.

> NB: как и для `SECRET_KEY`, локальный прогон тестов/импорт требует `DEBUG=true`
> ИЛИ заданного `MASTER_KEY_B64` (иначе fail-fast сработает — это и есть цель).
> CI pytest уже идёт с `DEBUG: 'true'` → не сломается.

- [ ] **Step 6 (suggested commit):**
```bash
git add backend/config.py backend/tests/unit/test_config_master_key.py
git commit -m "feat(security): fail-fast MASTER_KEY_B64 in production (INFRA-15)"
```

---

## Task 5: INFRA-13 — убрать `AUTO_INIT_DB=true` из CI pytest (несовместимо с Postgres-гардом)

**Files:**
- Modify: `.github/workflows/ci.yml:81`

Контекст: `config._resolve_auto_init_db()` (config.py:161-167) кидает `RuntimeError`, если `AUTO_INIT_DB=true` при PostgreSQL URL. Тесты схему берут из in-memory SQLite фикстуры (`tests/conftest.py:32-33`) + `alembic upgrade head` для Postgres-сервиса. Значит `AUTO_INIT_DB` в CI и вредна (краш-гард), и не нужна.

- [ ] **Step 1: Локально подтвердить поведение гарда**

Run:
```bash
cd /c/Users/Administrator/Eqio/ATOM/backend
DATABASE_URL=postgresql://x AUTO_INIT_DB=true PYTHONUTF8=1 python -X utf8 -c "import config; print('NO-RAISE (unexpected)')" || echo "RAISED as expected"
DATABASE_URL=postgresql://x PYTHONUTF8=1 python -X utf8 -c "import config; print('OK without AUTO_INIT_DB')"
```
Expected: первая команда → `RAISED as expected`; вторая → `OK without AUTO_INIT_DB`.

- [ ] **Step 2: Удалить строку из CI**

В `.github/workflows/ci.yml`, в шаге «Run pytest with coverage» (env-блок, ~строка 81) удалить строку:
```yaml
          AUTO_INIT_DB: 'true'
```
(Схему для Postgres-сервиса уже создаёт предыдущий шаг `alembic upgrade head`, строка 71.)

- [ ] **Step 3: Локально прогнать unit-тесты (sanity, что схема-фикстура самодостаточна)**

Run:
```bash
cd /c/Users/Administrator/Eqio/ATOM/backend
DEBUG=true PYTHONUTF8=1 python -X utf8 -m pytest tests/unit -q --maxfail=5
```
Expected: PASS (unit-тесты создают схему через `Base.metadata.create_all` в фикстуре, не зависят от `AUTO_INIT_DB`).

- [ ] **Step 4 (suggested commit):**
```bash
git add .github/workflows/ci.yml
git commit -m "ci: drop AUTO_INIT_DB=true (crashes on Postgres guard; schema from alembic) (INFRA-13)"
```

---

## Task 6: INFRA-01 — `--extra-index-url` для `t-tech-investments` в CI

**Files:**
- Modify: `.github/workflows/ci.yml` (шаги install + pip-audit)
- Verify: `backend/Dockerfile`

Без T-Bank GitLab PyPI пакет `t-tech-investments==0.3.5` не ставится (на public PyPI в карантине) → брокерский слой не собирается/не тестируется.

- [ ] **Step 1: Backend install — добавить extra-index**

В `.github/workflows/ci.yml`, шаг «Install dependencies (locked)» (строки 57-61), заменить:
```yaml
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.lock
```
на:
```yaml
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.lock \
            --extra-index-url https://opensource.tbank.ru/api/v4/projects/238/packages/pypi/simple
```

- [ ] **Step 2: pip-audit — тот же extra-index (иначе резолв t-tech-investments падает)**

В шаге «Run pip-audit on locked deps» (строка 120) заменить:
```yaml
        run: pip-audit --requirement requirements.lock --format json --output audit.json || true
```
на:
```yaml
        run: |
          pip-audit --requirement requirements.lock \
            --extra-index-url https://opensource.tbank.ru/api/v4/projects/238/packages/pypi/simple \
            --format json --output audit.json || true
```

- [ ] **Step 3: Проверить Dockerfile (docker-build job)**

Run:
```bash
cd /c/Users/Administrator/Eqio/ATOM
grep -n "opensource.tbank.ru\|extra-index-url\|requirements" backend/Dockerfile
```
- Если `pip install` в `backend/Dockerfile` НЕ содержит `--extra-index-url https://opensource.tbank.ru/...` — добавить его к соответствующей `pip install -r requirements*.` строке (тем же URL). Если уже есть — пропустить.

- [ ] **Step 4 (suggested commit):**
```bash
git add .github/workflows/ci.yml backend/Dockerfile
git commit -m "ci: add T-Bank PyPI extra-index-url so broker layer installs/tests (INFRA-01)"
```

---

## Task 7: INFRA-10a — фронт-гейты: tsc + vitest + eslint hard (и фикс tsc-ошибки)

**Files:**
- Modify: `frontend/src/app/layout.tsx:21-29`
- Modify: `frontend/package.json` (script `typecheck`)
- Modify: `.github/workflows/ci.yml` (frontend job)

`tsc` сейчас НЕ чист: `layout.tsx:25` передаёт `subsets: ["latin","cyrillic"]` в `Fraunces`, но Google-шрифт Fraunces не имеет cyrillic-сабсета (тип допускает только latin/latin-ext/vietnamese) → кириллица всё равно не грузилась в Fraunces (фолбэк). Чиним → tsc становится гейтом.

> ⚠️ Дизайн-нота (НЕ блокер S0): ADR-0006/design-system v3 предполагали Fraunces для кириллических заголовков, но шрифт её не поддерживает. Это пункт для продуктового/дизайн-трека (выбрать serif с кириллицей, напр. PT Serif/Playfair, или принять sans для RU-заголовков). Здесь — только делаем типы честными.

- [ ] **Step 1: Убрать невалидный сабсет в `layout.tsx`**

Заменить строки 21-29:
```tsx
// Editorial serif для headlines / lede / pull-quotes. Полный cyrillic-subset.
// См. ADR-0006 (editorial-financial-rebrand) и design-system.md v3.
const fraunces = Fraunces({
  variable: "--font-serif",
  subsets: ["latin", "cyrillic"],
  weight: ["300", "400", "500", "600"],
  style: ["normal", "italic"],
  display: "swap",
});
```
на:
```tsx
// Editorial serif для headlines / lede / pull-quotes.
// NB: Google-шрифт Fraunces не имеет cyrillic-сабсета — кириллица в этих
// местах рендерится фолбэком. Выбор serif с кириллицей — см. дизайн-трек.
// ADR-0006 (editorial-financial-rebrand), design-system.md v3.
const fraunces = Fraunces({
  variable: "--font-serif",
  subsets: ["latin"],
  weight: ["300", "400", "500", "600"],
  style: ["normal", "italic"],
  display: "swap",
});
```

- [ ] **Step 2: Проверить, что tsc теперь чист**

Run:
```bash
cd /c/Users/Administrator/Eqio/ATOM/frontend
npx tsc --noEmit
echo "exit: $?"
```
Expected: `exit: 0` (нет `error TS`).

- [ ] **Step 3: Добавить `typecheck` script в `package.json`**

В `frontend/package.json` в `"scripts"` добавить (после `"lint"`):
```json
    "typecheck": "tsc --noEmit",
```

- [ ] **Step 4: Проверить eslint exit-code (ошибки vs warnings)**

Run:
```bash
cd /c/Users/Administrator/Eqio/ATOM/frontend
npm run lint; echo "exit: $?"
```
Expected: `exit: 0` (только warnings, не errors). Если `exit: 1` (есть errors) — починить их в этом же шаге ДО снятия `|| true`; перечислить и исправить точечно.

- [ ] **Step 5: Прогнать vitest (должен быть зелёным)**

Run:
```bash
cd /c/Users/Administrator/Eqio/ATOM/frontend
npm test
```
Expected: `Test Files 2 passed`, все тесты passed.

- [ ] **Step 6: Включить гейты в CI frontend job**

В `.github/workflows/ci.yml`, frontend job (строки 145-159), заменить блок Lint/Build:
```yaml
      - name: Lint
        working-directory: frontend
        # ESLint не блокирует merge — сначала очищаем легаси, потом включаем strict
        run: npm run lint || true

      - name: Build
        working-directory: frontend
        env:
          NEXT_PUBLIC_API_URL: http://localhost:8000
        run: npm run build
```
на:
```yaml
      - name: Lint
        working-directory: frontend
        run: npm run lint

      - name: Typecheck
        working-directory: frontend
        run: npm run typecheck

      - name: Test (vitest)
        working-directory: frontend
        run: npm test

      - name: Build
        working-directory: frontend
        env:
          NEXT_PUBLIC_API_URL: http://localhost:8000
        run: npm run build
```

- [ ] **Step 7 (suggested commit):**
```bash
git add frontend/src/app/layout.tsx frontend/package.json .github/workflows/ci.yml
git commit -m "ci(frontend): hard gates tsc+vitest+eslint; fix Fraunces subset tsc error (INFRA-10)"
```

---

## Task 8: INFRA-10b — backend ruff + mypy как NON-blocking гейты (база для harden)

**Files:**
- Create: `backend/pyproject.toml`
- Modify: `.github/workflows/ci.yml` (новый job `backend-lint`)

Ruff/mypy ещё не настроены, нарушений будет много → в S0 вводим их **non-blocking** (видимость), ужесточаем в поздних спринтах. pip-audit hard-fail переносится в S2 (зависит от SEC-05 `python-jose`→PyJWT — иначе CI краснеет сразу).

- [ ] **Step 1: Минимальный конфиг**

Create `backend/pyproject.toml`:
```toml
# Минимальная конфигурация линтеров. Введены NON-blocking в Sprint 0
# (INFRA-10); ужесточение до hard-fail — в поздних спринтах harden-плана.
[tool.ruff]
target-version = "py311"
line-length = 100
exclude = ["alembic/versions", "tests/sandbox"]

[tool.ruff.lint]
# Стартовый консервативный набор: pyflakes (F) + базовый pycodestyle (E).
select = ["E", "F", "W"]
ignore = ["E501"]  # длину строк подключим отдельным проходом

[tool.mypy]
python_version = "3.11"
ignore_missing_imports = true
warn_unused_ignores = false
check_untyped_defs = false
exclude = "(alembic/|tests/)"
```

- [ ] **Step 2: Локальный sanity-прогон (увидеть объём, не падать)**

Run:
```bash
cd /c/Users/Administrator/Eqio/ATOM/backend
pip install ruff mypy >/dev/null 2>&1 || true
ruff check . || true
mypy . || true
```
Expected: команды отрабатывают (вывод с замечаниями — норм, это non-blocking baseline).

- [ ] **Step 3: Добавить non-blocking job в CI**

В `.github/workflows/ci.yml` добавить новый job (после `backend-audit`):
```yaml
  # ─────────────────── BACKEND LINT (non-blocking baseline) ───────────────────
  backend-lint:
    name: Backend (ruff + mypy — non-blocking)
    runs-on: ubuntu-latest
    timeout-minutes: 8
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install linters
        run: pip install ruff mypy
      - name: Ruff (non-blocking)
        working-directory: backend
        continue-on-error: true
        run: ruff check .
      - name: Mypy (non-blocking)
        working-directory: backend
        continue-on-error: true
        run: mypy .
```

- [ ] **Step 4 (suggested commit):**
```bash
git add backend/pyproject.toml .github/workflows/ci.yml
git commit -m "ci(backend): add ruff+mypy non-blocking baseline (INFRA-10; harden later)"
```

---

## Task 9: SEC-06 — регенерация `requirements.lock` (fastapi 0.114→0.136 / starlette drift)

**Files:**
- Create: `.github/workflows/regenerate-lock.yml`
- Modify (артефактом из CI): `backend/requirements.lock`

Lock рассинхронен с `requirements.txt` (lock: `fastapi==0.114.2`, `starlette==0.38.6`; txt: `fastapi>=0.136.1`). На хосте нет Docker и стоит Python 3.14 (целевой — 3.11), поэтому регенерируем в CI на python:3.11.

- [ ] **Step 1: Создать одноразовый workflow**

Create `.github/workflows/regenerate-lock.yml`:
```yaml
name: Regenerate backend lock

# Ручной запуск: Actions → "Regenerate backend lock" → Run workflow.
# Резолвит requirements.txt на python:3.11 (целевой рантайм) с T-Bank индексом
# и выкладывает свежий requirements.lock артефактом для ревью+коммита.
on:
  workflow_dispatch:

jobs:
  regen:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    container: python:3.11-slim
    steps:
      - uses: actions/checkout@v4
      - name: Resolve and freeze
        working-directory: backend
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt \
            --extra-index-url https://opensource.tbank.ru/api/v4/projects/238/packages/pypi/simple
          pip freeze --exclude-editable > requirements.lock.new
          echo "----- fastapi/starlette in new lock -----"
          grep -Ei '^(fastapi|starlette)==' requirements.lock.new || true
      - name: Upload regenerated lock
        uses: actions/upload-artifact@v4
        with:
          name: requirements-lock
          path: backend/requirements.lock.new
          retention-days: 7
```

- [ ] **Step 2: Запустить workflow и проверить результат**

Через GitHub UI: Actions → «Regenerate backend lock» → Run workflow (ветка `feature/costs-breakdown-card`). По завершении в логе шага «Resolve and freeze» убедиться, что `fastapi==0.136.x` и `starlette>=1.0`.

- [ ] **Step 3: Заменить lock артефактом**

Скачать артефакт `requirements-lock`, заменить `backend/requirements.lock` его содержимым (переименовать `requirements.lock.new` → `requirements.lock`).

- [ ] **Step 4: Проверить, что основной CI зелёный на новом lock**

Push ветку → дождаться backend job (ставит `requirements.lock` с `--extra-index-url` из Task 6, гоняет alembic + pytest). Expected: install без конфликтов, migrations + pytest зелёные.
> Если install падает на транзитивном конфликте (например anyio под starlette 1.0) — это и есть смысл регенерации: повторить Step 2 (freeze уже даёт согласованный набор); при необходимости снять верхние границы в `requirements.txt` для конфликтующего пакета и перерезолвить.

- [ ] **Step 5 (suggested commit):**
```bash
git add backend/requirements.lock .github/workflows/regenerate-lock.yml
git commit -m "chore(deps): regenerate requirements.lock (fastapi 0.136 / starlette 1.0) (SEC-06)"
```

---

## Self-Review

**1. Spec coverage (Sprint 0 findings):**
- SEC-04 → Task 1 ✓
- API-15 → Task 2 ✓
- SYNC-01 → Task 3 ✓
- INFRA-15 → Task 4 ✓
- INFRA-13 → Task 5 ✓
- INFRA-01 → Task 6 ✓
- INFRA-10 → Task 7 (frontend gates) + Task 8 (backend ruff/mypy non-blocking) ✓ — *примечание:* pip-audit hard-fail из INFRA-10 сознательно перенесён в S2 (зависит от SEC-05 `python-jose`→PyJWT; иначе CI краснеет немедленно).
- SEC-06 → Task 9 ✓

**2. Placeholder scan:** нет TBD/«добавь обработку ошибок»/«аналогично Task N» — весь код приведён дословно. ✓

**3. Type/identifier consistency:** `is_scheduler_worker()` (Task 3) и `_resolve_master_key_b64()` (Task 4) используются под теми же именами в импортах/тестах; `npm run typecheck` (Task 7 Step 3) совпадает со скриптом в CI (Step 6). ✓

**Известные допущения, проверяемые при исполнении:**
- Task 6 Step 3 — фактическое наличие `--extra-index-url` в `backend/Dockerfile` проверяется командой (если уже есть — no-op).
- Task 7 Step 4 — eslint предполагается exit 0 (только warnings); если errors — чиним до включения гейта.
- Task 9 — точный результат lock известен только после CI-прогона (по дизайну: резолв на целевом 3.11).
