import pandas as pd
import io
from datetime import datetime
from typing import List, Dict, Optional
import models
import re

class Inventory:
    def __init__(self):
        self.positions = {} # {symbol: {'qty': float, 'avg_price': float}}

    def process_trade(self, symbol: str, direction: models.TradeDirection, qty: float, price: float) -> Optional[float]:
        if symbol not in self.positions:
            self.positions[symbol] = {'qty': 0.0, 'avg_price': 0.0}
        
        pos = self.positions[symbol]
        current_qty = pos['qty']
        pnl = None

        if direction == models.TradeDirection.LONG:
            # BUY
            if current_qty < 0:
                # Covering a Short position
                covered_qty = min(abs(current_qty), qty)
                
                # Short PnL = (Sell Price - Buy Price) * Qty
                # Entry (Sell) was avg_price. Exit (Buy) is price.
                pnl = (pos['avg_price'] - price) * covered_qty
                
                # Update position
                remaining_buy = qty - covered_qty
                pos['qty'] += covered_qty # Move towards 0 (e.g. -10 + 10 = 0)
                
                if remaining_buy > 0:
                    # Flipped to Long
                    pos['qty'] = remaining_buy
                    pos['avg_price'] = price
            else:
                # Adding to Long position
                total_cost = current_qty * pos['avg_price'] + qty * price
                new_qty = current_qty + qty
                pos['avg_price'] = total_cost / new_qty if new_qty != 0 else 0
                pos['qty'] = new_qty

        elif direction == models.TradeDirection.SHORT:
            # SELL
            if current_qty > 0:
                # Closing a Long position
                closed_qty = min(current_qty, qty)
                
                # Long PnL = (Sell Price - Buy Price) * Qty
                pnl = (price - pos['avg_price']) * closed_qty
                
                # Update position
                remaining_sell = qty - closed_qty
                pos['qty'] -= closed_qty
                
                if remaining_sell > 0:
                    # Flipped to Short
                    pos['qty'] = -remaining_sell
                    pos['avg_price'] = price
            else:
                # Adding to Short position (qty is negative or 0)
                current_abs_qty = abs(current_qty)
                total_val = current_abs_qty * pos['avg_price'] + qty * price
                new_abs_qty = current_abs_qty + qty
                pos['avg_price'] = total_val / new_abs_qty if new_abs_qty != 0 else 0
                pos['qty'] -= qty # Make it more negative

        return pnl

def parse_tinkoff_excel(contents: bytes) -> List[Dict]:
    # Read Excel, finding the header row
    df = pd.read_excel(io.BytesIO(contents), header=None)
    
    start_row = -1
    for i, row in df.iterrows():
        row_str = row.astype(str).str.cat(sep=' ')
        if "Номер сделки" in row_str and "Вид сделки" in row_str:
            start_row = i
            break
            
    if start_row == -1:
        raise ValueError("Could not find trade table in Excel file")
        
    # Reload with correct header
    df = pd.read_excel(io.BytesIO(contents), header=start_row)
    
    trades = []
    inventory = Inventory()
    
    # Iterate through rows
    for _, row in df.iterrows():
        try:
            # Extract fields using column names (which might contain newlines)
            cols = {c.replace('\n', ' ').strip(): c for c in df.columns}
            
            date_val = row[cols.get('Дата заключения', 'Дата заключения')]
            time_val = row[cols.get('Время', 'Время')]
            side_val = row[cols.get('Вид сделки', 'Вид сделки')]
            symbol_val = row[cols.get('Код актива', 'Код актива')]
            qty_val = row[cols.get('Количество', 'Количество')]
            deal_sum_val = row[cols.get('Сумма сделки', 'Сумма сделки')]
            
            # Try to get Asset Name
            asset_name = row.get(cols.get('Сокращенное наименование', 'Сокращенное наименование'), None)
            if pd.isna(asset_name):
                 asset_name = row.get(cols.get('Наименование', 'Наименование'), None)
            
            if pd.isna(date_val) or pd.isna(symbol_val):
                continue
                
            # Parse Date/Time
            if isinstance(date_val, str):
                date_str = date_val
            else:
                date_str = date_val.strftime("%d.%m.%Y")
                
            if isinstance(time_val, str):
                time_str = time_val
            else:
                time_str = time_val.strftime("%H:%M:%S")
                
            entry_at = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M:%S")
            
            # Parse Side
            side_str = str(side_val).lower()
            
            # Filter REPO/Swap
            if 'репо' in side_str or 'рпс' in side_str:
                continue
                
            if 'покупка' in side_str:
                direction = models.TradeDirection.LONG
            elif 'продажа' in side_str:
                direction = models.TradeDirection.SHORT
            else:
                continue
                
            symbol = str(symbol_val).strip()
            quantity = float(qty_val)
            
            # Infer Asset Type
            asset_type = "Stock" # Default
            if re.search(r'[A-Z]{2,4}[A-Z0-9]\d', symbol): # e.g. RIZ5, SiH5
                asset_type = "Futures"
            
            # Calculate Effective Price in RUB (Deal Sum / Quantity)
            # This handles Futures (points -> rub) and Bonds (clean price -> dirty price) correctly
            if pd.notna(deal_sum_val):
                deal_sum = float(deal_sum_val)
                if quantity != 0:
                    price = deal_sum / quantity
                else:
                    price = 0.0
            else:
                # Fallback to 'Цена за единицу' if Deal Sum is missing (unlikely for valid trades)
                price = float(row[cols.get('Цена за единицу', 'Цена за единицу')])

            # Calculate Total Commission
            comm_broker = row.get(cols.get('Комиссия брокера', 'Комиссия брокера'), 0)
            comm_exchange = row.get(cols.get('Комиссия биржи', 'Комиссия биржи'), 0)
            comm_clear = row.get(cols.get('Комиссия клир. центра', 'Комиссия клир. центра'), 0)
            
            def parse_comm(val):
                try: return abs(float(val)) if pd.notna(val) else 0.0
                except: return 0.0
                
            commission = parse_comm(comm_broker) + parse_comm(comm_exchange) + parse_comm(comm_clear)
            
            # PnL Logic
            pnl = inventory.process_trade(symbol, direction, quantity, price)
                
            trades.append({
                "symbol": symbol,
                "asset_name": str(asset_name) if asset_name else None,
                "asset_type": asset_type,
                "direction": direction,
                "entry_price": price,
                "quantity": quantity,
                "entry_at": entry_at,
                "pnl": pnl,
                "commission": commission,
                "notes": "Imported from Tinkoff Excel",
                "tags": ["Tinkoff", "Imported"]
            })
            
        except Exception as e:
            # Skip bad rows
            print(f"Error parsing row {row.name}: {e}")
            continue
            
    return trades

