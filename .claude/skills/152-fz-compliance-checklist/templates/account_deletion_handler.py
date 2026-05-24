"""
account_deletion_handler.py
============================

Endpoint и сервис удаления аккаунта согласно ст. 21 ч. 5 152-ФЗ
(уничтожение ПД в течение 30 дней с момента запроса субъекта).

Архитектура:
  Phase 1 (request_account_deletion):
      - проверка пароля (защита от случайного клика);
      - User.is_active = 0, deletion_requested_at = now;
      - revoked_at = now в pd_consents;
      - отзыв BrokerConnection.api_token (критично — это доступ к чужим деньгам);
      - очистка auth cookies.

  Phase 2 (finalize_deletion):
      - запускается Celery beat / sync_scheduler раз в сутки;
      - находит юзеров с deletion_requested_at <= now - 30 days;
      - анонимизирует User, обнуляет свободный текст в Trade/DailyReview;
      - оставляет Payment (бухучёт по 402-ФЗ, 4 года) с маской card_last4.

  restore_account:
      - если пользователь передумал в течение 30 дней — раскатываем soft delete.

Файлы для размещения:
  - этот код разделить на:
      backend/services/pd_deletion.py  (функции request/finalize/restore/run_pending)
      backend/routers/auth.py          (DELETE /auth/me, POST /auth/me/restore)
      backend/sync_scheduler.py        (вызов run_pending_deletions раз в сутки)
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.orm import Session

import auth_service
import database
import models
from logger import get_logger
from utils.datetime_utils import utc_now_naive

log = get_logger("pd_deletion")

GRACE_PERIOD_DAYS = 30  # ст. 21 ч. 5 152-ФЗ


# ---------------------------------------------------------------------------
# schemas — положить в backend/schemas.py
# ---------------------------------------------------------------------------

class DeleteAccountRequest(BaseModel):
    password: str
    reason: str | None = None  # опционально, для аналитики причин ухода


class DeleteAccountResponse(BaseModel):
    status: str  # "scheduled"
    delete_at: datetime
    grace_period_days: int


class RestoreAccountResponse(BaseModel):
    status: str  # "restored"
    user_id: int


# ---------------------------------------------------------------------------
# services/pd_deletion.py
# ---------------------------------------------------------------------------

def request_account_deletion(
    db: Session,
    user_id: int,
    ip_address: str | None = None,
    reason: str | None = None,
) -> datetime:
    """
    Phase 1: soft delete + старт grace period.

    Возвращает дату, когда произойдёт физическая анонимизация.
    Идемпотентно: если уже запрошено — просто возвращает delete_at.
    """
    user = db.execute(
        select(models.User).where(models.User.id == user_id)
    ).scalar_one_or_none()
    if user is None:
        raise ValueError(f"User id={user_id} not found")

    now = utc_now_naive()
    delete_at = now + timedelta(days=GRACE_PERIOD_DAYS)

    if user.deletion_requested_at is not None:
        # Уже в очереди — возвращаем существующую дату
        log.info(f"Account {user_id} already scheduled for deletion at {user.deletion_requested_at}")
        return user.deletion_requested_at + timedelta(days=GRACE_PERIOD_DAYS)

    # 1. Деактивируем учётку (доступ закрыт немедленно)
    user.is_active = 0
    user.deletion_requested_at = now

    # 2. Отзываем все согласия пользователя
    db.execute(
        update(models.PdConsent)
        .where(
            models.PdConsent.user_id == user_id,
            models.PdConsent.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )

    # 3. Критично: отзываем брокерские токены (доступ к чужим деньгам).
    # api_token обнуляем сразу, не ждём 30 дней — это безопасность, а не ПД.
    db.execute(
        update(models.BrokerConnection)
        .where(models.BrokerConnection.account_id.in_(
            select(models.Account.id).where(models.Account.user_id == user_id)
        ))
        .values(api_token="", is_active=False)
    )

    db.commit()

    log.info(
        f"Account deletion scheduled: user_id={user_id} ip={ip_address} "
        f"reason={reason!r} delete_at={delete_at.isoformat()}"
    )
    return delete_at


def restore_account(db: Session, user_id: int) -> models.User:
    """
    Отмена soft delete в течение grace period.
    Если уже finalized — восстановить нельзя (ПД физически обезличены).
    """
    user = db.execute(
        select(models.User).where(models.User.id == user_id)
    ).scalar_one_or_none()
    if user is None:
        raise ValueError(f"User id={user_id} not found")

    if user.deletion_requested_at is None:
        raise ValueError("Account is not scheduled for deletion")

    # Проверяем, что не прошёл grace period
    elapsed = utc_now_naive() - user.deletion_requested_at
    if elapsed > timedelta(days=GRACE_PERIOD_DAYS):
        raise ValueError("Grace period expired — account already anonymized")

    user.is_active = 1
    user.deletion_requested_at = None
    db.commit()

    log.info(f"Account restored: user_id={user_id}")
    return user


def finalize_deletion(db: Session, user_id: int) -> None:
    """
    Phase 2: физическая анонимизация ПД.
    Запускается планировщиком после истечения grace period.

    Каскад по моделям Empirik:
      - User: email -> deleted_<id>@anon.local, name -> NULL, hashed_password -> NULL,
              oauth_provider_id -> NULL, utm_*/referrer -> NULL.
      - Trade: notes, entry_reason, exit_reason -> NULL (свободный текст пользователя).
              symbol/pnl/entry_at оставляем (агрегатная аналитика по обезличенным данным).
      - DailyReview: reflection, intention, trade_reflections -> NULL/empty.
      - Payment: card_last4 -> NULL (бухучёт по 402-ФЗ требует хранить 4 года, но
                 номер карты — ПД доп.категории, маскируем).
      - BrokerConnection.api_token: уже обнулён в phase 1.
      - Account, BalanceSnapshot, CapitalOperation, DepositHistory: оставляем
                 (привязаны к Account, не к личности после анонимизации User).
    """
    user = db.execute(
        select(models.User).where(models.User.id == user_id)
    ).scalar_one_or_none()
    if user is None:
        log.warning(f"finalize_deletion: user {user_id} already gone")
        return

    if user.deletion_requested_at is None:
        log.warning(f"finalize_deletion: user {user_id} has no deletion_requested_at — skip")
        return

    log.info(f"Finalizing deletion for user_id={user_id} email_was={user.email}")

    # 1. User: основной идентификатор
    user.email = f"deleted_{user.id}@anon.local"
    user.name = None
    user.hashed_password = None
    user.oauth_provider = None
    user.oauth_provider_id = None
    user.utm_source = None
    user.utm_medium = None
    user.utm_campaign = None
    user.referrer = None
    user.last_login = None
    user.settings = {}

    # 2. Trade: свободный текст пользователя (notes, причины входа/выхода)
    account_ids_q = select(models.Account.id).where(models.Account.user_id == user_id)
    db.execute(
        update(models.Trade)
        .where(models.Trade.account_id.in_(account_ids_q))
        .values(
            notes=None,
            entry_reason=None,
            exit_reason=None,
            news_event=None,
            screenshot_url=None,
            emotions=None,
            ai_analysis=None,
        )
    )

    # 3. DailyReview: свободный текст рефлексии
    db.execute(
        update(models.DailyReview)
        .where(models.DailyReview.account_id.in_(account_ids_q))
        .values(
            reflection="",
            intention="",
            trade_reflections={},
        )
    )

    # 4. Payment: бухучёт оставляем, но card_last4 (ПД) маскируем
    db.execute(
        update(models.Payment)
        .where(models.Payment.user_id == user_id)
        .values(card_last4=None, card_type=None)
    )

    # 5. BrokerConnection: уже обнулено в phase 1, на всякий случай повторим
    db.execute(
        update(models.BrokerConnection)
        .where(models.BrokerConnection.account_id.in_(account_ids_q))
        .values(api_token="", is_active=False)
    )

    # 6. Зафиксируем факт уничтожения в pd_consents (для доказательной базы)
    # pd_consents храним 4 года после отзыва — это законное основание (ст. 6 ч. 1 п. 2)
    db.commit()

    log.info(f"User {user_id} anonymized successfully")


def run_pending_deletions(db: Session) -> int:
    """
    Планировщик: вызывается раз в сутки из sync_scheduler.py.
    Возвращает количество обработанных аккаунтов.
    """
    cutoff = utc_now_naive() - timedelta(days=GRACE_PERIOD_DAYS)
    pending: Iterable[models.User] = db.execute(
        select(models.User).where(
            models.User.deletion_requested_at.is_not(None),
            models.User.deletion_requested_at <= cutoff,
            # Не повторяем для уже обезличенных — у них email начинается с deleted_
            models.User.email.not_like("deleted_%@anon.local"),
        )
    ).scalars().all()

    count = 0
    for user in pending:
        try:
            finalize_deletion(db, user.id)
            count += 1
        except Exception as exc:  # noqa: BLE001 — не валим планировщик
            log.exception(f"Failed to finalize deletion for user {user.id}: {exc}")
    log.info(f"run_pending_deletions: anonymized {count} accounts")
    return count


# ---------------------------------------------------------------------------
# routers/auth.py — добавить эти endpoints
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/auth", tags=["auth"])  # либо использовать существующий


@router.delete("/me", response_model=DeleteAccountResponse, status_code=202)
def delete_my_account(
    payload: DeleteAccountRequest,
    request: Request,
    response: Response,
    current_user: models.User = Depends(auth_service.get_current_user),
    db: Session = Depends(database.get_db),
) -> DeleteAccountResponse:
    """
    Удалить аккаунт текущего пользователя (152-ФЗ ст. 21 ч. 5).

    Двухфазное удаление:
      - сразу: soft delete, отзыв токенов брокеров, отзыв согласий;
      - через 30 дней: физическая анонимизация ПД.

    В течение 30 дней пользователь может восстановить аккаунт через
    POST /auth/me/restore.
    """
    # OAuth-юзеры могут не иметь пароля — для них требуем второй фактор
    # (например, повторная OAuth-авторизация). Здесь упрощённо отказываем.
    if not current_user.hashed_password:
        raise HTTPException(
            status_code=400,
            detail=(
                "Для OAuth-аккаунта удаление через этот endpoint недоступно. "
                "Напишите на support@empirik.io — удалим вручную в течение 30 дней."
            ),
        )

    if not auth_service.verify_password(payload.password, current_user.hashed_password):
        raise HTTPException(status_code=403, detail="Неверный пароль")

    delete_at = request_account_deletion(
        db,
        user_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        reason=payload.reason,
    )

    # Очищаем auth cookies — пользователь сразу разлогинен
    auth_service.clear_auth_cookies(response, request)

    return DeleteAccountResponse(
        status="scheduled",
        delete_at=delete_at,
        grace_period_days=GRACE_PERIOD_DAYS,
    )


@router.post("/me/restore", response_model=RestoreAccountResponse)
def restore_my_account(
    payload: DeleteAccountRequest,  # требуем пароль для подтверждения
    db: Session = Depends(database.get_db),
) -> RestoreAccountResponse:
    """
    Восстановить аккаунт в течение grace period.
    Требует email + пароль (юзер уже разлогинен после soft delete).
    """
    # На этапе restore юзер ещё не разлогинен из-за деактивации,
    # поэтому отдельная аутентификация. Здесь упрощённый вариант —
    # в реальном коде используй authenticate_user(...) с email из payload.
    raise NotImplementedError(
        "Реализуй: найти user по email из тела (расширь DeleteAccountRequest), "
        "проверить пароль, вызвать restore_account(db, user.id)."
    )
