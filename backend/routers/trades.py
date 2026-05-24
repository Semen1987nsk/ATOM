"""
Trades Router — CRUD для сделок, импорт, unrealized PnL
"""
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Query, Form
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
import asyncio

from decimal import Decimal

import database
import models
import schemas
import auth_service
import import_service
import market_service
import ai_service
from moex_service import get_moex_service
import pnl_service
from capital_service import sync_initial_balance
from config import settings
from logger import get_logger
from rate_limiter import limiter, IMPORT_LIMIT, AI_LIMIT, API_LIMIT
from subscription_service import enforce_trade_limit, require_pro

log = get_logger("trades")

router = APIRouter(prefix="/trades", tags=["trades"])


def _direction_value(direction) -> str:
    """
    Нормализует поле direction (Enum/str/None) в строковое значение.
    Используется для дедупликации import'а — ключ должен быть hashable
    и независим от того, как пришёл direction (TradeDirection.LONG vs 'long').
    """
    if direction is None:
        return ""
    if hasattr(direction, "value"):
        return str(direction.value).lower()
    return str(direction).lower()


async def _read_upload_with_limit(file: UploadFile) -> bytes:
    """
    Считывает UploadFile в память с проверкой лимита размера.

    Защита от:
    - DoS через гигантский xlsx-файл (xlsx-bomb).
    - Истощения памяти — лимит из settings.MAX_UPLOAD_SIZE_MB (default 10MB).

    UploadFile.read() полностью буферизирует в RAM, поэтому проверяем размер
    после чтения. Для real-streaming можно перейти на chunk-read, но для
    отчётов трейдеров (обычно <1MB) лимит в 10MB достаточен.
    """
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    contents = await file.read()
    if len(contents) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Файл слишком большой ({len(contents) // 1024} KB). "
                   f"Лимит: {settings.MAX_UPLOAD_SIZE_MB} MB.",
        )
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Пустой файл")
    return contents

# Инициализируем сервис рыночных данных
market_data_service = market_service.MarketService()


# get_account_id is now centralized in auth_service


@router.post("/", response_model=schemas.Trade)
async def create_trade(
    trade: schemas.TradeCreate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    account_id = auth_service.get_account_id(db, current_user)
    enforce_trade_limit(db, current_user)

    # Check for existing open trades for this symbol
    open_trades = db.query(models.Trade).filter(
        models.Trade.account_id == account_id,
        models.Trade.symbol == trade.symbol,
        models.Trade.exit_at == None
    ).order_by(models.Trade.entry_at).all()

    # Determine if this is a closing operation
    is_closing = False
    if open_trades:
        if open_trades[0].direction != trade.direction:
            is_closing = True

    if is_closing:
        qty_to_close = float(trade.quantity)
        last_modified_trade = None
        
        for open_trade in open_trades:
            if qty_to_close <= 0:
                break
            
            available_qty = float(open_trade.quantity)
            
            if qty_to_close >= available_qty:
                # Full close
                open_trade.exit_price = trade.entry_price
                open_trade.exit_at = trade.entry_at
                open_trade.exit_reason = trade.setup_name or "Manual Close"
                
                # Рассчитываем MAE/MFE
                try:
                    mae, mfe = market_data_service.calculate_mae_mfe(
                        ticker=open_trade.symbol,
                        direction=open_trade.direction.value,
                        entry_price=float(open_trade.entry_price),
                        entry_time=open_trade.entry_at,
                        exit_time=trade.entry_at
                    )
                    if mae is not None:
                        open_trade.mae_price = mae
                    if mfe is not None:
                        open_trade.mfe_price = mfe
                except Exception as e:
                    log.warning(f"Failed to calculate MAE/MFE for trade {open_trade.id}: {e}")
                
                # Calculate PnL + net_pnl via unified service
                ratio = available_qty / float(trade.quantity)
                exit_comm = (trade.commission or 0) * ratio
                pnl_service.apply_close_pnl(
                    trade=open_trade,
                    exit_commission=exit_comm,
                )

                qty_to_close -= available_qty
                last_modified_trade = open_trade
                
            else:
                # Partial close - Split the trade
                closed_trade = models.Trade(
                    account_id=open_trade.account_id,
                    symbol=open_trade.symbol,
                    asset_name=open_trade.asset_name,
                    asset_type=open_trade.asset_type,
                    direction=open_trade.direction,
                    entry_price=open_trade.entry_price,
                    quantity=qty_to_close,
                    entry_at=open_trade.entry_at,
                    setup_name=open_trade.setup_name,
                    notes=open_trade.notes,
                    tags=open_trade.tags
                )
                
                closed_trade.exit_price = trade.entry_price
                closed_trade.exit_at = trade.entry_at
                closed_trade.exit_reason = trade.setup_name or "Manual Partial Close"
                
                # Exit commission proportional to closed qty
                total_close_qty = float(trade.quantity)
                exit_comm_ratio = qty_to_close / total_close_qty
                exit_comm = (trade.commission or 0) * exit_comm_ratio
                
                # PnL + net_pnl via unified service (includes swap split)
                pnl_service.apply_partial_close_pnl(
                    closed_trade=closed_trade,
                    original_trade=open_trade,
                    close_quantity=qty_to_close,
                    exit_commission=exit_comm,
                )
                
                try:
                    mae, mfe = market_data_service.calculate_mae_mfe(
                        ticker=closed_trade.symbol,
                        direction=closed_trade.direction.value,
                        entry_price=float(closed_trade.entry_price),
                        entry_time=closed_trade.entry_at,
                        exit_time=trade.entry_at
                    )
                    if mae is not None:
                        closed_trade.mae_price = mae
                    if mfe is not None:
                        closed_trade.mfe_price = mfe
                except Exception as e:
                    log.warning(f"Failed to calculate MAE/MFE for partial close: {e}")
                
                db.add(closed_trade)
                # NOTE: open_trade.quantity already reduced by apply_partial_close_pnl
                
                qty_to_close = 0
                last_modified_trade = closed_trade
        
        # If quantity remains, create a new trade (Flip)
        if qty_to_close > 0:
            remainder_trade_data = trade.model_dump()
            remainder_trade = models.Trade(**remainder_trade_data)
            remainder_trade.quantity = qty_to_close
            
            total_qty = float(trade.quantity)
            rem_ratio = qty_to_close / total_qty
            remainder_trade.commission = (trade.commission or 0) * rem_ratio
            remainder_trade.entry_commission = remainder_trade.commission
            
            db.add(remainder_trade)
            last_modified_trade = remainder_trade
            
        db.commit()
        if last_modified_trade:
            db.refresh(last_modified_trade)
            return last_modified_trade
        return open_trades[0]

    else:
        # Standard New Trade
        db_trade = models.Trade(**trade.model_dump())
        db_trade.account_id = account_id
        db_trade.entry_commission = db_trade.commission
        db.add(db_trade)
        db.commit()
        db.refresh(db_trade)
        return db_trade


# ==================== IMPORT PREVIEW ====================

@router.post("/import/preview")
@limiter.limit(IMPORT_LIMIT)
async def preview_import(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """
    Превью импорта: парсит файл и возвращает список сделок БЕЗ сохранения.
    Показывает какие сделки новые, а какие уже существуют (дубликаты).
    """
    account_id = auth_service.get_account_id(db, current_user)

    contents = await _read_upload_with_limit(file)
    try:
        trades_data = import_service.parse_trade_file(contents, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Парсим информацию о балансе из файла
    balance_info = import_service.parse_account_balance(contents, file.filename)
    
    # Bulk-загрузка существующих сделок ОДНИМ запросом — раньше для 5K-строчного
    # отчёта было 5K SELECT (N+1). Строим локальный индекс по dedup-ключу.
    existing_rows = db.query(
        models.Trade.id, models.Trade.symbol, models.Trade.direction, models.Trade.entry_at
    ).filter(models.Trade.account_id == account_id).all()
    existing_index = {
        (sym, _direction_value(direction), entry_at): _id
        for _id, sym, direction, entry_at in existing_rows
    }

    # Проверяем каждую сделку на дубликат
    preview_items = []
    for idx, trade_dict in enumerate(trades_data):
        dedup_key = (
            trade_dict.get('symbol'),
            _direction_value(trade_dict.get('direction')),
            trade_dict.get('entry_at'),
        )
        existing_id = existing_index.get(dedup_key)

        # Форматируем для превью
        entry_at = trade_dict.get('entry_at')
        exit_at = trade_dict.get('exit_at')
        
        preview_items.append({
            "index": idx,
            "symbol": trade_dict.get('symbol', ''),
            "asset_name": trade_dict.get('asset_name', ''),
            "direction": trade_dict.get('direction').value if hasattr(trade_dict.get('direction'), 'value') else str(trade_dict.get('direction', '')),
            "entry_at": entry_at.isoformat() if isinstance(entry_at, datetime) else str(entry_at) if entry_at else None,
            "exit_at": exit_at.isoformat() if isinstance(exit_at, datetime) else str(exit_at) if exit_at else None,
            "entry_price": trade_dict.get('entry_price'),
            "exit_price": trade_dict.get('exit_price'),
            "quantity": trade_dict.get('quantity'),
            "pnl": trade_dict.get('pnl'),
            "net_pnl": trade_dict.get('net_pnl'),
            "is_duplicate": existing_id is not None,
            "existing_id": existing_id,
            "is_open": trade_dict.get('exit_at') is None,
        })
    
    # Статистика
    total = len(preview_items)
    duplicates = sum(1 for p in preview_items if p['is_duplicate'])
    new_trades = total - duplicates
    open_trades = sum(1 for p in preview_items if p['is_open'])
    
    return {
        "filename": file.filename,
        "total_trades": total,
        "new_trades": new_trades,
        "duplicates": duplicates,
        "open_trades": open_trades,
        "trades": preview_items,
        "date_range": {
            "first": preview_items[0]["entry_at"] if preview_items else None,
            "last": preview_items[-1]["entry_at"] if preview_items else None,
        },
        "balance_info": {
            "initial_balance": balance_info.get("initial_balance"),
            "final_balance": balance_info.get("final_balance"),
            "deposits": balance_info.get("deposits"),
            "withdrawals": balance_info.get("withdrawals"),
            "currency": balance_info.get("currency", "RUB"),
            "period_start": balance_info.get("period_start").isoformat() if balance_info.get("period_start") else None,
            "period_end": balance_info.get("period_end").isoformat() if balance_info.get("period_end") else None,
        }
    }


@router.post("/import", response_model=schemas.ImportResultResponse, status_code=200)
@limiter.limit(IMPORT_LIMIT)
async def import_trades(
    request: Request,
    file: UploadFile = File(...),
    start_index: Optional[int] = Form(None),
    end_index: Optional[int] = Form(None),
    skip_duplicates: bool = Form(True),
    initial_balance: Optional[float] = Form(None),
    final_balance: Optional[float] = Form(None),
    balance_date_start: Optional[str] = Form(None),
    balance_date_end: Optional[str] = Form(None),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """
    Импорт сделок из файла.
    
    - start_index: индекс первой сделки для импорта (0-based)
    - end_index: индекс последней сделки для импорта (inclusive)
    - skip_duplicates: пропускать дубликаты (default: True)
    - initial_balance: начальный баланс из отчёта (для снимка)
    - final_balance: конечный баланс из отчёта (для снимка)
    - balance_date_start: дата начала периода
    - balance_date_end: дата конца периода
    
    Дубликаты определяются по: symbol + direction + entry_at
    """
    account_id = auth_service.get_account_id(db, current_user)
    # FREE-tier gate. Проверяем ДО парсинга файла — если у юзера уже 50+
    # сделок, не тратим CPU на парсинг 5K-строчного отчёта.
    enforce_trade_limit(db, current_user)

    contents = await _read_upload_with_limit(file)
    try:
        trades_data = import_service.parse_trade_file(contents, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Применяем диапазон индексов если указан
    total_in_file = len(trades_data)
    actual_start = start_index if start_index is not None else 0
    actual_end = end_index if end_index is not None else total_in_file - 1

    # Валидация диапазона
    if actual_start < 0 or actual_start >= total_in_file:
        raise HTTPException(status_code=400, detail=f"start_index должен быть от 0 до {total_in_file - 1}")
    if actual_end < actual_start or actual_end >= total_in_file:
        raise HTTPException(status_code=400, detail=f"end_index должен быть от {actual_start} до {total_in_file - 1}")

    # Выбираем только нужный диапазон
    trades_to_import = trades_data[actual_start:actual_end + 1]

    imported_count = 0
    skipped_count = 0
    duplicate_count = 0
    balance_saved = False

    # Кеш колонок Trade — чтобы не пересчитывать на каждой итерации.
    valid_columns = {c.name for c in models.Trade.__table__.columns}

    # Bulk-загрузка существующих trade-ID одним SQL — устраняет N+1.
    # Возвращаем id, чтобы UPDATE-ветка могла достать ORM-объект lazy.
    existing_rows = db.query(
        models.Trade.id, models.Trade.symbol, models.Trade.direction, models.Trade.entry_at
    ).filter(models.Trade.account_id == account_id).all()
    existing_index = {
        (sym, _direction_value(direction), entry_at): _id
        for _id, sym, direction, entry_at in existing_rows
    }

    # Импорт в одной транзакции: при ЛЮБОЙ ошибке — полный откат батча.
    # Раньше частичная ошибка оставляла БД в несогласованном состоянии
    # (часть сделок уже вставлена, баланс пересчитан некорректно).
    try:
        for trade_dict in trades_to_import:
            dedup_key = (
                trade_dict.get('symbol'),
                _direction_value(trade_dict.get('direction')),
                trade_dict.get('entry_at'),
            )
            existing_id = existing_index.get(dedup_key)

            if existing_id is not None:
                duplicate_count += 1
                if skip_duplicates:
                    skipped_count += 1
                    continue
                # Не пропускаем — обновляем по ID. Один SELECT по PK — допустимо
                # (не N+1: UPDATE-ветка обычно редкая).
                existing = db.query(models.Trade).filter(models.Trade.id == existing_id).first()
                if existing is None:
                    continue
                for key, value in trade_dict.items():
                    if key in valid_columns and key not in ('id', 'created_at'):
                        setattr(existing, key, value)
                imported_count += 1
                continue

            trade_dict["account_id"] = account_id
            # Удаляем ключи, которых нет в модели Trade (import_service может вернуть лишние)
            clean_dict = {k: v for k, v in trade_dict.items() if k in valid_columns}
            db_trade = models.Trade(**clean_dict)
            db.add(db_trade)
            # Записываем в индекс, чтобы дубликаты в ОДНОМ батче ловились тоже.
            existing_index[dedup_key] = -1
            imported_count += 1
    except Exception as exc:
        db.rollback()
        log.error(f"Import batch failed, rolled back {imported_count} pending inserts: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Импорт прерван из-за ошибки: {exc}. Изменения откачены — повторите попытку.",
        )
    
    # Сохраняем снимки баланса если переданы
    if initial_balance is not None and balance_date_start:
        try:
            from datetime import datetime
            date_start = datetime.fromisoformat(balance_date_start.replace('Z', '+00:00'))
            
            # Проверяем нет ли уже снимка на эту дату
            existing_snapshot = db.query(models.BalanceSnapshot).filter(
                models.BalanceSnapshot.account_id == account_id,
                models.BalanceSnapshot.date == date_start
            ).first()
            
            if not existing_snapshot:
                snapshot = models.BalanceSnapshot(
                    account_id=account_id,
                    date=date_start,
                    balance=initial_balance,
                    source=file.filename
                )
                db.add(snapshot)
                balance_saved = True
                
            # Также обновляем initial_balance аккаунта если это первый снимок
            account = db.query(models.Account).filter(models.Account.id == account_id).first()
            if account and (account.initial_balance is None or account.initial_balance == 0):
                sync_initial_balance(
                    db,
                    account_id,
                    float(initial_balance),
                    date=date_start,
                    note=f"Initial balance imported from {file.filename}",
                    commit=False,
                )
        except Exception as e:
            log.warning(f"Could not save initial balance snapshot: {e}")
    
    if final_balance is not None and balance_date_end:
        try:
            from datetime import datetime
            date_end = datetime.fromisoformat(balance_date_end.replace('Z', '+00:00'))
            
            existing_snapshot = db.query(models.BalanceSnapshot).filter(
                models.BalanceSnapshot.account_id == account_id,
                models.BalanceSnapshot.date == date_end
            ).first()
            
            if not existing_snapshot:
                snapshot = models.BalanceSnapshot(
                    account_id=account_id,
                    date=date_end,
                    balance=final_balance,
                    source=file.filename
                )
                db.add(snapshot)
                balance_saved = True
        except Exception as e:
            log.warning(f"Could not save final balance snapshot: {e}")

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        log.error(f"Import commit failed, rolled back: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Не удалось сохранить импорт: {exc}. Изменения откачены — повторите попытку.",
        )
    return {
        "message": f"Импортировано: {imported_count}, пропущено дубликатов: {skipped_count}" + (", баланс сохранён" if balance_saved else ""),
        "imported": imported_count,
        "skipped": skipped_count,
        "duplicates_found": duplicate_count,
        "total_in_file": total_in_file,
        "balance_saved": balance_saved,
        "range_processed": {
            "start": actual_start,
            "end": actual_end,
            "count": len(trades_to_import)
        }
    }


@router.get("/", response_model=list[schemas.Trade])
async def read_trades(
    skip: int = 0,
    limit: int = 500,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    account_id = auth_service.get_account_id(db, current_user)
    trades = db.query(models.Trade).filter(
        models.Trade.account_id == account_id
    ).order_by(models.Trade.entry_at.desc()).offset(skip).limit(limit).all()
    return trades


# ─────────────── TR1: Trade Journal aggregation ───────────────


@router.get("/positions", response_model=list[schemas.PositionTrade])
async def read_position_trades(
    status: str = Query("all", pattern="^(all|open|closed)$"),
    skip: int = 0,
    limit: int = 500,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user),
):
    """TR1: Trade journal aggregated по `position_id` (round-trip lifecycle).

    Возвращает one-row-per-position view: scaled-in добавления и partial
    closes одного position lifecycle схлопываются в одну строку с
    weighted-average метриками и embedded list of executions.

    Filter `status`:
    - `all` — все позиции (default)
    - `open` — только активные (есть Trade с exit_at=None)
    - `closed` — только полностью закрытые (все Trade имеют exit_at)
    """
    account_id = auth_service.get_account_id(db, current_user)
    all_trades = (
        db.query(models.Trade)
        .filter(models.Trade.account_id == account_id)
        .order_by(models.Trade.entry_at.asc())
        .all()
    )

    # Группировка по position_id. Legacy/manual trades без position_id
    # получают synthetic key = ('legacy', id) — каждый сам себе позиция,
    # чтобы UI не схлопывал их некорректно.
    from collections import defaultdict
    groups: dict[tuple, list[models.Trade]] = defaultdict(list)
    for t in all_trades:
        if t.position_id is not None and t.instrument_uid:
            key = (t.instrument_uid, t.position_id)
        else:
            key = ("legacy", t.id)
        groups[key].append(t)

    positions: list[schemas.PositionTrade] = []
    for key, group in groups.items():
        first = group[0]  # earliest entry (sorted asc)
        # Detect status: any row with exit_at=None → position still open
        any_open = any(t.exit_at is None for t in group)
        position_status = "open" if any_open else "closed"

        if status != "all" and status != position_status:
            continue

        # Aggregations
        total_qty = sum(float(t.quantity or 0) for t in group)

        # Weighted entry price: Σ(price × qty) / Σ qty
        sum_qty = sum(float(t.quantity or 0) for t in group)
        sum_entry_value = sum(
            float(t.entry_price or 0) * float(t.quantity or 0) for t in group
        )
        weighted_entry = sum_entry_value / sum_qty if sum_qty > 0 else 0.0

        # Weighted exit price (только closed rows)
        closed_rows = [t for t in group if t.exit_at is not None and t.exit_price is not None]
        weighted_exit: Optional[float] = None
        if closed_rows:
            sum_exit_qty = sum(float(t.quantity or 0) for t in closed_rows)
            sum_exit_value = sum(
                float(t.exit_price or 0) * float(t.quantity or 0) for t in closed_rows
            )
            if sum_exit_qty > 0:
                weighted_exit = sum_exit_value / sum_exit_qty

        # Realized P&L = Σ net_pnl закрытых rows
        realized_pnl: Optional[float] = None
        closed_with_pnl = [t for t in closed_rows if t.net_pnl is not None]
        if closed_with_pnl:
            realized_pnl = sum(float(t.net_pnl) for t in closed_with_pnl)

        # Unrealized P&L: для open позиций берём из PositionORM (live mark-to-market).
        # Один PositionORM на (account, instrument_uid), не на (account, position_id) —
        # MTM считается на текущей живой позиции независимо от round-trip group.
        unrealized_pnl: Optional[float] = None
        if any_open and first.instrument_uid:
            pos_row = (
                db.query(models.PositionORM)
                .filter(
                    models.PositionORM.account_id == account_id,
                    models.PositionORM.instrument_uid == first.instrument_uid,
                )
                .first()
            )
            if pos_row and pos_row.unrealized_pnl is not None:
                unrealized_pnl = float(pos_row.unrealized_pnl)

        # Lifecycle timing
        first_entry_at = min(t.entry_at for t in group)
        last_exit_at: Optional[datetime] = None
        if not any_open:
            last_exit_at = max(t.exit_at for t in group if t.exit_at)

        holding_minutes: Optional[int] = None
        if last_exit_at is not None:
            delta_sec = (last_exit_at - first_entry_at).total_seconds()
            holding_minutes = int(delta_sec / 60) if delta_sec >= 0 else None

        # Executions list (sorted chronologically) — TR1.1: с MAE/MFE/screenshot,
        # TR1.3: + per-execution attributed fees
        executions = [
            schemas.TradeExecution(
                id=t.id,
                entry_at=t.entry_at,
                exit_at=t.exit_at,
                entry_price=float(t.entry_price or 0),
                exit_price=float(t.exit_price) if t.exit_price is not None else None,
                quantity=float(t.quantity or 0),
                direction=t.direction.value if hasattr(t.direction, "value") else str(t.direction),
                pnl=float(t.pnl) if t.pnl is not None else None,
                net_pnl=float(t.net_pnl) if t.net_pnl is not None else None,
                commission=float(t.commission) if t.commission is not None else None,
                entry_value=float(t.entry_value) if t.entry_value is not None else None,
                exit_value=float(t.exit_value) if t.exit_value is not None else None,
                mae_price=float(t.mae_price) if t.mae_price is not None else None,
                mfe_price=float(t.mfe_price) if t.mfe_price is not None else None,
                screenshot_url=t.screenshot_url,
                setup_name=t.setup_name,
                risk_amount=float(t.risk_amount) if t.risk_amount is not None else None,
                varmargin_attributed=float(t.varmargin_attributed) if t.varmargin_attributed is not None else None,
                margin_fee_attributed=float(t.margin_fee_attributed) if t.margin_fee_attributed is not None else None,
                service_fee_attributed=float(t.service_fee_attributed) if t.service_fee_attributed is not None else None,
                other_fees_attributed=float(t.other_fees_attributed) if t.other_fees_attributed is not None else None,
                # Phase 9: point_value snapshot для futures (computed body_from_prices)
                point_value=float(t.point_value) if t.point_value is not None else None,
                point_value_source=t.point_value_source,
                instrument_type_v2=t.instrument_type_v2,
            )
            for t in sorted(group, key=lambda x: x.entry_at)
        ]

        # Setup / tags / notes — от первого execution (per AskUserQuestion 2026-05-16:
        # один setup на всю сделку, наследуется от entry).
        setup_id = first.setup_id
        setup_name = first.setup_name
        tags = list(first.tags or []) if first.tags else []
        notes = first.notes

        position_id_val = first.position_id if first.position_id is not None else first.id

        # TR1.1 aggregations.

        total_entry_value = sum(float(t.entry_value or 0) for t in group) or None
        total_exit_value = sum(float(t.exit_value or 0) for t in group) or None

        # % result. Используем ту же логику что Trade.pnl_pct (schemas.py:400-430):
        # primary — entry_value, fallback — weighted_entry_price × |total_qty|.
        # Для open берём unrealized_pnl, для closed — realized_pnl.
        pnl_for_pct = realized_pnl if not any_open else unrealized_pnl
        pnl_pct: Optional[float] = None
        if pnl_for_pct is not None:
            if total_entry_value and total_entry_value > 0:
                pnl_pct = round((pnl_for_pct / total_entry_value) * 100, 4)
            elif weighted_entry and total_qty > 0:
                # Fallback: для legacy/manual trades без entry_value
                fallback_base = weighted_entry * abs(total_qty)
                if fallback_base > 0:
                    pnl_pct = round((pnl_for_pct / fallback_base) * 100, 4)

        # R-multiple = realized_pnl / Σ risk_amount (только closed rows
        # с явно заданным risk_amount). Dash в UI если нет.
        closed_with_risk = [
            t for t in group
            if t.exit_at is not None and t.risk_amount and float(t.risk_amount) > 0
        ]
        r_multiple: Optional[float] = None
        total_risk_amount: Optional[float] = None
        if closed_with_risk and realized_pnl is not None:
            total_risk_amount = sum(float(t.risk_amount) for t in closed_with_risk)
            if total_risk_amount > 0:
                r_multiple = round(realized_pnl / total_risk_amount, 2)

        # MAE/MFE: MIN/MAX across executions (worst adverse / best favorable).
        # MAE — наименее благоприятная цена; MFE — наиболее благоприятная.
        # Для LONG: MAE=min, MFE=max; для SHORT: MAE=max, MFE=min.
        # Trade ORM хранит уже-направленные значения, поэтому min/max по полю
        # верны независимо от direction.
        mae_vals = [float(t.mae_price) for t in group if t.mae_price is not None]
        mfe_vals = [float(t.mfe_price) for t in group if t.mfe_price is not None]
        mae_price = min(mae_vals) if mae_vals else None
        mfe_price = max(mfe_vals) if mfe_vals else None

        # Indicators.
        has_screenshot = any(t.screenshot_url for t in group)
        has_notes = bool(notes and str(notes).strip())

        # TR1.3: aggregated attributed fees + body P&L breakdown.
        total_varmargin = sum(float(t.varmargin_attributed or 0) for t in group) or None
        total_margin_fee = sum(float(t.margin_fee_attributed or 0) for t in group) or None
        total_service_fee = sum(float(t.service_fee_attributed or 0) for t in group) or None
        total_other_fees = sum(float(t.other_fees_attributed or 0) for t in group) or None
        # Body P&L = Σ trade.pnl (gross body — без commissions/fees). Используется
        # в UI breakdown card «Из чего сложился P&L».
        body_pnl_sum = sum(float(t.pnl or 0) for t in group if t.exit_at is not None) or None

        # Journaling fields — от первого execution (inheritance pattern).
        confidence = first.confidence
        mood = first.mood
        discipline = first.discipline
        timeframe = first.timeframe
        news_event = first.news_event
        stop_loss = float(first.stop_loss) if first.stop_loss is not None else None
        take_profit = float(first.take_profit) if first.take_profit is not None else None
        entry_reason = first.entry_reason
        exit_reason = first.exit_reason
        screenshot_url = first.screenshot_url

        positions.append(
            schemas.PositionTrade(
                position_id=position_id_val,
                account_id=account_id,
                instrument_uid=first.instrument_uid,
                symbol=first.symbol,
                asset_name=first.asset_name,
                asset_type=first.asset_type,
                direction=first.direction.value if hasattr(first.direction, "value") else str(first.direction),
                total_quantity=total_qty,
                weighted_entry_price=weighted_entry,
                weighted_exit_price=weighted_exit,
                realized_pnl=realized_pnl,
                unrealized_pnl=unrealized_pnl,
                total_commission=sum(float(t.commission or 0) for t in group),
                total_entry_value=total_entry_value,
                total_exit_value=total_exit_value,
                first_entry_at=first_entry_at,
                last_exit_at=last_exit_at,
                holding_time_minutes=holding_minutes,
                status=position_status,
                execution_count=len(group),
                is_scale_in=len(group) >= 2,
                setup_id=setup_id,
                setup_name=setup_name,
                tags=tags,
                notes=notes,
                # TR1.1 power-user metrics
                pnl_pct=pnl_pct,
                r_multiple=r_multiple,
                total_risk_amount=total_risk_amount,
                mae_price=mae_price,
                mfe_price=mfe_price,
                # TR1.1 indicators
                has_screenshot=has_screenshot,
                has_notes=has_notes,
                # TR1.1 journaling fields
                confidence=confidence,
                mood=mood,
                discipline=discipline,
                timeframe=timeframe,
                news_event=news_event,
                stop_loss=stop_loss,
                take_profit=take_profit,
                entry_reason=entry_reason,
                exit_reason=exit_reason,
                screenshot_url=screenshot_url,
                # TR1.3: aggregated attributed fees + body breakdown
                total_varmargin=total_varmargin,
                total_margin_fee=total_margin_fee,
                total_service_fee=total_service_fee,
                total_other_fees=total_other_fees,
                body_pnl=body_pnl_sum,
                executions=executions,
            )
        )

    # Sort: newest first by first_entry_at
    positions.sort(key=lambda p: p.first_entry_at, reverse=True)
    return positions[skip : skip + limit]


import os
import uuid
from pathlib import Path

UPLOAD_DIR = Path("uploads/screenshots")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.get("/{trade_id}/screenshot")
async def get_screenshot(
    trade_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user),
):
    """PR 26: authenticated endpoint для отдачи скриншота сделки.

    Раньше скриншоты были доступны через static `/uploads/screenshots/...`
    с UUID-именами — security through obscurity. Любой, кто угадал URL,
    мог посмотреть скриншот другого юзера. Теперь проверяем ownership.

    Возвращаем файл как `Content-Disposition: inline` (image preview в
    браузере) + строгий Content-Type из magic bytes (не from filename).
    """
    from fastapi.responses import FileResponse

    account_id = auth_service.get_account_id(db, current_user)
    trade = db.query(models.Trade).filter(
        models.Trade.id == trade_id,
        models.Trade.account_id == account_id,
    ).first()
    if not trade or not trade.screenshot_url:
        raise HTTPException(status_code=404, detail="Скриншот не найден")

    # screenshot_url хранится как `/uploads/screenshots/<filename>` — выдёргиваем
    # filename, чтобы не разрешить path traversal через user-controlled значение.
    import os as _os
    filename = _os.path.basename(trade.screenshot_url)
    filepath = UPLOAD_DIR / filename
    # Дополнительная защита: проверяем что resolved path действительно внутри
    # UPLOAD_DIR (защита от relative path tricks даже если basename странный).
    if not filepath.resolve().is_relative_to(UPLOAD_DIR.resolve()):
        raise HTTPException(status_code=404, detail="Скриншот не найден")
    if not filepath.is_file():
        raise HTTPException(status_code=404, detail="Скриншот не найден")

    ext = filepath.suffix.lstrip(".").lower()
    media_type = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "webp": "image/webp",
    }.get(ext, "application/octet-stream")
    return FileResponse(
        path=str(filepath),
        media_type=media_type,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.post("/{trade_id}/screenshot")
async def upload_screenshot(
    trade_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """Загрузить скриншот для сделки"""
    account_id = auth_service.get_account_id(db, current_user)
    
    trade = db.query(models.Trade).filter(
        models.Trade.id == trade_id,
        models.Trade.account_id == account_id
    ).first()
    
    if not trade:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    
    # Проверяем тип файла по Content-Type
    allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Разрешены только изображения (JPEG, PNG, GIF, WEBP)")
    
    # Читаем файл и проверяем размер (макс 10 МБ)
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
    content = await file.read()
    
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Файл слишком большой. Максимум 10 МБ")
    
    if len(content) < 8:
        raise HTTPException(status_code=400, detail="Файл повреждён или пуст")
    
    # Валидация magic bytes (реальный тип файла)
    MAGIC_BYTES = {
        b"\xff\xd8\xff": "jpg",       # JPEG
        b"\x89PNG": "png",             # PNG
        b"GIF87a": "gif",              # GIF87
        b"GIF89a": "gif",              # GIF89
        b"RIFF": "webp",              # WebP (starts with RIFF)
    }
    
    detected_ext = None
    for magic, ext in MAGIC_BYTES.items():
        if content[:len(magic)] == magic:
            detected_ext = ext
            break
    
    if not detected_ext:
        raise HTTPException(status_code=400, detail="Файл не является изображением (проверка magic bytes)")
    
    # Генерируем уникальное имя файла
    filename = f"{trade_id}_{uuid.uuid4().hex[:8]}.{detected_ext}"
    filepath = UPLOAD_DIR / filename
    
    # Сохраняем файл
    with open(filepath, "wb") as f:
        f.write(content)
    
    # Обновляем URL в сделке
    screenshot_url = f"/uploads/screenshots/{filename}"
    trade.screenshot_url = screenshot_url
    db.commit()
    
    return {"url": screenshot_url, "filename": filename}


@router.delete("/{trade_id}/screenshot", response_model=schemas.MessageResponse)
async def delete_screenshot(
    trade_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """Удалить скриншот сделки"""
    account_id = auth_service.get_account_id(db, current_user)

    trade = db.query(models.Trade).filter(
        models.Trade.id == trade_id,
        models.Trade.account_id == account_id
    ).first()

    if not trade:
        raise HTTPException(status_code=404, detail="Сделка не найдена")

    if trade.screenshot_url:
        # Удаляем файл
        filepath = Path(trade.screenshot_url.lstrip("/"))
        if filepath.exists():
            filepath.unlink()
        trade.screenshot_url = None
        db.commit()

    return {"message": "Скриншот удалён"}


@router.get("/{trade_id}", response_model=schemas.Trade)
async def read_trade(
    trade_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user),
):
    """Возвращает полный Trade row для editing surface (/positions → modal).

    /trades/positions executions содержат только subset полей (per-execution
    metrics), а для редактирования manual fields (notes, tags, confidence,
    mood, discipline, timeframe, stop_loss/take_profit, risk_amount, etc.)
    нужна полная Trade-запись. Иначе EditTradeModal заполнит form defaults
    и стерёт legitimate metadata при PATCH.
    """
    account_id = auth_service.get_account_id(db, current_user)
    db_trade = db.query(models.Trade).filter(
        models.Trade.id == trade_id,
        models.Trade.account_id == account_id,
    ).first()
    if not db_trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    return db_trade


@router.patch("/{trade_id}", response_model=schemas.Trade)
async def update_trade(
    trade_id: int,
    trade_update: schemas.TradeUpdate,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    account_id = auth_service.get_account_id(db, current_user)
    db_trade = db.query(models.Trade).filter(
        models.Trade.id == trade_id,
        models.Trade.account_id == account_id
    ).first()
    if not db_trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    update_data = trade_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_trade, key, value)

    db.commit()
    db.refresh(db_trade)
    return db_trade


@router.delete("/{trade_id}", response_model=schemas.MessageResponse)
async def delete_trade(
    trade_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    account_id = auth_service.get_account_id(db, current_user)
    trade = db.query(models.Trade).filter(
        models.Trade.id == trade_id,
        models.Trade.account_id == account_id
    ).first()
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    db.delete(trade)
    db.commit()
    return {"message": "Trade deleted"}


@router.patch("/{trade_id}/close", response_model=schemas.Trade)
async def close_trade(
    trade_id: int, 
    trade_close: schemas.TradeClose, 
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    account_id = auth_service.get_account_id(db, current_user)
    db_trade = db.query(models.Trade).filter(
        models.Trade.id == trade_id,
        models.Trade.account_id == account_id
    ).first()
    if not db_trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    
    db_trade.exit_price = trade_close.exit_price
    db_trade.exit_at = trade_close.exit_at
    db_trade.exit_reason = trade_close.exit_reason
    
    # Update swap if provided by client
    if trade_close.swap is not None:
        db_trade.swap = trade_close.swap
    
    # Auto-calculate MAE/MFE (only if not provided by client)
    # NOTE: mae_price/mfe_price are NOT sent from frontend anymore;
    # the backend always auto-calculates from market data.
    if trade_close.mae_price is not None:
        db_trade.mae_price = trade_close.mae_price
    if trade_close.mfe_price is not None:
        db_trade.mfe_price = trade_close.mfe_price
    
    if db_trade.mae_price is None or db_trade.mfe_price is None:
        try:
            mae, mfe = market_data_service.calculate_mae_mfe(
                ticker=db_trade.symbol,
                direction=db_trade.direction.value,
                entry_price=float(db_trade.entry_price),
                entry_time=db_trade.entry_at,
                exit_time=trade_close.exit_at
            )
            if mae is not None and db_trade.mae_price is None:
                db_trade.mae_price = mae
            if mfe is not None and db_trade.mfe_price is None:
                db_trade.mfe_price = mfe
        except Exception as e:
            log.warning(f"Failed to calculate MAE/MFE for trade {trade_id}: {e}")
    
    # Calculate PnL + net_pnl via unified service
    pnl_service.apply_close_pnl(
        trade=db_trade,
        exit_commission=float(trade_close.exit_commission or 0),
    )
    
    # AI Analysis (полный pack — psycho-метрики, последние PnL, account context)
    account = db.query(models.Account).filter(models.Account.id == db_trade.account_id).first()
    initial_balance = float(account.initial_balance or 0) if account else 0
    recent_trades = db.query(models.Trade).filter(
        models.Trade.account_id == db_trade.account_id,
        models.Trade.id != db_trade.id,
        models.Trade.pnl != None,
    ).order_by(models.Trade.exit_at.desc()).limit(5).all()
    recent_pnls = [float(t.pnl) for t in recent_trades]

    trade_data = {
        "symbol": db_trade.symbol,
        "direction": db_trade.direction.value,
        "pnl": float(db_trade.pnl),
        "entry_price": float(db_trade.entry_price) if db_trade.entry_price else None,
        "exit_price": float(db_trade.exit_price) if db_trade.exit_price else None,
        "stop_loss": float(db_trade.stop_loss) if db_trade.stop_loss else None,
        "take_profit": float(db_trade.take_profit) if db_trade.take_profit else None,
        "mae_price": float(db_trade.mae_price) if db_trade.mae_price else None,
        "mfe_price": float(db_trade.mfe_price) if db_trade.mfe_price else None,
        "holding_time_minutes": db_trade.holding_time_minutes,
        "setup_name": db_trade.setup_name,
        "tags": db_trade.tags,
        "notes": db_trade.notes,
        "mood": db_trade.mood,
        "confidence": db_trade.confidence,
        "discipline": db_trade.discipline,
    }
    db_trade.ai_analysis = await ai_service.analyze_trade_with_ai(
        trade_data,
        account_initial_balance=initial_balance,
        recent_pnls=recent_pnls,
    )

    db.commit()
    db.refresh(db_trade)
    return db_trade


@router.post("/{trade_id}/reanalyze")
@limiter.limit(AI_LIMIT)
async def reanalyze_trade(
    request: Request,
    trade_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(require_pro),  # AI-фича — только PRO
):
    """Перезапуск AI-анализа для существующей сделки (после правок)."""
    account_id = auth_service.get_account_id(db, current_user)
    db_trade = db.query(models.Trade).filter(
        models.Trade.id == trade_id,
        models.Trade.account_id == account_id,
    ).first()
    if not db_trade or db_trade.pnl is None:
        from fastapi import HTTPException
        raise HTTPException(404, "Сделка не найдена или ещё открыта")

    account = db.query(models.Account).filter(models.Account.id == account_id).first()
    initial_balance = float(account.initial_balance or 0) if account else 0
    recent_trades = db.query(models.Trade).filter(
        models.Trade.account_id == account_id,
        models.Trade.id != trade_id,
        models.Trade.pnl != None,
    ).order_by(models.Trade.exit_at.desc()).limit(5).all()
    recent_pnls = [float(t.pnl) for t in recent_trades]

    db_trade.ai_analysis = await ai_service.analyze_trade_with_ai(
        {
            "symbol": db_trade.symbol,
            "direction": db_trade.direction.value,
            "pnl": float(db_trade.pnl),
            "entry_price": float(db_trade.entry_price) if db_trade.entry_price else None,
            "exit_price": float(db_trade.exit_price) if db_trade.exit_price else None,
            "stop_loss": float(db_trade.stop_loss) if db_trade.stop_loss else None,
            "take_profit": float(db_trade.take_profit) if db_trade.take_profit else None,
            "mae_price": float(db_trade.mae_price) if db_trade.mae_price else None,
            "mfe_price": float(db_trade.mfe_price) if db_trade.mfe_price else None,
            "holding_time_minutes": db_trade.holding_time_minutes,
            "setup_name": db_trade.setup_name,
            "tags": db_trade.tags,
            "notes": db_trade.notes,
            "mood": db_trade.mood,
            "confidence": db_trade.confidence,
            "discipline": db_trade.discipline,
        },
        account_initial_balance=initial_balance,
        recent_pnls=recent_pnls,
    )
    db.commit()
    db.refresh(db_trade)
    return db_trade.ai_analysis


@router.get("/mae-mfe-stats")
async def get_mae_mfe_stats(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """
    Получить статистику по MAE/MFE: сколько сделок с метриками, сколько без.
    """
    account_id = auth_service.get_account_id(db, current_user)
    
    # Общее количество закрытых сделок
    total_closed = db.query(models.Trade).filter(
        models.Trade.account_id == account_id,
        models.Trade.exit_at != None
    ).count()
    
    # Сделки с MAE/MFE
    with_mae_mfe = db.query(models.Trade).filter(
        models.Trade.account_id == account_id,
        models.Trade.exit_at != None,
        models.Trade.mae_price != None,
        models.Trade.mfe_price != None
    ).count()
    
    # Сделки без MAE/MFE
    without_mae_mfe = total_closed - with_mae_mfe
    
    return {
        "total_closed": total_closed,
        "with_mae_mfe": with_mae_mfe,
        "without_mae_mfe": without_mae_mfe,
        "coverage_pct": round(with_mae_mfe / total_closed * 100, 1) if total_closed > 0 else 0
    }


@router.post("/calculate-mae-mfe")
async def calculate_mae_mfe_bulk(
    trade_ids: Optional[List[int]] = None,
    force_all: bool = False,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """
    Массовый расчёт MAE/MFE для закрытых сделок.
    - trade_ids: конкретные ID сделок для расчёта
    - force_all: если True, пересчитывает ВСЕ сделки (даже с уже существующими MAE/MFE)
    - Если ничего не указано, рассчитывает только для сделок без MAE/MFE.
    """
    account_id = auth_service.get_account_id(db, current_user)
    
    # Получаем закрытые сделки
    query = db.query(models.Trade).filter(
        models.Trade.account_id == account_id,
        models.Trade.exit_at != None,  # Только закрытые
    )
    
    if trade_ids:
        query = query.filter(models.Trade.id.in_(trade_ids))
    elif not force_all:
        # Только сделки без MAE или MFE (если не force_all)
        query = query.filter(
            (models.Trade.mae_price == None) | (models.Trade.mfe_price == None)
        )
    
    trades = query.all()
    
    if not trades:
        return {
            "message": "Нет сделок для расчёта MAE/MFE",
            "processed": 0,
            "updated": 0,
            "failed": 0
        }
    
    updated = 0
    failed = 0
    errors = []
    
    for trade in trades:
        try:
            if not trade.entry_at or not trade.exit_at:
                continue
            
            # Получаем операции для учёта усреднения
            operations = trade.operations if trade.operations else None
            
            # Проверяем есть ли усреднение (больше 1 входа)
            entry_count = 0
            if operations:
                entry_count = len([op for op in operations if op.get('type') == 'entry'])
            
            mae, mfe = market_data_service.calculate_mae_mfe(
                ticker=trade.symbol,
                direction=trade.direction.value if hasattr(trade.direction, 'value') else trade.direction,
                entry_price=float(trade.entry_price),  # Уже средневзвешенная при усреднении
                entry_time=trade.entry_at,
                exit_time=trade.exit_at,
                operations=operations,  # Передаём операции для точного определения периода
                exit_price=float(trade.exit_price) if trade.exit_price else None  # Для корректности MAE
            )
            
            if mae is not None and mfe is not None:
                trade.mae_price = mae
                trade.mfe_price = mfe
                updated += 1
                if entry_count > 1:
                    log.info(f"Trade {trade.id} ({trade.symbol}): averaged position with {entry_count} entries")
            else:
                failed += 1
                errors.append(f"{trade.symbol}: нет данных")
                
        except Exception as e:
            failed += 1
            errors.append(f"{trade.symbol}: {str(e)}")
            log.error(f"Error calculating MAE/MFE for trade {trade.id}: {e}")
    
    db.commit()
    
    return {
        "message": f"MAE/MFE рассчитан для {updated} сделок",
        "processed": len(trades),
        "updated": updated,
        "failed": failed,
        "errors": errors[:10] if errors else []  # Первые 10 ошибок
    }


@router.post("/calculate-post-exit")
async def calculate_post_exit_bulk(
    trade_ids: Optional[List[int]] = None,
    recalculate: bool = False,
    timeframe: Optional[str] = None,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """
    Анализ движения цены ПОСЛЕ закрытия сделок.
    
    Показывает:
    - Закрылись ли вы рано (цена продолжила движение в вашу сторону)
    - Было ли закрытие правильным (цена развернулась)
    
    Параметры:
    - trade_ids: список ID сделок для анализа
    - recalculate: если True, пересчитывает все; если False, только без анализа
    - timeframe: таймфрейм для анализа (1m, 5m, 15m, 30m, 1H, 4H, 1D, 1W)
    """
    account_id = auth_service.get_account_id(db, current_user)
    
    # Получаем закрытые сделки
    query = db.query(models.Trade).filter(
        models.Trade.account_id == account_id,
        models.Trade.exit_at != None,
    )
    
    if trade_ids:
        query = query.filter(models.Trade.id.in_(trade_ids))
    elif not recalculate:
        # Только сделки без post-exit анализа
        query = query.filter(models.Trade.post_exit_analysis == None)
    
    trades = query.order_by(models.Trade.exit_at.desc()).limit(50).all()  # Лимит 50 для скорости
    
    # Если нет сделок для расчёта, но есть уже проанализированные - возвращаем статистику
    if not trades:
        existing_trades = db.query(models.Trade).filter(
            models.Trade.account_id == account_id,
            models.Trade.post_exit_analysis != None
        ).all()
        
        if existing_trades:
            detailed_stats = _calculate_post_exit_detailed_stats(existing_trades)
            return {
                "message": "Статистика по ранее проанализированным сделкам",
                "processed": len(existing_trades),
                "updated": 0,
                "failed": 0,
                "summary": detailed_stats["summary"],
                "period_stats": detailed_stats["period_stats"],
                "top_early_exits": detailed_stats["top_early_exits"],
                "errors": []
            }
        
        return {
            "message": "Нет сделок для анализа",
            "processed": 0,
            "updated": 0,
            "summary": None
        }
    
    updated = 0
    failed = 0
    early_exits = 0
    good_exits = 0
    errors = []
    
    for trade in trades:
        try:
            if not trade.exit_at or not trade.exit_price:
                continue
            
            analysis = market_data_service.calculate_post_exit_analysis(
                ticker=trade.symbol,
                direction=trade.direction.value if hasattr(trade.direction, 'value') else trade.direction,
                exit_price=float(trade.exit_price),
                exit_time=trade.exit_at,
                timeframe=timeframe  # Используем выбранный пользователем таймфрейм
            )
            
            if analysis and analysis.get("periods"):
                trade.post_exit_analysis = analysis
                updated += 1
                
                # Подсчёт статистики
                if analysis.get("summary"):
                    early_exits += analysis["summary"].get("early_exits_count", 0)
                    if analysis["summary"].get("avg_quality_score", 0) >= 70:
                        good_exits += 1
            else:
                failed += 1
                errors.append(f"{trade.symbol}: нет данных")
                
        except Exception as e:
            failed += 1
            errors.append(f"{trade.symbol}: {str(e)}")
            log.error(f"Error calculating post-exit for trade {trade.id}: {e}")
    
    db.commit()
    
    # Собираем детальную статистику по всем обработанным сделкам
    detailed_stats = _calculate_post_exit_detailed_stats(trades)
    
    return {
        "message": f"Post-exit анализ выполнен для {updated} сделок",
        "processed": len(trades),
        "updated": updated,
        "failed": failed,
        "summary": detailed_stats["summary"],
        "period_stats": detailed_stats["period_stats"],
        "top_early_exits": detailed_stats["top_early_exits"],
        "errors": errors[:10] if errors else []
    }


def _calculate_post_exit_detailed_stats(trades: list) -> dict:
    """Рассчитывает детальную статистику по post-exit анализу"""
    period_stats = {}  # Статистика по каждому периоду
    all_continuation_moves = []  # Все % упущенной прибыли
    early_exits_list = []
    good_exits_count = 0
    neutral_count = 0
    
    for trade in trades:
        if not trade.post_exit_analysis:
            continue
            
        periods = trade.post_exit_analysis.get("periods", {})
        for period_key, period_data in periods.items():
            if not period_data.get("available"):
                continue
            
            # Инициализируем статистику для периода
            if period_key not in period_stats:
                period_stats[period_key] = {
                    "label": period_data.get("label", period_key),
                    "early_count": 0,
                    "good_count": 0,
                    "neutral_count": 0,
                    "total": 0,
                    "avg_continuation_pct": 0,
                    "max_continuation_pct": 0,
                    "continuation_moves": [],
                    "total_missed_pct": 0,
                }
            
            stats = period_stats[period_key]
            stats["total"] += 1
            
            quality = period_data.get("exit_quality")
            continuation_pct = period_data.get("continuation_move_pct", 0)
            
            if quality == "early":
                stats["early_count"] += 1
                stats["continuation_moves"].append(continuation_pct)
                stats["total_missed_pct"] += continuation_pct
                
                # Добавляем в список ранних выходов
                early_exits_list.append({
                    "trade_id": trade.id,
                    "symbol": trade.symbol,
                    "direction": trade.direction.value if hasattr(trade.direction, 'value') else trade.direction,
                    "exit_date": trade.exit_at.strftime("%d.%m.%Y") if trade.exit_at else None,
                    "pnl": float(trade.pnl) if trade.pnl else 0,
                    "period": period_data.get("label", period_key),
                    "missed_pct": continuation_pct,
                    "exit_price": float(trade.exit_price) if trade.exit_price else 0,
                    "max_price_after": period_data.get("max_price"),
                    "min_price_after": period_data.get("min_price"),
                    "final_price": period_data.get("final_price"),
                })
            elif quality == "good":
                stats["good_count"] += 1
                good_exits_count += 1
            else:
                stats["neutral_count"] += 1
                neutral_count += 1
            
            all_continuation_moves.append(continuation_pct)
    
    # Вычисляем средние значения
    for period_key, stats in period_stats.items():
        if stats["continuation_moves"]:
            stats["avg_continuation_pct"] = round(sum(stats["continuation_moves"]) / len(stats["continuation_moves"]), 2)
            stats["max_continuation_pct"] = round(max(stats["continuation_moves"]), 2)
        stats["avg_missed_pct"] = round(stats["total_missed_pct"] / stats["total"], 2) if stats["total"] > 0 else 0
        # Убираем временные данные
        del stats["continuation_moves"]
        del stats["total_missed_pct"]
    
    # Сортируем ранние выходы по упущенному %
    early_exits_list.sort(key=lambda x: x["missed_pct"], reverse=True)
    total_early = sum(s["early_count"] for s in period_stats.values()) // max(1, len(period_stats))  # Средний по периодам
    
    return {
        "summary": {
            "early_exits": len(set(e["trade_id"] for e in early_exits_list)),  # Уникальные сделки
            "good_exits": good_exits_count // max(1, len(period_stats)),
            "total_analyzed": len([t for t in trades if t.post_exit_analysis]),
            "avg_missed_profit_pct": round(sum(all_continuation_moves) / len(all_continuation_moves), 2) if all_continuation_moves else 0,
            "early_exit_tendency": total_early > good_exits_count // max(1, len(period_stats)) * 2
        },
        "period_stats": period_stats,
        "top_early_exits": early_exits_list[:10]  # Топ-10 худших ранних выходов
    }


@router.get("/post-exit/list")
async def get_trades_with_post_exit(
    limit: int = 50,
    early_only: bool = False,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """Получить список сделок с post-exit анализом"""
    account_id = auth_service.get_account_id(db, current_user)
    
    query = db.query(models.Trade).filter(
        models.Trade.account_id == account_id,
        models.Trade.post_exit_analysis != None
    ).order_by(models.Trade.exit_at.desc())
    
    trades = query.limit(limit).all()
    
    result = []
    for trade in trades:
        analysis = trade.post_exit_analysis or {}
        periods = analysis.get("periods", {})
        
        # Определяем худший период (максимальный missed %)
        worst_period = None
        max_missed = 0
        has_early = False
        
        for period_key, period_data in periods.items():
            if period_data.get("available") and period_data.get("exit_quality") == "early":
                has_early = True
                missed = period_data.get("continuation_move_pct", 0)
                if missed > max_missed:
                    max_missed = missed
                    worst_period = period_data
        
        if early_only and not has_early:
            continue
        
        result.append({
            "id": trade.id,
            "symbol": trade.symbol,
            "direction": trade.direction.value if hasattr(trade.direction, 'value') else trade.direction,
            "entry_at": trade.entry_at.isoformat() if trade.entry_at else None,
            "exit_at": trade.exit_at.isoformat() if trade.exit_at else None,
            "entry_price": float(trade.entry_price) if trade.entry_price else None,
            "exit_price": float(trade.exit_price) if trade.exit_price else None,
            "pnl": float(trade.pnl) if trade.pnl else None,
            "net_pnl": float(trade.net_pnl) if trade.net_pnl else None,
            "has_early_exit": has_early,
            "max_missed_pct": round(max_missed, 2),
            "worst_period": worst_period.get("label") if worst_period else None,
            "analysis": analysis
        })
    
    return {
        "trades": result,
        "total": len(result)
    }


@router.get("/{trade_id}/post-exit")
async def get_trade_post_exit(
    trade_id: int,
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """Получить post-exit анализ для конкретной сделки"""
    account_id = auth_service.get_account_id(db, current_user)
    
    trade = db.query(models.Trade).filter(
        models.Trade.id == trade_id,
        models.Trade.account_id == account_id
    ).first()
    
    if not trade:
        raise HTTPException(status_code=404, detail="Сделка не найдена")
    
    if not trade.exit_at:
        raise HTTPException(status_code=400, detail="Сделка ещё не закрыта")
    
    # Если анализ уже есть — возвращаем
    if trade.post_exit_analysis:
        return trade.post_exit_analysis
    
    # Иначе рассчитываем
    analysis = market_data_service.calculate_post_exit_analysis(
        ticker=trade.symbol,
        direction=trade.direction.value if hasattr(trade.direction, 'value') else trade.direction,
        exit_price=float(trade.exit_price),
        exit_time=trade.exit_at,
        timeframe=trade.timeframe  # Используем таймфрейм сделки
    )
    
    if analysis:
        trade.post_exit_analysis = analysis
        db.commit()
    
    return analysis