def parse_trade_file(contents: bytes, filename: str) -> List[Dict]:
    """
    Парсит файл (CSV/Excel) и возвращает список словарей для создания сделок.
    """
    if filename.endswith(('.xls', '.xlsx')):
        # Try Tinkoff Excel parser first if it looks like a report
        try:
            return parse_tinkoff_excel(contents)
        except:
            # Fallback to generic excel parser (implemented below via pandas)
            pass

    try:
        if filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents))
        elif filename.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(io.BytesIO(contents))
        else:
            raise ValueError("Unsupported file format")
    except Exception as e:
        raise ValueError(f"Failed to read file: {str(e)}")

    trades = []
    
    # Нормализация имен колонок для Generic парсера
    df.columns = [c.strip() for c in df.columns]
    lower_cols = {c.lower(): c for c in df.columns}


    # Маппинг колонок (можно расширять)
    col_map = {
        'date': ['date', 'time', 'created time', 'date(utc)'],
        'symbol': ['symbol', 'pair', 'instrument', 'contract'],
        'side': ['side', 'type', 'direction', 'operation'],
        'price': ['price', 'avg price', 'entry price', 'avg_price_usd'],
        'quantity': ['amount', 'quantity', 'executed', 'size', 'qty'],
        'pnl': ['pnl', 'realized pnl', 'profit', 'net profit'],
        'fee': ['fee', 'commission']
    }

    def get_col(key):
        for candidate in col_map[key]:
            if candidate in lower_cols:
                return lower_cols[candidate]
        return None

    # Проверяем обязательные поля
    required = ['date', 'symbol', 'side', 'price', 'quantity']
    missing = [key for key in required if get_col(key) is None]
    
    if missing:
        # Если не нашли стандартные, пробуем специфичные для Binance/Bybit
        # Но пока вернем ошибку или пустой список
        print(f"Missing columns: {missing}")
        # Fallback logic could go here
        pass

    date_col = get_col('date')
    symbol_col = get_col('symbol')
    side_col = get_col('side')
    price_col = get_col('price')
    qty_col = get_col('quantity')
    pnl_col = get_col('pnl')

    if not all([date_col, symbol_col, side_col, price_col, qty_col]):
         raise ValueError(f"Could not detect required columns. Found: {df.columns.tolist()}")

    for _, row in df.iterrows():
        try:
            # Парсинг даты
            raw_date = row[date_col]
            entry_at = pd.to_datetime(raw_date).to_pydatetime()

            # Парсинг направления
            raw_side = str(row[side_col]).lower()
            if 'buy' in raw_side or 'long' in raw_side:
                direction = models.TradeDirection.LONG
            elif 'sell' in raw_side or 'short' in raw_side:
                direction = models.TradeDirection.SHORT
            else:
                continue # Пропускаем неизвестные типы (напр. Transfer)

            # Числовые поля
            price = float(row[price_col])
            quantity = float(row[qty_col])
            
            pnl = None
            if pnl_col and pd.notna(row[pnl_col]):
                pnl = float(row[pnl_col])

            trade = {
                "symbol": str(row[symbol_col]).upper(),
                "direction": direction,
                "entry_price": price,
                "quantity": quantity,
                "entry_at": entry_at,
                "pnl": pnl,
                "notes": f"Imported from {filename}",
                "tags": ["Imported"]
            }
            trades.append(trade)
            
        except Exception as e:
            print(f"Skipping row due to error: {e}")
            continue

    return trades
