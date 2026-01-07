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
    
    # Парсим информацию о балансе из файла
    balance_info = import_service.parse_account_balance(contents, file.filename)
    
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


@router.post("/calculate-mae-mfe")
async def calculate_mae_mfe_bulk(
    trade_ids: Optional[List[int]] = None,
    db: Session = Depends(database.get_db),
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
):
    """
    Массовый расчёт MAE/MFE для закрытых сделок.
    Если trade_ids не указаны, рассчитывает для всех сделок без MAE/MFE.
    """
    account_id = get_account_id(db, current_user)
    
    # Получаем закрытые сделки без MAE/MFE
    query = db.query(models.Trade).filter(
        models.Trade.account_id == account_id,
        models.Trade.exit_at != None,  # Только закрытые
    )
    
    if trade_ids:
        query = query.filter(models.Trade.id.in_(trade_ids))
    else:
        # Только сделки без MAE или MFE
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
                operations=operations  # Передаём операции для точного определения периода
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
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
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
    account_id = get_account_id(db, current_user)
    
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
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
):
    """Получить список сделок с post-exit анализом"""
    account_id = get_account_id(db, current_user)
    
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
    current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)
):
    """Получить post-exit анализ для конкретной сделки"""
    account_id = get_account_id(db, current_user)
    
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