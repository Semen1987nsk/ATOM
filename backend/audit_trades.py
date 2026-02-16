"""
АУДИТ ИМПОРТА СДЕЛОК: API vs БД
=================================
Скрипт сверяет данные из Tinkoff API напрямую с тем, что хранится в БД.
Результат: сводная таблица расхождений по каждому столбцу каждой сделки.

Запуск:
    cd backend
    python audit_trades.py
"""

import os
import sys
import json
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta, timezone
from collections import defaultdict

# Загружаем .env
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Trade, TradeDirection, BrokerConnection, Account

# ==================== DB SETUP ====================
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./atom.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(bind=engine)

# ==================== TINKOFF API ====================
from tinkoff_service import TinkoffService


def fmt_decimal(val, places=4):
    """Format Decimal/float for display"""
    if val is None:
        return "None"
    try:
        return f"{float(val):.{places}f}"
    except:
        return str(val)


def parse_api_date(date_str):
    """Parse ISO date from Tinkoff API → naive datetime"""
    if not date_str:
        return None
    try:
        clean = date_str.strip()
        if clean.endswith('Z'):
            clean = clean[:-1] + '+00:00'
        dt = datetime.fromisoformat(clean)
        return dt.replace(tzinfo=None)
    except:
        return None


def money_to_decimal(money):
    """MoneyValue dict → Decimal"""
    if not money or not isinstance(money, dict):
        return Decimal(0)
    try:
        units = int(money.get("units", 0) or 0)
        nano = int(money.get("nano", 0) or 0)
        return Decimal(units) + Decimal(nano) / Decimal(1_000_000_000)
    except:
        return Decimal(0)


def get_executed_qty(op):
    """Реально исполненное количество (не заявленное!)"""
    qty_done = op.get("quantityDone")
    if qty_done is not None:
        try:
            val = int(qty_done)
            if val > 0:
                return val
        except:
            pass
    trades_list = op.get("trades", [])
    if trades_list:
        try:
            val = sum(int(t.get("quantity", 0)) for t in trades_list)
            if val > 0:
                return val
        except:
            pass
    raw_qty = int(op.get("quantity", 0))
    qty_rest = int(op.get("quantityRest", 0))
    if qty_rest > 0:
        return max(raw_qty - qty_rest, 0)
    return max(raw_qty, 0)


# ==================== MAIN AUDIT ====================

