# Сервис операций Tinkoff API — Детальная документация

## 📋 Обзор

Сервис операций (`OperationsService`) предоставляет доступ к:
- Истории операций (сделки, комиссии, дивиденды)
- Текущему портфелю
- Позициям по инструментам

---

## ⚠️ КРИТИЧНО: quantity vs quantityRest

**ВАЖНО!** Поле `quantity` содержит ЗАЯВЛЕННОЕ количество, а НЕ исполненное!

Для лимитных заявок (особенно в OTC торговле по субботам/воскресеньям) часть заявки может быть:
- Частично исполнена
- Отменена пользователем

**Как получить реально исполненное количество:**

1. **Рекомендуемый способ** - сумма `trades[].quantity`:
```python
executed_qty = sum(trade["quantity"] for trade in operation.get("trades", []))
```

2. **Альтернатива** - `quantity - quantityRest`:
```python
executed_qty = int(operation["quantity"]) - int(operation["quantityRest"])
```

**Пример проблемной операции:**
```json
{
  "operationType": "OPERATION_TYPE_BUY",
  "quantity": "900",           // Заявлено 900
  "quantityRest": "885",       // Не исполнено 885  
  "payment": {"units": "-1917", ...},  // Оплата только за 15 шт!
  "trades": [
    {"quantity": "5", ...},    // Исполнено 5
    {"quantity": "10", ...}    // Исполнено 10
  ]                            // Итого реально: 15 шт
}
```

---

## 🔧 Методы

### GetOperations

Получение списка операций за период.

**Endpoint (REST):**
```
POST /tinkoff.public.invest.api.contract.v1.OperationsService/GetOperations
```

**Параметры:**
```json
{
  "accountId": "string",
  "from": "2024-01-01T00:00:00Z",
  "to": "2024-01-31T23:59:59Z",
  "state": "OPERATION_STATE_EXECUTED",
  "figi": "optional_instrument_figi"
}
```

**Ответ:**
```json
{
  "operations": [
    {
      "id": "op_12345",
      "operationType": "OPERATION_TYPE_SELL",
      "state": "OPERATION_STATE_EXECUTED",
      "figi": "BBG004S68B31",
      "instrumentType": "share",
      "date": "2024-01-15T10:30:00Z",
      "payment": {
        "units": "12345",
        "nano": 670000000,
        "currency": "rub"
      },
      "price": {
        "units": "123",
        "nano": 450000000
      },
      "quantity": 100,
      "quantityRest": 0,
      "quantityDone": 100,
      "childOperations": [
        {
          "operationType": "OPERATION_TYPE_BROKER_FEE",
          "payment": {
            "units": "-12",
            "nano": -340000000,
            "currency": "rub"
          }
        }
      ]
    }
  ]
}
```

---

### GetOperationsByCursor

Получение операций с пагинацией (для больших объёмов данных).

**Endpoint:**
```
POST /tinkoff.public.invest.api.contract.v1.OperationsService/GetOperationsByCursor
```

**Параметры:**
```json
{
  "accountId": "string",
  "from": "2024-01-01T00:00:00Z",
  "to": "2024-01-31T23:59:59Z",
  "cursor": "",
  "limit": 100,
  "operationTypes": ["OPERATION_TYPE_BUY", "OPERATION_TYPE_SELL"],
  "state": "OPERATION_STATE_EXECUTED"
}
```

**Ответ:**
```json
{
  "hasNext": true,
  "nextCursor": "cursor_token_for_next_page",
  "items": [...]
}
```

---

### GetPortfolio

Получение текущего портфеля.

**Endpoint:**
```
POST /tinkoff.public.invest.api.contract.v1.OperationsService/GetPortfolio
```

**Ответ:**
```json
{
  "totalAmountShares": { "units": "100000", "nano": 0 },
  "totalAmountBonds": { "units": "50000", "nano": 0 },
  "totalAmountEtf": { "units": "25000", "nano": 0 },
  "totalAmountCurrencies": { "units": "10000", "nano": 0 },
  "totalAmountFutures": { "units": "0", "nano": 0 },
  "totalAmountPortfolio": { "units": "185000", "nano": 0 },
  "expectedYield": { "units": "5000", "nano": 0 },
  "positions": [
    {
      "figi": "BBG004S68B31",
      "instrumentType": "share",
      "quantity": { "units": "100", "nano": 0 },
      "averagePositionPrice": { "units": "150", "nano": 0 },
      "currentPrice": { "units": "155", "nano": 0 },
      "expectedYield": { "units": "500", "nano": 0 }
    }
  ]
}
```

---

## 📊 Типы операций

### Торговые операции

| Тип | Описание | payment |
|-----|----------|---------|
| `OPERATION_TYPE_BUY` | Покупка | Отрицательный (списание) |
| `OPERATION_TYPE_SELL` | Продажа | Положительный (зачисление) |
| `OPERATION_TYPE_BUY_CARD` | Покупка по карте | Отрицательный |
| `OPERATION_TYPE_SELL_CARD` | Продажа по карте | Положительный |

### Комиссии и сборы

| Тип | Описание |
|-----|----------|
| `OPERATION_TYPE_BROKER_FEE` | Комиссия брокера |
| `OPERATION_TYPE_EXCHANGE_FEE` | Комиссия биржи |
| `OPERATION_TYPE_MARGIN_FEE` | Плата за маржинальную торговлю |
| `OPERATION_TYPE_SERVICE_FEE` | Сервисный сбор |

