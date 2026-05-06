"""
Subscription / paywall service.

Один источник правды для:
- get_active_plan(db, user) — какой тариф активен сейчас
- get_user_trade_count(db, user) — сколько сделок у юзера на ВСЕХ его счетах
- require_pro(...)      — FastAPI Depends, кидает 402 если план не PRO+
- enforce_trade_limit(...) — вызывать при создании/импорте сделки

Дешёвая реализация: одна Subscription-row на user, plan=FREE по умолчанию.
Если subscription нет вообще, считаем FREE.

ЛИМИТЫ:
- FREE: 50 сделок суммарно, без AI, без advanced-аналитики
- PRO:  безлимит сделок, AI on, advanced on
- CORPORATE: то же что PRO + multi-account > 3 (на будущее)
"""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

import database
import models
import auth_service


FREE_PLAN_TRADE_LIMIT = 50


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
    """
    Проверяет, что юзер не упёрся в FREE-лимит. Вызывать ДО вставки новой сделки
    (POST /trades/ и каждой строки в /trades/import).

    На FREE: ≥ FREE_PLAN_TRADE_LIMIT → 402 с понятной ошибкой.
    На PRO+: пропускает.
    """
    plan = get_active_plan(db, user)
    if is_paid_plan(plan):
        return
    count = get_user_trade_count(db, user)
    if count >= FREE_PLAN_TRADE_LIMIT:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "trade_limit_reached",
                "current_plan": plan.value,
                "trade_count": count,
                "limit": FREE_PLAN_TRADE_LIMIT,
                "message": (
                    f"Достигнут лимит бесплатного тарифа: {FREE_PLAN_TRADE_LIMIT} сделок. "
                    "Оформите PRO для безлимита."
                ),
            },
        )
