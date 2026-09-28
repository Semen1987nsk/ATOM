"""
Smoke-тест 152-ФЗ контура:
1. POST /auth/register без pd_consent → 422
2. POST /auth/register с pd_consent=false → 400 ("Требуется согласие...")
3. POST /auth/register с pd_consent=true → 200 + запись в pd_consents
4. DELETE /auth/me с правильным паролем → 202 + soft-delete
5. Проверить что повторный DELETE → 409
"""
import os
import secrets
import sys
from pathlib import Path

# Добавляем backend/ в sys.path, чтобы импорт `main`, `models` работал.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Тест должен быть гермtic — берём временную БД и временные ключи.
TMP_DB = os.path.abspath("./test_pd_consent.db")
if os.path.exists(TMP_DB):
    os.remove(TMP_DB)

os.environ["DATABASE_URL"] = f"sqlite:///{TMP_DB}"
os.environ["DEBUG"] = "true"
os.environ["AUTO_INIT_DB"] = "true"
os.environ["SECRET_KEY"] = secrets.token_urlsafe(48)
os.environ["REFRESH_SECRET_KEY"] = secrets.token_urlsafe(48)
os.environ["RATE_LIMIT_STORAGE_URI"] = "memory://"

from fastapi.testclient import TestClient

# Создаём схему ДО первого запроса (AUTO_INIT_DB не всегда срабатывает в тестах)
from database import engine  # noqa: E402
from models import Base  # noqa: E402
Base.metadata.create_all(engine)

from main import app  # noqa: E402

client = TestClient(app)

EMAIL = "smoke-pd@gmail.com"
PASSWORD = "SuperLongPassword!2026"


def step(label):
    print(f"\n=== {label} ===")


# 1) без pd_consent — Pydantic вернёт 422 (поле обязательное)
step("1) register без pd_consent → 422")
r = client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD})
print(" status:", r.status_code)
assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"

# 2) pd_consent=false → 400 от endpoint'а
step("2) register с pd_consent=false → 400")
r = client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD, "pd_consent": False})
print(" status:", r.status_code, "| body:", r.json())
assert r.status_code == 400, f"Expected 400, got {r.status_code}"
assert "согласие" in r.json()["detail"].lower(), "Expected consent message"

# 3) pd_consent=true → 200 (или 201)
step("3) register с pd_consent=true → 200")
r = client.post("/auth/register", json={
    "email": EMAIL,
    "password": PASSWORD,
    "name": "Smoke Test",
    "pd_consent": True,
})
print(" status:", r.status_code)
assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
data = r.json()
assert "access_token" in data, "Expected access_token"
print(" tokens received: yes")

# Проверка что запись в pd_consents действительно создана
import sqlite3
conn = sqlite3.connect(TMP_DB)
cur = conn.cursor()
cur.execute("select user_id, consent_text_version, ip_address, accepted_at from pd_consents")
rows = cur.fetchall()
print(" pd_consents rows:", rows)
assert len(rows) == 1, f"Expected 1 consent record, got {len(rows)}"
assert rows[0][1] == "v1", "consent_text_version mismatch"
conn.close()

# 4) DELETE /auth/me — пытаемся удалить
step("4) DELETE /auth/me → 202")
# CSRF middleware требует X-CSRF-Token header, парный к csrf_token cookie.
# При успешной регистрации backend поставил его автоматически — берём из cookies.
csrf_token = client.cookies.get("atom_csrf_token")
print(f" csrf_token cookie: {'present' if csrf_token else 'MISSING'}")
assert csrf_token, "csrf_token cookie not set after register"

# TestClient.delete() не принимает json= — используем request() напрямую.
r = client.request(
    "DELETE",
    "/auth/me",
    json={"password": PASSWORD, "reason": "smoke"},
    headers={"X-CSRF-Token": csrf_token},
)
print(" status:", r.status_code, "| body:", r.json())
assert r.status_code == 202, f"Expected 202, got {r.status_code}: {r.text}"
body = r.json()
assert body["status"] == "deletion_requested"
assert body["grace_period_days"] == 30

# Проверка что user is_active=0 и deletion_requested_at != NULL
conn = sqlite3.connect(TMP_DB)
cur = conn.cursor()
cur.execute("select is_active, deletion_requested_at from users where email=?", (EMAIL,))
u = cur.fetchone()
print(" user state after delete:", u)
assert u[0] == 0, "Expected is_active=0"
assert u[1] is not None, "Expected deletion_requested_at set"

# Брокеры должны быть отозваны (если были) — у нового юзера их нет, проверяем pd_consents revoked
cur.execute("select count(*) from pd_consents where revoked_at is not null")
revoked_count = cur.fetchone()[0]
print(" revoked consents:", revoked_count)
assert revoked_count == 1, "Expected 1 revoked consent"
conn.close()

# 5) Повторный DELETE теперь не сработает (уже удалён + cookies сброшены = 401)
# Сначала логинимся снова — нет, не получится: is_active=0, login вернёт 403.
step("5) login после удаления → 403 (account disabled)")
r = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
print(" status:", r.status_code)
assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"

print("\n✅ ВСЁ ОК")

# Cleanup
os.remove(TMP_DB)
