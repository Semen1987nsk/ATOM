from datetime import datetime

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
        account_id=acc.id, symbol="SBER", direction=models.TradeDirection.LONG,
        entry_price=100, quantity=1, entry_at=datetime.now(),
        screenshot_url=f"/uploads/screenshots/{fname}",
    )
    db_session.add(trade)
    db_session.commit()

    pd_deletion.finalize_deletion(db_session, user)

    assert not fpath.exists(), "screenshot файл должен быть удалён при анонимизации"
    db_session.refresh(trade)
    assert trade.screenshot_url is None
