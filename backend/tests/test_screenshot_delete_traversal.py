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

    # Эмулируем реальный cwd воркера — на два уровня ниже victim
    # (напр. `backend/` при victim в корне репо).
    worker_cwd = tmp_path / "cwd_stub" / "nested"
    worker_cwd.mkdir(parents=True)

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
    monkeypatch.chdir(worker_cwd)

    user = models.User(id=1, email="u@e.com", is_active=1, settings={})

    class _FakeAuth:
        @staticmethod
        def get_account_id(db, u):
            return acc.id

    monkeypatch.setattr(trades_router, "auth_service", _FakeAuth)

    await trades_router.delete_screenshot(trade.id, db=db_session, current_user=user)

    # Фикс не должен удалять файл вне UPLOAD_DIR.
    assert victim.exists(), "path traversal: файл вне UPLOAD_DIR был удалён"
