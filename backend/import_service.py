import pandas as pd
import io
from datetime import datetime
from typing import List, Dict, Optional
import models
import re

class TradeManager:
    """
    Менеджер позиций с логикой FIFO.
    
    Логика объединения:
    - Все entry одного тикера в одном направлении до первого exit = ОДНА позиция
    - Добавления (averaging/pyramiding) объединяются в одну позицию
    - При exit закрывается вся позиция целиком
    - Операции сохраняются в массиве operations для аккордеона
    """
    
    def __init__(self):
        self.open_positions = {}  # {symbol: position_dict} - только ОДНА открытая позиция на тикер
        self.completed_trades = []  # Закрытые позиции для сохранения

    def process_trade(self, trade_data: Dict) -> bool:
        """Обработка одной сделки. Возвращает True если сделка обработана, False если пропущена."""
        
        # Валидация входных данных
        quantity = float(trade_data.get('quantity', 0))
        if quantity <= 0:
            # Пропускаем сделки с нулевым или отрицательным количеством
            return False
        
        symbol = trade_data.get('symbol', '').strip()
        if not symbol:
            # Пропускаем сделки без символа
            return False
        
        direction = trade_data.get('direction')
        if direction is None:
            return False
        
        entry_price = float(trade_data.get('entry_price', 0))
        if entry_price <= 0:
            # Пропускаем сделки с нулевой или отрицательной ценой
            return False
        
        entry_at = trade_data.get('entry_at')
        if entry_at is None:
            return False
        
        # Проверяем, есть ли открытая позиция по этому тикеру
        if symbol in self.open_positions:
            open_pos = self.open_positions[symbol]
            
            if open_pos['direction'] != direction:
                # Противоположное направление = ЗАКРЫТИЕ позиции
                self._close_position(trade_data)
            else:
                # Одинаковое направление = ДОБАВЛЕНИЕ к позиции
                self._add_to_position(trade_data)
        else:
            # Нет открытой позиции = новый ВХОД
            self._open_position(trade_data)
        
        return True

    def _open_position(self, trade_data: Dict):
        """Открытие новой позиции"""
        entry_time = trade_data['entry_at']
        
        position = {
            'symbol': trade_data['symbol'],
            'asset_name': trade_data.get('asset_name'),
            'asset_type': trade_data.get('asset_type', 'Stock'),
            'direction': trade_data['direction'],
            'entry_price': float(trade_data['entry_price']),
            'quantity': float(trade_data['quantity']),
            'entry_at': entry_time,
            'exit_at': None,
            'exit_price': None,
            'exit_reason': None,
            'entry_commission': float(trade_data.get('commission', 0)),
            'exit_commission': 0,
            'commission': float(trade_data.get('commission', 0)),
            'swap': float(trade_data.get('swap', 0)),
            'pnl': None,
            'net_pnl': None,
            'holding_time_minutes': None,
            'currency': trade_data.get('currency', 'RUB'),
            'notes': trade_data.get('notes'),
            'tags': trade_data.get('tags', []),
            # Для расчёта средневзвешенной цены
            '_total_cost': float(trade_data['entry_price']) * float(trade_data['quantity']),
            '_deal_sum': float(trade_data.get('deal_sum', 0)),
            # Операции для аккордеона
            'operations': [{
                "type": "entry",
                "time": entry_time.strftime("%H:%M:%S") if isinstance(entry_time, datetime) else str(entry_time),
                "date": entry_time.strftime("%d.%m.%Y") if isinstance(entry_time, datetime) else str(entry_time),
                "price": float(trade_data['entry_price']),
                "qty": float(trade_data['quantity']),
                "commission": float(trade_data.get('commission', 0)),
                "direction": trade_data['direction'].value if hasattr(trade_data['direction'], 'value') else str(trade_data['direction'])
            }]
        }
        
        self.open_positions[trade_data['symbol']] = position

    def _add_to_position(self, trade_data: Dict):
        """Добавление к существующей позиции (averaging/pyramiding)"""
        symbol = trade_data['symbol']
        pos = self.open_positions[symbol]
        
        add_qty = float(trade_data['quantity'])
        add_price = float(trade_data['entry_price'])
        add_comm = float(trade_data.get('commission', 0))
        add_swap = float(trade_data.get('swap', 0))
        add_time = trade_data['entry_at']
        
        # Обновляем общий объём и стоимость для средневзвешенной цены
        old_qty = pos['quantity']
        new_qty = old_qty + add_qty
        
        # Средневзвешенная цена (с защитой от деления на ноль)
        pos['_total_cost'] += add_price * add_qty
        if new_qty > 0:
            pos['entry_price'] = pos['_total_cost'] / new_qty
        # Если new_qty == 0, оставляем старую цену (не должно происходить после валидации)
        
        # Суммируем deal_sum для точного расчёта PnL
        pos['_deal_sum'] += float(trade_data.get('deal_sum', 0))
        
        pos['quantity'] = new_qty
        pos['entry_commission'] += add_comm
        pos['commission'] += add_comm
        pos['swap'] += add_swap
        
        # Добавляем операцию в список
        pos['operations'].append({
            "type": "entry",
            "time": add_time.strftime("%H:%M:%S") if isinstance(add_time, datetime) else str(add_time),
            "date": add_time.strftime("%d.%m.%Y") if isinstance(add_time, datetime) else str(add_time),
            "price": add_price,
            "qty": add_qty,
            "commission": add_comm,
            "direction": trade_data['direction'].value if hasattr(trade_data['direction'], 'value') else str(trade_data['direction'])
        })

    def _close_position(self, exit_trade: Dict):
        """Закрытие позиции (полное или частичное)"""
        symbol = exit_trade['symbol']
        pos = self.open_positions[symbol]
        
        exit_qty = float(exit_trade['quantity'])
        exit_price = float(exit_trade['entry_price'])
        exit_comm = float(exit_trade.get('commission', 0))
        exit_swap = float(exit_trade.get('swap', 0))
        exit_time = exit_trade['entry_at']
        exit_deal_sum = float(exit_trade.get('deal_sum', 0))
        
        pos_qty = pos['quantity']
        
        if exit_qty >= pos_qty:
            # Полное закрытие (или переворот позиции)
            close_qty = pos_qty
            remaining_exit_qty = exit_qty - pos_qty
            
            # Пропорция для комиссий
            exit_ratio = close_qty / exit_qty if exit_qty > 0 else 1
            
            pos['exit_at'] = exit_time
            pos['exit_price'] = exit_price
            pos['exit_commission'] = exit_comm * exit_ratio
            pos['commission'] = pos['entry_commission'] + pos['exit_commission']
            pos['swap'] += exit_swap * exit_ratio
            pos['exit_reason'] = 'Manual'
            
            # Добавляем exit операцию
            pos['operations'].append({
                "type": "exit",
                "time": exit_time.strftime("%H:%M:%S") if isinstance(exit_time, datetime) else str(exit_time),
                "date": exit_time.strftime("%d.%m.%Y") if isinstance(exit_time, datetime) else str(exit_time),
                "price": exit_price,
                "qty": close_qty,
                "commission": exit_comm * exit_ratio,
                "direction": exit_trade['direction'].value if hasattr(exit_trade['direction'], 'value') else str(exit_trade['direction'])
            })
            
            # Рассчитываем время удержания
            entry_at = pos['entry_at']
            if entry_at and exit_time:
                delta = exit_time - entry_at
                pos['holding_time_minutes'] = int(delta.total_seconds() / 60)
            
            # Рассчитываем PnL
            entry_deal_sum = pos['_deal_sum']
            exit_deal_sum_part = exit_deal_sum * exit_ratio
            
            if entry_deal_sum and exit_deal_sum_part:
                # Точный расчёт по суммам сделок
                if pos['direction'] == models.TradeDirection.LONG:
                    pnl = exit_deal_sum_part - entry_deal_sum
                else:
                    pnl = entry_deal_sum - exit_deal_sum_part
            else:
                # Fallback по ценам
                if pos['direction'] == models.TradeDirection.LONG:
                    pnl = (exit_price - pos['entry_price']) * close_qty
                else:
                    pnl = (pos['entry_price'] - exit_price) * close_qty
            
            pos['pnl'] = pnl
            pos['net_pnl'] = pnl - pos['commission'] - pos['swap']
            
            # Удаляем временные поля
            pos.pop('_total_cost', None)
            pos.pop('_deal_sum', None)
            
            # Сохраняем закрытую позицию
            self.completed_trades.append(pos)
            
            # Удаляем из открытых
            del self.open_positions[symbol]
            
            # Если остался объём — это переворот позиции
            if remaining_exit_qty > 0:
                flip_trade = exit_trade.copy()
                flip_trade['quantity'] = remaining_exit_qty
                flip_trade['commission'] = exit_comm * (remaining_exit_qty / exit_qty)
                flip_trade['swap'] = exit_swap * (remaining_exit_qty / exit_qty)
                flip_trade['deal_sum'] = exit_deal_sum * (remaining_exit_qty / exit_qty)
                self._open_position(flip_trade)
        
        else:
            # Частичное закрытие (редкий случай)
            close_ratio = exit_qty / pos_qty
            
            # Создаём закрытую часть
            closed_part = pos.copy()
            closed_part['operations'] = list(pos['operations'])  # Deep copy
            closed_part['quantity'] = exit_qty
            closed_part['entry_commission'] = pos['entry_commission'] * close_ratio
            closed_part['exit_commission'] = exit_comm
            closed_part['commission'] = closed_part['entry_commission'] + closed_part['exit_commission']
            closed_part['swap'] = pos['swap'] * close_ratio
            closed_part['exit_at'] = exit_time
            closed_part['exit_price'] = exit_price
            closed_part['exit_reason'] = 'Manual'
            
            # Добавляем exit операцию
            closed_part['operations'].append({
                "type": "exit",
                "time": exit_time.strftime("%H:%M:%S") if isinstance(exit_time, datetime) else str(exit_time),
                "date": exit_time.strftime("%d.%m.%Y") if isinstance(exit_time, datetime) else str(exit_time),
                "price": exit_price,
                "qty": exit_qty,
                "commission": exit_comm,
                "direction": exit_trade['direction'].value if hasattr(exit_trade['direction'], 'value') else str(exit_trade['direction'])
            })
            
            # Время удержания
            if pos['entry_at'] and exit_time:
                delta = exit_time - pos['entry_at']
                closed_part['holding_time_minutes'] = int(delta.total_seconds() / 60)
            
            # PnL для закрытой части
            entry_deal_sum_part = pos['_deal_sum'] * close_ratio
            
            if entry_deal_sum_part and exit_deal_sum:
                if pos['direction'] == models.TradeDirection.LONG:
                    pnl = exit_deal_sum - entry_deal_sum_part
                else:
                    pnl = entry_deal_sum_part - exit_deal_sum
            else:
                if pos['direction'] == models.TradeDirection.LONG:
                    pnl = (exit_price - pos['entry_price']) * exit_qty
                else:
                    pnl = (pos['entry_price'] - exit_price) * exit_qty
            
            closed_part['pnl'] = pnl
            closed_part['net_pnl'] = pnl - closed_part['commission'] - closed_part['swap']
            
            # Удаляем временные поля
            closed_part.pop('_total_cost', None)
            closed_part.pop('_deal_sum', None)
            
            self.completed_trades.append(closed_part)
            
            # Обновляем оставшуюся открытую позицию
            remaining_ratio = 1 - close_ratio
            pos['quantity'] = pos_qty - exit_qty
            pos['_total_cost'] *= remaining_ratio
            pos['_deal_sum'] *= remaining_ratio
            pos['entry_commission'] *= remaining_ratio
            pos['commission'] = pos['entry_commission']
            pos['swap'] *= remaining_ratio

    def finalize(self) -> List[Dict]:
        """Финализация: добавляем оставшиеся открытые позиции"""
        for symbol, pos in self.open_positions.items():
            # Удаляем временные поля
            pos.pop('_total_cost', None)
            pos.pop('_deal_sum', None)
            self.completed_trades.append(pos)
        
        self.open_positions = {}  # Очищаем
        return self.completed_trades


