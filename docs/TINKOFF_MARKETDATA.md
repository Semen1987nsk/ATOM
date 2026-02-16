# Сервис рыночных данных Tinkoff API — Документация

## 📋 Обзор

Сервис рыночных данных (`MarketDataService`) предоставляет:
- Исторические свечи (OHLCV)
- Последние цены
- Стакан заявок
- Статус торгов

---

## 🔧 Методы

### GetCandles

Получение исторических свечей.

**Endpoint:**
```
POST /tinkoff.public.invest.api.contract.v1.MarketDataService/GetCandles
```

**Параметры:**
```json
{
  "figi": "BBG004S68B31",
  "from": "2024-01-15T00:00:00Z",
  "to": "2024-01-15T23:59:59Z",
  "interval": "CANDLE_INTERVAL_5_MIN"
}
```

**Интервалы свечей:**
| Значение | Описание | Максимальный период |
|----------|----------|---------------------|
| `CANDLE_INTERVAL_1_MIN` | 1 минута | 1 день |
| `CANDLE_INTERVAL_5_MIN` | 5 минут | 1 день |
| `CANDLE_INTERVAL_15_MIN` | 15 минут | 1 день |
| `CANDLE_INTERVAL_HOUR` | 1 час | 7 дней |
| `CANDLE_INTERVAL_DAY` | 1 день | 1 год |
| `CANDLE_INTERVAL_WEEK` | 1 неделя | 2 года |
| `CANDLE_INTERVAL_MONTH` | 1 месяц | 10 лет |

**Ответ:**
```json
{
  "candles": [
    {
      "open": { "units": "150", "nano": 500000000 },
      "high": { "units": "152", "nano": 0 },
      "low": { "units": "149", "nano": 800000000 },
      "close": { "units": "151", "nano": 200000000 },
      "volume": 15000,
      "time": "2024-01-15T10:00:00Z",
      "isComplete": true
    }
  ]
}
```

---

### GetLastPrices

Получение последних цен по списку инструментов.

**Endpoint:**
```
POST /tinkoff.public.invest.api.contract.v1.MarketDataService/GetLastPrices
```

**Параметры:**
```json
{
  "figi": ["BBG004S68B31", "BBG004730N88"]
}
```

**Ответ:**
```json
{
  "lastPrices": [
    {
      "figi": "BBG004S68B31",
      "price": { "units": "151", "nano": 200000000 },
      "time": "2024-01-15T10:30:00Z"
    }
  ]
}
```

---

### GetOrderBook

Получение стакана заявок.

**Endpoint:**
```
POST /tinkoff.public.invest.api.contract.v1.MarketDataService/GetOrderBook
```

**Параметры:**
```json
{
  "figi": "BBG004S68B31",
  "depth": 10
}
```

**Ответ:**
```json
{
  "figi": "BBG004S68B31",
  "depth": 10,
  "bids": [
    { "price": { "units": "150", "nano": 900000000 }, "quantity": 100 },
    { "price": { "units": "150", "nano": 800000000 }, "quantity": 250 }
  ],
  "asks": [
    { "price": { "units": "151", "nano": 0 }, "quantity": 150 },
    { "price": { "units": "151", "nano": 100000000 }, "quantity": 300 }
  ],
  "lastPrice": { "units": "151", "nano": 0 },
  "closePrice": { "units": "150", "nano": 500000000 }
}
```

---

## 📊 Использование для MAE/MFE

### MAE (Maximum Adverse Excursion)
Максимальное неблагоприятное движение цены против позиции.

### MFE (Maximum Favorable Excursion)
Максимальное благоприятное движение цены в пользу позиции.

### Алгоритм расчёта:

```python
def calculate_mae_mfe(
    figi: str,
    entry_time: datetime,
    exit_time: datetime,
    entry_price: Decimal,
    exit_price: Decimal,
    direction: str
) -> Tuple[Decimal, Decimal]:
    """
    Расчёт MAE/MFE на основе исторических свечей.
    
    Returns:
        (mae_percent, mfe_percent)
    """
    # Получаем свечи за период сделки
    candles = get_candles(figi, entry_time, exit_time, "CANDLE_INTERVAL_1_MIN")
    
    if not candles:
        return (Decimal(0), Decimal(0))
    
    # Находим экстремумы
    all_highs = [c["high"] for c in candles]
    all_lows = [c["low"] for c in candles]
    
    max_price = max(all_highs)
    min_price = min(all_lows)
    
    # Учитываем exit_price
    max_price = max(max_price, exit_price)
    min_price = min(min_price, exit_price)
    
    if direction == "LONG":
        # MAE = максимальное падение от entry
        mae_price = min_price
        mae_percent = (entry_price - mae_price) / entry_price * 100
        
        # MFE = максимальный рост от entry
        mfe_price = max_price
        mfe_percent = (mfe_price - entry_price) / entry_price * 100
    else:  # SHORT
        # MAE = максимальный рост от entry (против позиции)
        mae_price = max_price
        mae_percent = (mae_price - entry_price) / entry_price * 100
        
        # MFE = максимальное падение от entry (в пользу позиции)
        mfe_price = min_price
        mfe_percent = (entry_price - mfe_price) / entry_price * 100
    
    return (mae_percent, mfe_percent)
```

---

## ⚠️ Ограничения

### Лимиты запросов
- Максимум ~100 запросов/секунду
- Для больших периодов разбивать на части

### Доступность данных
- Минутные свечи: только за последние 24 часа
- 5-минутные свечи: только за последний день
- Дневные свечи: за несколько лет

### Торговые часы
- Данные доступны только за время торгов
- Выходные и праздники — нет данных

### Инструменты без свечей
- Некоторые инструменты (БПИФ, облигации) могут не иметь свечей
- Для них MAE/MFE недоступен

---

## 📝 Пример использования

```python
def get_candles_for_trade(
    figi: str,
    entry_at: datetime,
    exit_at: datetime
) -> List[Dict]:
    """
    Получает свечи для расчёта MAE/MFE сделки.
    Автоматически выбирает оптимальный интервал.
    """
    duration = exit_at - entry_at
    
    # Выбор интервала в зависимости от длительности сделки
    if duration.total_seconds() < 3600:  # < 1 часа
        interval = "CANDLE_INTERVAL_1_MIN"
    elif duration.total_seconds() < 86400:  # < 1 дня
        interval = "CANDLE_INTERVAL_5_MIN"
    else:
        interval = "CANDLE_INTERVAL_HOUR"
    
    result = make_request(
        "POST",
        "/tinkoff.public.invest.api.contract.v1.MarketDataService/GetCandles",
        {
            "figi": figi,
            "from": entry_at.isoformat() + "Z",
            "to": exit_at.isoformat() + "Z",
            "interval": interval
        }
    )
    
    return result.get("candles", [])
```

---

## 🔗 Связь с MOEX ISS

Для инструментов, торгуемых на MOEX, можно также использовать **MOEX ISS API** как альтернативный источник:

```
https://iss.moex.com/iss/engines/stock/markets/shares/securities/{ticker}/candles.json
```

Это полезно для:
- Бэкапа при недоступности Tinkoff API
- Получения данных за более длительные периоды
- Инструментов без данных в Tinkoff (например, БПИФ)
