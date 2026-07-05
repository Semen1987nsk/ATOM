"""
routers.payments — заготовка под YooKassa / CloudPayments.

Сейчас:
- POST /payments/checkout-link {plan: 'pro'|'corporate'} → возвращает stub-URL.
- POST /payments/webhook                                 → принимает stub-payload и активирует подписку.
- GET  /payments/me                                       → возвращает текущий план юзера.

Когда подключим реальный YooKassa:
1. Создаёшь shop_id + secret_key в личном кабинете.
2. Кладёшь в env: YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY.
3. В `_create_checkout_link` заменяешь stub на yookassa.Payment.create(...).
4. В `_handle_webhook` валидируешь подпись по secret_key.

Контракт фронта (`frontend/src/app/pricing/page.tsx`):
- Кнопка «Выбрать PRO» → POST /payments/checkout-link?plan=pro → редирект на confirmation_url.
- После оплаты YooKassa посылает webhook → меняет Subscription.plan на PRO.
"""
from __future__ import annotations

import os
import secrets
from datetime import timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

import database
import models
import auth_service
from logger import get_logger
from utils.datetime_utils import utc_now_naive

log = get_logger("payments")

router = APIRouter(prefix="/payments", tags=["payments"])


# ──────────────────────────────────────────────────────────────────
#  Schemas
# ──────────────────────────────────────────────────────────────────


class CheckoutLinkIn(BaseModel):
    plan: Literal["pro", "corporate"] = "pro"


class CheckoutLinkOut(BaseModel):
    payment_id: str
    confirmation_url: str
    plan: str
    amount: float
    currency: str = "RUB"
    is_stub: bool


class CurrentPlanOut(BaseModel):
    plan: str
    is_active: bool
    started_at: Optional[str] = None
    expires_at: Optional[str] = None


class WebhookIn(BaseModel):
    """
    Унифицированный stub-payload, чтобы можно было руками потестить активацию.
    Реальный YooKassa-webhook имеет собственную форму — будет адаптер.
    """
    payment_id: str
    user_email: str
    plan: Literal["pro", "corporate"]
    status: Literal["succeeded", "canceled", "pending"]
    amount: float = 399.0


# ──────────────────────────────────────────────────────────────────
#  Pricing config (один источник правды)
# ──────────────────────────────────────────────────────────────────

PLAN_PRICES: dict[str, float] = {
    "pro": 399.0,         # ₽/мес
    "corporate": 4990.0,  # ₽/мес, индивидуально
}

PLAN_DURATION_DAYS: dict[str, int] = {
    "pro": 30,
    "corporate": 30,
}


# ──────────────────────────────────────────────────────────────────
#  Endpoints
# ──────────────────────────────────────────────────────────────────


@router.get("/me", response_model=CurrentPlanOut)
def get_my_plan(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user),
):
    """Возвращает активную подписку юзера. None плана = FREE."""
    sub = (
        db.query(models.Subscription)
        .filter(models.Subscription.user_id == current_user.id, models.Subscription.is_active == 1)
        .order_by(models.Subscription.started_at.desc())
        .first()
    )
    if sub is None:
        return CurrentPlanOut(plan="free", is_active=True)
    return CurrentPlanOut(
        plan=sub.plan.value if hasattr(sub.plan, "value") else str(sub.plan),
        is_active=bool(sub.is_active),
        started_at=sub.started_at.isoformat() if sub.started_at else None,
        expires_at=sub.expires_at.isoformat() if sub.expires_at else None,
    )


@router.post("/checkout-link", response_model=CheckoutLinkOut)
def create_checkout_link(
    payload: CheckoutLinkIn,
    request: Request,
    current_user: models.User = Depends(auth_service.get_current_user),
):
    """
    Создаёт checkout-сессию для оплаты.

    Сейчас — STUB: возвращает локальный URL `/payments/stub-confirm?...`,
    чтобы фронт мог пройти весь happy path. В env есть YOOKASSA_SHOP_ID —
    переключаемся на реальный YooKassa SDK.
    """
    if payload.plan not in PLAN_PRICES:
        raise HTTPException(status_code=400, detail="Неизвестный план")

    amount = PLAN_PRICES[payload.plan]
    payment_id = secrets.token_urlsafe(16)

    yookassa_shop = os.getenv("YOOKASSA_SHOP_ID")
    if yookassa_shop:
        # TODO: подключить yookassa SDK когда будут реальные ключи
        log.warning("YOOKASSA_SHOP_ID set but real integration not implemented yet — falling back to stub")

    # STUB confirmation URL — фронт может редиректить туда и нажать «Подтвердить»
    base = str(request.base_url).rstrip("/")
    confirmation_url = (
        f"{base}/payments/stub-confirm"
        f"?payment_id={payment_id}"
        f"&user={current_user.email}"
        f"&plan={payload.plan}"
        f"&amount={amount}"
    )

    return CheckoutLinkOut(
        payment_id=payment_id,
        confirmation_url=confirmation_url,
        plan=payload.plan,
        amount=amount,
        currency="RUB",
        is_stub=True,
    )


