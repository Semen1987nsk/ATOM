"""
Real PnL Router — Получение РЕАЛЬНОГО PnL напрямую из API брокера

Этот роутер возвращает точные данные о PnL, рассчитанные на основе:
- Текущего баланса от API
- Net Deposit (ввод - вывод)
- Вариационной маржи для фьючерсов
- Всех комиссий (Broker Fee, Margin Fee, Service Fee)

ФОРМУЛЫ:
- Real PnL = Текущий баланс - Net Deposit
- Закрытый PnL = Акции PnL + Varmargin + Комиссии + Другое
- Нереализованный PnL = Real PnL - Закрытый PnL
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from decimal import Decimal
from typing import Optional

import database
import models
import auth_service
import pnl_service
from logger import get_logger

log = get_logger("real_pnl")

router = APIRouter(tags=["real_pnl"])


# get_account_id is now centralized in auth_service


@router.get("/")
async def get_real_pnl(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """
    Получить РЕАЛЬНЫЙ PnL напрямую из API брокера.
    
    Возвращает:
    - real_pnl: Фактический PnL = Баланс - Net Deposit
    - stocks_pnl: PnL по акциям (закрытые сделки)
    - futures_pnl: PnL по фьючерсам (вариационная маржа)
    - broker_fee, margin_fee, service_fee: РљРѕРјРёСЃСЃРёРё
    - unrealized_pnl: Нереализованный PnL (открытые позиции)
    - roi: Return on Investment (%)
    """
    account_id = auth_service.get_account_id(db, current_user)
    
    # Получаем подключение к брокеру
    connection = db.query(models.BrokerConnection).filter(
        models.BrokerConnection.account_id == account_id,
        models.BrokerConnection.is_active == True
    ).first()
    
    if not connection:
        raise HTTPException(status_code=404, detail="No active broker connection")
    
    # Импортируем сервис
    from tinkoff_service_v2 import TinkoffServiceV2
    
    try:
        service = TinkoffServiceV2(connection.api_token)
        
        # Получаем текущий баланс
        portfolio = service._make_request(
            "POST",
            "/tinkoff.public.invest.api.contract.v1.OperationsService/GetPortfolio",
            {"accountId": connection.broker_account_id, "currency": "RUB"}
        )
        current_balance = float(service._money_to_decimal(portfolio.get("totalAmountPortfolio", {})))
        cash = float(service._money_to_decimal(portfolio.get("totalAmountCurrencies", {})))
        positions_value = float(
            service._money_to_decimal(portfolio.get("totalAmountShares", {})) +
            service._money_to_decimal(portfolio.get("totalAmountFutures", {})) +
            service._money_to_decimal(portfolio.get("totalAmountBonds", {})) +
            service._money_to_decimal(portfolio.get("totalAmountEtf", {}))
        )
        
        # Получаем все операции
        from_date = datetime(2020, 1, 1)  # Начало истории
        to_date = datetime.now()
        
        operations = service.get_operations(connection.broker_account_id, from_date, to_date)
        
        # Рассчитываем все компоненты
        net_deposit = Decimal(0)
        stocks_pnl = Decimal(0)
        varmargin = Decimal(0)
        broker_fee = Decimal(0)
        margin_fee = Decimal(0)
        service_fee = Decimal(0)
        other = Decimal(0)
        
        for op in operations:
            op_type = op.get("operationType", "")
            payment = service._money_to_decimal(op.get("payment", {}))
            figi = op.get("figi", "")
            
            if op_type == "OPERATION_TYPE_INPUT":
                net_deposit += payment
            elif op_type == "OPERATION_TYPE_OUTPUT":
                net_deposit += payment  # Отрицательный
            elif op_type in ["OPERATION_TYPE_BUY", "OPERATION_TYPE_SELL"]:
                # Проверяем тип инструмента
                if figi:
                    info = service.get_instrument_info(figi)
                    if info and info.get("instrument_type") != "INSTRUMENT_TYPE_FUTURES":
                        stocks_pnl += payment
            elif op_type == "OPERATION_TYPE_ACCRUING_VARMARGIN":
                varmargin += payment
            elif op_type == "OPERATION_TYPE_WRITING_OFF_VARMARGIN":
                varmargin += payment
            elif op_type == "OPERATION_TYPE_BROKER_FEE":
                broker_fee += payment  # Отрицательный
            elif op_type == "OPERATION_TYPE_MARGIN_FEE":
                margin_fee += payment  # Отрицательный
            elif op_type == "OPERATION_TYPE_SERVICE_FEE":
                service_fee += payment  # Отрицательный
            elif op_type in ["OPERATION_TYPE_TAX", "OPERATION_TYPE_INP_MULTI", "OPERATION_TYPE_OPTION_EXPIRATION"]:
                other += payment
        
        # Расчёты
        net_deposit_float = float(net_deposit)
        real_pnl = current_balance - net_deposit_float
        
        closed_pnl = float(stocks_pnl + varmargin + broker_fee + margin_fee + service_fee + other)
        unrealized_pnl = real_pnl - closed_pnl
        
        roi = (real_pnl / net_deposit_float * 100) if net_deposit_float > 0 else 0
        
        return {
            "current_balance": round(current_balance, 2),
            "cash": round(cash, 2),
            "positions_value": round(positions_value, 2),
            "net_deposit": round(net_deposit_float, 2),
            
            "real_pnl": round(real_pnl, 2),
            "roi": round(roi, 2),
            
            "breakdown": {
                "stocks_pnl": round(float(stocks_pnl), 2),
                "futures_pnl": round(float(varmargin), 2),
                "broker_fee": round(float(broker_fee), 2),
                "margin_fee": round(float(margin_fee), 2),
                "service_fee": round(float(service_fee), 2),
                "other": round(float(other), 2),
                "closed_pnl": round(closed_pnl, 2),
                "unrealized_pnl": round(unrealized_pnl, 2)
            },
            
            "totals": {
                "varmargin_accruing": round(float(sum(
                    service._money_to_decimal(op.get("payment", {}))
                    for op in operations
                    if op.get("operationType") == "OPERATION_TYPE_ACCRUING_VARMARGIN"
                )), 2),
                "varmargin_writing_off": round(float(sum(
                    service._money_to_decimal(op.get("payment", {}))
                    for op in operations
                    if op.get("operationType") == "OPERATION_TYPE_WRITING_OFF_VARMARGIN"
                )), 2),
                "total_operations": len(operations)
            },
            
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        log.error(f"Error fetching real PnL: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/recalculate")
async def recalculate_trades_pnl(
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)
):
    """
    Recalculate PnL for ALL closed trades using unified pnl_service.
    Uses moex_service for correct point_value (no hardcoded specs).
    No broker connection required.
    """
    account_id = auth_service.get_account_id(db, current_user)

    try:
        closed_trades = db.query(models.Trade).filter(
            models.Trade.account_id == account_id,
            models.Trade.exit_at != None
        ).all()

        updated_count = 0
        total_correction = Decimal(0)

        for trade in closed_trades:
            if not trade.exit_price or not trade.entry_price:
                continue

            new_pnl, new_net_pnl = pnl_service.recalculate_trade_pnl(trade)

            old_pnl = Decimal(str(trade.pnl or 0))
            if abs(Decimal(str(new_pnl)) - old_pnl) > Decimal("0.01"):
                total_correction += Decimal(str(new_pnl)) - old_pnl
                trade.pnl = new_pnl
                trade.net_pnl = new_net_pnl
                updated_count += 1

        db.commit()

        return {
            "updated_trades": updated_count,
            "total_trades": len(closed_trades),
            "total_correction": round(float(total_correction), 2),
            "message": f"Recalculated {updated_count} of {len(closed_trades)} closed trades"
        }

    except Exception as e:
        log.error(f"Error recalculating PnL: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
