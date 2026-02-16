# MOEX ISS API — Информационно-статистический сервер Московской Биржи

## 📚 Официальные источники

| Ресурс | URL | Описание |
|--------|-----|----------|
| **ISS Reference** | https://iss.moex.com/iss/reference/ | Интерактивная документация API |
| **ISS Описание** | https://www.moex.com/a2193 | Общее описание сервиса |
| **Спецификации фьючерсов** | https://www.moex.com/ru/derivatives/contracts.aspx | Параметры контрактов |

---

## 🎯 Что такое MOEX ISS

**ISS (Information & Statistical Server)** — бесплатный публичный API Московской биржи для получения:
- Котировок и свечей (candles)
- Информации об инструментах
- Итогов торгов
- Индексов

### Базовый URL:
```
https://iss.moex.com/iss/
```

---

## 📊 Основные endpoints

### 1. Получение свечей (candles)

**Endpoint:**
```
GET /iss/engines/{engine}/markets/{market}/securities/{security}/candles.json
```

**Параметры:**
| Параметр | Описание | Пример |
|----------|----------|--------|
| `engine` | Торговая система | `stock`, `futures` |
| `market` | Рынок | `shares`, `forts` |
| `security` | Тикер инструмента | `SBER`, `SiH5` |
| `from` | Начальная дата | `2024-01-01` |
| `till` | Конечная дата | `2024-12-31` |
| `interval` | Интервал свечей | `1`, `10`, `60`, `24` |

**Интервалы свечей:**
| Значение | Описание |
|----------|----------|
| `1` | 1 минута |
| `10` | 10 минут |
| `60` | 1 час |
| `24` | 1 день |
| `7` | 1 неделя |
| `31` | 1 месяц |
| `4` | 1 квартал |

**Пример запроса:**
```
https://iss.moex.com/iss/engines/stock/markets/shares/securities/SBER/candles.json?from=2024-01-01&till=2024-01-31&interval=60
```

**Ответ:**
```json
{
  "candles": {
    "columns": ["open", "close", "high", "low", "value", "volume", "begin", "end"],
    "data": [
      [265.50, 266.20, 266.50, 265.10, 1234567890.50, 4567890, "2024-01-02 10:00:00", "2024-01-02 10:59:59"],
      ...
    ]
  }
}
```

---

### 2. Информация об инструменте

**Endpoint:**
```
GET /iss/securities/{security}.json
```

**Пример:**
```
https://iss.moex.com/iss/securities/SBER.json
```

**Ответ содержит:**
- `description` — описание инструмента
- `boards` — на каких режимах торгуется
- `indices` — в какие индексы входит

---

### 3. Список инструментов рынка

**Endpoint:**
```
GET /iss/engines/{engine}/markets/{market}/securities.json
```

**Пример (акции):**
```
https://iss.moex.com/iss/engines/stock/markets/shares/securities.json
```

**Пример (фьючерсы):**
```
https://iss.moex.com/iss/engines/futures/markets/forts/securities.json
```

---

### 4. Спецификации фьючерсов

**Endpoint:**
```
GET /iss/engines/futures/markets/forts/securities/{security}.json
```

**Ключевые поля для фьючерсов:**
| Поле | Описание |
|------|----------|
| `MINSTEP` | Минимальный шаг цены |
| `STEPPRICE` | Стоимость шага цены (руб) |
| `LOTSIZE` | Размер лота |
| `LASTTRADEDATE` | Последний день торгов |
| `ASSETCODE` | Код базового актива |

---

## 💰 Расчёт вариационной маржи на MOEX

### Что такое вариационная маржа

**Вариационная маржа (ВМ)** — это денежная сумма, которая начисляется или списывается с счёта по результатам клиринга.

### Формула расчёта:

```
ВМ = (Расчётная_цена_закрытия - Расчётная_цена_предыдущего_клиринга) × Количество × Стоимость_шага_цены / Шаг_цены
```

Или проще:
```
ВМ = Δ_цены × Количество × point_value
где point_value = STEPPRICE / MINSTEP
```

### Пример расчёта:

