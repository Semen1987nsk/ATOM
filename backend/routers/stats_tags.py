"""
Stats Tags Router — статистика по тегам сделок.

Вынесено из `routers/stats.py` (god-router, 1874 строки) как первый шаг
изолированного рефакторинга — тег-эндпоинт самодостаточен и не делит
вспомогательные функции с остальной dashboard-аналитикой.

Регистрируется в `main.py` дважды: как `tags_router` (без префикса,
URL `/tags/`) и как часть основного `stats_router` (с префиксом
`/stats`, URL `/stats/tags/`). Оба пути сохраняются для обратной
совместимости с фронтом.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

import database
import models
import auth_service

# Роутер для пути `/tags/` (включается без префикса в main.py).
router = APIRouter(tags=["stats"])

# Роутер для пути `/stats/tags/` (подмонтирован под `/stats` в main.py
# через основной `stats_router`). Экспортируется обратно в
# `routers.stats` ради сохранения существующего include в main.py
# и двойной регистрации эндпоинта на одном handler.
stats_prefixed_router = APIRouter(tags=["stats"])


@router.get("/tags/")
@stats_prefixed_router.get("/tags/")
async def get_all_tags(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """Get all unique tags used in trades with their statistics."""
    account_id = auth_service.get_account_id(db, current_user)
    trades = db.query(models.Trade).filter(
        models.Trade.account_id == account_id,
        models.Trade.pnl != None
    ).all()

    tag_stats = {}
    for t in trades:
        if not t.tags:
            continue
        for tag in t.tags:
            tag_lower = tag.lower()
            if tag_lower not in tag_stats:
                tag_stats[tag_lower] = {"tag": tag_lower, "count": 0, "pnl": 0, "wins": 0}
            tag_stats[tag_lower]["count"] += 1
            tag_stats[tag_lower]["pnl"] += float(t.pnl or 0)
            if t.pnl and t.pnl > 0:
                tag_stats[tag_lower]["wins"] += 1

    result = []
    for tag, data in tag_stats.items():
        result.append({
            "tag": data["tag"],
            "count": data["count"],
            "pnl": round(data["pnl"], 2),
            "win_rate": round((data["wins"] / data["count"]) * 100, 1) if data["count"] > 0 else 0
        })

    return sorted(result, key=lambda x: x["count"], reverse=True)
