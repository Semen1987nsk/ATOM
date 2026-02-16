# Tinkoff Invest API — Полная документация

## 📚 Официальные источники

| Ресурс | URL | Описание |
|--------|-----|----------|
| **Основная документация** | https://tinkoff.github.io/investAPI/ | Полный справочник всех сервисов |
| **GitHub репозиторий** | https://github.com/Tinkoff/investAPI | Protobuf-контракты, примеры, Issues |
| **Python SDK** | https://github.com/Tinkoff/invest-python | Официальный клиент для Python |
| **T-Bank (ребрендинг)** | https://developer.tbank.ru/invest/intro/intro | Новый домен после ребрендинга |

---

## 🎯 Что такое Tinkoff Invest API

**TINKOFF INVEST API** — это gRPC-интерфейс для взаимодействия с торговой платформой Тинькофф Инвестиции.

### Возможности:
- Выставление всех видов торговых поручений (лимитные, рыночные, стоп-заявки)
- Получение рыночных данных (streaming и unary-запросы)
- Получение информации по портфелю и доходности
- Проверка алгоритмов на исторических данных

### Адреса сервисов:
- **Боевой контур**: `invest-public-api.tinkoff.ru:443`
- **Песочница**: `sandbox-invest-public-api.tinkoff.ru:443`

---

## 📡 Основные сервисы API

### 1. Сервис счетов (UsersService)
Управление брокерскими счетами.

**Методы:**
- `GetAccounts` — список счетов
- `GetInfo` — информация о пользователе

### 2. Сервис инструментов (InstrumentsService)
Информация о торговых инструментах.

**Методы:**
- `GetInstrumentBy` — информация об инструменте по FIGI/ticker
- `FutureBy` — информация о фьючерсе
- `ShareBy` — информация об акции
- `Futures` — список всех фьючерсов
- `Shares` — список всех акций

**Ключевые поля инструмента:**
| Поле | Описание |
|------|----------|
| `figi` | Уникальный идентификатор инструмента |
| `ticker` | Биржевой тикер |
| `lot` | Размер лота |
| `minPriceIncrement` | Минимальный шаг цены |
| `minPriceIncrementAmount` | Стоимость шага цены (для фьючерсов) |

### 3. Сервис операций (OperationsService) ⭐
Получение истории операций, PnL, комиссий.

**Методы:**
- `GetOperations` — список операций за период
- `GetOperationsByCursor` — операции с пагинацией (для больших объёмов)
- `GetPortfolio` — текущий портфель
- `GetPositions` — текущие позиции

**Типы операций (OperationType):**
| Тип | Описание |
|-----|----------|
| `OPERATION_TYPE_BUY` | Покупка |
| `OPERATION_TYPE_SELL` | Продажа |
| `OPERATION_TYPE_BUY_CARD` | Покупка картой |
| `OPERATION_TYPE_SELL_CARD` | Продажа картой |
| `OPERATION_TYPE_BROKER_FEE` | Комиссия брокера |
| `OPERATION_TYPE_INPUT` | Ввод денег |
| `OPERATION_TYPE_OUTPUT` | Вывод денег |
| `OPERATION_TYPE_DIVIDEND` | Дивиденды |
| `OPERATION_TYPE_COUPON` | Купоны |

**Структура операции:**
```json
{
  "id": "unique_operation_id",
  "operationType": "OPERATION_TYPE_SELL",
  "state": "OPERATION_STATE_EXECUTED",
  "figi": "BBG004S68B31",
  "payment": {
    "units": "1234",
    "nano": 560000000,
    "currency": "rub"
  },
  "price": {
    "units": "123",
    "nano": 450000000
  },
  "quantity": 10,
  "date": "2024-01-15T10:30:00Z",
  "childOperations": [
    {
      "operationType": "OPERATION_TYPE_BROKER_FEE",
      "payment": {
        "units": "-5",
        "nano": -230000000
      }
    }
  ]
}
```

### 4. Сервис котировок (MarketDataService)
Рыночные данные в реальном времени и исторические.

**Методы:**
- `GetCandles` — исторические свечи
- `GetLastPrices` — последние цены
- `GetOrderBook` — стакан заявок

**Интервалы свечей (CandleInterval):**
| Значение | Описание |
|----------|----------|
| `CANDLE_INTERVAL_1_MIN` | 1 минута |
| `CANDLE_INTERVAL_5_MIN` | 5 минут |
| `CANDLE_INTERVAL_15_MIN` | 15 минут |
| `CANDLE_INTERVAL_HOUR` | 1 час |
| `CANDLE_INTERVAL_DAY` | 1 день |

### 5. Сервис ордеров (OrdersService)
Управление торговыми заявками.

