"""
seed_demo_trades.py — заполняет Demo User случайными сделками для тестирования UI.

Запуск: DEBUG=true python scripts/seed_demo_trades.py
"""
import os
import sys
import random
from datetime import datetime, timedelta
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import SessionLocal
import models

random.seed(42)  # детерминированно для воспроизводимости

SYMBOLS = ["SBER", "GAZP", "LKOH", "YNDX", "ROSN", "MGNT", "VTBR", "TATN"]
SETUPS = ["Пробой", "Откат к уровню", "Разворот", "Импульс", "Контр-тренд"]
TAGS_POOL = ["FOMO", "По плану", "Догон", "Без стопа", "Утренний гэп", "Вечерняя распродажа"]
DIRECTIONS = ["LONG", "SHORT"]


def make_trade(account_id: int, idx: int, base_date: datetime) -> models.Trade:
    symbol = random.choice(SYMBOLS)
    direction = random.choice(DIRECTIONS)
    entry_at = base_date + timedelta(days=idx, hours=random.randint(10, 19))
    hold_minutes = random.choice([15, 30, 60, 240, 1440, 4320])
    exit_at = entry_at + timedelta(minutes=hold_minutes)

    entry_price = round(random.uniform(50, 5000), 2)
    qty = random.randint(1, 100)
    risk_amount = round(entry_price * qty * 0.02, 2)  # 2% риск

    # 55% побед, 45% убытков (реалистичное распределение)
    is_win = random.random() < 0.55
    if is_win:
        pnl = round(random.uniform(0.5, 3.5) * risk_amount, 2)  # 0.5-3.5 R win
    else:
        pnl = round(-random.uniform(0.3, 1.2) * risk_amount, 2)  # 0.3-1.2 R loss

    if direction == "LONG":
        exit_price = round(entry_price * (1 + (pnl / (entry_price * qty))), 2)
        sl = round(entry_price * 0.98, 2)
        tp = round(entry_price * 1.04, 2)
    else:
        exit_price = round(entry_price * (1 - (pnl / (entry_price * qty))), 2)
        sl = round(entry_price * 1.02, 2)
        tp = round(entry_price * 0.96, 2)

    commission = round(abs(pnl) * 0.05 + 5, 2)
    net_pnl = pnl - commission

    return models.Trade(
        account_id=account_id,
        symbol=symbol,
        asset_type="Stock",
        direction=direction,
        entry_price=Decimal(str(entry_price)),
        exit_price=Decimal(str(exit_price)),
        quantity=Decimal(str(qty)),
        leverage=Decimal("1"),
        entry_at=entry_at,
        exit_at=exit_at,
        stop_loss=Decimal(str(sl)),
        take_profit=Decimal(str(tp)),
        risk_amount=Decimal(str(risk_amount)),
        pnl=Decimal(str(pnl)),
        net_pnl=Decimal(str(net_pnl)),
        commission=Decimal(str(commission)),
        setup_name=random.choice(SETUPS),
        timeframe=random.choice(["5m", "15m", "1H", "4H", "1D"]),
        currency="RUB",
        tags=random.sample(TAGS_POOL, k=random.randint(1, 3)),
        confidence=random.randint(2, 5),
        mood=random.randint(2, 5),
        discipline=random.randint(2, 5) if random.random() > 0.2 else 1,  # 20% нарушений
        holding_time_minutes=hold_minutes,
        r_multiple=Decimal(str(round(pnl / risk_amount, 4))) if risk_amount > 0 else None,
    )


def main():
    db = SessionLocal()
    user = db.query(models.User).filter(models.User.email == "demo@eqio.app").first()
    if not user:
        print("Demo user not found")
        return
    account = db.query(models.Account).filter(models.Account.user_id == user.id).first()
    if not account:
        # Создаём счёт
        account = models.Account(
            user_id=user.id,
            name="Демо-счёт",
            initial_balance=Decimal("100000"),
            currency="RUB",
        )
        db.add(account)
        db.commit()
        db.refresh(account)
    print(f"Using account id={account.id}")

    # Удаляем старые тестовые сделки (если уже сидил)
    deleted = db.query(models.Trade).filter(models.Trade.account_id == account.id).delete()
    print(f"Deleted {deleted} old trades")

    base = datetime(2026, 1, 1, 10, 0, 0)
    trades = [make_trade(account.id, i, base) for i in range(30)]
    db.add_all(trades)
    db.commit()
    print(f"Seeded {len(trades)} trades")

    total_pnl = sum(float(t.pnl) for t in trades)
    wins = sum(1 for t in trades if float(t.pnl) > 0)
    print(f"Total PnL: {total_pnl:.2f} ₽, Wins: {wins}/{len(trades)} ({wins/len(trades)*100:.1f}%)")
    db.close()


if __name__ == "__main__":
    main()
