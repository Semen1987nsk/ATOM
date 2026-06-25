"""
Broker Integration API (PR 12 — рестарт после greenfield rewrite PR 0–11).

Подключение Tinkoff Invest API через новый gRPC SDK:

* `POST /broker/verify-token` — echo-валидация токена + список счетов.
* `POST /broker/connect`       — сохраняет зашифрованный токен (AESGCM).
* `POST /broker/connections/{id}/sync` — ручной trigger через orchestrator.
* `POST /broker/trigger-sync/{id}` — alias выше для совместимости с UI.
* `GET  /broker/connections`   — список подключений пользователя.
* `DELETE /broker/connections/{id}` — soft-delete.
* `PATCH /broker/connections/{id}` — обновить sync interval / auto_sync.
* `GET  /broker/portfolio`     — текущий портфель + ROI.
* `GET  /broker/balance-history` — equity curve по BalanceSnapshot.
* `GET  /broker/net-deposit`   — баланс на дату.
* `GET  /broker/sync-status`   — общий статус.

Безопасность: токен принимается через JSON body (не Query), шифруется
AESGCM в БД, никогда не возвращается клиенту. Scope-валидация требует,
чтобы у токена был хотя бы READ_ONLY на выбранном счёте.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

import models
from adapters.persistence.token_repo import TokenRepository
from adapters.security.token_encryption import (
    TokenEncryptionError,
    TokenEncryptionService,
)
from adapters.tinkoff.client_factory import client_factory
from adapters.tinkoff.operations_client import TinkoffOperationsClient
from adapters.tinkoff.users_client import TinkoffAccountInfo, TinkoffUsersClient
from application.sync.orchestrator import build_default_orchestrator
from auth_service import get_current_user, get_user_account
from capital_service import sync_initial_balance
from config import settings
from database import get_db
from domain.exceptions import (
    BrokerError,
    BrokerUnavailable,
    RateLimitExceeded,
    TokenInvalid,
    TokenScopeInsufficient,
)
from logger import get_logger
from models import (
    Account,
    BalanceSnapshot,
    BrokerConnection,
    BrokerType,
    CapitalOperation,
    Trade,
)
from rate_limiter import limiter, AUTH_LIMIT
from sync_scheduler import scheduler
from utils.datetime_utils import utc_now_naive

log = get_logger("broker_router")
router = APIRouter(prefix="/broker", tags=["broker"])


# ── feature flag ──────────────────────────────────────────────────────


_BROKER_SYNC_V2_DISABLED_DETAIL = (
    "Интеграция с Тинькофф временно отключена администратором (BROKER_SYNC_V2_ENABLED=false). "
    "Включите флаг и перезагрузите backend."
)


def _ensure_broker_sync_v2_enabled() -> None:
    if not settings.BROKER_SYNC_V2_ENABLED:
        raise HTTPException(status_code=503, detail=_BROKER_SYNC_V2_DISABLED_DETAIL)


def _token_repo() -> TokenRepository:
    """Singleton-инстанс TokenRepository. Создаётся лениво при первом запросе."""
    try:
        encryption = TokenEncryptionService()
    except TokenEncryptionError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Master encryption key not configured: {exc}",
        )
    return TokenRepository(encryption=encryption)


# ── schemas ───────────────────────────────────────────────────────────


class BrokerAccountInfoResponse(BaseModel):
    id: str
    name: str
    type: str
    status: str
    access_level: str


class TokenVerifyRequest(BaseModel):
    broker: str = Field("tinkoff", description="Тип брокера")
    api_token: str = Field(..., min_length=10, description="API токен")


class TokenVerifyResponse(BaseModel):
    valid: bool
    error: Optional[str] = None
    accounts: list[BrokerAccountInfoResponse] = []


class ConnectBrokerRequest(BaseModel):
    broker: str = Field("tinkoff", description="Тип брокера")
    api_token: str = Field(..., min_length=10, description="API токен")
    broker_account_id: str = Field(..., description="ID счёта в брокере")
    sync_from_date: Optional[datetime] = None
    auto_sync_enabled: bool = True
    sync_interval_minutes: int = Field(15, ge=5, le=1440)


class BrokerConnectionResponse(BaseModel):
    id: int
    broker: str
    broker_account_id: str
    is_active: bool
    auto_sync_enabled: bool
    sync_interval_minutes: int
    last_sync_at: Optional[datetime]
    last_sync_status: Optional[str]
    # SYNC-01: причина последней ошибки (orchestrator пишет
    # "deactivated: token_invalid" при отозванном токене) + computed-флаг
    # для UI «нужно переподключить брокера». Сам токен НЕ возвращается.
    last_sync_error: Optional[str] = None
    needs_reconnect: bool = False
    total_synced_trades: int  # legacy: кумулятивный счётчик из BrokerConnection
    created_at: datetime
    consecutive_failures: int = 0
    circuit_open_until: Optional[datetime] = None
    # PR 26 (Phase 3): rich детали последнего sync для UI карточки.
    last_sync_operations_count: Optional[int] = None
    last_sync_trades_count: Optional[int] = None
    last_sync_positions_count: Optional[int] = None
    last_sync_duration_ms: Optional[int] = None
    # Реальный count из таблиц (а не legacy total_synced_trades).
    real_trades_count: int = 0
    real_operations_count: int = 0

    model_config = ConfigDict(from_attributes=True)


class SyncResultResponse(BaseModel):
    success: bool
    operations_synced: int = 0
    trades_built: int = 0
    positions_open: int = 0
    account_varmargin_total: str = "0"
    duration_sec: float = 0.0
    error: Optional[str] = None


# ── helpers ───────────────────────────────────────────────────────────


def _validate_token_scope(accounts: List[TinkoffAccountInfo], broker_account_id: str) -> None:
    """Подтверждает, что токен strictly READ_ONLY на выбранном счёте.

    AU7 hardening: FULL_ACCESS токены отклоняются — Полистата это
    журнал-аналитика, ему хватает read-only прав, а у full-access
    blast radius существенно больше (потенциальные ордера, вывод средств).
    Раньше мы принимали оба уровня; теперь требуем строго read-only.
    """
    matched = next((a for a in accounts if a.id == broker_account_id), None)
    if matched is None:
        raise HTTPException(
            status_code=400,
            detail=f"Счёт {broker_account_id} не найден в списке аккаунтов токена",
        )
    if matched.access_level == "ACCOUNT_ACCESS_LEVEL_FULL_ACCESS":
        raise HTTPException(
            status_code=400,
            detail=(
                f"Токен имеет FULL_ACCESS на счёте {broker_account_id}. "
                "Для безопасности Полистата принимает только read-only токены. "
                "Создайте новый read-only токен в lk.tbank.ru → Инвестиции → "
                "Настройки → API → «Доступ только на чтение»."
            ),
        )
    if not matched.is_strictly_read_only:
        raise HTTPException(
            status_code=400,
            detail=(
                f"У токена нет прав чтения для счёта {broker_account_id} "
                f"(access_level={matched.access_level}). Создайте read-only "
                "токен в lk.tbank.ru → Инвестиции → Настройки → API."
            ),
        )


def _account_to_response(acc: TinkoffAccountInfo) -> BrokerAccountInfoResponse:
    return BrokerAccountInfoResponse(
        id=acc.id,
        name=acc.name,
        type=acc.type,
        status=acc.status,
        access_level=acc.access_level,
    )


def _orm_to_response(conn: BrokerConnection, db: Optional[Session] = None) -> BrokerConnectionResponse:
    # PR 26 (Phase 3): реальные counts из таблиц для информативной карточки.
    real_trades_count = 0
    real_operations_count = 0
    if db is not None and conn.account_id is not None:
        from sqlalchemy import func as sa_func
        real_trades_count = (
            db.query(sa_func.count(models.Trade.id))
            .filter(models.Trade.account_id == conn.account_id)
            .scalar()
        ) or 0
        real_operations_count = (
            db.query(sa_func.count(models.OperationORM.id))
            .filter(models.OperationORM.account_id == conn.account_id)
            .scalar()
        ) or 0

    return BrokerConnectionResponse(
        id=conn.id,
        broker=conn.broker.value if hasattr(conn.broker, "value") else str(conn.broker),
        broker_account_id=conn.broker_account_id or "",
        is_active=bool(conn.is_active),
        auto_sync_enabled=bool(conn.auto_sync_enabled),
        sync_interval_minutes=conn.sync_interval_minutes or 60,
        last_sync_at=conn.last_sync_at,
        last_sync_status=conn.last_sync_status,
        last_sync_error=conn.last_sync_error,
        needs_reconnect=not bool(conn.is_active),
        total_synced_trades=conn.total_synced_trades or 0,
        created_at=conn.created_at,
        consecutive_failures=conn.consecutive_failures or 0,
        circuit_open_until=conn.circuit_open_until,
        last_sync_operations_count=conn.last_sync_operations_count,
        last_sync_trades_count=conn.last_sync_trades_count,
        last_sync_positions_count=conn.last_sync_positions_count,
        last_sync_duration_ms=conn.last_sync_duration_ms,
        real_trades_count=int(real_trades_count),
        real_operations_count=int(real_operations_count),
    )


# ── endpoints ──────────────────────────────────────────────────────────


@router.post("/verify-token", response_model=TokenVerifyResponse)
@limiter.limit(AUTH_LIMIT)
async def verify_broker_token(
    request: Request,
    payload: TokenVerifyRequest,
    current_user: models.User = Depends(get_current_user),
):
    """Echo-валидация токена через `users.list_accounts()`.

    AU6 hardening: только для авторизованных юзеров + 5/min rate-limit.
    Раньше endpoint был открытым и работал как DoS-oracle: любой мог
    выжигать наш ежеминутный лимит к T-Bank API на 200 запросов.
    """
    _ensure_broker_sync_v2_enabled()
    if payload.broker.lower() != "tinkoff":
        raise HTTPException(status_code=400, detail="Пока поддерживается только Тинькофф")

    try:
        async with client_factory.async_client(payload.api_token) as services:
            users = TinkoffUsersClient(services)
            accounts = await users.list_accounts()
    except TokenInvalid as exc:
        return TokenVerifyResponse(valid=False, error=f"Токен невалиден: {exc.message}")
    except TokenScopeInsufficient as exc:
        return TokenVerifyResponse(valid=False, error=f"Недостаточно прав: {exc.message}")
    except RateLimitExceeded:
        return TokenVerifyResponse(valid=False, error="Превышен лимит запросов, попробуйте через минуту")
    except BrokerUnavailable as exc:
        return TokenVerifyResponse(valid=False, error=f"Сервис временно недоступен: {exc.message}")
    except BrokerError as exc:
        return TokenVerifyResponse(valid=False, error=f"{type(exc).__name__}: {exc.message}")

    return TokenVerifyResponse(
        valid=True,
        accounts=[_account_to_response(a) for a in accounts],
    )


@router.post("/connect", response_model=BrokerConnectionResponse)
async def connect_broker(
    request: ConnectBrokerRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Подключить брокера: validate scope → encrypt → store. Никакого
    plaintext-токена в БД.
    """
    _ensure_broker_sync_v2_enabled()
    if request.broker.lower() != "tinkoff":
        raise HTTPException(status_code=400, detail="Пока поддерживается только Тинькофф")

    # 1. Echo-валидация + scope check.
    try:
        async with client_factory.async_client(request.api_token) as services:
            users = TinkoffUsersClient(services)
            accounts = await users.list_accounts()
    except TokenInvalid:
        raise HTTPException(status_code=400, detail="Невалидный токен")
    except TokenScopeInsufficient:
        raise HTTPException(status_code=400, detail="Недостаточно прав у токена")
    except BrokerError as exc:
        raise HTTPException(status_code=502, detail=f"Tinkoff API: {exc.message}")

    _validate_token_scope(accounts, request.broker_account_id)

    # 2. Найти/создать наш Account.
    user_account = get_user_account(db, current_user)

    # AU5: один broker_account_id per наш Account.
    # FIFO matching и positions scope сейчас работают по account_id, не по
    # (account_id, broker_account_id). Если бы юзер подключил БС + ИИС
    # к одному local Account, операции смешались бы в FIFO.
    # Решение: если для этого Account уже есть active BrokerConnection
    # с ДРУГИМ broker_account_id — отказать с подсказкой создать второй
    # local Account (через /accounts API).
    existing_conn = (
        db.query(BrokerConnection)
        .filter(
            BrokerConnection.account_id == user_account.id,
            BrokerConnection.is_active.is_(True),
            BrokerConnection.broker_account_id != request.broker_account_id,
        )
        .first()
    )
    if existing_conn is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"К вашему Account «{user_account.name}» уже подключён другой "
                f"брокерский счёт ({existing_conn.broker_account_id}). FIFO-расчёт "
                "не разделяет позиции между разными broker-счетами в одном local "
                "Account, поэтому нужно создать отдельный Account (Настройки → "
                "Счета → «+ Добавить») и подключить второй брокер туда."
            ),
        )

    # 3. Зашифровать и сохранить.
    repo = _token_repo()
    try:
        connection = repo.store(
            db,
            account_id=user_account.id,
            broker_account_id=request.broker_account_id,
            plaintext_token=request.api_token,
            sync_interval_minutes=request.sync_interval_minutes,
        )
    except TokenEncryptionError as exc:
        raise HTTPException(status_code=500, detail=f"Encryption failed: {exc}")

    if not request.auto_sync_enabled:
        connection.auto_sync_enabled = False
    if request.sync_from_date is not None:
        connection.sync_from_date = (
            request.sync_from_date.replace(tzinfo=None)
            if request.sync_from_date.tzinfo
            else request.sync_from_date
        )
    db.commit()
    db.refresh(connection)

    log.info(
        "broker connect: user_id=%s account_id=%s broker_account_id=%s",
        current_user.id,
        user_account.id,
        request.broker_account_id,
    )
    return _orm_to_response(connection, db)


