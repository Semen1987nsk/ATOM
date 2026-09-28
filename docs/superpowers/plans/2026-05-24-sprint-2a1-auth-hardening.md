# Sprint 2A-1 — Auth & Token Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

> **NO-COMMIT MODE:** реализуй + тесты до зелёного, НЕ выполняй `git add`/`git commit`. Пользователь ревьюит и коммитит.

> **Окружение:** dev py3.14 (no Docker, no venv), CI/prod py3.11. Все Python-команды через `PYTHONUTF8=1 python -X utf8 ...`. Ребренд Eqio→Empirik уже в дереве — не вводить «eqio»-строк; искать места правок по символам, не по номерам строк.

**Goal:** Закрыть auth/token-находки Sprint 2A-1 (SEC-05/08/09/10, API-05/06/07/08/11): уйти с заброшенного python-jose на PyJWT, добавить ротацию refresh-токенов, инвалидацию сессий при сбросе/смене пароля, account-lockout, OAuth redirect allowlist, единую парольную политику, убрать токены из тела ответа и PII-email из логов.

**Architecture:** SEC-05 (PyJWT swap) — фундамент, кладётся первым (переписывает ядро `auth_service`). Инвалидация сессий через новый `User.tokens_valid_after` + claim `iat` (переиспользуется API-07 и full reuse-detection API-05). Lockout — новые поля `User.failed_login_count`/`locked_until`. Одна миграция `0026` на все DB-изменения.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, Alembic, PyJWT (заменяет python-jose; уже в lock 2.12.1 транзитивно), pytest+asyncio.

**Зафиксированные политические решения (env-конфигурируемы, дефолты безопасны):**
- API-11: `LOGIN_MAX_FAILED_ATTEMPTS=10`, `LOGIN_LOCKOUT_MINUTES=15`, generic 401, сброс при успехе.
- API-08: `OAUTH_ALLOWED_REDIRECT_URIS` (comma-env), exact-match, default `[]`.
- API-05: строгая ротация (revoke старого refresh при использовании) + reuse-detection через revocation.
- API-07: `tokens_valid_after` инвалидация распространяется и на change-password (не только reset).

---

## Verified current locations (audit line-numbers были pre-rebrand)

| Finding | Реальное место (на момент планирования; ПЕРЕПРОВЕРИТЬ перед правкой) |
|---|---|
| SEC-05 | `auth_service.py:16` (единственный `from jose import`), usages :196/:220 (encode), :245/:281 (decode), :267/:302 (`except JWTError`); `requirements.txt:23`; PyJWT 2.12.1 уже в `requirements.lock` |
| API-05 | `auth_service.py:306-324` (`refresh_tokens`) |
| API-06 | `schemas.py:199` (ChangePasswordRequest min_length=6), `schemas.py:193` (PasswordResetConfirm — нет ограничения), `routers/auth.py:384-388` и `:635-636` (`< 6`); регистрация `schemas.py:58` min_length=12 |
| API-07 | `routers/auth.py:642-650` (комментарий «текущие JWT остаются валидными») |
| API-08 | `routers/auth.py:665-686` (`oauth_authorize`), `:689-718` (callback) |
| API-11 | `rate_limiter.py:142` (только IP 5/min); `models.py` User (нет lockout-полей); `authenticate_user` `auth_service.py:382-405` |
| SEC-08 | `routers/auth.py:99-104/135-140/181-186/776-787` (токен в теле); фронт читает только куки |
| SEC-09 | confirm уже POST (`:610-616`); остаток — фронт reset-link URL → S5 |
| SEC-10 | `routers/auth.py:57/97/133/274/393/560/565/768/774` (email в INFO) |

Alembic head: **`0025_account_pnl_health_cache`**.

---