def parse_account_balance(contents: bytes, filename: str = "") -> Dict:
    """
    Парсит информацию о балансе счёта из файла брокера.
    
    Возвращает:
    {
        "initial_balance": float | None,
        "final_balance": float | None,
        "deposits": float | None,
        "withdrawals": float | None,
        "currency": str,
        "period_start": datetime | None,
        "period_end": datetime | None,
    }
    """
    from openpyxl import load_workbook
    
    result = {
        "initial_balance": None,
        "final_balance": None,
        "deposits": None,
        "withdrawals": None,
        "currency": "RUB",
        "period_start": None,
        "period_end": None,
    }
    
    if not filename.lower().endswith(('.xlsx', '.xls')):
        return result
    
    try:
        wb = load_workbook(io.BytesIO(contents))
        ws = wb.active
        
        # Ищем информацию в первых 100 строках
        for row in range(1, 100):
            for col in range(1, 20):
                cell_val = ws.cell(row=row, column=col).value
                if not cell_val:
                    continue
                cell_str = str(cell_val).lower()
                
                # Период отчёта
                if 'период' in cell_str or 'period' in cell_str:
                    # Ищем даты в соседних ячейках
                    for c in range(col, min(col + 5, 20)):
                        val = ws.cell(row=row, column=c).value
                        if isinstance(val, datetime):
                            if result["period_start"] is None:
                                result["period_start"] = val
                            else:
                                result["period_end"] = val
                
                # Начальный баланс / Входящий остаток
                if any(x in cell_str for x in ['входящий остаток', 'начальный баланс', 'opening balance', 'на начало периода']):
                    # Ищем число в соседних ячейках
                    for c in range(col, min(col + 10, 30)):
                        val = ws.cell(row=row, column=c).value
                        if val and isinstance(val, (int, float)):
                            result["initial_balance"] = float(val)
                            break
                
                # Конечный баланс / Исходящий остаток
                if any(x in cell_str for x in ['исходящий остаток', 'конечный баланс', 'closing balance', 'на конец периода', 'итого активов']):
                    for c in range(col, min(col + 10, 30)):
                        val = ws.cell(row=row, column=c).value
                        if val and isinstance(val, (int, float)):
                            result["final_balance"] = float(val)
                            break
                
                # Зачисления / Пополнения
                if any(x in cell_str for x in ['зачисление', 'пополнение', 'deposit', 'ввод денег', 'ввод дс']):
                    for c in range(col, min(col + 10, 30)):
                        val = ws.cell(row=row, column=c).value
                        if val and isinstance(val, (int, float)) and float(val) > 0:
                            result["deposits"] = float(val)
                            break
                
                # Списания / Снятия
                if any(x in cell_str for x in ['списание', 'снятие', 'withdrawal', 'вывод денег', 'вывод дс']):
                    for c in range(col, min(col + 10, 30)):
                        val = ws.cell(row=row, column=c).value
                        if val and isinstance(val, (int, float)):
                            result["withdrawals"] = abs(float(val))
                            break
                
                # Валюта
                if 'валюта' in cell_str or 'currency' in cell_str:
                    for c in range(col, min(col + 5, 20)):
                        val = ws.cell(row=row, column=c).value
                        if val and str(val).upper() in ['RUB', 'USD', 'EUR', 'РУБ', 'РУБЛЬ']:
                            result["currency"] = "RUB" if 'РУБ' in str(val).upper() else str(val).upper()
                            break
        
    except Exception as e:
        print(f"Warning: Could not parse balance info: {e}")
    
    return result


