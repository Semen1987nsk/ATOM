"""
Reverse-Trial subscription service.

См. ADR-0005 (.business/tech/decisions/0005-reverse-trial-model.md).

Жизненный цикл подписки:

    register
       │
       ▼
    trial_active  ───21 days──▶  trial_expired ──auto──▶ free_plus
       │                                                    │
       │ upgrade (YooKassa)                       upgrade (YooKassa)
       ▼                                                    ▼
    pro_active ◀─────────────renew / re-upgrade──────────────

При downgrade trial_active → free_plus:
    - sync_enabled = False у всех BrokerConnection юзера
    - API-токены брокеров остаются зашифрованными в БД (см. ADR-0005)
      Юзер может вручную удалить токен в /settings/integrations.
    - subscription.frozen_at = now() — метка для UI «Расчёт остановлен X»

Capabilities (проверяются перед чувствительными вызовами):
    - api_sync          — фоновый sync брокера каждые 60s
    - new_ai_insight    — генерация нового AI-инсайта (cap 30 запросов в trial)
    - live_mae_mfe      — расчёт MAE/MFE для новой сделки
    - trade_replay_all  — Replay для любой сделки (на Free+ — только trial-сделок)
    - optimal_f_live    — live-расчёт Optimal f/SQN/Monte Carlo
    - multi_account     — больше 1 торгового счёта
    - pdf_unlimited     — безлимит PDF-экспорта (на Free+ — 1/мес)
"""
from __future__ import annotations

from datetime import timedelta
from typing import Iterable

from sqlalchemy import select, update
from sqlalchemy.orm import Session

import models
from logger import get_logger
from utils.datetime_utils import utc_now_naive

log = get_logger("subscription_service")

TRIAL_DURATION_DAYS = 21
AI_REQUESTS_CAP_TRIAL = 30


# ---------------------------------------------------------------------------
# Status constants — пока в moders.py не добавлен Enum, работаем со строками.
# Имена соответствуют alembic 0019_reverse_trial.
# ---------------------------------------------------------------------------

STATUS_NONE = "none"
STATUS_TRIAL_ACTIVE = "trial_active"
STATUS_TRIAL_EXPIRED = "trial_expired"
STATUS_FREE_PLUS = "free_plus"
STATUS_PRO_ACTIVE = "pro_active"
STATUS_CORPORATE_ACTIVE = "corporate_active"

ALL_STATUSES = {
    STATUS_NONE,
    STATUS_TRIAL_ACTIVE,
    STATUS_TRIAL_EXPIRED,
    STATUS_FREE_PLUS,
    STATUS_PRO_ACTIVE,
    STATUS_CORPORATE_ACTIVE,
}

PRO_LIKE = {STATUS_TRIAL_ACTIVE, STATUS_PRO_ACTIVE, STATUS_CORPORATE_ACTIVE}
"""Статусы, в которых юзер пользуется полным Pro-функционалом."""

POST_TRIAL = {STATUS_TRIAL_EXPIRED, STATUS_FREE_PLUS}
"""Юзер прошёл trial и сейчас на Free+. trial_expired переходит в free_plus
сразу же при первом запуске expire_trials() — оба статуса означают одно и то же
права-wise, разница только в том, был ли отображён D+21 dialog."""


# ---------------------------------------------------------------------------
# Capabilities matrix
# ---------------------------------------------------------------------------

_PRO_CAPABILITIES = frozenset(
    {
        "api_sync",
        "new_ai_insight",
        "live_mae_mfe",
        "trade_replay_all",
        "optimal_f_live",
        "multi_account",
        "pdf_unlimited",
    }
)

_FREE_PLUS_CAPABILITIES = frozenset(
    {
        # доступ к архиву только; live-фичи запрещены
    }
)


def capabilities_for(status: str) -> frozenset[str]:
    """Множество разрешённых capability-ключей для данного статуса."""
    if status in PRO_LIKE:
        return _PRO_CAPABILITIES
    if status in POST_TRIAL:
        return _FREE_PLUS_CAPABILITIES
    # 'none' — старые юзеры до миграции на Reverse-Trial; на них Pro-проверки
    # должны опираться на subscription.plan, как раньше. Возвращаем пустое
    # множество — вызывающий код должен сделать fallback на plan-based check.
    return _FREE_PLUS_CAPABILITIES