## Ordering (критично)
1. **SEC-05 первым** — переписывает ядро token-кода; API-05/07/SEC-08 строятся поверх. После SEC-05 — вся существующая сюита зелёная + regen lock + pip-audit.
2. **API-06** — тривиально, унифицирует ожидания длины пароля для остальных тестов.
3. **Миграция `0026`** (+ обновить `models.py User`) — нужна до API-07/API-11 кода.
4. **API-07** (`tokens_valid_after`+`iat`) → **API-05** (ротация, переиспользует revocation).
5. **API-11** (lockout, зависит от `0026`).
6. **SEC-08 + SEC-10** вместе (те же return-блоки/строки логов).
7. **API-08** (allowlist).
8. **SEC-09** — только регресс-тест (бэкенд уже удовлетворён).
9. **security-reviewer** по всему диффу.

---

## Task SEC-05: python-jose → PyJWT (foundation)

**Files:** Modify `auth_service.py`, `requirements.txt`; Test: `tests/test_auth_hardening.py` (create).

- [ ] **Step 1: Failing test** — create `tests/test_auth_hardening.py`:

```python
import jwt as _pyjwt
import auth_service


def test_tokens_use_pyjwt_not_jose():
    assert hasattr(auth_service.jwt, "ExpiredSignatureError")
    assert auth_service.jwt.__name__ == "jwt"


def test_access_token_roundtrip_hs256():
    tok = auth_service.create_access_token({"sub": "1", "email": "a@b.c"})
    payload = _pyjwt.decode(tok, auth_service.SECRET_KEY, algorithms=[auth_service.ALGORITHM])
    assert payload["sub"] == "1"
    assert payload["type"] == "access"
    assert payload["jti"]


def test_expired_access_token_returns_none():
    from datetime import timedelta
    tok = auth_service.create_access_token({"sub": "1", "email": "a@b.c"}, expires_delta=timedelta(seconds=-1))
    assert auth_service.decode_access_token(tok) is None


def test_wrong_secret_refresh_returns_none():
    bad = _pyjwt.encode({"sub": "1", "type": "refresh", "jti": "x"}, "WRONG", algorithm="HS256")
    assert auth_service.decode_refresh_token(bad) is None
```

- [ ] **Step 2: Run → RED** — `PYTHONUTF8=1 python -X utf8 -m pytest tests/test_auth_hardening.py -v` (fails: jose имеет JWTError, не ExpiredSignatureError).

- [ ] **Step 3: Implement** — in `auth_service.py`:
  - Replace `from jose import JWTError, jwt` → `import jwt` + `from jwt import InvalidTokenError`.
  - `jwt.encode(...)` / `jwt.decode(..., algorithms=[ALGORITHM])` calls: API-identical, no change to call bodies. Keep `algorithms=[ALGORITHM]` explicit.
  - `except JWTError:` (both sites) → `except InvalidTokenError:` (PyJWT `ExpiredSignatureError` ⊂ `InvalidTokenError` → expired+malformed both → return None, preserves behavior).
  - Verify alg stays HS256, same SECRET_KEY/REFRESH_SECRET_KEY, same claims, naive-UTC `exp` (PyJWT treats naive as UTC).
  - `requirements.txt`: replace `python-jose[cryptography]>=3.3.0,<4.0.0` → `PyJWT>=2.10,<3.0`. Keep `cryptography` (Fernet broker-token enc). python-jose fully removable (sole importer).

- [ ] **Step 4: Run → GREEN** — `PYTHONUTF8=1 python -X utf8 -m pytest tests/test_auth_hardening.py -v` + full auth regression: `PYTHONUTF8=1 python -X utf8 -m pytest tests/ -k auth -q`.

- [ ] **Step 5: Lock regen (отложить пользователю)** — regen `requirements.lock` нужно в CI py3.11 (`regenerate-lock` workflow) — на dev py3.14 не делать. Отметить: после merge запустить workflow; pip-audit hard-fail (INFRA-10) разблокируется.

- [ ] **Step 6: Commit** — NO-COMMIT, пропустить.