def parse_margin_fees(contents: bytes) -> Dict[str, float]:
    """
    Парсит раздел 3.4 'Комиссия за маржинальную торговлю' из Excel отчёта Тинькофф.
    Возвращает словарь {дата: сумма} для распределения по позициям.
    """
    from openpyxl import load_workbook
    
    wb = load_workbook(io.BytesIO(contents))
    ws = wb.active
    
    margin_fees = {}
    in_margin_section = False
    
    for row in range(1, 500):
        cell_val = ws.cell(row=row, column=1).value
        
        # Ищем начало раздела 3.4
        if cell_val and '3.4' in str(cell_val) and 'комисси' in str(cell_val).lower():
            in_margin_section = True
            continue
        
        # Конец раздела
        if in_margin_section and cell_val and ('3.5' in str(cell_val) or 'Итого' in str(cell_val)):
            break
        
        if in_margin_section:
            # Колонка 5 = Вид комиссии, 28 = Дата начисления, 44 = Сумма
            fee_type = ws.cell(row=row, column=5).value
            if fee_type and 'MARGIN' in str(fee_type).upper():
                date_val = ws.cell(row=row, column=28).value
                amount = ws.cell(row=row, column=44).value
                
                if date_val and amount:
                    try:
                        date_str = str(date_val)
                        amt = float(amount)
                        if date_str not in margin_fees:
                            margin_fees[date_str] = 0
                        margin_fees[date_str] += amt
                    except:
                        pass
    
    return margin_fees