@router.get("/stub-confirm")
def stub_confirm(payment_id: str, user: str, plan: str, amount: float, db: Session = Depends(database.get_db)):
    """
    Stub-симулятор успешной оплаты — DEV ONLY.

    PR 26: жёсткая проверка `settings.DEBUG` (не `os.getenv`, чтобы не
    обходилось env-trick'ом). В prod возвращает 404.
    """
    from config import settings as _settings
    if not _settings.DEBUG:
        raise HTTPException(status_code=404)

    user_obj = db.query(models.User).filter(models.User.email == user).first()
    if not user_obj:
        raise HTTPException(status_code=404, detail="User not found")

    _activate_subscription(db, user_obj, plan, amount, payment_id, "stub-confirm")
    return {"ok": True, "message": f"Stub payment confirmed: {plan} for {user}"}


@router.post("/webhook")
async def payment_webhook(request: Request, db: Session = Depends(database.get_db)):
    """
    PR 26: реальный YooKassa webhook handler.

    Защита:
    1. **HMAC signature**: проверяем `X-YooKassa-Signature` HMAC-SHA256 по
       `YOOKASSA_WEBHOOK_SECRET`. Без этого любой может POSTить fake-webhook
       и активировать платную подписку себе.
    2. **Idempotency**: дубликат `payment.id` → 200 без re-активации.
       YooKassa повторяет webhook до 30 раз пока не получит 200.
    3. **`payment.refunded`**: если приходит — деактивируем подписку.

    Stub-режим (DEBUG=true + WebhookIn-формат): принимаем для удобства dev,
    но в prod автоматически отключён.

    Документация YooKassa webhook: https://yookassa.ru/developers/using-api/webhooks
    """
    from config import settings as _settings

    raw_body = await request.body()
    signature_header = request.headers.get("X-YooKassa-Signature", "")

    # 1. Парсим JSON (поддержка YooKassa и stub формата)
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON")

    # 2. HMAC verification (если задан webhook secret)
    webhook_secret = os.getenv("YOOKASSA_WEBHOOK_SECRET", "")
    if webhook_secret:
        import hmac
        import hashlib
        expected = hmac.new(
            webhook_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature_header):
            log.warning("payment_webhook: HMAC mismatch — REJECTED. body_len=%d", len(raw_body))
            raise HTTPException(status_code=403, detail="invalid signature")
    elif not _settings.DEBUG:
        # Prod без webhook_secret = security incident.
        log.error("payment_webhook: YOOKASSA_WEBHOOK_SECRET not set in production — REJECTED")
        raise HTTPException(status_code=500, detail="webhook secret not configured")

    # 3. Парсим под два формата: real YooKassa и stub.
    yookassa_event = body.get("event")
    yookassa_payment = body.get("object") or {}

    if yookassa_event:
        # Real YooKassa format
        payment_id = yookassa_payment.get("id", "")
        status = yookassa_payment.get("status", "")
        amount_obj = yookassa_payment.get("amount", {})
        amount_rub = float(amount_obj.get("value", 0) or 0)
        metadata = yookassa_payment.get("metadata", {}) or {}
        user_id = metadata.get("user_id")
        plan = metadata.get("plan", "pro")

        if yookassa_event == "payment.succeeded":
            target_status = "succeeded"
        elif yookassa_event == "payment.canceled":
            target_status = "canceled"
        elif yookassa_event == "refund.succeeded":
            target_status = "refunded"
            payment_id = yookassa_payment.get("payment_id", payment_id)
        else:
            log.info("payment_webhook: ignored event=%s", yookassa_event)
            return {"ok": True, "ignored": True}
    else:
        # Stub format (для dev-тестов) — поддерживаем только в DEBUG
        if not _settings.DEBUG:
            raise HTTPException(status_code=400, detail="unknown webhook format")
        payment_id = body.get("payment_id", "")
        target_status = body.get("status", "")
        amount_rub = float(body.get("amount", 0) or 0)
        plan = body.get("plan", "pro")
        user_email = body.get("user_email", "")
        if not user_email:
            raise HTTPException(status_code=400, detail="missing user_email")
        user_id = None  # будем искать по email ниже

    # 4. Найти юзера (нужен user.id для замка payment_attempts.user_id NOT NULL)
    user = None
    if user_id:
        user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    elif "user_email" in body:
        user = db.query(models.User).filter(models.User.email == body["user_email"]).first()

    if user is None:
        log.error("payment_webhook: user not found payment_id=%s", payment_id)
        raise HTTPException(status_code=404, detail="user not found")

    # 5. Атомарная идемпотентность: СНАЧАЛА вставляем payment_attempts как замок
    #    по UNIQUE(external_id), и только при успешном захвате замка применяем
    #    действие в ТОЙ ЖЕ транзакции. Раньше активация шла ДО записи попытки →
    #    ретрай/конкурентный webhook (YooKassa повторяет до 30 раз) мог активировать
    #    подписку дважды. IntegrityError на вставке = повтор → 200 без re-активации.
    attempt_attr = getattr(models, "PaymentAttemptORM", None)
    if attempt_attr is not None and payment_id:
        from sqlalchemy.exc import IntegrityError

        db.add(attempt_attr(
            external_id=payment_id,
            user_id=user.id,
            amount_rub=amount_rub,
            status=target_status,
            created_at=utc_now_naive(),
        ))
        try:
            db.flush()  # бьёт по UNIQUE(external_id) немедленно — захват замка
        except IntegrityError:
            db.rollback()
            log.info("payment_webhook: idempotent replay payment_id=%s status=%s", payment_id, target_status)
            return {"ok": True, "idempotent": True}

    # 6. Применить действие (commit внутри = атомарно с замком payment_attempts)
    if target_status == "succeeded":
        _activate_subscription(db, user, plan, amount_rub, payment_id, "yookassa")
    elif target_status == "refunded":
        _deactivate_subscription(db, user, payment_id)
    else:
        # Нет subscription-действия, но замок уже захвачен — фиксируем его.
        db.commit()
        log.info("payment_webhook: status=%s — no action", target_status)

    return {"ok": True}


