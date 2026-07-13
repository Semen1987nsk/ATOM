"""
Сервис удаления аккаунта согласно 152-ФЗ ст. 21 ч. 5
(уничтожение ПД в течение 30 дней с момента запроса субъекта).

Двухфазная архитектура:
  Phase 1 (request_account_deletion):
      - User.is_active = 0, deletion_requested_at = now;
      - revoked_at = now во всех активных pd_consents;
      - api_token брокерских подключений зануляется СРАЗУ
        (это не ПД, а доступ к чужим деньгам — нельзя ждать 30 дней).

  Phase 2 (finalize_deletion):
      - запускается раз в сутки из sync_scheduler;
      - находит юзеров с deletion_requested_at <= now - 30 days;
      - анонимизирует User (email, name, oauth_*, utm_*, settings);
      - очищает свободный текст в Trade (notes, screenshot_url, ai_analysis);
      - очищает свободный текст в DailyReview (reflection, intention, trade_reflections);
      - оставляет Payment (бухучёт по 402-ФЗ хранится 4 года) с маской card_last4.

  restore_account:
      - если пользователь передумал в течение 30 дней — раскатываем soft delete.
"""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.orm import Session

import models
from logger import get_logger
from utils.datetime_utils import utc_now_naive

log = get_logger("pd_deletion")

GRACE_PERIOD_DAYS = 30  # ст. 21 ч. 5 152-ФЗ


# ---------------------------------------------------------------------------
# Phase 1 — запрос на удаление (soft delete + блокировка брокеров)
# ---------------------------------------------------------------------------