@router.get("/connections", response_model=List[BrokerConnectionResponse])
async def list_connections(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Список подключений юзера, ВКЛЮЧАЯ неактивные.

    SYNC-01: orchestrator деактивирует подключение при отозванном токене
    (is_active=False, api_token=""). Раньше фильтр is_active=True молча
    прятал его из UI — юзер видел «подключение исчезло» вместо баннера
    «переподключите брокера». Теперь неактивные возвращаются с
    needs_reconnect=true + last_sync_error; фронт сам решает что показывать.
    """
    account = get_user_account(db, current_user)
    rows = (
        db.query(BrokerConnection)
        .filter(BrokerConnection.account_id == account.id)
        .all()
    )
    return [_orm_to_response(r, db) for r in rows]


@router.post("/connections/{connection_id}/sync", response_model=SyncResultResponse)
async def sync_now(
    connection_id: int,
    full: bool = Query(False, description="Полная синхронизация с начала истории"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Ручной trigger sync через orchestrator. Блокирующий — ждёт результат."""
    _ensure_broker_sync_v2_enabled()
    account = get_user_account(db, current_user)
    conn = (
        db.query(BrokerConnection)
        .filter(BrokerConnection.id == connection_id, BrokerConnection.account_id == account.id)
        .first()
    )
    if conn is None:
        raise HTTPException(status_code=404, detail="Подключение не найдено")
    if not conn.is_active:
        raise HTTPException(status_code=400, detail="Подключение деактивировано")
    if full:
        conn.sync_cursor = None
        db.commit()

    orchestrator = build_default_orchestrator()
    if orchestrator is None:
        raise HTTPException(status_code=500, detail="Orchestrator unavailable")

    try:
        report = await orchestrator.sync_one_account(connection_id)
    except TokenInvalid:
        raise HTTPException(status_code=401, detail="Токен невалиден или отозван")
    except RateLimitExceeded:
        raise HTTPException(status_code=429, detail="Превышен лимит запросов")
    except BrokerError as exc:
        raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc.message}")
    except Exception as exc:
        # Плановый sync переживает любые исключения через _guard_one; ручной
        # путь (sync_one_account) — нет. Без этого catch-all непредвиденная
        # ошибка (ValueError/KeyError/DB) рвала HTTP-коннект → «Failed to fetch»
        # в браузере вместо понятного ответа. Внутренности не светим клиенту.
        log.exception("sync_now failed unexpectedly for connection_id=%s", connection_id)
        raise HTTPException(
            status_code=500,
            detail=f"Синхронизация завершилась с ошибкой: {type(exc).__name__}",
        )

    return SyncResultResponse(
        success=report.success,
        operations_synced=report.operations_new_or_updated,
        trades_built=report.trades_built,
        positions_open=report.positions_open,
        account_varmargin_total=str(report.account_varmargin_total),
        duration_sec=report.duration_sec,
        error=report.error_message,
    )


