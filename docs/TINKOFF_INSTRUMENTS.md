# Сервис инструментов Tinkoff API — Документация

## 📋 Обзор

Сервис инструментов (`InstrumentsService`) предоставляет информацию о торговых инструментах:
- Акции (shares)
- Облигации (bonds)
- ETF
- Фьючерсы (futures)
- Опционы (options)
- Валюты (currencies)

---

## 🔧 Методы

### GetInstrumentBy

Получение информации об инструменте по FIGI, ticker или UID.

**Endpoint:**
```
POST /tinkoff.public.invest.api.contract.v1.InstrumentsService/GetInstrumentBy
```

**Параметры:**
```json
{
  "idType": "INSTRUMENT_ID_TYPE_FIGI",
  "id": "BBG004S68B31"
}
```

**Типы идентификаторов:**
| Тип | Описание |
|-----|----------|
| `INSTRUMENT_ID_TYPE_FIGI` | По FIGI |
| `INSTRUMENT_ID_TYPE_TICKER` | По тикеру |
| `INSTRUMENT_ID_TYPE_UID` | По внутреннему UID |

**Ответ:**
```json
{
  "instrument": {
    "figi": "BBG004S68B31",
    "ticker": "ALRS",
    "classCode": "TQBR",
    "isin": "RU0007252813",
    "lot": 10,
    "currency": "rub",
    "name": "Алроса",
    "exchange": "MOEX",
    "countryOfRisk": "RU",
    "sector": "materials",
    "instrumentKind": "INSTRUMENT_TYPE_SHARE",
    "tradingStatus": "SECURITY_TRADING_STATUS_NORMAL_TRADING",
    "minPriceIncrement": {
      "units": "0",
      "nano": 10000000
    }
  }
}
```

---

### FutureBy

Получение детальной информации о фьючерсе.

**Endpoint:**
```
POST /tinkoff.public.invest.api.contract.v1.InstrumentsService/FutureBy
```

**Ответ:**
```json
{
  "instrument": {
    "figi": "FUTSI1224000",
    "ticker": "SiZ4",
    "classCode": "SPBFUT",
    "lot": 1,
    "currency": "rub",
    "name": "Фьючерс Si-12.24",
    "instrumentKind": "INSTRUMENT_TYPE_FUTURES",
    "minPriceIncrement": {
      "units": "1",
      "nano": 0
    },
    "minPriceIncrementAmount": {
      "units": "1",
      "nano": 0,
      "currency": "rub"
    },
    "basicAsset": "USD000UTSTOM",
    "basicAssetSize": {
      "units": "1000",
      "nano": 0
    },
    "expirationDate": "2024-12-19T00:00:00Z",
    "firstTradeDate": "2024-03-21T00:00:00Z",
    "lastTradeDate": "2024-12-19T00:00:00Z"
  }
}
```

---

## 📊 Типы инструментов

| Тип | Описание | Пример |
|-----|----------|--------|
| `INSTRUMENT_TYPE_SHARE` | Акция | SBER, GAZP |
| `INSTRUMENT_TYPE_BOND` | Облигация | SU26238RMFS4 |
| `INSTRUMENT_TYPE_ETF` | Биржевой фонд | TMOS, FXGD |
| `INSTRUMENT_TYPE_FUTURES` | Фьючерс | SiZ4, RIH5 |
| `INSTRUMENT_TYPE_CURRENCY` | Валюта | USD000UTSTOM |
| `INSTRUMENT_TYPE_OPTION` | Опцион | |

---

## 💰 Расчёт стоимости для фьючерсов

### Ключевые поля:

| Поле | Описание |
|------|----------|
| `minPriceIncrement` | Минимальный шаг цены (в пунктах) |
| `minPriceIncrementAmount` | Стоимость шага цены (в рублях) |
| `basicAssetSize` | Размер базового актива |

### Формула расчёта PnL:

```python
point_value = min_price_increment_amount / min_price_increment
pnl = (exit_price - entry_price) * quantity * point_value
```

### Примеры:

**Фьючерс Si (USD/RUB):**
- `minPriceIncrement = 1`
- `minPriceIncrementAmount = 1₽`
- `point_value = 1 / 1 = 1₽ за пункт`
- Если цена изменилась на 100 пунктов, PnL = 100₽ за 1 контракт

**Фьючерс RI (индекс РТС):**
- `minPriceIncrement = 10`
- `minPriceIncrementAmount ≈ 2₽` (зависит от курса)
- `point_value = 2 / 10 = 0.2₽ за пункт`

**Фьючерс BR (нефть Brent):**
- `minPriceIncrement = 0.01`
- `minPriceIncrementAmount = 10₽` (примерно)
- `point_value = 10 / 0.01 = 1000₽ за 1 доллар изменения цены`

---

## 🏷️ Идентификаторы инструментов

### FIGI (Financial Instrument Global Identifier)
Глобальный уникальный идентификатор инструмента.

**Формат:** 12 символов (например, `BBG004S68B31`)

### Ticker
Биржевой код инструмента.

**Примеры:**
- `SBER` — Сбербанк
- `GAZP` — Газпром
- `SiZ4` — Фьючерс Si декабрь 2024

### Class Code
Код режима торгов на бирже.

| Код | Описание |
|-----|----------|
| `TQBR` | Акции Т+ (основной режим) |
| `SPBFUT` | Фьючерсы |
| `CETS` | Валютный рынок |

---

## 📝 Пример использования

```python
def get_instrument_info(self, figi: str) -> Optional[Dict]:
    """Получает информацию об инструменте по FIGI"""
    
    # Базовая информация
    result = self._make_request(
        "POST",
        "/tinkoff.public.invest.api.contract.v1.InstrumentsService/GetInstrumentBy",
        {"idType": "INSTRUMENT_ID_TYPE_FIGI", "id": figi}
    )
    
    instrument = result.get("instrument", {})
    instrument_type = instrument.get("instrumentKind", "")
    
    # Для фьючерсов получаем дополнительную информацию
    if instrument_type == "INSTRUMENT_TYPE_FUTURES":
        futures_result = self._make_request(
            "POST",
            "/tinkoff.public.invest.api.contract.v1.InstrumentsService/FutureBy",
            {"idType": "INSTRUMENT_ID_TYPE_FIGI", "id": figi}
        )
        instrument = futures_result.get("instrument", instrument)
    
    return {
        "figi": figi,
        "ticker": instrument.get("ticker", figi),
        "name": instrument.get("name", figi),
        "lot": instrument.get("lot", 1),
        "currency": instrument.get("currency", "RUB").upper(),
        "instrument_type": instrument_type,
        "min_price_increment": self._money_to_decimal(
            instrument.get("minPriceIncrement", {})
        ),
        "min_price_increment_amount": self._money_to_decimal(
            instrument.get("minPriceIncrementAmount", {})
        )
    }
```

---

## ⚠️ Особенности

### Кэширование
- Информация об инструментах меняется редко
- Рекомендуется кэшировать на время сессии

### Фьючерсы
- `minPriceIncrementAmount` доступен только через `FutureBy`
- Для базового `GetInstrumentBy` это поле может быть пустым

### SPB Exchange
- Инструменты с SPB могут иметь ISIN вместо тикера
- Необходим маппинг ISIN → ticker