**Risk:** Уже выпущенные токены — БЕЗ риска (идентичный HS256/secret/claims, jose↔PyJWT взаимозаменяемы).

---

## Task API-06: Unify password min-length → 12

**Files:** Modify `schemas.py`, `routers/auth.py`; Test: `tests/test_auth_hardening.py`.

- [ ] **Step 1: Failing test** (append):

```python
def test_change_password_rejects_short_new_password(test_app):
    db = test_app["db"]
    user, _ = _make_user(db, "pw@test.com")
    r = test_app["client"].post(
        "/auth/change-password",
        json={"old_password": "pass1234", "new_password": "short11chr"},
        headers=_auth_headers(user),
    )
    assert r.status_code in (400, 422)
```
> `_make_user`, `_auth_headers` живут в `tests/integration/test_pr26_endpoints.py` — импортировать оттуда или продублировать минимально. Проверить фактическое имя fixture `test_app`.

- [ ] **Step 2: Run → RED.**

- [ ] **Step 3: Implement:**
  - `schemas.py:199` → `min_length=12, max_length=128`.
  - `schemas.py:193` (`PasswordResetConfirm.new_password`) → add `Field(..., min_length=12, max_length=128)`.
  - `routers/auth.py` change-pw (`:384-388`) и reset-confirm (`:635-636`): `< 6` → `< 12`, message «минимум 12 символов».

- [ ] **Step 4: Run → GREEN.**
- [ ] **Step 5: Commit** — NO-COMMIT.

---

## Task 0026-migration: auth-hardening columns (для API-07 + API-11)

**Files:** Create `alembic/versions/0026_auth_hardening.py`; Modify `models.py` (User).

- [ ] **Step 1: Update `models.py` User** — add three columns (ORM и миграция должны совпадать, тесты используют `create_all`):

```python
    failed_login_count = Column(Integer, nullable=False, server_default="0")
    locked_until = Column(DateTime, nullable=True)
    tokens_valid_after = Column(DateTime, nullable=True)
```

- [ ] **Step 2: Create migration** — `down_revision = "0025_account_pnl_health_cache"`, `batch_alter_table` (SQLite-safe):

```python
def upgrade():
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("failed_login_count", sa.Integer(), nullable=False, server_default="0"))
        b.add_column(sa.Column("locked_until", sa.DateTime(), nullable=True))
        b.add_column(sa.Column("tokens_valid_after", sa.DateTime(), nullable=True))

def downgrade():
    with op.batch_alter_table("users") as b:
        b.drop_column("tokens_valid_after")
        b.drop_column("locked_until")
        b.drop_column("failed_login_count")
```

- [ ] **Step 3: Roundtrip verify:**
```
PYTHONUTF8=1 python -X utf8 -m alembic upgrade head
PYTHONUTF8=1 python -X utf8 -m alembic downgrade -1
PYTHONUTF8=1 python -X utf8 -m alembic upgrade head
```
Expected: clean up/down/up. `server_default="0"` обязателен (backfill существующих строк).

- [ ] **Step 4: Commit** — NO-COMMIT.

---

## Task API-07: Password reset/change invalidates active JWTs

**Files:** Modify `auth_service.py` (add `iat`, check `tokens_valid_after`), `routers/auth.py` (set marker), `schemas.py` (TokenData `iat_ts`); Test: `tests/test_auth_hardening.py`.

- [ ] **Step 1: Failing test:**

```python
def test_password_reset_invalidates_existing_access_token(test_app):
    db = test_app["db"]
    from models import PasswordResetTokenORM
    from utils.datetime_utils import utc_now_naive
    from datetime import timedelta
    user, _ = _make_user(db, "inv@test.com")
    headers = _auth_headers(user)
    assert test_app["client"].get("/auth/me", headers=headers).status_code == 200
    db.add(PasswordResetTokenORM(token="reset-inv-1", user_id=user.id,
        created_at=utc_now_naive(), expires_at=utc_now_naive()+timedelta(hours=1)))
    db.commit()
    r = test_app["client"].post("/auth/password-reset/confirm",
        json={"token": "reset-inv-1", "new_password": "brandnew_password_123"})
    assert r.status_code == 200
    assert test_app["client"].get("/auth/me", headers=headers).status_code == 401
```
> Проверить реальную модель reset-токена (имя ORM/поля) перед написанием.

