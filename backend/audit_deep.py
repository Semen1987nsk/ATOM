"""
ГЛУБОКИЙ АУДИТ: ВСЕ ОШИБКИ В ДАННЫХ
======================================
Проверяет:
1. DB-internal: exit < entry, net_pnl=None, дубликаты, holding_time, commission=0 и т.д.
2. Независимая перегруппировка API операций (не через сервис!)
3. Поштучная сверка каждой операции
4. Точный пересчёт PnL по формулам из документации
"""

import os, sys, json
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timedelta, timezone
from collections import defaultdict, Counter

from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from models import Trade, TradeDirection, BrokerConnection, Account

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./atom.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(bind=engine)

from tinkoff_service import TinkoffService


def money_to_decimal(money):
    if not money or not isinstance(money, dict):
        return Decimal(0)
    try:
        units = int(money.get("units", 0) or 0)
        nano = int(money.get("nano", 0) or 0)
        return Decimal(units) + Decimal(nano) / Decimal(1_000_000_000)
    except:
        return Decimal(0)


def parse_api_date(date_str):
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


def get_executed_qty(op):
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


def run_deep_audit():
    db = SessionLocal()
    all_errors = []
    error_id = [0]
    
    def add_error(category, severity, ticker, trade_id, field, detail, api_val="", db_val=""):
        error_id[0] += 1
        all_errors.append({
            "id": error_id[0],
            "cat": category,
            "sev": severity,
            "ticker": ticker,
            "trade_id": trade_id,
            "field": field,
            "detail": detail,
            "api": str(api_val)[:30],
            "db": str(db_val)[:30],
        })
    
    try:
        # ==============================================================
        # ЧАСТЬ 1: ВНУТРЕННЯЯ КОНСИСТЕНТНОСТЬ БД
        # ==============================================================
        print("=" * 100)
        print("ЧАСТЬ 1: ВНУТРЕННЯЯ КОНСИСТЕНТНОСТЬ БД")
        print("=" * 100)
        
        connections = db.query(BrokerConnection).filter(BrokerConnection.is_active == True).all()
        if not connections:
            print("❌ Нет подключений к брокеру!")
            return
        conn = connections[0]
        
        all_trades = db.query(Trade).filter(Trade.account_id == conn.account_id).order_by(Trade.entry_at).all()
        print(f"Всего трейдов в БД: {len(all_trades)}")
        
        # --- 1.1 exit_at < entry_at ---
        print("\n--- 1.1 exit_at < entry_at (физически невозможно) ---")
        for t in all_trades:
            if t.exit_at and t.entry_at and t.exit_at < t.entry_at:
                delta = (t.entry_at - t.exit_at).total_seconds()
                add_error("DB_CONSISTENCY", "🔴 CRITICAL", t.symbol, t.id, "exit_at < entry_at",
                          f"exit {t.exit_at} РАНЬШЕ entry {t.entry_at} на {delta:.0f}s",
                          str(t.exit_at)[:19], str(t.entry_at)[:19])
        
        # --- 1.2 net_pnl = None когда pnl есть ---
        print("--- 1.2 net_pnl = None при наличии pnl ---")
        for t in all_trades:
            if t.pnl is not None and t.net_pnl is None:
                add_error("DB_CONSISTENCY", "🔴 CRITICAL", t.symbol, t.id, "net_pnl is None",
                          f"pnl={t.pnl} но net_pnl=None (не рассчитан)",
                          str(t.pnl), "None")
        
        # --- 1.3 Точные дубликаты ---
        print("--- 1.3 Точные дубликаты (symbol + direction + entry_at) ---")
        seen = {}
        for t in all_trades:
            key = (t.symbol, t.direction.value, str(t.entry_at)[:19])
            if key in seen:
                prev = seen[key]
                add_error("DUPLICATE", "🔴 CRITICAL", t.symbol, t.id, "EXACT DUPLICATE",
                          f"Дубль id={prev.id} vs id={t.id}, entry={str(t.entry_at)[:19]}",
                          f"id={prev.id}", f"id={t.id}")
            else:
                seen[key] = t
        
        # --- 1.4 Близкие дубликаты (±5 секунд, тот же символ+направление) ---
        print("--- 1.4 Близкие дубликаты (±5 sec, same qty) ---")
        sorted_trades = sorted(all_trades, key=lambda t: (t.symbol, t.direction.value, t.entry_at))
        for i in range(len(sorted_trades) - 1):
            a = sorted_trades[i]
            b = sorted_trades[i + 1]
            if a.symbol == b.symbol and a.direction == b.direction:
                delta = abs((a.entry_at - b.entry_at).total_seconds())
                if 0 < delta <= 5 and a.quantity == b.quantity:
                    add_error("DUPLICATE", "🟠 WARN", a.symbol, b.id, "NEAR DUPLICATE",
                              f"id={a.id} vs id={b.id}, Δt={delta:.1f}s, qty={a.quantity}",
                              f"id={a.id}", f"id={b.id}")
        
        # --- 1.5 holding_time_minutes неправильный ---
        print("--- 1.5 holding_time_minutes ---")
        for t in all_trades:
            if t.entry_at and t.exit_at and t.holding_time_minutes is not None:
                expected = int((t.exit_at - t.entry_at).total_seconds() / 60)
                if expected < 0:
                    continue  # Already caught in 1.1
                if abs(expected - t.holding_time_minutes) > 2:
                    add_error("DB_CONSISTENCY", "🟡 WARN", t.symbol, t.id, "holding_time",
                              f"expected={expected}min, actual={t.holding_time_minutes}min",
                              str(expected), str(t.holding_time_minutes))
            if t.entry_at and t.exit_at is None and t.holding_time_minutes is not None and t.holding_time_minutes > 0:
                add_error("DB_CONSISTENCY", "🟡 WARN", t.symbol, t.id, "holding_time on open",
                          f"Открытая сделка но holding_time={t.holding_time_minutes}", "", str(t.holding_time_minutes))
        
        # --- 1.6 commission = 0 на закрытых сделках ---
        print("--- 1.6 commission = 0 на закрытых сделках ---")
        for t in all_trades:
            if t.exit_at and (t.commission is None or float(t.commission or 0) == 0):
                tags = t.tags or []
                if "#tinkoff" in tags or "#autosync" in tags:
                    add_error("DB_CONSISTENCY", "🟠 WARN", t.symbol, t.id, "commission = 0",
                              f"Закрытая сделка с нулевой комиссией (autosync)",
                              "0", "expected > 0")
        
        # --- 1.7 pnl на открытых сделках (должен быть None) ---
        print("--- 1.7 pnl на открытых сделках ---")
        for t in all_trades:
            if t.exit_at is None and t.pnl is not None:
                add_error("DB_CONSISTENCY", "🟡 WARN", t.symbol, t.id, "pnl on OPEN trade",
                          f"pnl={t.pnl} на открытой сделке (exit_at=None)",
                          str(t.pnl), "should be None")
        
        # --- 1.8 quantity <= 0 ---
        print("--- 1.8 quantity <= 0 ---")
        for t in all_trades:
            if t.quantity is not None and float(t.quantity) <= 0:
                add_error("DB_CONSISTENCY", "🔴 CRITICAL", t.symbol, t.id, "quantity <= 0",
                          f"quantity={t.quantity}", str(t.quantity), "> 0")
        
        # --- 1.9 entry_price <= 0 ---
        print("--- 1.9 entry_price <= 0 ---")
        for t in all_trades:
            if t.entry_price is not None and float(t.entry_price) <= 0:
                add_error("DB_CONSISTENCY", "🔴 CRITICAL", t.symbol, t.id, "entry_price <= 0",
                          f"entry_price={t.entry_price}", str(t.entry_price), "> 0")
        
        # --- 1.10 net_pnl != pnl - commission (когда оба заполнены) ---
        print("--- 1.10 net_pnl != pnl - commission ---")
        for t in all_trades:
            if t.pnl is not None and t.net_pnl is not None and t.commission is not None:
                expected_net = float(t.pnl) - float(t.commission)
                actual_net = float(t.net_pnl)
                if abs(expected_net) > 0.01:
                    pct_diff = abs(expected_net - actual_net) / abs(expected_net) * 100
                else:
                    pct_diff = abs(expected_net - actual_net) * 100
                if pct_diff > 1 and abs(expected_net - actual_net) > 0.5:
                    add_error("PNL_CALC", "🔴 CRITICAL", t.symbol, t.id, "net_pnl formula",
                              f"pnl={float(t.pnl):.2f} - comm={float(t.commission):.2f} = {expected_net:.2f}, but net_pnl={actual_net:.2f}",
                              f"{expected_net:.2f}", f"{actual_net:.2f}")
        
        # --- 1.11 Операции в trade.operations не соответствуют полям ---
        print("--- 1.11 Operations vs trade fields ---")
        for t in all_trades:
            ops = t.operations
            if not ops or not isinstance(ops, list):
                continue
            
            entries_ops = [o for o in ops if o.get("type") == "entry"]
            exits_ops = [o for o in ops if o.get("type") == "exit"]
            
            # Entry price из операций
            if entries_ops:
                total_val = sum(float(o.get("price", 0)) * int(o.get("qty", 0)) for o in entries_ops)
                total_qty = sum(int(o.get("qty", 0)) for o in entries_ops)
                if total_qty > 0:
                    ops_entry_price = total_val / total_qty
                    db_entry_price = float(t.entry_price) if t.entry_price else 0
                    if db_entry_price > 0:
                        pct = abs(ops_entry_price - db_entry_price) / db_entry_price * 100
                        if pct > 1:
                            add_error("OPS_MISMATCH", "🟠 WARN", t.symbol, t.id, "ops entry_price",
                                      f"ops_avg={ops_entry_price:.4f} vs db={db_entry_price:.4f} ({pct:.1f}%)",
                                      f"{ops_entry_price:.4f}", f"{db_entry_price:.4f}")
                    
                    # Quantity из операций
                    db_qty = float(t.quantity) if t.quantity else 0
                    if db_qty > 0 and total_qty != int(db_qty):
                        # Для partial close операции могут содержать больше чем quantity
                        if total_qty > db_qty * 1.5 or total_qty < db_qty * 0.5:
                            add_error("OPS_MISMATCH", "🟠 WARN", t.symbol, t.id, "ops quantity",
                                      f"ops_entry_qty={total_qty} vs db_qty={int(db_qty)}",
                                      str(total_qty), str(int(db_qty)))
            
            # Exit price из операций
            if exits_ops and t.exit_price:
                total_exit_val = sum(float(o.get("price", 0)) * int(o.get("qty", 0)) for o in exits_ops if o.get("note") != "partial_close")
                total_exit_qty = sum(int(o.get("qty", 0)) for o in exits_ops if o.get("note") != "partial_close")
                if total_exit_qty > 0:
                    ops_exit_price = total_exit_val / total_exit_qty
                    db_exit_price = float(t.exit_price)
                    if db_exit_price > 0:
                        pct = abs(ops_exit_price - db_exit_price) / db_exit_price * 100
                        if pct > 1:
                            add_error("OPS_MISMATCH", "🟠 WARN", t.symbol, t.id, "ops exit_price",
                                      f"ops_avg={ops_exit_price:.4f} vs db={db_exit_price:.4f} ({pct:.1f}%)",
                                      f"{ops_exit_price:.4f}", f"{db_exit_price:.4f}")
        
        # ==============================================================
        # ЧАСТЬ 2: НЕЗАВИСИМАЯ ПЕРЕГРУППИРОВКА API ОПЕРАЦИЙ
        # ==============================================================
        print("\n" + "=" * 100)
        print("ЧАСТЬ 2: НЕЗАВИСИМАЯ ПЕРЕГРУППИРОВКА API ОПЕРАЦИЙ")
        print("=" * 100)
        
        service = TinkoffService(conn.api_token)
        from_date = conn.sync_from_date or datetime(2024, 1, 1)
        to_date = datetime.utcnow()
        
        print(f"Загружаем операции из API {from_date.date()} — {to_date.date()}...")
        operations = service.get_operations(conn.broker_account_id, from_date, to_date)
        
        buy_types = ["OPERATION_TYPE_BUY", "OPERATION_TYPE_BUY_CARD"]
        sell_types = ["OPERATION_TYPE_SELL", "OPERATION_TYPE_SELL_CARD"]
        comm_types = ["OPERATION_TYPE_BROKER_FEE", "OPERATION_TYPE_MARGIN_FEE", 
                       "OPERATION_TYPE_SERVICE_FEE", "OPERATION_TYPE_SUCCESS_FEE",
                       "OPERATION_TYPE_TRACK_MFEE", "OPERATION_TYPE_TRACK_PFEE"]
        
        trade_ops = [op for op in operations if op.get("operationType") in buy_types + sell_types]
        all_comm_ops = [op for op in operations if op.get("operationType") in comm_types]
        
        print(f"Всего операций: {len(operations)}")
        print(f"BUY/SELL: {len(trade_ops)}")
        print(f"Commission ops: {len(all_comm_ops)}")
        
        # --- 2.1 Независимая группировка по FIGI ---
        by_figi = defaultdict(list)
        for op in trade_ops:
            figi = op.get("figi", "")
            if figi:
                by_figi[figi].append(op)
        
        print(f"Инструментов: {len(by_figi)}")
        
        # Группируем в позиции самостоятельно (FIFO)
        independent_positions = []
        
        for figi, ops in by_figi.items():
            ops_sorted = sorted(ops, key=lambda x: x.get("date", ""))
            instrument = service.get_instrument_info(figi)
            ticker = instrument.get("ticker", figi) if instrument else figi
            inst_type = instrument.get("instrument_type", "") if instrument else ""
            lot_size = int(instrument.get("lot", 1)) if instrument else 1
            
            # FIFO: строим позиции
            current_qty = 0  # >0 = long, <0 = short
            current_pos = None
            
            for op in ops_sorted:
                op_type = op.get("operationType", "")
                is_buy = op_type in buy_types
                qty = get_executed_qty(op)
                if qty <= 0:
                    continue
                
                price = money_to_decimal(op.get("price", {}))
                payment = money_to_decimal(op.get("payment", {}))
                date = parse_api_date(op.get("date"))
                op_id = op.get("id", "")
                
                # Комиссии из childOperations
                child_comm = Decimal(0)
                for child in op.get("childOperations", []):
                    cp = child.get("payment")
                    if cp:
                        cv = money_to_decimal(cp)
                        if cv != 0:
                            child_comm += abs(cv)
                
                qty_change = qty if is_buy else -qty
                new_qty = current_qty + qty_change
                
                # Определяем entry vs exit
                if current_pos is None or current_qty == 0:
                    # Открытие новой позиции
                    current_pos = {
                        "figi": figi,
                        "ticker": ticker,
                        "type": inst_type,
                        "lot_size": lot_size,
                        "direction": "LONG" if is_buy else "SHORT",
                        "entries": [],
                        "exits": [],
                        "commission": Decimal(0),
                    }
                    current_pos["entries"].append({"price": price, "qty": qty, "date": date, "payment": payment, "id": op_id})
                    current_pos["commission"] += child_comm
                    current_qty = qty_change
                    continue
                
                # Flip detection
                is_flip = (current_qty > 0 and new_qty < 0) or (current_qty < 0 and new_qty > 0)
                
                if is_flip:
                    # Close current position fully
                    close_qty = abs(current_qty)
                    current_pos["exits"].append({"price": price, "qty": close_qty, "date": date, "payment": payment * Decimal(close_qty) / Decimal(qty) if qty else Decimal(0), "id": op_id})
                    current_pos["commission"] += child_comm * Decimal(close_qty) / Decimal(qty) if qty else Decimal(0)
                    independent_positions.append(current_pos)
                    
                    # Open new position with remainder
                    open_qty = abs(new_qty)
                    current_pos = {
                        "figi": figi,
                        "ticker": ticker,
                        "type": inst_type,
                        "lot_size": lot_size,
                        "direction": "LONG" if new_qty > 0 else "SHORT",
                        "entries": [],
                        "exits": [],
                        "commission": child_comm * Decimal(open_qty) / Decimal(qty) if qty else Decimal(0),
                    }
                    current_pos["entries"].append({"price": price, "qty": open_qty, "date": date, "payment": payment * Decimal(open_qty) / Decimal(qty) if qty else Decimal(0), "id": op_id})
                    current_qty = new_qty
                    continue
                
                # Same direction = add to position / opposite direction = exit
                is_same_dir = (is_buy and current_qty > 0) or (not is_buy and current_qty < 0)
                
                if is_same_dir:
                    # Добавляем к позиции
                    current_pos["entries"].append({"price": price, "qty": qty, "date": date, "payment": payment, "id": op_id})
                    current_pos["commission"] += child_comm
                else:
                    # Закрываем (частично или полностью)
                    current_pos["exits"].append({"price": price, "qty": qty, "date": date, "payment": payment, "id": op_id})
                    current_pos["commission"] += child_comm
                
                current_qty = new_qty
                
                # Если позиция полностью закрыта
                if current_qty == 0:
                    independent_positions.append(current_pos)
                    current_pos = None
            
            # Оставшаяся открытая позиция
            if current_pos and current_qty != 0:
                independent_positions.append(current_pos)
        
        print(f"\nНезависимая группировка: {len(independent_positions)} позиций")
        
        # --- 2.2 Расчёт данных для каждой позиции ---
        api_positions = []
        for pos in independent_positions:
            entries = pos["entries"]
            exits = pos["exits"]
            
            total_entry_qty = sum(e["qty"] for e in entries)
            total_entry_value = sum(e["price"] * e["qty"] for e in entries)
            entry_price = total_entry_value / total_entry_qty if total_entry_qty else Decimal(0)
            
            exit_price = None
            total_exit_qty = 0
            if exits:
                total_exit_qty = sum(e["qty"] for e in exits)
                total_exit_value = sum(e["price"] * e["qty"] for e in exits)
                exit_price = total_exit_value / total_exit_qty if total_exit_qty else None
            
            entry_dates = [e["date"] for e in entries if e["date"]]
            exit_dates = [e["date"] for e in exits if e["date"]]
            entry_at = min(entry_dates) if entry_dates else None
            exit_at = max(exit_dates) if exit_dates else None
            
            is_closed = total_exit_qty >= total_entry_qty
            
            # PnL — независимый расчёт
            pnl = None
            if exits:
                instrument = service.get_instrument_info(pos["figi"])
                is_futures = pos["type"] == "INSTRUMENT_TYPE_FUTURES"
                
                if is_futures and instrument:
                    min_inc = money_to_decimal(instrument.get("min_price_increment", {}))
                    min_inc_amt = money_to_decimal(instrument.get("min_price_increment_amount", {}))
                    if min_inc and min_inc > 0 and min_inc_amt and min_inc_amt > 0:
                        point_value = min_inc_amt / min_inc
                        price_diff = exit_price - entry_price
                        if pos["direction"] == "SHORT":
                            price_diff = -price_diff
                        pnl = price_diff * total_exit_qty * point_value
                    else:
                        entry_pay = sum(e.get("payment", Decimal(0)) for e in entries)
                        exit_pay = sum(e.get("payment", Decimal(0)) for e in exits)
                        pnl = entry_pay + exit_pay
                else:
                    entry_pay = sum(e.get("payment", Decimal(0)) for e in entries)
                    exit_pay = sum(e.get("payment", Decimal(0)) for e in exits)
                    pnl = entry_pay + exit_pay
            
            commission = pos["commission"]
            net_pnl = pnl - commission if pnl is not None else None
            
            api_positions.append({
                "ticker": pos["ticker"],
                "figi": pos["figi"],
                "direction": pos["direction"],
                "type": pos["type"],
                "entry_price": entry_price,
                "exit_price": exit_price,
                "quantity": total_entry_qty,
                "exit_qty": total_exit_qty,
                "entry_at": entry_at,
                "exit_at": exit_at,
                "commission": commission,
                "pnl": pnl,
                "net_pnl": net_pnl,
                "is_closed": is_closed,
                "n_entries": len(entries),
                "n_exits": len(exits),
                "entries": entries,
                "exits": exits,
            })
        
        # ==============================================================
        # ЧАСТЬ 3: ПОЛНАЯ СВЕРКА НЕЗАВИСИМЫХ ПОЗИЦИЙ С БД
        # ==============================================================
        print("\n" + "=" * 100)
        print("ЧАСТЬ 3: ПОЛНАЯ СВЕРКА API ПОЗИЦИЙ С БД")
        print("=" * 100)
        
        db_matched = set()
        api_matched = set()
        
        for idx, api_pos in enumerate(api_positions):
            ticker = api_pos["ticker"]
            direction = api_pos["direction"]
            api_entry_at = api_pos["entry_at"]
            db_direction = "long" if direction == "LONG" else "short"
            
            if not api_entry_at:
                add_error("API_MATCH", "🔴 CRITICAL", ticker, "-", "no entry_at",
                          "API позиция без даты входа", "", "")
                continue
            
            # Ищем ВСЕ матчи в БД (не только лучший!)
            matches = []
            for t in all_trades:
                if t.id in db_matched:
                    continue
                if t.symbol != ticker or t.direction.value != db_direction:
                    continue
                delta = abs((t.entry_at - api_entry_at).total_seconds())
                if delta < 1800:  # 30 min
                    matches.append((delta, t))
            
            if not matches:
                add_error("API_MATCH", "🔴 MISSING", ticker, "-", "НЕТ В БД",
                          f"API: {direction} entry={api_entry_at}, qty={api_pos['quantity']}, pnl={api_pos['pnl']}",
                          str(api_entry_at)[:19], "—")
                continue
            
            # Если несколько матчей — это тоже проблема
            if len(matches) > 1:
                ids = [str(m[1].id) for m in matches]
                add_error("DUPLICATE", "🔴 CRITICAL", ticker, ",".join(ids), "MULTIPLE DB MATCHES",
                          f"API pos → {len(matches)} DB trades: ids={','.join(ids)}", 
                          f"1 expected", f"{len(matches)} found")
            
            # Берём лучший матч
            matches.sort(key=lambda x: x[0])
            best_match = matches[0][1]
            db_matched.add(best_match.id)
            api_matched.add(idx)
            t = best_match
            
            # --- Сверяем поля ---
            
            # entry_price
            if api_pos["entry_price"] and t.entry_price:
                a, b = float(api_pos["entry_price"]), float(t.entry_price)
                if a > 0:
                    pct = abs(a - b) / a * 100
                    if pct > 0.1:
                        sev = "🟢 MINOR" if pct < 1 else ("🟡 WARN" if pct < 5 else "🔴 CRITICAL")
                        add_error("DATA_MISMATCH", sev, ticker, t.id, "entry_price",
                                  f"API={a:.6f} DB={b:.6f} Δ={pct:.2f}%", f"{a:.6f}", f"{b:.6f}")
            
            # exit_price
            if api_pos["exit_price"] is not None and t.exit_price is not None:
                a, b = float(api_pos["exit_price"]), float(t.exit_price)
                if a > 0:
                    pct = abs(a - b) / a * 100
                    if pct > 0.1:
                        sev = "🟢 MINOR" if pct < 1 else ("🟡 WARN" if pct < 5 else "🔴 CRITICAL")
                        add_error("DATA_MISMATCH", sev, ticker, t.id, "exit_price",
                                  f"API={a:.6f} DB={b:.6f} Δ={pct:.2f}%", f"{a:.6f}", f"{b:.6f}")
            elif (api_pos["exit_price"] is None) != (t.exit_price is None):
                add_error("DATA_MISMATCH", "🔴 CRITICAL", ticker, t.id, "exit_price NULL",
                          f"API={'None' if api_pos['exit_price'] is None else 'has value'} vs DB={'None' if t.exit_price is None else 'has value'}",
                          str(api_pos["exit_price"])[:15], str(t.exit_price)[:15])
            
            # quantity
            a_qty = api_pos["quantity"]
            b_qty = float(t.quantity) if t.quantity else 0
            if a_qty > 0 and b_qty > 0:
                pct = abs(a_qty - b_qty) / a_qty * 100
                if pct > 0.1:
                    sev = "🟡 WARN" if pct < 10 else "🔴 CRITICAL"
                    add_error("DATA_MISMATCH", sev, ticker, t.id, "quantity",
                              f"API={a_qty} DB={int(b_qty)} Δ={pct:.1f}%", str(a_qty), str(int(b_qty)))
            
            # entry_at
            if api_pos["entry_at"] and t.entry_at:
                delta = abs((api_pos["entry_at"] - t.entry_at).total_seconds())
                if delta > 5:
                    sev = "🟡 WARN" if delta < 60 else "🔴 CRITICAL"
                    add_error("DATA_MISMATCH", sev, ticker, t.id, "entry_at",
                              f"Δ={delta:.0f}s", str(api_pos["entry_at"])[:19], str(t.entry_at)[:19])
            
            # exit_at
            if api_pos["exit_at"] and t.exit_at:
                delta = abs((api_pos["exit_at"] - t.exit_at).total_seconds())
                if delta > 5:
                    sev = "🟡 WARN" if delta < 60 else "🔴 CRITICAL"
                    add_error("DATA_MISMATCH", sev, ticker, t.id, "exit_at",
                              f"Δ={delta:.0f}s", str(api_pos["exit_at"])[:19], str(t.exit_at)[:19])
            elif api_pos["exit_at"] and not t.exit_at:
                add_error("DATA_MISMATCH", "🔴 CRITICAL", ticker, t.id, "exit_at NULL",
                          "API has exit_at but DB doesn't", str(api_pos["exit_at"])[:19], "None")
            elif not api_pos["exit_at"] and t.exit_at:
                add_error("DATA_MISMATCH", "🟠 WARN", ticker, t.id, "exit_at extra",
                          "DB has exit_at but API doesn't", "None", str(t.exit_at)[:19])
            
            # commission
            a_comm = float(api_pos["commission"]) if api_pos["commission"] else 0
            b_comm = float(t.commission) if t.commission else 0
            if a_comm > 0:
                pct = abs(a_comm - b_comm) / a_comm * 100
                if pct > 1:
                    sev = "🟡 WARN" if pct < 20 else "🔴 CRITICAL"
                    add_error("DATA_MISMATCH", sev, ticker, t.id, "commission",
                              f"API={a_comm:.2f} DB={b_comm:.2f} Δ={pct:.1f}%", f"{a_comm:.2f}", f"{b_comm:.2f}")
            elif b_comm == 0 and t.exit_at:
                pass  # Already caught in 1.6
            
            # pnl
            a_pnl = float(api_pos["pnl"]) if api_pos["pnl"] is not None else None
            b_pnl = float(t.pnl) if t.pnl is not None else None
            if a_pnl is not None and b_pnl is not None:
                if abs(a_pnl) > 0.01:
                    pct = abs(a_pnl - b_pnl) / abs(a_pnl) * 100
                    if pct > 0.5:
                        sev = "🟢 MINOR" if pct < 2 else ("🟡 WARN" if pct < 10 else "🔴 CRITICAL")
                        add_error("DATA_MISMATCH", sev, ticker, t.id, "pnl",
                                  f"API={a_pnl:.2f} DB={b_pnl:.2f} Δ={pct:.1f}%", f"{a_pnl:.2f}", f"{b_pnl:.2f}")
                elif abs(b_pnl) > 1:
                    add_error("DATA_MISMATCH", "🟡 WARN", ticker, t.id, "pnl",
                              f"API≈0 but DB={b_pnl:.2f}", f"{a_pnl:.2f}", f"{b_pnl:.2f}")
            elif (a_pnl is None) != (b_pnl is None):
                if t.exit_at:  # Only flag if trade should be closed
                    add_error("DATA_MISMATCH", "🔴 CRITICAL", ticker, t.id, "pnl NULL mismatch",
                              f"API={'None' if a_pnl is None else f'{a_pnl:.2f}'} DB={'None' if b_pnl is None else f'{b_pnl:.2f}'}",
                              str(a_pnl), str(b_pnl))
            
            # net_pnl
            a_net = float(api_pos["net_pnl"]) if api_pos["net_pnl"] is not None else None
            b_net = float(t.net_pnl) if t.net_pnl is not None else None
            if a_net is not None and b_net is not None:
                if abs(a_net) > 0.01:
                    pct = abs(a_net - b_net) / abs(a_net) * 100
                    if pct > 1:
                        sev = "🟡 WARN" if pct < 10 else "🔴 CRITICAL"
                        add_error("DATA_MISMATCH", sev, ticker, t.id, "net_pnl",
                                  f"API={a_net:.2f} DB={b_net:.2f} Δ={pct:.1f}%", f"{a_net:.2f}", f"{b_net:.2f}")
            elif a_net is not None and b_net is None and t.exit_at:
                add_error("DATA_MISMATCH", "🔴 CRITICAL", ticker, t.id, "net_pnl is None",
                          f"API={a_net:.2f} but DB=None", f"{a_net:.2f}", "None")
        
        # --- Orphan DB trades ---
        for t in all_trades:
            if t.id not in db_matched:
                tags = t.tags or []
                is_autosync = "#tinkoff" in tags or "#autosync" in tags
                label = "ORPHAN (autosync)" if is_autosync else "ORPHAN (manual/excel)"
                sev = "🔴 CRITICAL" if is_autosync else "🟡 INFO"
                add_error("ORPHAN", sev, t.symbol, t.id, label,
                          f"entry={str(t.entry_at)[:19]} qty={t.quantity} pnl={t.pnl}",
                          "НЕТ В API", f"id={t.id}")
        
        # ==============================================================
        # ЧАСТЬ 4: ОПЕРАЦИОННЫЙ АУДИТ (каждая операция → ровно 1 трейд)
        # ==============================================================
        print("\n" + "=" * 100)
        print("ЧАСТЬ 4: ОПЕРАЦИОННЫЙ АУДИТ")
        print("=" * 100)
        
        # Собираем все operation IDs из DB trades
        db_op_ids = set()
        for t in all_trades:
            if t.operations:
                for op in t.operations:
                    oid = op.get("id")
                    if oid:
                        db_op_ids.add(oid)
        
        # API operations
        api_op_ids = set()
        for op in trade_ops:
            oid = op.get("id")
            if oid:
                api_op_ids.add(oid)
        
        missing_in_db = api_op_ids - db_op_ids
        extra_in_db = db_op_ids - api_op_ids
        
        print(f"API операций (BUY/SELL): {len(api_op_ids)}")
        print(f"Операций в DB trades: {len(db_op_ids)}")
        print(f"Есть в API, нет в DB: {len(missing_in_db)}")
        print(f"Есть в DB, нет в API: {len(extra_in_db)}")
        
        # Операции в DB, которых нет в API — возможно, были удалены или это фантомы
        # Не логируем их как ошибки, т.к. DB хранит op id из tinkoff, а не все trades хранят id
        
        # ==============================================================
        # ИТОГОВЫЙ ОТЧЁТ
        # ==============================================================
        print("\n" + "=" * 100)
        print("ИТОГОВЫЙ ОТЧЁТ")
        print("=" * 100)
        
        # Таблица
        print(f"\n{'#':>4} | {'Кат':<16} | {'Sev':<14} | {'Тикер':<8} | {'ID':<8} | {'Поле':<22} | Детали")
        print("-" * 140)
        
        for e in all_errors:
            print(f"{e['id']:>4} | {e['cat']:<16} | {e['sev']:<14} | {e['ticker']:<8} | {str(e['trade_id']):<8} | {e['field']:<22} | {e['detail'][:70]}")
        
        print("-" * 140)
        
        # Статистика
        print(f"\nВСЕГО ОШИБОК: {len(all_errors)}")
        
        print("\nПо категории:")
        by_cat = Counter(e["cat"] for e in all_errors)
        for cat, cnt in by_cat.most_common():
            print(f"  {cat:<20} {cnt}")
        
        print("\nПо критичности:")
        by_sev = Counter(e["sev"] for e in all_errors)
        for sev, cnt in by_sev.most_common():
            print(f"  {sev:<20} {cnt}")
        
        print("\nПо полю:")
        by_field = Counter(e["field"] for e in all_errors)
        for field, cnt in by_field.most_common(20):
            print(f"  {field:<25} {cnt}")
        
        print("\nПо тикеру (top-20):")
        by_ticker = Counter(e["ticker"] for e in all_errors)
        for ticker, cnt in by_ticker.most_common(20):
            print(f"  {ticker:<10} {cnt}")
        
        # Только non-orphan errors
        data_errors = [e for e in all_errors if e["cat"] != "ORPHAN"]
        print(f"\n🔥 ОШИБОК В ДАННЫХ (без orphan): {len(data_errors)}")
        
        orphan_autosync = [e for e in all_errors if "autosync" in e.get("field", "")]
        orphan_manual = [e for e in all_errors if "manual" in e.get("field", "") or "excel" in e.get("field", "")]
        print(f"   Orphan autosync (дубли от синка): {len(orphan_autosync)}")
        print(f"   Orphan manual/excel:              {len(orphan_manual)}")
        
    finally:
        db.close()


if __name__ == "__main__":
    run_deep_audit()