# ──────────────────────────────────────────────────────────────────
#  Internals
# ──────────────────────────────────────────────────────────────────


def _activate_subscription(
    db: Session, user: models.User, plan_str: str, amount: float, payment_id: str, source: str
) -> None:
    """Деактивирует старые подписки + создаёт новую активную + пишет Payment."""
    plan_enum = (
        models.SubscriptionPlan.PRO if plan_str == "pro" else models.SubscriptionPlan.CORPORATE
    )

    # Деактивируем все предыдущие активные
    db.query(models.Subscription).filter(
        models.Subscription.user_id == user.id,
        models.Subscription.is_active == 1,
    ).update({"is_active": 0})

    started = utc_now_naive()
    expires = started + timedelta(days=PLAN_DURATION_DAYS.get(plan_str, 30))

    sub = models.Subscription(
        user_id=user.id,
        plan=plan_enum,
        is_active=1,
        started_at=started,
        expires_at=expires,
        auto_renew=1,
        max_trades=None,  # unlimited на платном
        max_accounts=10 if plan_str == "corporate" else 5,
        ai_analysis_enabled=1,
    )
    db.add(sub)
    db.flush()  # получаем sub.id для FK на Payment

    payment = models.Payment(
        user_id=user.id,
        subscription_id=sub.id,
        amount=amount,
        currency="RUB",
        status=models.PaymentStatus.COMPLETED,
        external_id=payment_id,
        payment_method=source,
        completed_at=started,
    )
    db.add(payment)
    db.commit()
    log.info(f"Subscription activated: user={user.email} plan={plan_str} expires={expires}")


def _deactivate_subscription(db: Session, user: models.User, payment_id: str) -> None:
    """PR 26: refund handling. Деактивирует все активные подписки юзера."""
    affected = db.query(models.Subscription).filter(
        models.Subscription.user_id == user.id,
        models.Subscription.is_active == 1,
    ).update({"is_active": 0})

    # Помечаем Payment как REFUNDED
    db.query(models.Payment).filter(
        models.Payment.external_id == payment_id
    ).update({"status": models.PaymentStatus.REFUNDED if hasattr(models.PaymentStatus, "REFUNDED") else models.PaymentStatus.FAILED})

    db.commit()
    log.warning("Subscription DEACTIVATED (refund): user=%s payment_id=%s affected=%d",
                user.email, payment_id, affected)