### Ввод/вывод средств

| Тип | Описание |
|-----|----------|
| `OPERATION_TYPE_INPUT` | Пополнение счёта |
| `OPERATION_TYPE_OUTPUT` | Вывод со счёта |
| `OPERATION_TYPE_INPUT_CARD` | Пополнение с карты |
| `OPERATION_TYPE_OUTPUT_CARD` | Вывод на карту |

### Доходы

| Тип | Описание |
|-----|----------|
| `OPERATION_TYPE_DIVIDEND` | Дивиденды |
| `OPERATION_TYPE_COUPON` | Купоны по облигациям |
| `OPERATION_TYPE_TAX` | Налог (списание) |
| `OPERATION_TYPE_TAX_DIVIDEND` | Налог на дивиденды |

---

## 💰 Расчёт PnL из операций

### Алгоритм для акций:

```python
def calculate_pnl_from_operations(operations: List[Dict]) -> Decimal:
    """
    Расчёт PnL на основе payment из операций.
    
    payment:
    - BUY: отрицательный (деньги потрачены)
    - SELL: положительный (деньги получены)
    
    PnL = sum(all payments) = payment_sell + payment_buy
    """
    total_pnl = Decimal(0)
    
    for op in operations:
        payment = money_to_decimal(op.get("payment", {}))
        total_pnl += payment
    
    return total_pnl
```

### Алгоритм для фьючерсов:

```python
def calculate_futures_pnl(
    entry_price: Decimal,
    exit_price: Decimal,
    quantity: int,
    direction: str,
    min_price_increment: Decimal,
    min_price_increment_amount: Decimal
) -> Decimal:
    """
    Расчёт PnL для фьючерсов.
    
    Формула:
    PnL = (exit_price - entry_price) × quantity × point_value
    
    где point_value = min_price_increment_amount / min_price_increment
    """
    if min_price_increment == 0:
        return Decimal(0)
    
    point_value = min_price_increment_amount / min_price_increment
    
    price_diff = exit_price - entry_price
    if direction == "SHORT":
        price_diff = -price_diff
    
    pnl = price_diff * quantity * point_value
    return pnl
```

### Извлечение комиссий:

```python
def extract_commission(operation: Dict) -> Decimal:
    """
    Комиссии находятся в childOperations с типом OPERATION_TYPE_BROKER_FEE
    """
    total_commission = Decimal(0)
    
    for child in operation.get("childOperations", []):
        if "FEE" in child.get("operationType", ""):
            payment = money_to_decimal(child.get("payment", {}))
            total_commission += abs(payment)  # Комиссия всегда положительное число
    
    return total_commission
```

---

## 🔄 Группировка операций в сделки

### Логика FIFO:

```
Операции:
1. BUY 100 @ 150   → Открытие LONG позиции
2. BUY 50 @ 152    → Добавление к позиции (averaging)
3. SELL 150 @ 160  → Закрытие позиции

Результат:
- Entry price: (100×150 + 50×152) / 150 = 150.67
- Exit price: 160
- PnL: (160 - 150.67) × 150 = 1400
```

### Обработка частичного закрытия:

```
Операции:
1. BUY 100 @ 150   → Открытие
2. SELL 60 @ 160   → Частичное закрытие

Результат:
Trade 1 (закрытая): qty=60, entry=150, exit=160, PnL=600
Trade 2 (открытая): qty=40, entry=150, exit=None, PnL=None
```

### Обработка переворота (flip):

```
Операции:
1. BUY 100 @ 150   → LONG 100
2. SELL 150 @ 160  → Закрытие LONG + открытие SHORT

Результат:
Trade 1 (закрытая LONG): qty=100, entry=150, exit=160, PnL=1000
Trade 2 (открытая SHORT): qty=50, entry=160, exit=None
```

---

## ⚠️ Особенности и edge cases

### 1. Лимит операций
- `GetOperations` возвращает максимум **1000 операций**
- Для больших периодов разбивайте запрос на интервалы по 30 дней

### 2. Фьючерсы и вариационная маржа
- Для фьючерсов `payment` в BUY/SELL может быть 0
- Реальный PnL = клиринговые операции (вариационная маржа)
- Используйте формулу с `point_value` для точного расчёта

### 3. Отмена операций
- Операции с `state = OPERATION_STATE_CANCELED` нужно игнорировать
- Фильтруйте только `OPERATION_STATE_EXECUTED`

### 4. Дубликаты
- При повторных запросах могут возвращаться те же операции
- Используйте `id` для дедупликации

---

## 📝 Пример использования в проекте

```python
class TinkoffService:
    def get_operations(self, account_id: str, from_date: datetime, to_date: datetime) -> List[Dict]:
        all_operations = []
        current_start = from_date
        
        while current_start < to_date:
            current_end = min(current_start + timedelta(days=30), to_date)
            
            chunk = self._make_request(
                "POST",
                "/tinkoff.public.invest.api.contract.v1.OperationsService/GetOperations",
                {
                    "accountId": account_id,
                    "from": self._to_timestamp(current_start),
                    "to": self._to_timestamp(current_end),
                    "state": "OPERATION_STATE_EXECUTED"
                }
            )
            
            all_operations.extend(chunk.get("operations", []))
            current_start = current_end
        
        # Дедупликация по id
        unique_ops = {op["id"]: op for op in all_operations}
        return list(unique_ops.values())
```