def run_audit():
    db = SessionLocal()
    
    try:
        # 1. Получаем подключение к брокеру
        connections = db.query(BrokerConnection).filter(
            BrokerConnection.is_active == True
        ).all()
        
        if not connections:
            print("❌ Нет активных подключений к брокеру!")
            return
        
        conn = connections[0]
        print(f"📡 Брокер: {conn.broker.value}, account_id={conn.account_id}")
        print(f"   broker_account_id: {conn.broker_account_id}")
        print(f"   sync_from_date: {conn.sync_from_date}")
        print()
        
        # 2. Загружаем ВСЕ сделки из БД
        db_trades = db.query(Trade).filter(
            Trade.account_id == conn.account_id
        ).order_by(Trade.entry_at).all()
        
        print(f"📊 Сделки в БД: {len(db_trades)}")
        
        # 3. Получаем операции из API
        service = TinkoffService(conn.api_token)
        
        from_date = conn.sync_from_date or datetime(2024, 1, 1)
        to_date = datetime.utcnow()
        
        print(f"📡 Загружаем операции из API за {from_date.date()} — {to_date.date()}...")
        operations = service.get_operations(conn.broker_account_id, from_date, to_date)
        
        buy_types = ["OPERATION_TYPE_BUY", "OPERATION_TYPE_BUY_CARD"]
        sell_types = ["OPERATION_TYPE_SELL", "OPERATION_TYPE_SELL_CARD"]
        
        trade_ops = [op for op in operations if op.get("operationType") in buy_types + sell_types]
        print(f"   Всего операций: {len(operations)}")
        print(f"   BUY/SELL операций: {len(trade_ops)}")
        
        # 4. Группируем API операции в позиции (FIFO v2)
        closed_trades, open_positions = service._build_trades_fifo(operations)
        print(f"   Закрытых сделок (FIFO): {len(closed_trades)}")
        print(f"   Открытых позиций (FIFO): {len(open_positions)}")
        print()
        
        # 5. Для каждой закрытой сделки из API — сравниваем с БД
        
        errors = []  # Список расхождений
        api_positions_detail = []
        
        for ct in closed_trades:
            figi = ct.figi
            instrument = service.get_instrument_info(figi)
            ticker = instrument.get("ticker", figi) if instrument else figi
            inst_name = instrument.get("name", "") if instrument else ""
            inst_type = instrument.get("instrument_type", "SHARE") if instrument else "SHARE"
            lot_size = int(instrument.get("lot", 1)) if instrument else 1
            
            entries = ct.entry_lots
            exits = ct.exit_lots
            direction_str = ct.direction
            
            if not entries:
                continue
            
            # --- API: расчёт данных позиции ---
            total_entry_qty = sum(e.qty for e in entries)
            total_entry_value = sum(e.price * e.qty for e in entries)
            api_entry_price = total_entry_value / total_entry_qty if total_entry_qty else Decimal(0)
            
            api_exit_price = None
            total_exit_qty = 0
            if exits:
                total_exit_qty = sum(e.qty for e in exits)
                total_exit_value = sum(e.price * e.qty for e in exits)
                api_exit_price = total_exit_value / total_exit_qty if total_exit_qty else None
            
            entry_dates = [e.date for e in entries if e.date]
            exit_dates = [e.date for e in exits if e.date]
            
            api_entry_at = min(entry_dates) if entry_dates else None
            api_exit_at = max(exit_dates) if exit_dates else None
            
            api_commission = sum(e.commission for e in entries) + sum(e.commission for e in exits)
            
            # PnL
            is_closed = bool(exits) and total_exit_qty >= total_entry_qty
            api_pnl = None
            if exits:
                is_futures = inst_type == "INSTRUMENT_TYPE_FUTURES"
                if is_futures:
                    min_inc = instrument.get("min_price_increment", Decimal(0)) if instrument else Decimal(0)
                    min_inc_amt = instrument.get("min_price_increment_amount", Decimal(0)) if instrument else Decimal(0)
                    if min_inc and min_inc > 0 and min_inc_amt and min_inc_amt > 0:
                        point_value = min_inc_amt / min_inc
                        price_diff = api_exit_price - api_entry_price
                        if direction_str == "SHORT":
                            price_diff = -price_diff
                        api_pnl = price_diff * total_entry_qty * point_value
                    else:
                        entry_payments = sum(e.payment for e in entries)
                        exit_payments = sum(e.payment for e in exits)
                        api_pnl = entry_payments + exit_payments
                else:
                    entry_payments = sum(e.payment for e in entries)
                    exit_payments = sum(e.payment for e in exits)
                    api_pnl = entry_payments + exit_payments
            
            api_net_pnl = api_pnl - api_commission if api_pnl is not None else None
            
            api_pos = {
                "ticker": ticker,
                "name": inst_name,
                "type": inst_type,
                "direction": direction_str,
                "entry_price": api_entry_price,
                "exit_price": api_exit_price,
                "quantity": total_entry_qty,
                "entry_at": api_entry_at,
                "exit_at": api_exit_at,
                "commission": api_commission,
                "pnl": api_pnl,
                "net_pnl": api_net_pnl,
                "is_closed": is_closed,
                "lot_size": lot_size,
                "n_entries": len(entries),
                "n_exits": len(exits),
                "entries_raw": entries,
                "exits_raw": exits,
            }
            api_positions_detail.append(api_pos)
        
        # 6. Сопоставляем API позиции с DB трейдами
        
        # Индексируем DB трейды по (symbol, direction, entry_at±5s)
        db_matched = set()
        
        print("=" * 130)
        print(f"{'#':>3} | {'Тикер':<10} | {'Dir':<5} | {'Поле':<18} | {'API':>22} | {'БД':>22} | {'Δ':>15} | Критичность")
        print("=" * 130)
        
        error_count = 0
        position_count = 0
        matched_count = 0
        unmatched_api = []
        
        for api_pos in api_positions_detail:
            position_count += 1
            ticker = api_pos["ticker"]
            direction = api_pos["direction"]
            api_entry_at = api_pos["entry_at"]
            
            if not api_entry_at:
                errors.append({
                    "pos": position_count,
                    "ticker": ticker,
                    "dir": direction,
                    "field": "entry_at",
                    "api": "None",
                    "db": "—",
                    "delta": "—",
                    "severity": "🔴 CRITICAL"
                })
                continue
            
            # Ищем соответствующий трейд в БД
            db_direction = "long" if direction == "LONG" else "short"
            best_match = None
            best_delta = timedelta(days=999)
            
            for t in db_trades:
                if t.id in db_matched:
                    continue
                if t.symbol != ticker:
                    continue
                if t.direction.value != db_direction:
                    continue
                    
                delta = abs(t.entry_at - api_entry_at)
                if delta < best_delta and delta < timedelta(minutes=30):
                    best_delta = delta
                    best_match = t
            
            if not best_match:
                unmatched_api.append(api_pos)
                errors.append({
                    "pos": position_count,
                    "ticker": ticker,
                    "dir": direction,
                    "field": "MATCH",
                    "api": f"entry={api_entry_at}",
                    "db": "НЕТ В БД",
                    "delta": "—",
                    "severity": "🔴 MISSING"
                })
                continue
            
            db_matched.add(best_match.id)
            matched_count += 1
            t = best_match
            
            # ---- СРАВНИВАЕМ КАЖДОЕ ПОЛЕ ----
            
            def compare(field, api_val, db_val, tol=0, is_date=False, is_decimal=True):
                nonlocal error_count
                
                if api_val is None and db_val is None:
                    return  # Both None = OK
                
                if is_date:
                    if api_val and db_val:
                        delta = abs((api_val - db_val).total_seconds())
                        if delta > tol:
                            error_count += 1
                            errors.append({
                                "pos": position_count,
                                "ticker": ticker,
                                "dir": direction,
                                "field": field,
                                "api": str(api_val)[:19],
                                "db": str(db_val)[:19],
                                "delta": f"{delta:.0f}s",
                                "severity": "🟡 DATE" if delta < 60 else "🔴 DATE"
                            })
                    elif (api_val is None) != (db_val is None):
                        error_count += 1
                        errors.append({
                            "pos": position_count,
                            "ticker": ticker,
                            "dir": direction,
                            "field": field,
                            "api": str(api_val)[:19] if api_val else "None",
                            "db": str(db_val)[:19] if db_val else "None",
                            "delta": "NULL mismatch",
                            "severity": "🔴 NULL"
                        })
                    return
                
                if is_decimal:
                    try:
                        a = float(api_val) if api_val is not None else None
                        b = float(db_val) if db_val is not None else None
                    except:
                        a, b = api_val, db_val
                    
                    if a is None and b is None:
                        return
                    if a is not None and b is not None:
                        diff = abs(a - b)
                        pct = abs(diff / a * 100) if a != 0 else (0 if diff == 0 else 100)
                        if pct > tol:
                            error_count += 1
                            sev = "🟢 MINOR" if pct < 1 else ("🟡 WARN" if pct < 5 else "🔴 CRIT")
                            errors.append({
                                "pos": position_count,
                                "ticker": ticker,
                                "dir": direction,
                                "field": field,
                                "api": fmt_decimal(a),
                                "db": fmt_decimal(b),
                                "delta": f"{pct:.2f}%",
                                "severity": sev
                            })
                    elif (a is None) != (b is None):
                        error_count += 1
                        errors.append({
                            "pos": position_count,
                            "ticker": ticker,
                            "dir": direction,
                            "field": field,
                            "api": fmt_decimal(a) if a is not None else "None",
                            "db": fmt_decimal(b) if b is not None else "None",
                            "delta": "NULL mismatch",
                            "severity": "🔴 NULL"
                        })
                    return
                
                # String/exact compare
                if str(api_val) != str(db_val):
                    error_count += 1
                    errors.append({
                        "pos": position_count,
                        "ticker": ticker,
                        "dir": direction,
                        "field": field,
                        "api": str(api_val)[:22],
                        "db": str(db_val)[:22],
                        "delta": "≠",
                        "severity": "🟡 DIFF"
                    })
            
            # Direction
            compare("direction", direction.lower(), t.direction.value, is_decimal=False)
            
            # Entry Price (tolerance 0.1% — rounding)
            compare("entry_price", api_pos["entry_price"], t.entry_price, tol=0.1)
            
            # Exit Price
            compare("exit_price", api_pos["exit_price"], t.exit_price, tol=0.1)
            
            # Quantity
            compare("quantity", api_pos["quantity"], t.quantity, tol=0.1)
            
            # Entry Date (tolerance 10 seconds)
            compare("entry_at", api_pos["entry_at"], t.entry_at, tol=10, is_date=True)
            
            # Exit Date (tolerance 10 seconds)
            compare("exit_at", api_pos["exit_at"], t.exit_at, tol=10, is_date=True)
            
            # Commission (tolerance 1%)
            compare("commission", api_pos["commission"], t.commission, tol=1)
            
            # PnL (tolerance 0.5%)
            compare("pnl", api_pos["pnl"], t.pnl, tol=0.5)
            
            # Net PnL (tolerance 1%)
            compare("net_pnl", api_pos["net_pnl"], t.net_pnl, tol=1)
            
            # Asset type
            type_map = {
                "INSTRUMENT_TYPE_SHARE": "Stock",
                "INSTRUMENT_TYPE_BOND": "Bond",
                "INSTRUMENT_TYPE_ETF": "ETF",
                "INSTRUMENT_TYPE_FUTURES": "Futures",
                "INSTRUMENT_TYPE_CURRENCY": "Currency",
            }
            expected_type = type_map.get(api_pos["type"], "Stock")
            if t.asset_type:
                compare("asset_type", expected_type, t.asset_type, is_decimal=False)
        
        # 7. Ищем трейды в БД, которых нет в API
        unmatched_db = []
        for t in db_trades:
            if t.id not in db_matched:
                unmatched_db.append(t)
                errors.append({
                    "pos": "-",
                    "ticker": t.symbol,
                    "dir": t.direction.value.upper(),
                    "field": "MATCH",
                    "api": "НЕТ В API",
                    "db": f"id={t.id}, entry={t.entry_at}",
                    "delta": "—",
                    "severity": "🟠 ORPHAN"
                })
        
        # 8. Печатаем таблицу
        print()
        if not errors:
            print("✅ Все данные совпадают!")
        else:
            for e in errors:
                print(f"{str(e['pos']):>3} | {e['ticker']:<10} | {e['dir']:<5} | "
                      f"{e['field']:<18} | {e['api']:>22} | {e['db']:>22} | "
                      f"{e['delta']:>15} | {e['severity']}")
        
        print("=" * 130)
        
        # 9. Сводка
        print()
        print("📊 СВОДКА АУДИТА")
        print(f"   API позиций:      {position_count}")
        print(f"   DB трейдов:       {len(db_trades)}")
        print(f"   Совпало:          {matched_count}")
        print(f"   Нет в БД:         {len(unmatched_api)}")
        print(f"   Orphan в БД:      {len(unmatched_db)}")
        print(f"   Расхождений:      {error_count}")
        print()
        
        # Группировка ошибок по типу
        by_field = defaultdict(int)
        by_severity = defaultdict(int)
        for e in errors:
            by_field[e["field"]] += 1
            by_severity[e["severity"]] += 1
        
        print("   По полю:")
        for field, cnt in sorted(by_field.items(), key=lambda x: -x[1]):
            print(f"     {field:<18} {cnt}")
        
        print()
        print("   По критичности:")
        for sev, cnt in sorted(by_severity.items(), key=lambda x: -x[1]):
            print(f"     {sev:<18} {cnt}")
        
        # 10. Детали: полная выгрузка API данных для ручной проверки
        print()
        print("=" * 80)
        print("📋 ПОЛНЫЕ ДАННЫЕ ИЗ API (для ручной сверки)")
        print("=" * 80)
        
        for i, api_pos in enumerate(api_positions_detail, 1):
            ticker = api_pos["ticker"]
            direction = api_pos["direction"]
            status = "CLOSED" if api_pos["is_closed"] else "OPEN"
            
            print(f"\n--- Позиция #{i}: {ticker} {direction} [{status}] ---")
            print(f"  Entry Price:  {fmt_decimal(api_pos['entry_price'], 6)}")
            print(f"  Exit Price:   {fmt_decimal(api_pos['exit_price'], 6)}")
            print(f"  Quantity:     {api_pos['quantity']} (lot_size={api_pos['lot_size']})")
            print(f"  Entry At:     {api_pos['entry_at']}")
            print(f"  Exit At:      {api_pos['exit_at']}")
            print(f"  Commission:   {fmt_decimal(api_pos['commission'])}")
            print(f"  PnL (gross):  {fmt_decimal(api_pos['pnl'])}")
            print(f"  PnL (net):    {fmt_decimal(api_pos['net_pnl'])}")
            print(f"  Entries:      {api_pos['n_entries']} ops")
            print(f"  Exits:        {api_pos['n_exits']} ops")
            
            # Детали входов
            for j, e in enumerate(api_pos["entries_raw"]):
                print(f"    Entry[{j}]: price={fmt_decimal(e['price'],6)} qty={e['quantity']} "
                      f"date={str(e.get('date',''))[:19]} payment={fmt_decimal(e.get('payment',0))}")
            for j, e in enumerate(api_pos["exits_raw"]):
                print(f"    Exit[{j}]:  price={fmt_decimal(e['price'],6)} qty={e['quantity']} "
                      f"date={str(e.get('date',''))[:19]} payment={fmt_decimal(e.get('payment',0))}")
        
        # 11. DB трейды для сверки
        print()
        print("=" * 80)
        print("📋 ДАННЫЕ ИЗ БД")
        print("=" * 80)
        
        for t in db_trades:
            status = "CLOSED" if t.exit_at else "OPEN"
            tags_str = ", ".join(t.tags) if t.tags else ""
            print(f"\n--- Trade id={t.id}: {t.symbol} {t.direction.value.upper()} [{status}] {tags_str} ---")
            print(f"  Entry Price:  {fmt_decimal(t.entry_price, 6)}")
            print(f"  Exit Price:   {fmt_decimal(t.exit_price, 6)}")
            print(f"  Quantity:     {fmt_decimal(t.quantity)}")
            print(f"  Entry At:     {t.entry_at}")
            print(f"  Exit At:      {t.exit_at}")
            print(f"  Commission:   {fmt_decimal(t.commission)}")
            print(f"  PnL (gross):  {fmt_decimal(t.pnl)}")
            print(f"  PnL (net):    {fmt_decimal(t.net_pnl)}")
            print(f"  Asset Type:   {t.asset_type}")
            print(f"  Asset Name:   {t.asset_name}")
            if t.operations:
                for op in t.operations[:10]:
                    print(f"    Op: {op.get('type','?')} price={op.get('price','?')} qty={op.get('qty','?')} "
                          f"time={str(op.get('time',''))[:19]}")
        
        print()
        print("=" * 80)
        print(f"✅ Аудит завершён. Расхождений: {error_count}")
        print("=" * 80)
        
    finally:
        db.close()


if __name__ == "__main__":
    run_audit()