**Фьючерс Si (доллар/рубль):**
- MINSTEP = 1 (шаг цены 1 пункт)
- STEPPRICE = 1₽ (стоимость шага)
- point_value = 1/1 = 1₽

**Позиция:** LONG 10 контрактов, цена входа 90000

**Вечерний клиринг (19:00):**
- Расчётная цена = 90500
- ВМ = (90500 - 90000) × 10 × 1 = **+5000₽**

**Дневной клиринг следующего дня (14:00):**
- Расчётная цена = 90300
- ВМ = (90300 - 90500) × 10 × 1 = **-2000₽**

**Итого за всё время:**
- Позиция закрыта по 90700
- ВМ = (90700 - 90000) × 10 × 1 = **+7000₽**

---

### Время клирингов на MOEX:

| Клиринг | Время (МСК) | Описание |
|---------|-------------|----------|
| Дневной | 14:00-14:05 | Основная торговая сессия |
| Вечерний | 18:50-19:00 | Перед вечерней сессией |
| Промежуточный | 19:00-19:05 | После вечерней сессии |

---

## 📈 Типы инструментов на MOEX

### Фондовый рынок (engine: stock)

| Рынок | market | Описание |
|-------|--------|----------|
| Акции | `shares` | Обыкновенные и привилегированные акции |
| Облигации | `bonds` | Корпоративные, ОФЗ |
| ETF | `shares` | Биржевые фонды (ISIN начинается на RU000A) |

### Срочный рынок (engine: futures)

| Рынок | market | Описание |
|-------|--------|----------|
| Фьючерсы и опционы | `forts` | Деривативы на MOEX |

### Валютный рынок (engine: currency)

| Рынок | market | Описание |
|-------|--------|----------|
| СЕЛЬТ | `selt` | Валютные пары |

---

## 🔢 Тикеры фьючерсов MOEX

### Формат тикера:
```
{БазовыйАктив}{Месяц}{Год}
```

### Коды месяцев:
| Код | Месяц | Код | Месяц |
|-----|-------|-----|-------|
| F | Январь | N | Июль |
| G | Февраль | Q | Август |
| H | Март | U | Сентябрь |
| J | Апрель | V | Октябрь |
| K | Май | X | Ноябрь |
| M | Июнь | Z | Декабрь |

### Примеры:
| Тикер | Расшифровка |
|-------|-------------|
| `SiH5` | Фьючерс на доллар, март 2025 |
| `RIZ4` | Фьючерс на индекс РТС, декабрь 2024 |
| `BRG5` | Фьючерс на нефть Brent, февраль 2025 |
| `GZM5` | Фьючерс на Газпром, июнь 2025 |
| `SRH5` | Фьючерс на Сбербанк, март 2025 |

---

## 💼 Популярные фьючерсы и их параметры

| Тикер | Базовый актив | MINSTEP | STEPPRICE | point_value |
|-------|---------------|---------|-----------|-------------|
| Si* | USD/RUB | 1 | 1₽ | 1₽ |
| RI* | Индекс РТС | 10 | ~2₽* | ~0.2₽ |
| BR* | Нефть Brent | 0.01 | ~10₽* | ~1000₽ |
| GZ* | Газпром | 1 | ~10₽* | ~10₽ |
| SR* | Сбербанк | 1 | ~10₽* | ~10₽ |
| MX* | Индекс МосБиржи | 1 | 1₽ | 1₽ |
| BB* | Alibaba (ADR) | 0.01 | ~10₽* | ~1000₽ |

*Стоимость шага зависит от курса валюты и пересчитывается ежедневно

---

## 🔄 Интеграция с брокером (Tinkoff)

При использовании **Tinkoff Invest API** для торговли на MOEX:

### Источники данных:

| Данные | Источник | Метод |
|--------|----------|-------|
| Операции (сделки) | Tinkoff API | `GetOperations` |
| Свечи (MAE/MFE) | MOEX ISS | `/candles.json` |
| Спецификации | Tinkoff API | `GetInstrumentBy`, `FutureBy` |
| Вариационная маржа | Tinkoff API | `OPERATION_TYPE_ACCRUING_VARMARGIN` |

### Типы операций по вариационной марже:

| Тип | Описание |
|-----|----------|
| `OPERATION_TYPE_ACCRUING_VARMARGIN` | Начисление ВМ (прибыль) |
| `OPERATION_TYPE_WRITING_OFF_VARMARGIN` | Списание ВМ (убыток) |

**ВАЖНО:** Операции по вариационной марже в Tinkoff API **НЕ содержат FIGI** — они агрегированы на уровне счёта, не по инструментам!

---

## ⚠️ Ограничения MOEX ISS API

### Лимиты:
- Максимум **500 свечей** за один запрос
- Для получения большего объёма используйте пагинацию (`start` параметр)
- Rate limit: ~50 запросов в секунду

### Доступность данных:
- Минутные свечи хранятся ~30 дней
- Часовые свечи — 1 год
- Дневные свечи — вся история

### Инструменты без свечей:
- Фонды денежного рынка (LQDT, SBMM)
- Некоторые облигации
- Неликвидные инструменты

---

## 📝 Пример использования в Python

```python
import httpx
from datetime import datetime, timedelta
from typing import List, Dict, Optional

class MoexISSClient:
    BASE_URL = "https://iss.moex.com/iss"
    
    def get_candles(
        self,
        security: str,
        engine: str = "stock",
        market: str = "shares",
        from_date: Optional[datetime] = None,
        till_date: Optional[datetime] = None,
        interval: int = 60
    ) -> List[Dict]:
        """
        Получение свечей с MOEX ISS.
        
        Args:
            security: Тикер инструмента (SBER, SiH5)
            engine: stock, futures, currency
            market: shares, forts, selt
            interval: 1 (1 мин), 10, 60 (1 час), 24 (день)
        """
        url = f"{self.BASE_URL}/engines/{engine}/markets/{market}/securities/{security}/candles.json"
        
        params = {
            "interval": interval,
            "iss.meta": "off",
            "iss.only": "candles"
        }
        
        if from_date:
            params["from"] = from_date.strftime("%Y-%m-%d %H:%M:%S")
        if till_date:
            params["till"] = till_date.strftime("%Y-%m-%d %H:%M:%S")
        
        all_candles = []
        start = 0
        
        while True:
            params["start"] = start
            
            with httpx.Client() as client:
                response = client.get(url, params=params, timeout=30)
                
                if response.status_code != 200:
                    break
                
                data = response.json()
                candles_data = data.get("candles", {}).get("data", [])
                
                if not candles_data:
                    break
                
                columns = data.get("candles", {}).get("columns", [])
                
                for row in candles_data:
                    candle = dict(zip(columns, row))
                    all_candles.append(candle)
                
                if len(candles_data) < 500:
                    break
                    
                start += 500
        
        return all_candles
    
    def get_futures_spec(self, ticker: str) -> Dict:
        """Получение спецификации фьючерса"""
        url = f"{self.BASE_URL}/engines/futures/markets/forts/securities/{ticker}.json"
        
        with httpx.Client() as client:
            response = client.get(url, timeout=30)
            data = response.json()
        
        securities = data.get("securities", {})
        columns = securities.get("columns", [])
        rows = securities.get("data", [])
        
        if rows:
            spec = dict(zip(columns, rows[0]))
            return {
                "ticker": spec.get("SECID"),
                "minstep": float(spec.get("MINSTEP", 1)),
                "stepprice": float(spec.get("STEPPRICE", 1)),
                "lotsize": int(spec.get("LOTSIZE", 1)),
                "lasttradedate": spec.get("LASTTRADEDATE"),
                "assetcode": spec.get("ASSETCODE")
            }
        
        return {}
```

---

## 🔗 Полезные ссылки

- [ISS Reference (интерактивная документация)](https://iss.moex.com/iss/reference/)
- [Спецификации контрактов](https://www.moex.com/ru/derivatives/contracts.aspx)
- [Календарь экспираций](https://www.moex.com/ru/derivatives/expiration.aspx)
- [Тарифы срочного рынка](https://www.moex.com/s2184)
- [GitHub: moexalgo](https://github.com/moexalgo/moexalgo) — Python библиотека