def parse_tinkoff_excel(contents: bytes) -> List[Dict]:
    # Parse margin fees first
    margin_fees = parse_margin_fees(contents)
    total_margin_fee = sum(margin_fees.values())
    
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
            
            # Пропускаем повторяющиеся строки-заголовки в середине файла
            if str(date_val).lower() in ['дата заключения', 'дата', 'date']:
                continue
                
            if isinstance(date_val, str):
                date_str = date_val
            else:
                date_str = date_val.strftime("%d.%m.%Y")
                
            if isinstance(time_val, str):
                time_str = time_val
            else:
                time_str = time_val.strftime("%H:%M:%S")
            
            # Пропускаем если время - это заголовок
            if str(time_str).lower() in ['время', 'time']:
                continue
                
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

    # 2. Сортируем сделки по времени для корректной работы FIFO логики
    raw_trades.sort(key=lambda x: x['entry_at'])
    
    # 3. Group by (entry_at, symbol, direction)
    # Since the file is now sorted chronologically, we can iterate and coalesce consecutive matches
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

    # ISIN to readable ticker mapping (SPB Exchange uses ISIN codes)
    # For client, it's the same stock - broker decides which exchange to use
    isin_to_ticker = {
        'RU0006944147': 'TATNP',   # Татнефть привилегированные
        'RU0007661625': 'GAZP',    # Газпром
        'RU0009033591': 'TATN',    # Татнефть обыкновенные
        'RU0009062285': 'AFLT',    # Аэрофлот
        'RU0009062467': 'SIBN',    # Газпром нефть
        'RU000A0DKVS5': 'NVTK',    # Новатэк
        'RU000A0JXNU8': 'FLOT',    # Совкомфлот
        'RU000A107UL4': 'T',       # Т-Банк (Т-Технологии)
        'RU000A10ANA1': 'CNRU',    # Циан
    }

    # 3. Process grouped trades through TradeManager
    for t in grouped_trades:
        symbol = t['symbol']
        direction = t['direction']
        quantity = t['quantity']
        deal_sum = t['deal_sum']
        
        # Replace ISIN with readable ticker-СПБ if known
        if symbol in isin_to_ticker:
            symbol = isin_to_ticker[symbol]
        
        # Infer Asset Type first (needed for price calculation)
        asset_type = "Stock"
        # Futures have format like ETZ5, SiZ4, RIH5 (2-3 letters + month code + year)
        # Используем re.IGNORECASE для учёта тикеров типа SiZ4 (mixed case)
        is_futures = re.search(r'^[A-Za-z]{2,4}[FGHJKMNQUVXZfghjkmnquvxz]\d$', symbol)
        if is_futures:
            asset_type = "Futures"
        # Bonds typically have longer codes or specific patterns
        elif symbol.startswith('SU') or 'ОФЗ' in str(t.get('asset_name', '')):
            asset_type = "Bond"

        # Calculate price based on asset type
        # For futures, use price_per_unit (in native units like USD for commodities)
        # For stocks, use deal_sum / quantity (in RUB)
        if asset_type == "Futures":
            # For futures: use price in points/native currency (e.g., USD for PLD)
            price = t['price_per_unit'] if t['price_per_unit'] else (deal_sum / quantity if quantity else 0)
        else:
            # For stocks: use deal_sum / quantity
            if quantity != 0 and deal_sum != 0:
                price = deal_sum / quantity
            else:
                price = t['price_per_unit']

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
    
    # Финализируем: добавляем оставшиеся открытые позиции
    manager.finalize()
    
    # Распределяем плату за маржинальную торговлю по позициям,
    # которые были открыты в дату начисления комиссии
    for fee_date_str, fee_amount in margin_fees.items():
        if fee_amount <= 0:
            continue
            
        # Парсим дату комиссии
        try:
            fee_date = datetime.strptime(fee_date_str, "%d.%m.%Y").date()
        except:
            continue
        
        # Находим позиции, которые были перенесены через ночь на эту дату
        # Сначала ищем акции, если нет - берём фьючерсы
        stock_positions = []
        futures_positions = []
        
        for trade in manager.completed_trades:
            entry_date = trade.get('entry_at')
            exit_date = trade.get('exit_at')
            asset_type = trade.get('asset_type', 'Stock')
            
            if entry_date:
                entry_d = entry_date.date() if hasattr(entry_date, 'date') else entry_date
                exit_d = exit_date.date() if exit_date and hasattr(exit_date, 'date') else None
                
                # Плата за плечи берётся только за ПЕРЕНОС через ночь:
                # позиция открыта СТРОГО ДО даты комиссии (entry_d < fee_date)
                # И (не закрыта ИЛИ закрыта в эту дату или позже)
                if entry_d < fee_date and (exit_d is None or exit_d >= fee_date):
                    if asset_type == 'Futures':
                        futures_positions.append(trade)
                    else:
                        stock_positions.append(trade)
        
        # Приоритет: акции, если нет акций - фьючерсы
        positions_on_date = stock_positions if stock_positions else futures_positions
        
        if positions_on_date:
            # Распределяем пропорционально стоимости
            total_value = sum(abs(t.get('entry_price', 0) * t.get('quantity', 0)) for t in positions_on_date)
            if total_value > 0:
                for trade in positions_on_date:
                    position_value = abs(trade.get('entry_price', 0) * trade.get('quantity', 0))
                    trade_fee = fee_amount * (position_value / total_value)
                    trade['swap'] = trade.get('swap', 0) + trade_fee
                    # Пересчитываем net_pnl с учётом нового swap
                    if trade.get('pnl') is not None:
                        trade['net_pnl'] = trade['pnl'] - trade.get('commission', 0) - trade['swap']
    
    # Очищаем временные поля, которые не являются полями модели Trade
    result = []
    fields_to_remove = ['deal_sum', 'price_per_unit', '_total_cost', '_deal_sum']
    for trade in manager.completed_trades:
        clean_trade = {k: v for k, v in trade.items() if k not in fields_to_remove}
        result.append(clean_trade)
    
    return result

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