- [ ] **Step 2: Run → RED** (текущий токен остаётся валиден → 200).

- [ ] **Step 3: Implement:**
  - `auth_service.create_access_token`/`create_refresh_token`: add `"iat": utc_now_naive()` claim.
  - `schemas.TokenData`: add `iat_ts: Optional[int] = None`; populate в `decode_*`.
  - `get_current_user` (после загрузки user) и `refresh_tokens`: `if user.tokens_valid_after and token_iat < user.tokens_valid_after: raise/return None`. Сравнение в naive-UTC, секундное разрешение (−1s leeway на маркере чтобы token той же секунды не выживал).
  - reset-confirm (`routers/auth.py:~643`) и change-password (`:~390`): `user.tokens_valid_after = utc_now_naive()`; commit.

- [ ] **Step 4: Run → GREEN.**
- [ ] **Step 5: Commit** — NO-COMMIT.

**Risk:** iat/marker секундное разрешение — leeway −1s. Применяем и к change-password (зафиксировано).

---

## Task API-05: Refresh-token rotation + reuse detection

**Files:** Modify `auth_service.py` (`refresh_tokens`); Test: `tests/test_auth_hardening.py`.

- [ ] **Step 1: Failing test:**

```python
def test_refresh_rotates_and_revokes_old_token(test_app):
    db = test_app["db"]
    user, _ = _make_user(db, "rot@test.com")
    _, refresh = auth_service.create_token_pair(user.id, user.email)
    r1 = test_app["client"].post("/auth/refresh", json={"refresh_token": refresh})
    assert r1.status_code == 200
    new_refresh = r1.json().get("refresh_token")  # см. SEC-08 — если тело без токена, читать из cookie
    r2 = test_app["client"].post("/auth/refresh", json={"refresh_token": refresh})
    assert r2.status_code == 401
```
> ВНИМАНИЕ порядка: если SEC-08 уже выполнен (токены не в теле), этот тест должен брать refresh из cookie (`r1.cookies`), а replay слать через cookie. Сначала API-05 (до SEC-08) или адаптировать тест под cookie. Делать API-05 ДО SEC-08.

- [ ] **Step 2: Run → RED** (старый refresh продолжает работать → r2=200).

- [ ] **Step 3: Implement** `auth_service.refresh_tokens`:
  - после decode: `if is_token_revoked(db, token_data.jti): return None` (reuse-detection).
  - on success: `revoke_token(db, jti=token_data.jti, user_id=..., exp_ts=..., reason="rotated")` ПЕРЕД выпуском новой пары.
  - вернуть новую пару.

- [ ] **Step 4: Run → GREEN.**
- [ ] **Step 5: Commit** — NO-COMMIT.

**Risk:** double-submit refresh из одного истёкшего access → второй 401. **ПРОВЕРИТЬ** `frontend/src/lib/apiClient.ts` single-flight'ит refresh (один in-flight refresh, остальные ждут). Если нет — flag (strict ротация может разлогинивать при гонке). По умолчанию strict.

---

## Task API-11: Account-level lockout

**Files:** Modify `config.py`, `auth_service.py` (`authenticate_user`); Test: `tests/test_auth_hardening.py`. (Колонки — из `0026`.)

- [ ] **Step 1: Failing test:**

