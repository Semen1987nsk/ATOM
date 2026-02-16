"""CCH6 (Какао) — детальный разбор: API сырые операции → FIFO позиции → сравнение с БД"""
import os, json
from decimal import Decimal
from datetime import datetime
from collections import defaultdict
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Trade, TradeDirection, BrokerConnection

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./atom.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)

from tinkoff_service import TinkoffService


def money(obj):
    if not obj or not isinstance(obj, dict):
        return 0.0
    return int(obj.get("units", 0) or 0) + int(obj.get("nano", 0) or 0) / 1e9


def get_qty(op):
    qd = op.get("quantityDone")
    if qd is not None:
        try:
            v = int(qd)
            if v > 0:
                return v
        except:
            pass
    trades_list = op.get("trades", [])
    if trades_list:
        try:
            v = sum(int(t.get("quantity", 0)) for t in trades_list)
            if v > 0:
                return v
        except:
            pass
    return max(int(op.get("quantity", 0)), 0)


def main():
    db = SessionLocal()
    
    conn = db.query(BrokerConnection).filter(BrokerConnection.is_active == True).first()
    if not conn:
        print("No active broker connection!")
        return
    
    service = TinkoffService(conn.api_token)
    
    from_date = conn.sync_from_date or datetime(2024, 1, 1)
    to_date = datetime.utcnow()
    
    print("=" * 90)
    print(f"Загрузка операций: {from_date.date()} — {to_date.date()}")
    print("=" * 90)
    
    operations = service.get_operations(conn.broker_account_id, from_date, to_date)
    print(f"Всего операций: {len(operations)}")
    
    buy_types = ["OPERATION_TYPE_BUY", "OPERATION_TYPE_BUY_CARD"]
    sell_types = ["OPERATION_TYPE_SELL", "OPERATION_TYPE_SELL_CARD"]
    
    # Find CCH6 figi
    cch6_figi = None
    for op in operations:
        figi = op.get("figi", "")
        if not figi:
            continue
        instrument = service.get_instrument_info(figi)
        if instrument and instrument.get("ticker") == "CCH6":
            cch6_figi = figi
            print(f"\n✅ CCH6 figi={figi}")
            print(f"   name={instrument.get('name')}")
            print(f"   type={instrument.get('instrument_type')}")
            print(f"   lot={instrument.get('lot')}")
            break
    
    if not cch6_figi:
        # Show all futures
        seen = set()
        print("\nВсе фьючерсы:")
        for op in operations:
            figi = op.get("figi", "")
            if figi and figi not in seen:
                seen.add(figi)
                inst = service.get_instrument_info(figi)
                if inst and inst.get("instrument_type") in ("futures", "future"):
                    print(f"  {inst.get('ticker'):12s} figi={figi}")
        return
    
    # Filter CCH6 ops
    cch6_ops = [o for o in operations if o.get("figi") == cch6_figi]
    trade_ops = sorted(
        [o for o in cch6_ops if o.get("operationType") in buy_types + sell_types],
        key=lambda x: x.get("date", "")
    )
    
    print(f"\nВсего операций CCH6: {len(cch6_ops)}")
    print(f"BUY/SELL: {len(trade_ops)}")
    
    # ==================== RAW OPS ====================
    print("\n" + "=" * 90)
    print("СЫРЫЕ BUY/SELL ОПЕРАЦИИ CCH6")
    print("=" * 90)
    
    tb, ts, tp_b, tp_s, tc = 0, 0, 0.0, 0.0, 0.0
    
    for op in trade_ops:
        otype = op.get("operationType", "")
        date = op.get("date", "")[:23]
        qty = get_qty(op)
        price = money(op.get("price"))
        payment = money(op.get("payment"))
        op_id = op.get("id", "")[:12]
        
        children = op.get("childOperations", [])
        comm = sum(abs(money(ch.get("payment"))) for ch in children
                   if ch.get("operationType") == "OPERATION_TYPE_BROKER_FEE")
        
        side = "BUY " if otype in buy_types else "SELL"
        print(f"  {date}  {side}  qty={qty:>4}  price={price:>10.2f}  payment={payment:>12.2f}  comm={comm:>8.2f}  id={op_id}")
        
        if otype in buy_types:
            tb += qty; tp_b += payment
        else:
            ts += qty; tp_s += payment
        tc += comm
    
    net = tp_b + tp_s
    print(f"\n--- Итого API ---")
    print(f"  BUY:  {tb} шт, payment={tp_b:>12.2f}")
    print(f"  SELL: {ts} шт, payment={tp_s:>12.2f}")
    print(f"  PnL (net payment): {net:.2f}")
    print(f"  Commission: {tc:.2f}")
    print(f"  Net PnL: {net - tc:.2f}")
    print(f"  Open balance: {tb - ts}")
    
    # ==================== FIFO GROUPING ====================
    print("\n" + "=" * 90)
    print("FIFO-ГРУППИРОВКА CCH6")
    print("=" * 90)
    
    positions = []
    cur_qty = 0
    cur_pos = None
    
    for op in trade_ops:
        otype = op.get("operationType", "")
        is_buy = otype in buy_types
        qty = get_qty(op)
        price = money(op.get("price"))
        payment = money(op.get("payment"))
        date = op.get("date", "")
        
        children = op.get("childOperations", [])
        comm = sum(abs(money(ch.get("payment"))) for ch in children
                   if ch.get("operationType") == "OPERATION_TYPE_BROKER_FEE")
        
        signed = qty if is_buy else -qty
        
        if cur_pos is None:
            direction = "LONG" if is_buy else "SHORT"
            cur_pos = {"direction": direction, "entries": [], "exits": [], "comm": 0}
            cur_qty = 0
        
        same_dir = (cur_qty >= 0 and is_buy) or (cur_qty <= 0 and not is_buy)
        
        if cur_qty == 0 or same_dir:
            cur_pos["entries"].append({"date": date, "qty": qty, "price": price, "payment": payment})
            cur_pos["comm"] += comm
            cur_qty += signed
        else:
            cur_pos["exits"].append({"date": date, "qty": qty, "price": price, "payment": payment})
            cur_pos["comm"] += comm
            new_qty = cur_qty + signed
            
            if abs(new_qty) < 0.001:
                positions.append(cur_pos)
                cur_pos = None
                cur_qty = 0
            elif (new_qty > 0) != (cur_qty > 0):
                positions.append(cur_pos)
                direction = "LONG" if new_qty > 0 else "SHORT"
                cur_pos = {"direction": direction, "entries": [{"date": date, "qty": abs(new_qty), "price": price, "payment": 0}], "exits": [], "comm": 0}
                cur_qty = new_qty
            else:
                cur_qty = new_qty
    
    if cur_pos:
        positions.append(cur_pos)
    
    print(f"\nПозиций: {len(positions)}\n")
    
    api_total_pnl = 0
    api_total_comm = 0
    
    for i, pos in enumerate(positions):
        eq = sum(e["qty"] for e in pos["entries"])
        xq = sum(e["qty"] for e in pos["exits"])
        ep = sum(e["payment"] for e in pos["entries"])
        xp = sum(e["payment"] for e in pos["exits"])
        pnl = ep + xp
        comm = pos["comm"]
        net = pnl - comm
        is_open = xq < eq
        
        we = sum(e["price"] * e["qty"] for e in pos["entries"]) / eq if eq > 0 else 0
        wx = sum(e["price"] * e["qty"] for e in pos["exits"]) / xq if xq > 0 else 0
        
        es = pos["entries"][0]["date"][:19]
        xs = pos["exits"][0]["date"][:19] if pos["exits"] else "N/A"
        xe = pos["exits"][-1]["date"][:19] if len(pos["exits"]) > 1 else xs
        
        flag = "🔓 OPEN" if is_open else "🔒 CLOSED"
        print(f"  #{i+1} {pos['direction']:5s} {flag}  qty={eq}  entries={len(pos['entries'])} exits={len(pos['exits'])}")
        print(f"    Entry: {es}  Avg price: {we:.2f}")
        print(f"    Exit:  {xs} {'→ ' + xe if xe != xs else ''}  Avg price: {wx:.2f}")
        print(f"    PnL={pnl:.2f}  Comm={comm:.2f}  Net={net:.2f}")
        print()
        
        api_total_pnl += pnl
        api_total_comm += comm
    
    print(f"  ИТОГО API: PnL={api_total_pnl:.2f}  Comm={api_total_comm:.2f}  Net={api_total_pnl - api_total_comm:.2f}")
    
    # ==================== DB ====================
    print("\n" + "=" * 90)
    print("ТРЕЙДЫ CCH6 В БД")
    print("=" * 90)
    
    db_trades = db.query(Trade).filter(
        Trade.account_id == conn.account_id,
        Trade.symbol == "CCH6"
    ).order_by(Trade.entry_at).all()
    
    print(f"\nТрейдов: {len(db_trades)}\n")
    
    db_total_pnl = 0
    db_total_comm = 0
    db_total_net = 0
    
    for t in db_trades:
        ops = t.operations or []
        if isinstance(ops, str):
            ops = json.loads(ops)
        is_open = t.exit_at is None
        pv = float(t.pnl) if t.pnl is not None else 0
        nv = float(t.net_pnl) if t.net_pnl is not None else 0
        cv = float(t.commission) if t.commission is not None else 0
        
        probs = []
        if t.exit_at and t.entry_at and t.exit_at < t.entry_at:
            probs.append("⚠️ EXIT<ENTRY!")
        if t.pnl is not None and t.net_pnl is None:
            probs.append("⚠️ net_pnl=None!")
        if t.exit_at and cv == 0:
            probs.append("⚠️ comm=0!")
        
        flag = "🔓 OPEN" if is_open else "🔒 CLOSED"
        d = "LONG" if t.direction == TradeDirection.LONG else "SHORT"
        print(f"  id={t.id:>4} {d:5s} {flag}  qty={float(t.quantity):>8.0f}  ops={len(ops):>2}")
        print(f"    Entry: {str(t.entry_at)[:19]}  Price: {float(t.entry_price):.2f}")
        ex_str = str(t.exit_at)[:19] if t.exit_at else "N/A"
        ex_p = float(t.exit_price) if t.exit_price else 0
        print(f"    Exit:  {ex_str:19s}  Price: {ex_p:.2f}")
        print(f"    PnL={pv:>12.2f}  Comm={cv:>8.2f}  Net={nv:>12.2f}")
        if probs:
            print(f"    {'  '.join(probs)}")
        print()
        
        db_total_pnl += pv
        db_total_comm += cv
        db_total_net += nv
    
    print(f"  ИТОГО DB: PnL={db_total_pnl:.2f}  Comm={db_total_comm:.2f}  Net={db_total_net:.2f}")
    
    # ==================== COMPARISON ====================
    print("\n" + "=" * 90)
    print("СРАВНЕНИЕ API vs DB")
    print("=" * 90)
    
    def cmp(label, a, d):
        delta = d - a
        pct = abs(delta / a * 100) if a != 0 else 0
        f = " ⚠️" if pct > 5 else ""
        print(f"  {label:25s} {a:>15.2f} {d:>15.2f} {delta:>+15.2f} {pct:>8.1f}%{f}")
    
    print(f"\n  {'':25s} {'API':>15s} {'DB':>15s} {'Δ':>15s} {'%':>8s}")
    print(f"  {'─'*80}")
    cmp("Позиций / Трейдов", len(positions), len(db_trades))
    cmp("PnL", api_total_pnl, db_total_pnl)
    cmp("Commission", api_total_comm, db_total_comm)
    cmp("Net PnL", api_total_pnl - api_total_comm, db_total_net)
    
    db.close()


if __name__ == "__main__":
    main()