**Методы:**
- `PostOrder` — выставление заявки
- `CancelOrder` — отмена заявки
- `GetOrders` — активные заявки
- `ReplaceOrder` — изменение заявки

### 6. Сервис стоп-ордеров (StopOrdersService)
Управление стоп-заявками.

**Методы:**
- `PostStopOrder` — выставление стоп-заявки
- `CancelStopOrder` — отмена стоп-заявки
- `GetStopOrders` — список стоп-заявок

---

## 💰 Расчёт PnL

### Для акций:
```
PnL = payment_sell + payment_buy
    = (exit_price × quantity) + (-entry_price × quantity)
    = (exit_price - entry_price) × quantity
```

**Пример:**
- Покупка 10 акций по 100₽: `payment = -1000₽`
- Продажа 10 акций по 110₽: `payment = +1100₽`
- **PnL = -1000 + 1100 = +100₽**

### Для фьючерсов:
```
PnL = (exit_price - entry_price) × quantity × point_value

где point_value = min_price_increment_amount / min_price_increment
```

**Пример (фьючерс Si):**
- `min_price_increment = 1` (шаг цены 1 пункт)
- `min_price_increment_amount = 1₽` (стоимость шага)
- Покупка по 90000, продажа по 90100
- **PnL = (90100 - 90000) × 1 × 1 = 100₽**

### Комиссии:
Комиссии находятся в `childOperations` с типом `OPERATION_TYPE_BROKER_FEE`.

```
Net PnL = Gross PnL - Commission
```

---

## 🔧 Python SDK

### Установка:
```bash
pip install tinkoff-investments
```

### Базовый пример:
```python
from tinkoff.invest import Client

TOKEN = "your_token_here"

with Client(TOKEN) as client:
    # Получение списка счетов
    accounts = client.users.get_accounts()
    print(accounts)
    
    # Получение портфеля
    portfolio = client.operations.get_portfolio(account_id="your_account_id")
    print(portfolio)
    
    # Получение операций
    from datetime import datetime, timedelta
    
    operations = client.operations.get_operations(
        account_id="your_account_id",
        from_=datetime.now() - timedelta(days=30),
        to=datetime.now()
    )
    print(operations)
```

### Переключение контуров:
```python
from tinkoff.invest import Client
from tinkoff.invest.constants import INVEST_GRPC_API_SANDBOX

# Песочница
with Client(TOKEN, target=INVEST_GRPC_API_SANDBOX) as client:
    ...
```

---

## 📊 Типы данных

### MoneyValue
Денежное значение с точностью до наносекунды.

```python
def money_to_decimal(money: dict) -> Decimal:
    units = int(money.get("units", 0))
    nano = int(money.get("nano", 0))
    return Decimal(units) + Decimal(nano) / Decimal(1_000_000_000)
```

### Quotation
Котировка (цена).

```python
def quotation_to_decimal(quotation: dict) -> Decimal:
    units = int(quotation.get("units", 0))
    nano = int(quotation.get("nano", 0))
    return Decimal(units) + Decimal(nano) / Decimal(1_000_000_000)
```

---

## 🚀 Алгоритмическая торговля

### Этапы разработки торгового робота:

1. **Сбор исторических данных**
   - Загрузка котировок через `GetCandles`
   - Формирование датасетов

2. **Выдвижение гипотезы**
   - Разработка торговой стратегии
   - Определение сигналов входа/выхода

3. **Бэктестинг**
   - Проверка на исторических данных
   - Оценка метрик (Sharpe, Sortino, Max DD)

4. **Тестирование в песочнице**
   - Торговля в реальном времени без реальных денег
   - Проверка исполнения ордеров

5. **Реальная торговля**
   - Запуск на боевом контуре
   - Мониторинг и корректировка

---

## ⚠️ Лимиты API

| Метод | Лимит |
|-------|-------|
| `GetOperations` | Максимум 1000 операций за запрос |
| `GetCandles` | Зависит от интервала |
| Общий rate limit | ~100 запросов/секунду |

**Рекомендации:**
- Использовать `GetOperationsByCursor` для больших периодов
- Кэшировать данные инструментов
- Разбивать запросы на интервалы по 30 дней

---

## 📝 Полезные ссылки

- [Глоссарий терминов](https://tinkoff.github.io/investAPI/glossary/)
- [FAQ](https://tinkoff.github.io/investAPI/faq/)
- [Коды ошибок](https://tinkoff.github.io/investAPI/errors/)
- [Примеры запросов](https://tinkoff.github.io/investAPI/example/)
- [Telegram канал](https://t.me/joinchat/VaW05CDzcSdsPULM)
