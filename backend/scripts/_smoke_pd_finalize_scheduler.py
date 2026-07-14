"""
Smoke-тест: SyncScheduler._check_pd_finalizations() вызывает
pd_deletion.run_pending_deletions() и анонимизирует юзера у которого
deletion_requested_at > 30 дней назад.

Проверяем end-to-end:
1. Создаём юзера + согласие
2. Ставим deletion_requested_at = now() - 31 day
3. Сбрасываем _last_pd_finalize_at = None (первый запуск)
4. Вызываем scheduler._check_pd_finalizations()
5. Проверяем что email анонимизирован → "deleted-{id}@anon.empirik"
"""
import asyncio
import os
import secrets
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

TMP_DB = os.path.abspath("./test_pd_finalize_scheduler.db")
if os.path.exists(TMP_DB):
    os.remove(TMP_DB)

os.environ["DATABASE_URL"] = f"sqlite:///{TMP_DB}"
os.environ["DEBUG"] = "true"
os.environ["AUTO_INIT_DB"] = "true"
os.environ["SECRET_KEY"] = secrets.token_urlsafe(48)
os.environ["REFRESH_SECRET_KEY"] = secrets.token_urlsafe(48)
os.environ["RATE_LIMIT_STORAGE_URI"] = "memory://"

from database import SessionLocal, engine  # noqa: E402
from models import Base, User, PdConsent  # noqa: E402
from utils.datetime_utils import utc_now_naive  # noqa: E402
from sync_scheduler import scheduler  # noqa: E402

# Создаём схему
Base.metadata.create_all(engine)


async def main():
    db = SessionLocal()

    # 1) Юзер с истёкшим grace period (32 дня назад)
    user = User(
        email="expired@gmail.com",
        name="Expired Account",
        hashed_password="x" * 60,
        is_active=0,
        deletion_requested_at=utc_now_naive() - timedelta(days=32),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id
    print(f"Created user_id={user_id} email={user.email} requested_at={user.deletion_requested_at}")

    # Добавим pd_consent чтобы было что отзывать
    consent = PdConsent(
        user_id=user_id,
        consent_text_version="v1",
        accepted_at=utc_now_naive() - timedelta(days=60),
    )
    db.add(consent)
    db.commit()

    # 2) Юзер с НЕ истёкшим grace period (5 дней назад) — НЕ должен быть тронут
    fresh = User(
        email="fresh@gmail.com",
        name="Fresh Request",
        hashed_password="y" * 60,
        is_active=0,
        deletion_requested_at=utc_now_naive() - timedelta(days=5),
    )
    db.add(fresh)
    db.commit()
    db.refresh(fresh)
    fresh_id = fresh.id

    # 3) Юзер активный — НЕ должен быть тронут
    active = User(
        email="active@gmail.com",
        name="Active",
        hashed_password="z" * 60,
        is_active=1,
        deletion_requested_at=None,
    )
    db.add(active)
    db.commit()
    db.refresh(active)
    active_id = active.id
    db.close()

    # 4) Сбрасываем scheduler-state и вызываем
    scheduler._last_pd_finalize_at = None
    print("\nCalling scheduler._check_pd_finalizations()...")
    await scheduler._check_pd_finalizations()

    # 5) Проверка
    db = SessionLocal()
    try:
        u_expired = db.query(User).filter(User.id == user_id).first()
        u_fresh = db.query(User).filter(User.id == fresh_id).first()
        u_active = db.query(User).filter(User.id == active_id).first()

        print(f"\nExpired user after finalize: email={u_expired.email}, name={u_expired.name}")
        print(f"Fresh user (should be untouched): email={u_fresh.email}, name={u_fresh.name}")
        print(f"Active user (should be untouched): email={u_active.email}, name={u_active.name}")

        assert u_expired.email == f"deleted-{user_id}@anon.empirik", (
            f"Expected anonymized email, got {u_expired.email!r}"
        )
        assert u_expired.name is None, "Expected name=NULL"

        assert u_fresh.email == "fresh@gmail.com", "Fresh user must NOT be touched"
        assert u_active.email == "active@gmail.com", "Active user must NOT be touched"

        # Scheduler должен был обновить _last_pd_finalize_at
        assert scheduler._last_pd_finalize_at is not None, (
            "_last_pd_finalize_at must be set after run"
        )
        print(f"\n_last_pd_finalize_at set: {scheduler._last_pd_finalize_at}")

        # Повторный вызов — должен no-op (не прошло 24 ч)
        print("\nSecond call (within 24h) — should be no-op...")
        prev_ts = scheduler._last_pd_finalize_at
        await scheduler._check_pd_finalizations()
        assert scheduler._last_pd_finalize_at == prev_ts, (
            "Second call within 24h should not update timestamp"
        )
        print("OK — no-op confirmed")

        print("\n✅ ВСЁ ОК")
    finally:
        db.close()

    if os.path.exists(TMP_DB):
        try:
            os.remove(TMP_DB)
        except PermissionError:
            pass  # Windows lock, не критично


if __name__ == "__main__":
    asyncio.run(main())
