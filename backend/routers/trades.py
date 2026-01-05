"""
Trades Router — CRUD для сделок, импорт, unrealized PnL
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Form
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime

import database
import models
import schemas
import auth_service
import import_service
import market_service
import ai_service
from logger import get_logger

log = get_logger("trades")

router = APIRouter(prefix="/trades", tags=["trades"])

# Инициализируем сервис рыночных данных
market_data_service = market_service.MarketService()


def get_account_id(db: Session, user: Optional[models.User] = None) -> int:
    """Получить account_id для текущего пользователя или вернуть 1 для анонима"""
    if user:
        account = auth_service.get_user_account(db, user)
        return account.id
    return 1  # Fallback для обратной совместимости


@router.post("/", response_model=schemas.Trade)
async def create_trade(
    trade: schemas.TradeCreate, 
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
):
    account_id = get_account_id(db, current_user)
    
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
                
                # Calculate PnL
                if open_trade.direction == models.TradeDirection.LONG:
                    open_trade.pnl = (float(open_trade.exit_price) - float(open_trade.entry_price)) * float(open_trade.quantity)
                else:
                    open_trade.pnl = (float(open_trade.entry_price) - float(open_trade.exit_price)) * float(open_trade.quantity)
                
                # Commission handling
                ratio = available_qty / float(trade.quantity)
                exit_comm = (trade.commission or 0) * ratio
                open_trade.exit_commission = exit_comm
                open_trade.commission = float(open_trade.commission or 0) + exit_comm
                open_trade.net_pnl = open_trade.pnl - open_trade.commission - float(open_trade.swap or 0)

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
                
                ratio = qty_to_close / available_qty
                part_entry_comm = float(open_trade.entry_commission or 0) * ratio
                closed_trade.entry_commission = part_entry_comm
                
                open_trade.entry_commission = float(open_trade.entry_commission or 0) - part_entry_comm
                open_trade.commission = float(open_trade.commission or 0) - part_entry_comm
                
                closed_trade.exit_price = trade.entry_price
                closed_trade.exit_at = trade.entry_at
                closed_trade.exit_reason = trade.setup_name or "Manual Partial Close"
                
                total_close_qty = float(trade.quantity)
                exit_comm_ratio = qty_to_close / total_close_qty
                exit_comm = (trade.commission or 0) * exit_comm_ratio
                
                closed_trade.exit_commission = exit_comm
                closed_trade.commission = closed_trade.entry_commission + exit_comm
                
                if closed_trade.direction == models.TradeDirection.LONG:
                    closed_trade.pnl = (float(closed_trade.exit_price) - float(closed_trade.entry_price)) * float(closed_trade.quantity)
                else:
                    closed_trade.pnl = (float(closed_trade.entry_price) - float(closed_trade.exit_price)) * float(closed_trade.quantity)
                
                closed_trade.net_pnl = closed_trade.pnl - closed_trade.commission
                
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
                open_trade.quantity = float(open_trade.quantity) - qty_to_close
                
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
async def preview_import(
    file: UploadFile = File(...), 
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
):
    """
    Превью импорта: парсит файл и возвращает список сделок БЕЗ сохранения.
    Показывает какие сделки новые, а какие уже существуют (дубликаты).
    """
    account_id = get_account_id(db, current_user)
    
    contents = await file.read()
    try:
        trades_data = import_service.parse_trade_file(contents, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Проверяем каждую сделку на дубликат
    preview_items = []
    for idx, trade_dict in enumerate(trades_data):
        existing = db.query(models.Trade).filter(
            models.Trade.account_id == account_id,
            models.Trade.symbol == trade_dict['symbol'],
            models.Trade.direction == trade_dict['direction'],
            models.Trade.entry_at == trade_dict['entry_at']
        ).first()
        
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
            "is_duplicate": existing is not None,
            "existing_id": existing.id if existing else None,
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
        }
    }


@router.post("/import")
async def import_trades(
    file: UploadFile = File(...),
    start_index: Optional[int] = Form(None),
    end_index: Optional[int] = Form(None),
    skip_duplicates: bool = Form(True),
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
):
    """
    Импорт сделок из файла.
    
    - start_index: индекс первой сделки для импорта (0-based)
    - end_index: индекс последней сделки для импорта (inclusive)
    - skip_duplicates: пропускать дубликаты (default: True)
    
    Дубликаты определяются по: symbol + direction + entry_at
    """
    account_id = get_account_id(db, current_user)
    
    contents = await file.read()
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
    
    for trade_dict in trades_to_import:
        existing = db.query(models.Trade).filter(
            models.Trade.account_id == account_id,
            models.Trade.symbol == trade_dict['symbol'],
            models.Trade.direction == trade_dict['direction'],
            models.Trade.entry_at == trade_dict['entry_at']
        ).first()
        
        if existing:
            duplicate_count += 1
            if skip_duplicates:
                skipped_count += 1
                continue
            else:
                # Если не пропускаем, обновляем существующую сделку
                for key, value in trade_dict.items():
                    setattr(existing, key, value)
                imported_count += 1
                continue
        
        trade_dict["account_id"] = account_id
        db_trade = models.Trade(**trade_dict)
        db.add(db_trade)
        imported_count += 1
    
    db.commit()
    return {
        "message": f"Импортировано: {imported_count}, пропущено дубликатов: {skipped_count}",
        "imported": imported_count,
        "skipped": skipped_count,
        "duplicates_found": duplicate_count,
        "total_in_file": total_in_file,
        "range_processed": {
            "start": actual_start,
            "end": actual_end,
            "count": len(trades_to_import)
        }
    }


@router.get("/", response_model=list[schemas.Trade])
async def read_trades(
    skip: int = 0, 
    limit: int = 5000, 
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
):
    account_id = get_account_id(db, current_user)
    trades = db.query(models.Trade).filter(
        models.Trade.account_id == account_id
    ).offset(skip).limit(limit).all()
    return trades


@router.patch("/{trade_id}", response_model=schemas.Trade)
async def update_trade(
    trade_id: int, 
    trade_update: schemas.TradeUpdate, 
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
):
    account_id = get_account_id(db, current_user)
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


@router.delete("/{trade_id}")
async def delete_trade(
    trade_id: int, 
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
):
    account_id = get_account_id(db, current_user)
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
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
):
    account_id = get_account_id(db, current_user)
    db_trade = db.query(models.Trade).filter(
        models.Trade.id == trade_id,
        models.Trade.account_id == account_id
    ).first()
    if not db_trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    
    db_trade.exit_price = trade_close.exit_price
    db_trade.exit_at = trade_close.exit_at
    db_trade.exit_reason = trade_close.exit_reason
    
    if trade_close.mae_price is not None:
        db_trade.mae_price = trade_close.mae_price
    if trade_close.mfe_price is not None:
        db_trade.mfe_price = trade_close.mfe_price
    
    # Auto-calculate MAE/MFE if not provided
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
    
    # Calculate PnL
    if db_trade.direction == models.TradeDirection.LONG:
        db_trade.pnl = (db_trade.exit_price - db_trade.entry_price) * db_trade.quantity
    else:
        db_trade.pnl = (db_trade.entry_price - db_trade.exit_price) * db_trade.quantity
    
    # AI Analysis
    trade_data = {
        "symbol": db_trade.symbol,
        "direction": db_trade.direction.value,
        "pnl": float(db_trade.pnl),
        "mae_price": float(db_trade.mae_price) if db_trade.mae_price else None,
        "mfe_price": float(db_trade.mfe_price) if db_trade.mfe_price else None,
        "notes": db_trade.notes,
        "exit_price": float(db_trade.exit_price)
    }
    db_trade.ai_analysis = await ai_service.analyze_trade_with_ai(trade_data)
        
    db.commit()
    db.refresh(db_trade)
    return db_trade


@router.get("/unrealized-pnl")
async def get_unrealized_pnl(
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
):
    account_id = get_account_id(db, current_user)
    open_trades = db.query(models.Trade).filter(
        models.Trade.account_id == account_id,
        models.Trade.exit_at == None
    ).all()
    if not open_trades:
        return []
    
    tickers = list(set(t.symbol for t in open_trades))
    current_prices = market_data_service.get_current_prices(tickers)
    futures_specs = market_data_service.get_futures_specs(tickers)
    
    results = []
    for trade in open_trades:
        current_price = current_prices.get(trade.symbol)
        if current_price:
            entry_price = float(trade.entry_price)
            quantity = float(trade.quantity)
            
            spec = futures_specs.get(trade.symbol)
            if spec and spec.get('stepprice') and spec.get('minstep'):
                stepprice = spec['stepprice']
                minstep = spec['minstep']
                price_diff = current_price - entry_price
                if trade.direction == models.TradeDirection.SHORT:
                    price_diff = -price_diff
                pnl = price_diff * (stepprice / minstep) * quantity
            else:
                if trade.direction == models.TradeDirection.LONG:
                    pnl = (current_price - entry_price) * quantity
                else:
                    pnl = (entry_price - current_price) * quantity
            
            results.append({
                "trade_id": trade.id,
                "symbol": trade.symbol,
                "current_price": current_price,
                "unrealized_pnl": pnl
            })
            
    return results
