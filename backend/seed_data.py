import sqlite3
from datetime import datetime, timedelta
import random
import json

def seed_db():
    conn = sqlite3.connect('/workspaces/ATOM/backend/atom.db')
    cursor = conn.cursor()

    # Очистим старые данные для чистого теста
    cursor.execute("DELETE FROM trades")
    
    symbols = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "AAPL", "TSLA", "NVDA"]
    directions = ["LONG", "SHORT"]
    setups = ["Breakout", "Mean Reversion", "Trend Following", "Scalp"]
    tags_pool = ["fomo", "trend", "news", "reversal", "tilt", "disciplined"]
    
    start_date = datetime.now() - timedelta(days=30)
    
    trades_to_add = []
    
    for i in range(15):
        symbol = random.choice(symbols)
        direction = random.choice(directions)
        entry_price = random.uniform(100, 50000)
        quantity = random.uniform(0.1, 10)
        
        # Генерируем результат
        is_win = random.random() > 0.4 # 60% win rate
        pnl_percent = random.uniform(0.01, 0.05) if is_win else random.uniform(-0.01, -0.03)
        
        exit_price = entry_price * (1 + pnl_percent) if direction == "LONG" else entry_price * (1 - pnl_percent)
        pnl = (exit_price - entry_price) * quantity if direction == "LONG" else (entry_price - exit_price) * quantity
        
        # MAE/MFE
        if direction == "LONG":
            mae_price = entry_price * (1 - random.uniform(0, 0.02))
            mfe_price = max(exit_price, entry_price * (1 + random.uniform(0, 0.06)))
        else:
            mae_price = entry_price * (1 + random.uniform(0, 0.02))
            mfe_price = min(exit_price, entry_price * (1 - random.uniform(0, 0.06)))
            
        entry_at = start_date + timedelta(days=i, hours=random.randint(0, 23))
        exit_at = entry_at + timedelta(hours=random.randint(1, 48))
        
        tags = random.sample(tags_pool, random.randint(1, 3))
        
        # Mock AI Analysis
        ai_analysis = {
            "verdict": "Good Trade" if is_win else "Poor Execution",
            "analysis": "The trade followed the plan." if is_win else "Entry was a bit late, leading to higher MAE.",
            "advice": "Keep following the trend." if is_win else "Wait for a clearer confirmation.",
            "score": random.randint(60, 95) if is_win else random.randint(30, 65)
        }

        trades_to_add.append((
            1, symbol, direction, entry_price, exit_price, quantity,
            entry_at.strftime("%Y-%m-%d %H:%M:%S"), exit_at.strftime("%Y-%m-%d %H:%M:%S"),
            entry_price * 0.95, entry_price * 1.1, 500, mae_price, mfe_price, pnl,
            random.choice(setups), json.dumps(tags), json.dumps(ai_analysis), "Automated seed trade"
        ))

    cursor.executemany("""
        INSERT INTO trades (
            account_id, symbol, direction, entry_price, exit_price, quantity,
            entry_at, exit_at, stop_loss, take_profit, risk_amount, mae_price, mfe_price, pnl,
            setup_name, tags, ai_analysis, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, trades_to_add)

    conn.commit()
    print(f"Successfully seeded {len(trades_to_add)} trades.")
    conn.close()

if __name__ == "__main__":
    seed_db()
