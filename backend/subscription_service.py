"""
Subscription / paywall service.

Один источник правды для:
- get_active_plan(db, user) — какой тариф активен сейчас
- get_user_trade_count(db, user) — сколько сделок у юзера на ВСЕХ его счетах
- require_pro(...)      — FastAPI Depends, кидает 402 если план не PRO+
- enforce_trade_limit(...) — вызывать при создании/импорте сделки

Дешёвая реализация: одна Subscription-row на user, plan=FREE по умолчанию.
Если subscription нет вообще, считаем FREE.

ЛИМИТЫ (ADR-0009, MVP flat freemium):
- FREE: безлимит сделок + импорт + 6 базовых метрик; без AI/автосинка/MAE-MFE/advanced
- PRO:  всё разморожено (AI, MAE/MFE, advanced-метрики, автосинк, до 5 счетов)
- CORPORATE: то же что PRO + multi-account (на будущее)
Лимит «50 сделок» снят (ADR-0005/0009) — Free безлимитен по числу сделок,
импорт всегда бесплатен; платный гейт — автосинк/AI/advanced (см. require_pro).
"""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

import database
import models
import auth_service


def get_active_subscription(db: Session, user: models.User) -> Optional[models.Subscription]:
    """
    Возвращает активную (is_active=1, не истёкшую) подписку юзера.
    None означает FREE по умолчанию.
    """
    sub = (
        db.query(models.Subscription)
        .filter(
            models.Subscription.user_id == user.id,
            models.Subscription.is_active == 1,
        )
        .order_by(models.Subscription.started_at.desc())
        .first()
    )
    return sub


def get_active_plan(db: Session, user: models.User) -> models.SubscriptionPlan:
    sub = get_active_subscription(db, user)
    if sub is None:
        return models.SubscriptionPlan.FREE
    # Истёкшая подписка → FREE.
    if sub.expires_at is not None:
        from utils.datetime_utils import utc_now_naive

        if sub.expires_at < utc_now_naive():
            return models.SubscriptionPlan.FREE
    return sub.plan or models.SubscriptionPlan.FREE


def is_paid_plan(plan: models.SubscriptionPlan) -> bool:
    return plan in (models.SubscriptionPlan.PRO, models.SubscriptionPlan.CORPORATE)


def get_user_trade_count(db: Session, user: models.User) -> int:
    """
    Сколько сделок у юзера на всех его счетах. Используется для FREE-лимита.
    """
    count = (
        db.query(models.Trade)
        .join(models.Account, models.Trade.account_id == models.Account.id)
        .filter(models.Account.user_id == user.id)
        .count()
    )
    return count


def require_pro(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user),
) -> models.User:
    """
    FastAPI dependency: разрешает запрос ТОЛЬКО на платном тарифе.
    Иначе 402 Payment Required с честной диагностикой.
    """
    plan = get_active_plan(db, current_user)
    if not is_paid_plan(plan):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "pro_required",
                "current_plan": plan.value,
                "message": "Эта функция доступна на тарифе PRO. Оформите подписку на /pricing.",
            },
        )
    return current_user


def enforce_trade_limit(db: Session, user: models.User) -> None:
    """No-op: Free безлимитен по числу сделок (ADR-0009; лимит «50» снят).

    Оставлено как seam в точках создания/импорта сделок (trades.py). При
    подключении reverse-trial (ADR-0005) сюда может вернуться per-feature
    гейтинг, но лимит по КОЛИЧЕСТВУ сделок не вернётся — импорт всегда бесплатен
    (это aha-момент активации, а не depth-gate).
    """
    return None