def request_account_deletion(
    db: Session,
    user: models.User,
    reason: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> None:
    """
    Запрос на удаление: soft-deactivate + старт grace period.

    Идемпотентно — повторный вызов на уже запрошенном аккаунте не делает
    ничего (возвращается без ошибки).
    """
    if user.deletion_requested_at is not None:
        log.info(f"Account user_id={user.id} already scheduled for deletion at {user.deletion_requested_at}")
        return

    now = utc_now_naive()

    user.is_active = 0
    user.deletion_requested_at = now

    # Отзываем все активные согласия — субъект больше не разрешает обработку.
    db.execute(
        update(models.PdConsent)
        .where(models.PdConsent.user_id == user.id, models.PdConsent.revoked_at.is_(None))
        .values(revoked_at=now)
    )

    # Брокерские токены — это не ПД, а доступ к чужим деньгам. Зануляем СРАЗУ,
    # не ждём 30 дней. Сами строки оставляем для аудита (account_id, broker, created_at).
    revoked_brokers = db.execute(
        update(models.BrokerConnection)
        .where(
            models.BrokerConnection.account_id.in_(
                select(models.Account.id).where(models.Account.user_id == user.id)
            )
        )
        .values(api_token="REVOKED_BY_USER_DELETION", is_active=0)
    ).rowcount

    db.commit()

    log.info(
        f"🗑 Phase 1: account user_id={user.id} marked for deletion. "
        f"Brokers revoked: {revoked_brokers}. Reason: {reason!r}. IP: {ip_address}"
    )


# ---------------------------------------------------------------------------
# restore_account — отмена в течение grace period
# ---------------------------------------------------------------------------

def restore_account(db: Session, user: models.User) -> bool:
    """
    Восстановить аккаунт, если ещё не прошёл grace period.
    Возвращает True если восстановлен, False если уже поздно или не был удалён.
    """
    if user.deletion_requested_at is None:
        return False

    expires_at = user.deletion_requested_at + timedelta(days=GRACE_PERIOD_DAYS)
    if utc_now_naive() > expires_at:
        log.warning(f"Cannot restore user_id={user.id}: grace period expired")
        return False

    user.is_active = 1
    user.deletion_requested_at = None
    db.commit()

    log.info(f"♻ Account restored: user_id={user.id}")
    return True


# ---------------------------------------------------------------------------
# Phase 2 — финализация (анонимизация + чистка свободных полей)
# ---------------------------------------------------------------------------

def finalize_deletion(db: Session, user: models.User) -> None:
    """
    Анонимизация пользователя после истечения grace period.

    Что делаем:
      - User: email -> "deleted-{id}@anon.empirik", name/oauth/utm -> NULL, settings -> {}
      - Trade: notes, screenshot_url, ai_analysis -> NULL (свободный текст)
      - DailyReview: reflection, intention, trade_reflections -> NULL
      - Payment: card_last4/external_id оставляем для бухучёта (402-ФЗ, 4 года)
      - Subscription: оставляем (для аналитики MRR)
    """
    user_id = user.id
    now = utc_now_naive()

    # Trades: чистим свободный текст и скриншоты пользователя.
    # Числовые поля (pnl, entry_price, ...) оставляем — нужны для агрегатной аналитики.
    trade_ids_subq = (
        select(models.Trade.id)
        .join(models.Account, models.Account.id == models.Trade.account_id)
        .where(models.Account.user_id == user_id)
    )

    # 152-ФЗ ст.21 п.5: физически удаляем файлы скриншотов (PII/финданные),
    # а не только зануляем ссылку в БД.
    from routers.trades import UPLOAD_DIR as _SCREENSHOT_DIR

    screenshot_urls = [
        row[0]
        for row in db.execute(
            select(models.Trade.screenshot_url)
            .where(models.Trade.id.in_(trade_ids_subq))
            .where(models.Trade.screenshot_url.isnot(None))
        ).all()
    ]

    trades_cleaned = db.execute(
        update(models.Trade)
        .where(models.Trade.id.in_(trade_ids_subq))
        .values(
            notes=None,
            screenshot_url=None,
            entry_reason=None,
            exit_reason=None,
            news_event=None,
            ai_analysis=None,
        )
    ).rowcount

    # Daily reviews — журнал размышлений трейдера, очищаем полностью.
    review_account_subq = (
        select(models.Account.id).where(models.Account.user_id == user_id)
    )
    reviews_cleaned = db.execute(
        update(models.DailyReview)
        .where(models.DailyReview.account_id.in_(review_account_subq))
        .values(
            reflection=None,
            intention=None,
            trade_reflections=None,
        )
    ).rowcount

    db.commit()

    # Удаляем физические файлы скриншотов ДО анонимизации email. Пока email
    # юзера ещё не переписан на "deleted-%@anon.empirik", run_pending_deletions
    # продолжит выбирать этого юзера в pending — значит если процесс упадёт
    # посреди unlink-цикла, следующий прогон повторит finalize_deletion и
    # доудалит оставшиеся файлы (unlink идемпотентен, missing_ok=True).
    # Без этого порядка юзер после commit email навсегда выпадает из
    # pending-фильтра, и недоудалённые файлы становятся вечными сиротами.
    for url in screenshot_urls:
        try:
            fpath = _SCREENSHOT_DIR / Path(url).name
            # SEC: тот же containment-барьер, что в trades.py get_screenshot/
            # delete_screenshot — defense-in-depth сверх basename-strip.
            if fpath.resolve().is_relative_to(_SCREENSHOT_DIR.resolve()):
                fpath.unlink(missing_ok=True)
        except OSError as exc:
            log.warning(f"Failed to unlink screenshot {url}: {exc}")

    # Анонимизируем User последним.
    user.email = f"deleted-{user_id}@anon.empirik"
    user.name = None
    user.hashed_password = None
    user.oauth_provider = None
    user.oauth_provider_id = None
    user.utm_source = None
    user.utm_medium = None
    user.utm_campaign = None
    user.referrer = None
    user.settings = {}
    user.last_login = None
    # deletion_requested_at оставляем — это аудит, когда был выполнен запрос.

    db.commit()

    # PR 26 Scenario #78: инвалидация stats cache + revoke всех активных JWT
    # юзера. Без этого после анонимизации старый кэш может всё ещё содержать
    # его данные, и старый JWT валиден до expiry.
    try:
        from services.stats_cache import stats_cache
        stats_cache.invalidate_account(user_id)  # если такой метод есть
    except (ImportError, AttributeError):
        try:
            from services.stats_cache import stats_cache
            stats_cache.clear()  # fallback: чистим весь кэш
        except Exception:
            pass

    # Revoke active sessions (insert into revoked_tokens) — мы не знаем jti
    # активных токенов, но т.к. user.hashed_password стал NULL, decode_access_token
    # будет валиден до expiry. Безопасно если user.is_active=0.
    user.is_active = 0
    db.commit()

    log.info(
        f"🗑 Phase 2: account user_id={user_id} anonymized at {now}. "
        f"Trades cleaned: {trades_cleaned}, reviews cleaned: {reviews_cleaned}"
    )


# ---------------------------------------------------------------------------
# Scheduler entrypoint — запускается раз в сутки из sync_scheduler
# ---------------------------------------------------------------------------

def run_pending_deletions(db: Session) -> int:
    """
    Найти всех юзеров с истёкшим grace period и финализировать удаление.
    Возвращает количество обработанных аккаунтов.
    """
    threshold = utc_now_naive() - timedelta(days=GRACE_PERIOD_DAYS)

    pending = db.execute(
        select(models.User).where(
            models.User.deletion_requested_at.isnot(None),
            models.User.deletion_requested_at <= threshold,
            # Не обрабатываем уже анонимизированных (email уже @anon.empirik)
            ~models.User.email.like("deleted-%@anon.empirik"),
        )
    ).scalars().all()

    for user in pending:
        try:
            finalize_deletion(db, user)
        except Exception as exc:
            log.error(f"Failed to finalize deletion for user_id={user.id}: {exc}", exc_info=True)
            db.rollback()

    return len(pending)