```python
def test_account_lockout_after_max_failed_attempts(test_app, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "LOGIN_MAX_FAILED_ATTEMPTS", 3)
    db = test_app["db"]
    user, _ = _make_user(db, "lock@test.com")
    for _ in range(3):
        test_app["client"].post("/auth/login", json={"email": "lock@test.com", "password": "wrong-pass-12"})
    db.refresh(user)
    assert user.locked_until is not None
    # даже верный пароль теперь отвергается
    r = test_app["client"].post("/auth/login", json={"email": "lock@test.com", "password": "pass1234"})
    assert r.status_code in (401, 423, 429)
```
> Ассертить на `user.locked_until` (DB-state детерминирован независимо от IP-limiter, который читается на import). Не полагаться на код ответа от limiter.

- [ ] **Step 2: Run → RED.**

- [ ] **Step 3: Implement:**
  - `config.py` (SECURITY block): `LOGIN_MAX_FAILED_ATTEMPTS: int = int(os.getenv("LOGIN_MAX_FAILED_ATTEMPTS", "10"))`, `LOGIN_LOCKOUT_MINUTES: int = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15"))`.
  - `authenticate_user`: до проверки пароля — `if user.locked_until and user.locked_until > utc_now_naive(): return None`. На неверный пароль: `failed_login_count += 1`; если `>= MAX` → `locked_until = now + LOCKOUT_MINUTES`, reset count; commit. На успех: `failed_login_count = 0`, `locked_until = None`. Generic 401 (не раскрывать lock-state).

- [ ] **Step 4: Run → GREEN.**
- [ ] **Step 5: Commit** — NO-COMMIT.

**Risk — victim-DoS:** атакующий лочит чужой email. Митигация (зафиксировано): порог 10, лок 15 мин, generic 401, self-healing. Достаточно для pre-launch.

---

## Task SEC-08 + SEC-10: Drop body token + redact email logs (вместе — те же блоки)

**Files:** Modify `routers/auth.py`, `schemas.py` (AuthSuccess), create `utils/log_redaction.py`; Test: `tests/test_auth_hardening.py`.

- [ ] **Step 1: Failing tests:**

```python
def test_login_does_not_return_token_in_body(test_app):
    db = test_app["db"]; _make_user(db, "body@test.com")
    r = test_app["client"].post("/auth/login", json={"email": "body@test.com", "password": "pass1234"})
    assert r.status_code == 200
    body = r.json()
    assert "access_token" not in body and "refresh_token" not in body
    assert any("access" in c for c in r.cookies)  # cookie всё ещё ставится

def test_mask_email_redacts_pii():
    from utils.log_redaction import mask_email
    out = mask_email("alice@example.com")
    assert "alice" not in out and "example" not in out and out.endswith(".com")
    assert mask_email("") == "<none>" and mask_email(None) == "<none>"
```

- [ ] **Step 2: Run → RED.**

- [ ] **Step 3: Implement:**
  - `utils/log_redaction.py`: `mask_email(email) -> "a***@e***.tld"`, None/"" → `"<none>"`.
  - `schemas.py`: `class AuthSuccess(BaseModel): token_type: str="bearer"; expires_in: int; authenticated: bool=True`.
  - `routers/auth.py` register/login/refresh/oauth-callback: `response_model=AuthSuccess`, убрать `access_token`/`refresh_token` из тела (куки через `set_auth_cookies` без изменений). OAuth callback оставить non-secret `user`-блок без токенов.
  - Заменить cleartext-email во ВСЕХ перечисленных логах на `mask_email(...)` (или `user_id` где есть).
  - **НЕ ТРОГАТЬ** admin impersonate (`routers/admin.py`) — он намеренно отдаёт токен.

- [ ] **Step 4: Run → GREEN** + проверить, что существующие тесты не ждут токен в теле login/register/refresh (impersonate в admin — не трогаем).

> caplog + `propagate=False` (logger.py): тест на лог может не поймать через caplog — привязать handler к `logging.getLogger("atom.auth")` или `caplog.set_level(INFO, logger="atom")`.

- [ ] **Step 5: Commit** — NO-COMMIT.

---