def can(subscription: models.Subscription | None, capability: str) -> bool:
    """Главная точка проверки прав. Возвращает True, если юзер может пользоваться
    указанной capability на данном плане.

    Если subscription is None (анонимный? broken state?) — отказ.
    """
    if subscription is None:
        return False
    status = getattr(subscription, "status", STATUS_NONE) or STATUS_NONE
    return capability in capabilities_for(status)


# ---------------------------------------------------------------------------
# Trial lifecycle
# ---------------------------------------------------------------------------


def start_trial(db: Session, user: models.User) -> models.Subscription:
    """
    Стартует 21-дневный Reverse-Trial для нового юзера.

    Идемпотентно: повторный вызов не сбрасывает уже идущий trial. Защита
    от каннибализации (см. ADR-0005) — если у юзера уже есть subscription с
    непустым trial_started_at, возвращаем существующую запись.

    Карта не запрашивается. См. anti-pattern TradeZella 7d-trial с картой.
    """
    sub: models.Subscription | None = (
        db.execute(
            select(models.Subscription).where(models.Subscription.user_id == user.id)
        ).scalar_one_or_none()
    )

    now = utc_now_naive()

    if sub is None:
        sub = models.Subscription(user_id=user.id)
        db.add(sub)
        db.flush()

    if getattr(sub, "trial_started_at", None) is not None:
        log.info(f"start_trial: user_id={user.id} already had trial started — noop")
        return sub

    sub.status = STATUS_TRIAL_ACTIVE
    sub.trial_started_at = now
    sub.trial_ended_at = now + timedelta(days=TRIAL_DURATION_DAYS)
    sub.frozen_at = None
    log.info(
        f"start_trial: user_id={user.id} trial_ends_at={sub.trial_ended_at.isoformat()}"
    )
    return sub


def expire_trials(db: Session) -> list[int]:
    """
    Job (раз в час): найти истёкшие trial и перевести в free_plus.

    Действия при downgrade:
      1. status: trial_active → trial_expired
         (trial_expired переходит в free_plus при первом запросе fronend'а,
          либо здесь же если хотим)
      2. frozen_at = now() — для UI «Расчёт остановлен X»
      3. Все BrokerConnection юзера: auto_sync_enabled = False
         API-токен остаётся (см. ADR-0005, политика v2)
      4. trial_summary_shown остаётся False — фронт покажет D+21 dialog
         при следующем входе.

    Возвращает список user_id, у которых произошёл downgrade
    (для последующей отправки D+21 email с PDF-отчётом).
    """
    now = utc_now_naive()

    expired: Iterable[models.Subscription] = (
        db.execute(
            select(models.Subscription).where(
                models.Subscription.status == STATUS_TRIAL_ACTIVE,
                models.Subscription.trial_ended_at.is_not(None),
                models.Subscription.trial_ended_at <= now,
            )
        ).scalars()
    )

    downgraded: list[int] = []
    for sub in expired:
        sub.status = STATUS_TRIAL_EXPIRED
        sub.frozen_at = now
        downgraded.append(sub.user_id)

        # Отключаем sync у всех брокерских подключений юзера.
        # ВАЖНО: api_token не зануляем — см. ADR-0005, политика v2.
        # Юзер может вручную удалить токен в /settings/integrations.
        db.execute(
            update(models.BrokerConnection)
            .where(models.BrokerConnection.user_id == sub.user_id)
            .values(auto_sync_enabled=False)
        )

    if downgraded:
        log.info(f"expire_trials: downgraded {len(downgraded)} users: {downgraded}")

    return downgraded


def upgrade_to_pro(db: Session, user: models.User) -> models.Subscription:
    """
    Юзер оплатил Pro (через ЮKassa webhook).

    Действия:
      1. status → pro_active
      2. frozen_at = None — «размораживаем» виджеты
      3. Включаем sync у всех BrokerConnection (auto_sync_enabled=True)
         Токен уже в БД (если был во время trial) — sync включается мгновенно
         без повторного ввода. См. ADR-0005 (снижает friction upgrade в 3-4×).

    Сама запись Payment и продление expires_at — забота routers/payments.py.
    """
    sub: models.Subscription | None = (
        db.execute(
            select(models.Subscription).where(models.Subscription.user_id == user.id)
        ).scalar_one_or_none()
    )

    if sub is None:
        sub = models.Subscription(user_id=user.id)
        db.add(sub)
        db.flush()

    sub.status = STATUS_PRO_ACTIVE
    sub.frozen_at = None

    db.execute(
        update(models.BrokerConnection)
        .where(models.BrokerConnection.user_id == user.id)
        .values(auto_sync_enabled=True)
    )

    log.info(f"upgrade_to_pro: user_id={user.id}")
    return sub