@router.post("/trigger-sync/{connection_id}", response_model=SyncResultResponse)
async def trigger_manual_sync(
    connection_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Alias для `/connections/{id}/sync` (совместимость со старым UI)."""
    return await sync_now(connection_id, full=False, db=db, current_user=current_user)


@router.post("/connections/{connection_id}/reset")
async def reset_connection(
    connection_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    Полная пересинхронизация: удаляет все sync-данные (trades с
    data_source='tinkoff_v2', positions, operations) и сбрасывает cursor.
    Следующий sync будет полным (с начала истории).

    Сохраняет: legacy/manual сделки, само подключение и токен.
    """
    from tools.reset_broker_account import reset_account

    account = get_user_account(db, current_user)
    conn = (
        db.query(BrokerConnection)
        .filter(BrokerConnection.id == connection_id, BrokerConnection.account_id == account.id)
        .first()
    )
    if conn is None:
        raise HTTPException(status_code=404, detail="Подключение не найдено")

    # Закрываем текущую сессию (database.get_db) перед reset_account, чтобы
    # тот мог открыть свою собственную SessionLocal и сделать commit.
    db.commit()
    result = reset_account(account.id, confirmed=True)
    return {
        "message": "Аккаунт сброшен, готов к полной пересинхронизации",
        "connection_id": connection_id,
        **result,
    }


@router.delete("/connections/{connection_id}")
async def disconnect_broker(
    connection_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Soft-delete: is_active=False, api_token затирается."""
    account = get_user_account(db, current_user)
    conn = (
        db.query(BrokerConnection)
        .filter(BrokerConnection.id == connection_id, BrokerConnection.account_id == account.id)
        .first()
    )
    if conn is None:
        raise HTTPException(status_code=404, detail="Подключение не найдено")

    repo = _token_repo()
    repo.deactivate(
        db,
        account_id=account.id,
        broker_account_id=conn.broker_account_id,
        reason="user_request",
    )
    db.commit()

    # SYNC-11 (Sprint 3, Task 4.3): cleanup stream-task и per-account lock,
    # чтобы они не утекали навсегда после soft-delete. Lock привязан к
    # account_id, поэтому освобождаем его только если у аккаунта не
    # осталось других активных BrokerConnection'ов (иначе соседний
    # connection или cursor-sync orchestrator продолжают пользоваться
    # тем же lock'ом).
    from application.sync.stream_manager import stream_manager

    await stream_manager.stop_task(connection_id)

    remaining_active = (
        db.query(BrokerConnection.id)
        .filter(
            BrokerConnection.account_id == account.id,
            BrokerConnection.is_active.is_(True),
        )
        .count()
    )
    if remaining_active == 0:
        stream_manager.release_account_lock(account.id)

    return {"message": "Брокер отключён", "id": connection_id}


@router.patch("/connections/{connection_id}", response_model=BrokerConnectionResponse)
async def update_connection(
    connection_id: int,
    auto_sync_enabled: Optional[bool] = None,
    sync_interval_minutes: Optional[int] = Query(None, ge=5, le=1440),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    account = get_user_account(db, current_user)
    conn = (
        db.query(BrokerConnection)
        .filter(
            BrokerConnection.id == connection_id,
            BrokerConnection.account_id == account.id,
            BrokerConnection.is_active.is_(True),
        )
        .first()
    )
    if conn is None:
        raise HTTPException(status_code=404, detail="Подключение не найдено")
    if auto_sync_enabled is not None:
        conn.auto_sync_enabled = auto_sync_enabled
    if sync_interval_minutes is not None:
        conn.sync_interval_minutes = sync_interval_minutes
    conn.updated_at = utc_now_naive()
    db.commit()
    db.refresh(conn)
    return _orm_to_response(conn, db)


@router.get("/sync-status")
async def get_sync_status(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    account = get_user_account(db, current_user)
    connections = (
        db.query(BrokerConnection)
        .filter(BrokerConnection.account_id == account.id, BrokerConnection.is_active.is_(True))
        .all()
    )
    now = utc_now_naive()
    items = []
    for c in connections:
        next_sync = None
        if c.auto_sync_enabled and c.last_sync_at:
            next_sync = c.last_sync_at + timedelta(minutes=c.sync_interval_minutes or 60)
        items.append(
            {
                "id": c.id,
                "broker": c.broker.value if hasattr(c.broker, "value") else str(c.broker),
                "broker_account_id": c.broker_account_id,
                "auto_sync_enabled": bool(c.auto_sync_enabled),
                "sync_interval_minutes": c.sync_interval_minutes,
                "last_sync_at": c.last_sync_at.isoformat() if c.last_sync_at else None,
                "last_sync_status": c.last_sync_status,
                "last_sync_error": c.last_sync_error,
                "next_sync_at": next_sync.isoformat() if next_sync else None,
                "consecutive_failures": c.consecutive_failures or 0,
                "circuit_open_until": c.circuit_open_until.isoformat() if c.circuit_open_until else None,
                "total_synced_trades": c.total_synced_trades or 0,
                # PR 17: детали последней синхронизации для UI-индикатора.
                "last_sync_operations_count": c.last_sync_operations_count,
                "last_sync_trades_count": c.last_sync_trades_count,
                "last_sync_positions_count": c.last_sync_positions_count,
                "last_sync_duration_ms": c.last_sync_duration_ms,
            }
        )
    return {
        "has_connections": bool(items),
        "scheduler": scheduler.get_status(),
        "connections": items,
    }


@router.get("/health")
async def get_sync_health(
    history_days: int = Query(7, ge=1, le=90, description="История за N дней"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    PR 20: Health-audit состояния импорта Tinkoff для текущего юзера.

    Возвращает последний health check (для UI-индикатора) + историю за N дней.
    Юзер видит свой статус: ok / warning / error + краткое описание.
    Технические детали (sample_ids конкретных trade'ов) включены — фронт сам
    решает что показывать пользователю, а что только админу.
    """
    from datetime import timedelta

    from models import SyncHealthCheckORM

    account = get_user_account(db, current_user)
    latest = (
        db.query(SyncHealthCheckORM)
        .filter(SyncHealthCheckORM.account_id == account.id)
        .order_by(SyncHealthCheckORM.checked_at.desc())
        .first()
    )
    threshold = utc_now_naive() - timedelta(days=history_days)
    history_rows = (
        db.query(SyncHealthCheckORM)
        .filter(
            SyncHealthCheckORM.account_id == account.id,
            SyncHealthCheckORM.checked_at >= threshold,
        )
        .order_by(SyncHealthCheckORM.checked_at.desc())
        .all()
    )

    def _serialize(row: "SyncHealthCheckORM") -> dict:
        issues = row.issues_json or []
        return {
            "id": row.id,
            "checked_at": row.checked_at.isoformat() if row.checked_at else None,
            "status": row.status,
            "total_trades_checked": row.total_trades_checked,
            "trades_with_issues": row.trades_with_issues,
            "main_issue": issues[0]["check_id"] if issues else None,
            "issues": issues,
        }

    return {
        "latest": _serialize(latest) if latest else None,
        "history": [_serialize(r) for r in history_rows],
    }


@router.get("/portfolio")
async def get_portfolio(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Текущий портфель из Tinkoff API (live)."""
    _ensure_broker_sync_v2_enabled()
    account = get_user_account(db, current_user)
    conn = (
        db.query(BrokerConnection)
        .filter(BrokerConnection.account_id == account.id, BrokerConnection.is_active.is_(True))
        .first()
    )
    if conn is None:
        raise HTTPException(status_code=404, detail="Нет активных подключений к брокеру")

    repo = _token_repo()
    try:
        token = repo.get_decrypted(db, account_id=account.id, broker_account_id=conn.broker_account_id)
    except TokenEncryptionError as exc:
        raise HTTPException(status_code=500, detail=f"Cannot decrypt token: {exc}")
    if not token:
        raise HTTPException(status_code=410, detail="Подключение брокера повреждено, переподключите")

    # Распарсить базовые поля.
    def _money_decimal(m) -> float:
        if m is None:
            return 0.0
        units = getattr(m, "units", 0) or 0
        nano = getattr(m, "nano", 0) or 0
        return float(units) + float(nano) / 1e9

    # SDK-вызов И парсинг ответа — в одном guarded-блоке: раньше парсинг
    # (доступ к полям raw) шёл ВНЕ try, и кривой/неполный PortfolioResponse рвал
    # HTTP-коннект («Failed to fetch») вместо чистого 502.
    try:
        async with client_factory.async_client(token) as services:
            ops = TinkoffOperationsClient(services)
            raw = await ops.get_portfolio_raw(conn.broker_account_id)

        total_balance = _money_decimal(getattr(raw, "total_amount_portfolio", None))
        cash = _money_decimal(getattr(raw, "total_amount_currencies", None))
        stocks = _money_decimal(getattr(raw, "total_amount_shares", None))
        bonds_value = _money_decimal(getattr(raw, "total_amount_bonds", None))
        etf_value = _money_decimal(getattr(raw, "total_amount_etf", None))
        futures_value = _money_decimal(getattr(raw, "total_amount_futures", None))
        options_value = _money_decimal(getattr(raw, "total_amount_options", None))

        initial = float(account.initial_balance) if account and account.initial_balance else None
        roi = None
        if initial and initial > 0:
            roi = (total_balance - initial) / initial * 100

        positions_raw = list(getattr(raw, "positions", []) or [])
        positions = []
        for p in positions_raw:
            ticker = getattr(p, "figi", None) or ""
            qty = _money_decimal(getattr(p, "quantity", None))
            if ticker == "RUB000UTSTOM":
                continue  # рубли отдельно
            positions.append(
                {
                    "ticker": ticker,
                    "instrument_uid": getattr(p, "instrument_uid", None),
                    "instrument_type": getattr(p, "instrument_type", None),
                    "quantity": qty,
                    "average_price": _money_decimal(getattr(p, "average_position_price", None)),
                    "current_price": _money_decimal(getattr(p, "current_price", None)),
                    "unrealized_pnl": _money_decimal(getattr(p, "expected_yield_fifo", None)),
                }
            )
    except TokenInvalid:
        raise HTTPException(status_code=401, detail="Токен невалиден")
    except BrokerError as exc:
        raise HTTPException(status_code=502, detail=f"Tinkoff API: {exc.message}")
    except Exception as exc:
        log.exception("get_portfolio failed unexpectedly for account_id=%s", account.id)
        raise HTTPException(
            status_code=502,
            detail=f"Не удалось получить портфель: {type(exc).__name__}",
        )

    return {
        "success": True,
        "total_balance": total_balance,
        "cash": cash,
        "stocks_value": stocks,
        "bonds_value": bonds_value,
        "etf_value": etf_value,
        "futures_value": futures_value,
        "options_value": options_value,
        "initial_balance": initial,
        "roi_percent": roi,
        "positions": positions,
        "updated_at": utc_now_naive().isoformat(),
    }


@router.get("/balance-history")
async def get_balance_history(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Equity curve из BalanceSnapshot — без вызова Tinkoff API."""
    account = get_user_account(db, current_user)
    conn = (
        db.query(BrokerConnection)
        .filter(BrokerConnection.account_id == account.id, BrokerConnection.is_active.is_(True))
        .first()
    )
    if conn is None:
        return {"snapshots": [], "metrics": None}

    from_date = utc_now_naive() - timedelta(days=days)
    snapshots = (
        db.query(BalanceSnapshot)
        .filter(BalanceSnapshot.account_id == conn.account_id, BalanceSnapshot.date >= from_date)
        .order_by(BalanceSnapshot.date.asc())
        .all()
    )
    if not snapshots:
        return {"snapshots": [], "metrics": None}

    balances = [float(s.balance) for s in snapshots]
    first_balance = balances[0]
    last_balance = balances[-1]
    peak = max(balances)
    roi = ((last_balance - first_balance) / first_balance * 100) if first_balance > 0 else 0

    max_drawdown = 0
    peak_so_far = balances[0]
    for b in balances:
        if b > peak_so_far:
            peak_so_far = b
        dd = (peak_so_far - b) / peak_so_far * 100 if peak_so_far > 0 else 0
        if dd > max_drawdown:
            max_drawdown = dd

    return {
        "snapshots": [
            {
                "date": s.date.isoformat(),
                "balance": float(s.balance),
                "cash": float(s.cash) if s.cash else 0,
                "stocks_value": float(s.stocks_value) if s.stocks_value else 0,
                "futures_value": float(s.futures_value) if s.futures_value else 0,
                "unrealized_pnl": float(s.unrealized_pnl) if s.unrealized_pnl else 0,
            }
            for s in snapshots
        ],
        "metrics": {
            "start_balance": first_balance,
            "current_balance": last_balance,
            "peak_balance": peak,
            "roi_percent": round(roi, 2),
            "max_drawdown_percent": round(max_drawdown, 2),
            "trading_days": len(snapshots),
        },
    }


@router.post("/set-initial-balance", deprecated=True)
async def set_initial_balance(
    initial_balance: float,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """
    DEPRECATED (PR 21): ручной ввод стартового капитала отключён.

    Используем автоподстановку из Tinkoff `portfolio.total_amount`
    при первом sync (см. `pipeline._autoset_initial_balance_if_needed`).

    Endpoint оставлен возвращать 410 для backward-compat — клиент должен
    обновиться. Удаление через 1 минорный релиз.
    """
    raise HTTPException(
        status_code=410,
        detail=(
            "Ручной ввод стартового капитала отключён. "
            "Стартовый капитал рассчитывается автоматически из Tinkoff API "
            "при первой синхронизации."
        ),
    )


@router.get("/net-deposit")
async def get_net_deposit_on_date(
    date: datetime,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Рассчитывает баланс на дату: (Вводы - Выводы) + (Реализованный PnL - Комиссии)."""
    account = get_user_account(db, current_user)
    conn = (
        db.query(BrokerConnection)
        .filter(BrokerConnection.account_id == account.id, BrokerConnection.is_active.is_(True))
        .first()
    )
    if conn is None:
        raise HTTPException(status_code=404, detail="Нет активных подключений")

    target = date.replace(hour=23, minute=59, second=59)
    deposits = (
        db.query(func.sum(CapitalOperation.amount))
        .filter(
            CapitalOperation.account_id == conn.account_id,
            CapitalOperation.operation_type == "deposit",
            CapitalOperation.date <= target,
        )
        .scalar()
        or 0
    )
    withdrawals = (
        db.query(func.sum(CapitalOperation.amount))
        .filter(
            CapitalOperation.account_id == conn.account_id,
            CapitalOperation.operation_type == "withdrawal",
            CapitalOperation.date <= target,
        )
        .scalar()
        or 0
    )
    trade_stats = (
        db.query(func.sum(Trade.pnl), func.sum(Trade.commission))
        .filter(Trade.account_id == conn.account_id, Trade.exit_at <= target)
        .first()
    )
    realized_pnl = float(trade_stats[0] or 0)
    commissions = float(trade_stats[1] or 0)

    net_deposit = float(deposits) - float(withdrawals)
    return {
        "date": target.isoformat(),
        "deposits": float(deposits),
        "withdrawals": float(withdrawals),
        "realized_pnl": realized_pnl,
        "commissions": commissions,
        "net_deposit": net_deposit,
        "equity_on_date": net_deposit + realized_pnl - commissions,
    }