## Task API-08: OAuth redirect_uri allowlist

**Files:** Modify `config.py`, `routers/auth.py` (или `oauth_service.py`); Test: `tests/test_auth_hardening.py`.

- [ ] **Step 1: Failing test:**

```python
def test_oauth_authorize_rejects_unlisted_redirect(test_app, monkeypatch):
    from config import settings
    monkeypatch.setattr(settings, "OAUTH_ALLOWED_REDIRECT_URIS", ["https://app.empirik.io/auth/callback"])
    r = test_app["client"].get("/auth/oauth/google/authorize",
        params={"redirect_uri": "https://evil.example.com/steal"})
    assert r.status_code == 400
```
> Если провайдер не сконфигурён в тесте — провайдер-check может вернуть 400 первым; замокать `oauth_service.get_provider` стабом, чтобы тестировать именно allowlist-ветку.

- [ ] **Step 2: Run → RED.**

- [ ] **Step 3: Implement:**
  - `config.py`: `OAUTH_ALLOWED_REDIRECT_URIS: List[str]` из env (comma), default `[]` (паттерн `_parse_cors_origins`).
  - guard `_assert_allowed_redirect(uri)`: `if uri not in settings.OAUTH_ALLOWED_REDIRECT_URIS: raise HTTPException(400, "redirect_uri не разрешён")`. Вызвать в начале `oauth_authorize` И `oauth_callback`. Exact-match.

- [ ] **Step 4: Run → GREEN.**
- [ ] **Step 5: Commit** — NO-COMMIT.

---

## Task SEC-09: Reset token not in GET (regression только — бэкенд уже удовлетворён)

**Files:** Test: `tests/test_auth_hardening.py`.

- [ ] **Step 1: Add regression test:**

```python
def test_reset_confirm_is_post_only(test_app):
    r = test_app["client"].get("/auth/password-reset/confirm?token=x&new_password=yyyyyyyyyyyy")
    assert r.status_code in (404, 405)
```

- [ ] **Step 2: Run → GREEN** (уже POST-only). Остаток (фронт reset-link URL scrub) — Sprint 5.
- [ ] **Step 3: Commit** — NO-COMMIT.

---

## Final verification

- [ ] Full suite: `PYTHONUTF8=1 python -X utf8 -m pytest tests/unit tests/integration tests/test_auth_hardening.py -q` — всё зелёное, без регрессий (647+ baseline).
- [ ] App import smoke: `PYTHONUTF8=1 python -X utf8 -c "import main; print(len(main.app.routes))"`.
- [ ] Alembic roundtrip (см. 0026).
- [ ] `security-reviewer` субагент по всему диффу: reuse-detection гонки, lockout victim-DoS, allowlist exact-match, нет токенов/PII в логах, PyJWT alg-confusion (algorithms=[HS256] явно задан).

## Self-Review
1. **Spec coverage:** SEC-05/08/09/10, API-05/06/07/08/11 — все 9 имеют task. SEC-09 сведён к регрессу (бэкенд уже ок) — задокументировано.
2. **Placeholders:** тест-код приведён; «проверить реальную модель/fixture» — явные verify-инструкции, не placeholder логики.
3. **Type consistency:** `tokens_valid_after`/`failed_login_count`/`locked_until` (models+migration), `AuthSuccess`, `mask_email`, `OAUTH_ALLOWED_REDIRECT_URIS`, `LOGIN_MAX_FAILED_ATTEMPTS`/`LOGIN_LOCKOUT_MINUTES` — согласованы между задачами.

## Открытые решения (дефолты приняты, env-конфигурируемы — veto пользователя возможен)
- (a) lockout policy hard-lock vs backoff → выбран hard-lock 10/15мин generic-401.
- (b) prod OAuth redirect URIs → env, default пусто (задать на деплое).
- (c) refresh strict vs grace → strict + проверка single-flight во фронте.
- (d) tokens_valid_after на change-password → да.