def mark_trial_summary_shown(db: Session, user: models.User) -> None:
    """Фронт вызывает после показа D+21 dialog, чтобы он не повторялся."""
    db.execute(
        update(models.Subscription)
        .where(models.Subscription.user_id == user.id)
        .values(trial_summary_shown=True, status=STATUS_FREE_PLUS)
    )


# ---------------------------------------------------------------------------
# AI usage cap (trial: 30 запросов на весь период)
# ---------------------------------------------------------------------------


def check_and_log_ai_request(
    db: Session,
    user: models.User,
    kind: str,
    *,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    cost_rub: float | None = None,
) -> bool:
    """
    Проверяет, может ли юзер сделать новый AI-запрос (по плану), и сразу
    логирует его в ai_request_log.

    Возвращает True, если запрос разрешён. False — если cap исчерпан или
    юзер не имеет права на новые AI-запросы.

    Поведение по статусам:
      - pro_active / corporate_active: безлимит
      - trial_active: cap AI_REQUESTS_CAP_TRIAL=30 на весь trial-период
      - trial_expired / free_plus: запрещено (видны только архивные инсайты)
      - none: запрещено (миграция ещё не запущена для юзера)
    """
    sub = user.subscription
    if not can(sub, "new_ai_insight"):
        return False

    status = sub.status if sub else STATUS_NONE

    if status == STATUS_TRIAL_ACTIVE:
        used = (
            db.execute(
                select(models.AiRequestLog).where(
                    models.AiRequestLog.user_id == user.id,
                    models.AiRequestLog.requested_at >= sub.trial_started_at,
                )
            ).all()
        )
        if len(used) >= AI_REQUESTS_CAP_TRIAL:
            log.info(
                f"check_and_log_ai_request: user_id={user.id} trial cap reached "
                f"({AI_REQUESTS_CAP_TRIAL})"
            )
            return False

    db.add(
        models.AiRequestLog(
            user_id=user.id,
            requested_at=utc_now_naive(),
            kind=kind,
            plan_at_request=status,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_rub=cost_rub,
        )
    )
    return True


# ---------------------------------------------------------------------------
# Serialization for frontend
# ---------------------------------------------------------------------------


def to_status_payload(subscription: models.Subscription | None) -> dict:
    """Возвращает плоский dict для GET /subscription/status — фронт использует
    для SubscriptionContext (показ баннеров trial-countdown, замороженных
    виджетов, D+21 dialog).
    """
    if subscription is None:
        return {
            "status": STATUS_NONE,
            "trial_started_at": None,
            "trial_ended_at": None,
            "trial_days_left": None,
            "trial_summary_shown": False,
            "frozen_at": None,
            "capabilities": [],
        }

    status = getattr(subscription, "status", STATUS_NONE) or STATUS_NONE
    trial_ended_at = getattr(subscription, "trial_ended_at", None)

    days_left: int | None = None
    if status == STATUS_TRIAL_ACTIVE and trial_ended_at is not None:
        delta = trial_ended_at - utc_now_naive()
        days_left = max(0, delta.days + (1 if delta.seconds > 0 else 0))

    return {
        "status": status,
        "trial_started_at": (
            subscription.trial_started_at.isoformat()
            if getattr(subscription, "trial_started_at", None)
            else None
        ),
        "trial_ended_at": trial_ended_at.isoformat() if trial_ended_at else None,
        "trial_days_left": days_left,
        "trial_summary_shown": bool(getattr(subscription, "trial_summary_shown", False)),
        "frozen_at": (
            subscription.frozen_at.isoformat()
            if getattr(subscription, "frozen_at", None)
            else None
        ),
        "capabilities": sorted(capabilities_for(status)),
    }
