"""
Экспорт всех персональных данных пользователя (152-ФЗ ст. 14).

Право доступа: субъект ПД вправе получить копию всех своих ПД у оператора.

Что отдаём:
- User (без hashed_password)
- Accounts, Trades, BalanceSnapshots, CapitalOperation, DepositHistory
- Setups, DailyReviews
- Subscriptions, Payments (без полных номеров карт — только маска card_last4)
- pd_consents (журнал согласий, включая отозванные)
- BrokerConnection (БЕЗ api_token — даже зашифрованного)

Формат: dict, готовый к JSON-сериализации. Конкретные поля — см. _serialize_*().

ВАЖНО: это операция чтения, изменений в БД не делает. Поэтому транзакция
не открывается. Логика построена на простых .query().filter().all().
"""
from __future__ import annotations

from decimal import Decimal
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

import models
from utils.datetime_utils import utc_now_naive


# Версия формата экспорта. Если поменяли структуру — поднять.
EXPORT_VERSION = "1"
POLICY_VERSION = "v1"


def _to_jsonable(value: Any) -> Any:
    """Decimal → str (точность), datetime → ISO, enum → value."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "value") and hasattr(type(value), "_value2member_map_"):
        # Это Enum
        return value.value
    return value


def _serialize_columns(obj, *, exclude: Optional[set[str]] = None) -> Dict[str, Any]:
    """Достаёт все колонки SQLAlchemy-объекта, фильтрует исключения."""
    exclude = exclude or set()
    result: Dict[str, Any] = {}
    for column in obj.__table__.columns:
        name = column.name
        if name in exclude:
            continue
        result[name] = _to_jsonable(getattr(obj, name))
    return result


def build_user_export(
    db: Session,
    user: models.User,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Собирает полный snapshot ПД пользователя.

    Не использует .relationship() lazy-load — вместо этого делает явные queries
    по user_id / account_id, чтобы не зависеть от состояния session expiration.
    """
    # User — без hashed_password
    user_data = _serialize_columns(user, exclude={"hashed_password"})

    # Accounts (нужны для дальнейших запросов)
    accounts = db.query(models.Account).filter(models.Account.user_id == user.id).all()
    account_ids = [a.id for a in accounts]
    accounts_data = [_serialize_columns(a) for a in accounts]

    # Subscriptions
    subs = db.query(models.Subscription).filter(models.Subscription.user_id == user.id).all()
    subs_data = [_serialize_columns(s) for s in subs]

    # Payments (полная история — это его финансовые документы)
    payments = db.query(models.Payment).filter(models.Payment.user_id == user.id).all()
    payments_data = [_serialize_columns(p) for p in payments]

    # PdConsents (журнал согласий, включая отозванные)
    consents = (
        db.query(models.PdConsent).filter(models.PdConsent.user_id == user.id).all()
    )
    consents_data = [_serialize_columns(c) for c in consents]

    # Trades (через account_ids)
    trades_data: List[Dict[str, Any]] = []
    daily_reviews_data: List[Dict[str, Any]] = []
    setups_data: List[Dict[str, Any]] = []
    deposit_history_data: List[Dict[str, Any]] = []
    capital_ops_data: List[Dict[str, Any]] = []
    balance_snapshots_data: List[Dict[str, Any]] = []
    broker_connections_data: List[Dict[str, Any]] = []

    if account_ids:
        trades = (
            db.query(models.Trade)
            .filter(models.Trade.account_id.in_(account_ids))
            .all()
        )
        trades_data = [_serialize_columns(t) for t in trades]

        reviews = (
            db.query(models.DailyReview)
            .filter(models.DailyReview.account_id.in_(account_ids))
            .all()
        )
        daily_reviews_data = [_serialize_columns(r) for r in reviews]

        setups = (
            db.query(models.Setup)
            .filter(models.Setup.account_id.in_(account_ids))
            .all()
        )
        setups_data = [_serialize_columns(s) for s in setups]

        deposit_history = (
            db.query(models.DepositHistory)
            .filter(models.DepositHistory.account_id.in_(account_ids))
            .all()
        )
        deposit_history_data = [_serialize_columns(d) for d in deposit_history]

        capital_ops = (
            db.query(models.CapitalOperation)
            .filter(models.CapitalOperation.account_id.in_(account_ids))
            .all()
        )
        capital_ops_data = [_serialize_columns(c) for c in capital_ops]

        snapshots = (
            db.query(models.BalanceSnapshot)
            .filter(models.BalanceSnapshot.account_id.in_(account_ids))
            .all()
        )
        balance_snapshots_data = [_serialize_columns(s) for s in snapshots]

        # BrokerConnection — БЕЗ api_token (это шифрованный credential, не PD,
        # и пользователю нет смысла отдавать его в JSON-экспорте).
        brokers = (
            db.query(models.BrokerConnection)
            .filter(models.BrokerConnection.account_id.in_(account_ids))
            .all()
        )
        broker_connections_data = [
            _serialize_columns(b, exclude={"api_token"}) for b in brokers
        ]

    counts = {
        "accounts": len(accounts_data),
        "subscriptions": len(subs_data),
        "payments": len(payments_data),
        "pd_consents": len(consents_data),
        "trades": len(trades_data),
        "daily_reviews": len(daily_reviews_data),
        "setups": len(setups_data),
        "deposit_history": len(deposit_history_data),
        "capital_operations": len(capital_ops_data),
        "balance_snapshots": len(balance_snapshots_data),
        "broker_connections": len(broker_connections_data),
    }

    return {
        "export_version": EXPORT_VERSION,
        "exported_at": utc_now_naive(),
        "request_id": request_id,
        "policy_version": POLICY_VERSION,
        "user": user_data,
        "accounts": accounts_data,
        "subscriptions": subs_data,
        "payments": payments_data,
        "pd_consents": consents_data,
        "trades": trades_data,
        "daily_reviews": daily_reviews_data,
        "setups": setups_data,
        "deposit_history": deposit_history_data,
        "capital_operations": capital_ops_data,
        "balance_snapshots": balance_snapshots_data,
        "broker_connections": broker_connections_data,
        "counts": counts,
    }
