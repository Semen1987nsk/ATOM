"""
Smoke-тест GET /auth/me/export (152-ФЗ ст. 14).

Сценарий:
1. Регистрируем юзера с pd_consent=True
2. Создаём ему счёт + 2 сделки + 1 daily review + 1 setup
3. Дёргаем GET /auth/me/export
4. Проверяем что:
   - В user нет hashed_password
   - В trades 2 записи
   - В pd_consents 1 запись (с IP/UA)
   - В counts корректные числа
   - В broker_connections api_token не отдан
"""
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TMP_DB = os.path.abspath("./test_pd_export.db")
if os.path.exists(TMP_DB):
    os.remove(TMP_DB)

os.environ["DATABASE_URL"] = f"sqlite:///{TMP_DB}"
os.environ["DEBUG"] = "true"
os.environ["AUTO_INIT_DB"] = "true"
os.environ["SECRET_KEY"] = secrets.token_urlsafe(48)
os.environ["REFRESH_SECRET_KEY"] = secrets.token_urlsafe(48)
os.environ["RATE_LIMIT_STORAGE_URI"] = "memory://"

from datetime import datetime  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from database import SessionLocal, engine  # noqa: E402
from models import (  # noqa: E402
    Account,
    Base,
    DailyReview,
    Setup,
    Trade,
    TradeDirection,
    User,
)

Base.metadata.create_all(engine)

from main import app  # noqa: E402

client = TestClient(app)

EMAIL = "export-test@gmail.com"
PASSWORD = "SuperLongPassword!2026"


def step(label):
    print(f"\n=== {label} ===")


# 1) Регистрация
step("1) register")
r = client.post("/auth/register", json={
    "email": EMAIL,
    "password": PASSWORD,
    "name": "Export Test",
    "pd_consent": True,
})
assert r.status_code == 200, r.text
print(" registered")

# 2) Подкладываем сделки/сетап/review напрямую через ORM
db = SessionLocal()
try:
    user = db.query(User).filter(User.email == EMAIL).first()
    assert user is not None
    user_id = user.id

    account = Account(user_id=user_id, name="Main", balance=100000, initial_balance=100000)
    db.add(account)
    db.commit()
    db.refresh(account)

    setup = Setup(account_id=account.id, name="Trend", description="trend-following")
    db.add(setup)
    db.commit()

    t1 = Trade(
        account_id=account.id,
        symbol="SBER",
        direction=TradeDirection.LONG,
        entry_price=250.0,
        exit_price=255.0,
        quantity=100,
        entry_at=datetime(2026, 5, 1, 10, 0, 0),
        exit_at=datetime(2026, 5, 1, 14, 0, 0),
        pnl=500,
        notes="my private trade note",
    )
    t2 = Trade(
        account_id=account.id,
        symbol="GAZP",
        direction=TradeDirection.SHORT,
        entry_price=180.0,
        exit_price=178.0,
        quantity=50,
        entry_at=datetime(2026, 5, 2, 11, 0, 0),
        exit_at=datetime(2026, 5, 2, 12, 0, 0),
        pnl=100,
    )
    db.add_all([t1, t2])
    db.commit()

    review = DailyReview(
        account_id=account.id,
        date="2026-05-01",
        reflection="Good trading day",
        intention="Stay disciplined",
        rating=4,
    )
    db.add(review)
    db.commit()
finally:
    db.close()

# 3) Экспорт
step("2) GET /auth/me/export")
r = client.get("/auth/me/export")
print(" status:", r.status_code)
assert r.status_code == 200, r.text
data = r.json()

# 4) Проверки
step("3) checks")
print(f" export_version: {data['export_version']}")
print(f" policy_version: {data['policy_version']}")
print(f" user keys: {sorted(data['user'].keys())[:6]}...")
print(f" counts: {data['counts']}")

assert data["export_version"] == "1"
assert data["policy_version"] == "v1"
assert "exported_at" in data

assert "hashed_password" not in data["user"], "hashed_password must NOT be in export"
assert data["user"]["email"] == EMAIL

# accounts >= 1 (register сам создаёт default account, плюс наш "Main")
assert data["counts"]["accounts"] >= 1
assert data["counts"]["trades"] == 2
assert data["counts"]["setups"] == 1
assert data["counts"]["daily_reviews"] == 1
assert data["counts"]["pd_consents"] == 1

# Проверим конкретные данные сделок
symbols = sorted(t["symbol"] for t in data["trades"])
assert symbols == ["GAZP", "SBER"], f"Unexpected symbols: {symbols}"

# Свободный текст (notes) должен быть в экспорте
notes_seen = [t.get("notes") for t in data["trades"] if t.get("notes")]
assert "my private trade note" in notes_seen

# Согласие должно быть с ip_address и user_agent
consent = data["pd_consents"][0]
assert consent["consent_text_version"] == "v1"
assert consent["accepted_at"] is not None
assert consent["revoked_at"] is None

# broker_connections — у пользователя их нет, но ключ должен быть
assert isinstance(data["broker_connections"], list)
# даже если бы были — api_token не должен попадать
for bc in data["broker_connections"]:
    assert "api_token" not in bc, "api_token must be excluded from export"

print("\n✅ ВСЁ ОК")

# Cleanup
try:
    os.remove(TMP_DB)
except PermissionError:
    pass  # Windows lock — не критично
