import pandas as pd
import io
from datetime import datetime
from typing import List, Dict, Optional
import models
import re

class TradeManager:
    def __init__(self):
        self.open_trades = {} # {symbol: [trade_dict, ...]}
        self.completed_trades = [] # List of trade dicts to be saved

    def process_trade(self, trade_data: Dict):
        symbol = trade_data['symbol']
        direction = trade_data['direction']
        
        # Check if we have open trades for this symbol
        if symbol in self.open_trades and self.open_trades[symbol]:
            # Check if direction is opposite to the first open trade
            first_open = self.open_trades[symbol][0]
            if first_open['direction'] != direction:
                # This is a CLOSING trade (Exit)
                self._close_trade(trade_data)
            else:
                # Same direction -> Adding to position (Entry)
                self._add_trade(trade_data)
        else:
            # No open trades -> New Entry
            self._add_trade(trade_data)

    def _add_trade(self, trade_data):
        # Create a new trade record
        new_trade = trade_data.copy()
        new_trade['pnl'] = None
        new_trade['net_pnl'] = None
        new_trade['exit_at'] = None
        new_trade['exit_price'] = None
        new_trade['exit_reason'] = None
        new_trade['entry_commission'] = trade_data['commission'] # Store initial commission as entry commission
        new_trade['exit_commission'] = 0
        
        if new_trade['symbol'] not in self.open_trades:
            self.open_trades[new_trade['symbol']] = []
        
        self.open_trades[new_trade['symbol']].append(new_trade)
        self.completed_trades.append(new_trade)
        
    def _close_trade(self, exit_trade):
        # FIFO logic
        symbol = exit_trade['symbol']
        remaining_qty = exit_trade['quantity']
        
        while remaining_qty > 0 and self.open_trades[symbol]:
            open_trade = self.open_trades[symbol][0]
            
            # How much can we close?
            # Note: We assume quantity is always positive in the dict
            close_qty = min(remaining_qty, open_trade['quantity'])
            
            if close_qty < open_trade['quantity']:
                # Partial Close
                # Create a copy for the closed part
                closed_part = open_trade.copy()
                closed_part['quantity'] = close_qty
                closed_part['exit_at'] = exit_trade['entry_at']
                closed_part['exit_price'] = exit_trade['entry_price']
                
                # Proportional calculations
                ratio = close_qty / open_trade['quantity']
                exit_ratio = close_qty / exit_trade['quantity']
                
                # Split commissions
                entry_comm = open_trade['commission'] * ratio
                exit_comm = exit_trade['commission'] * exit_ratio
                
                closed_part['entry_commission'] = entry_comm
                closed_part['exit_commission'] = exit_comm
                closed_part['commission'] = entry_comm + exit_comm
                
                closed_part['swap'] = (open_trade.get('swap', 0) * ratio) + (exit_trade.get('swap', 0) * exit_ratio)
                
                # Precise PnL using Deal Sum if available
                entry_deal_sum = open_trade.get('deal_sum', 0) * ratio
                exit_deal_sum = exit_trade.get('deal_sum', 0) * exit_ratio
                
                if entry_deal_sum and exit_deal_sum:
                    if open_trade['direction'] == models.TradeDirection.LONG:
                        pnl = exit_deal_sum - entry_deal_sum
                    else:
                        pnl = entry_deal_sum - exit_deal_sum
                else:
                    # Fallback to price-based calculation
                    if open_trade['direction'] == models.TradeDirection.LONG:
                        pnl = (closed_part['exit_price'] - closed_part['entry_price']) * close_qty
                    else:
                        pnl = (closed_part['entry_price'] - closed_part['exit_price']) * close_qty
                
                closed_part['pnl'] = pnl
                closed_part['net_pnl'] = pnl - closed_part['commission'] - closed_part.get('swap', 0)
                closed_part['exit_reason'] = "Manual"
                
                # Update the original open trade (reduce qty)
                open_trade['quantity'] -= close_qty
                open_trade['commission'] -= (open_trade['commission'] * ratio) 
                open_trade['swap'] -= (open_trade.get('swap', 0) * ratio)
                if 'deal_sum' in open_trade:
                    open_trade['deal_sum'] -= entry_deal_sum
                
                # Add the closed part to completed_trades (it's a new split trade)
                self.completed_trades.append(closed_part)
                
                remaining_qty = 0
                
            else:
                # Full Close (or Over-Close)
                open_trade['exit_at'] = exit_trade['entry_at']
                open_trade['exit_price'] = exit_trade['entry_price']
                
                exit_ratio = close_qty / exit_trade['quantity']
                
                # Split commissions
                entry_comm = open_trade['commission'] # Full entry comm
                exit_comm = exit_trade['commission'] * exit_ratio
                
                open_trade['entry_commission'] = entry_comm
                open_trade['exit_commission'] = exit_comm
                open_trade['commission'] = entry_comm + exit_comm
                
                open_trade['swap'] += (exit_trade.get('swap', 0) * exit_ratio)
                
                # Precise PnL using Deal Sum if available
                entry_deal_sum = open_trade.get('deal_sum', 0)
                exit_deal_sum = exit_trade.get('deal_sum', 0) * exit_ratio
                
                if entry_deal_sum and exit_deal_sum:
                    if open_trade['direction'] == models.TradeDirection.LONG:
                        pnl = exit_deal_sum - entry_deal_sum
                    else:
                        pnl = entry_deal_sum - exit_deal_sum
                else:
                    if open_trade['direction'] == models.TradeDirection.LONG:
                        pnl = (open_trade['exit_price'] - open_trade['entry_price']) * close_qty
                    else:
                        pnl = (open_trade['entry_price'] - open_trade['exit_price']) * close_qty
                
                open_trade['pnl'] = pnl
                open_trade['net_pnl'] = pnl - open_trade['commission'] - open_trade.get('swap', 0)
                open_trade['exit_reason'] = "Manual"
                
                self.open_trades[symbol].pop(0) # Remove from open
                remaining_qty -= close_qty

        # If there is still remaining quantity, it means we flipped position
        if remaining_qty > 0:
            # Create a new entry for the remaining quantity
            new_entry = exit_trade.copy()
            new_entry['quantity'] = remaining_qty
            # Adjust commission for the new entry part
            new_entry['commission'] = exit_trade['commission'] * (remaining_qty / exit_trade['quantity'])
            new_entry['swap'] = exit_trade.get('swap', 0) * (remaining_qty / exit_trade['quantity'])
            self._add_trade(new_entry)

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
    
    manager = TradeManager()
    
    # 1. Extract raw rows
    raw_trades = []
    
    for _, row in df.iterrows():
        try:
            # Normalize column names: replace newlines and multiple spaces with single space
            cols = { " ".join(str(c).replace('\n', ' ').split()): c for c in df.columns }
            
            date_val = row[cols.get('Дата заключения', 'Дата заключения')]
            time_val = row[cols.get('Время', 'Время')]
            side_val = row[cols.get('Вид сделки', 'Вид сделки')]
            symbol_val = row[cols.get('Код актива', 'Код актива')]
            qty_val = row[cols.get('Количество', 'Количество')]
            deal_sum_val = row[cols.get('Сумма сделки', 'Сумма сделки')]
            
            # Asset Name: Try 'Сокращенное наименование', 'Наименование', 'Наименование актива'
            asset_name = None
            for key in ['Сокращенное наименование', 'Наименование', 'Наименование актива']:
                if key in cols:
                    val = row[cols[key]]
                    if pd.notna(val):
                        asset_name = val
                        break
            
            if pd.isna(date_val) or pd.isna(symbol_val):
                continue
                
            if isinstance(date_val, str):
                date_str = date_val
            else:
                date_str = date_val.strftime("%d.%m.%Y")
                
            if isinstance(time_val, str):
                time_str = time_val
            else:
                time_str = time_val.strftime("%H:%M:%S")
                
            entry_at = datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M:%S")
            
            side_str = str(side_val).lower()
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
            
            # Commissions
            comm_broker = row.get(cols.get('Комиссия брокера', 'Комиссия брокера'), 0)
            
            def parse_comm(val):
                try: return abs(float(val)) if pd.notna(val) else 0.0
                except: return 0.0
            
            # User correction: Broker commission already includes exchange and clearing fees
            commission = parse_comm(comm_broker)
            
            # Swap / Rollover
            swap_val = row.get(cols.get('Плата за перенос позиций', 'Плата за перенос позиций'), 0)
            if pd.isna(swap_val) or swap_val == 0:
                 swap_val = row.get(cols.get('Своп', 'Своп'), 0)
            swap = parse_comm(swap_val)

            # Deal Sum (for price calc)
            deal_sum = 0.0
            if pd.notna(deal_sum_val):
                deal_sum = float(deal_sum_val)
            
            # Fallback price if deal_sum is 0 (unlikely but possible)
            price_per_unit = float(row[cols.get('Цена за единицу', 'Цена за единицу')]) if pd.notna(row.get(cols.get('Цена за единицу', 'Цена за единицу'))) else 0.0

            raw_trades.append({
                "entry_at": entry_at,
                "symbol": symbol,
                "direction": direction,
                "quantity": quantity,
                "deal_sum": deal_sum,
                "commission": commission,
                "swap": swap,
                "asset_name": str(asset_name) if asset_name else None,
                "price_per_unit": price_per_unit
            })

        except Exception as e:
            print(f"Error parsing row {row.name}: {e}")
            continue

    # 2. Group by (entry_at, symbol, direction)
    # Since the file is chronological, we can just iterate and coalesce consecutive matches
    grouped_trades = []
    if raw_trades:
        current_group = raw_trades[0]
        
        for next_trade in raw_trades[1:]:
            if (next_trade['entry_at'] == current_group['entry_at'] and 
                next_trade['symbol'] == current_group['symbol'] and 
                next_trade['direction'] == current_group['direction']):
                
                # Merge
                current_group['quantity'] += next_trade['quantity']
                current_group['deal_sum'] += next_trade['deal_sum']
                current_group['commission'] += next_trade['commission']
                current_group['swap'] += next_trade['swap']
                # Asset name - keep first non-null
                if not current_group['asset_name'] and next_trade['asset_name']:
                    current_group['asset_name'] = next_trade['asset_name']
            else:
                grouped_trades.append(current_group)
                current_group = next_trade
        grouped_trades.append(current_group)

    # 3. Process grouped trades through TradeManager
    for t in grouped_trades:
        symbol = t['symbol']
        direction = t['direction']
        quantity = t['quantity']
        deal_sum = t['deal_sum']
        
        # Calculate weighted price
        if quantity != 0 and deal_sum != 0:
            price = deal_sum / quantity
        else:
            price = t['price_per_unit']

        # Infer Asset Type
        asset_type = "Stock"
        if re.search(r'[A-Z]{2,4}[A-Z0-9]\d', symbol):
            asset_type = "Futures"

        trade_data = {
            "symbol": symbol,
            "asset_name": t['asset_name'],
            "asset_type": asset_type,
            "direction": direction,
            "entry_price": price,
            "quantity": quantity,
            "deal_sum": deal_sum, # Pass deal_sum for precise PnL calc
            "entry_at": t['entry_at'],
            "commission": t['commission'],
            "swap": t['swap'],
            "notes": "Imported from Tinkoff Excel",
            "tags": ["Tinkoff", "Imported"]
        }
        
        manager.process_trade(trade_data)
            
    return manager.completed_trades

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
                "net_pnl": pnl, # Assuming generic import PnL is Net? Or Gross? Let's assume Gross for now and calc Net if fee exists
                "notes": f"Imported from {filename}",
                "tags": ["Imported"]
            }
            trades.append(trade)
            
        except Exception as e:
            print(f"Skipping row due to error: {e}")
            continue

    return trades
