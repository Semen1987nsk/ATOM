# ATOM Trade Model Documentation

## Модель Trade — Структура данных сделки

Последнее обновление: 29 декабря 2025

---

## Содержание

1. [Основные поля](#основные-поля)
2. [Поля входа и выхода](#поля-входа-и-выхода)
3. [Комиссии и результат](#комиссии-и-результат)
4. [Риск-менеджмент](#риск-менеджмент)
5. [Метаданные и аналитика](#метаданные-и-аналитика)
6. [Логика импорта (FIFO)](#логика-импорта-fifo)
7. [Отображение в UI](#отображение-в-ui)

---

## Основные поля

| Поле | Тип | Обязательное | Описание |
|------|-----|--------------|----------|
| `id` | Integer | ✅ | Уникальный идентификатор сделки (auto) |
| `account_id` | Integer | ❌ | ID связанного счёта |
| `symbol` | String | ✅ | Тикер инструмента (напр. `AFKS`, `SBER`) |
| `asset_name` | String | ❌ | Полное название (напр. "АФК Система") |
| `asset_type` | String | ❌ | Тип инструмента: `Stock`, `Futures`, `Bond`, `Currency`, `Crypto` |
| `direction` | Enum | ✅ | Направление: `long` или `short` |
| `currency` | String | ❌ | Валюта сделки (default: `RUB`) |

---

## Поля входа и выхода

| Поле | Тип | Описание |
|------|-----|----------|
| `entry_price` | Numeric | Средневзвешенная цена входа |
| `exit_price` | Numeric | Средневзвешенная цена выхода (null = позиция открыта) |
| `quantity` | Numeric | Объём позиции (количество лотов/акций) |
| `leverage` | Float | Плечо (default: 1.0) |
| `entry_at` | DateTime | Дата/время входа |
| `exit_at` | DateTime | Дата/время выхода (null = позиция открыта) |
| `entry_reason` | String | **Причина входа** — логика, сигналы, паттерны (для ИИ анализа) |
| `exit_reason` | String | Причина выхода: `Manual`, `Stop Loss`, `Take Profit`, `Strategy`, `Time`, `Panic` |

### Формулы расчёта

```
entry_price = Σ(price_i × qty_i) / Σ qty_i   (средневзвешенная)
exit_price  = Σ(price_i × qty_i) / Σ qty_i   (средневзвешенная)
```

---

## Комиссии и результат

| Поле | Тип | Описание |
|------|-----|----------|
| `commission` | Numeric | ⚠️ Deprecated — используйте entry/exit_commission |
| `entry_commission` | Numeric | Комиссия на вход (сумма всех комиссий входных операций) |
| `exit_commission` | Numeric | Комиссия на выход (сумма всех комиссий выходных операций) |
| `swap` | Numeric | Плата за перенос позиции (overnight) |
| `pnl` | Numeric | Валовая прибыль/убыток (Gross P&L) |
| `net_pnl` | Numeric | Чистая прибыль (Net P&L = PnL - Commission - Swap) |

### Формулы расчёта PnL

**LONG позиция:**
```
pnl = (exit_price - entry_price) × quantity
```

**SHORT позиция:**
```
pnl = (entry_price - exit_price) × quantity
```

**Чистая прибыль:**
```
net_pnl = pnl - entry_commission - exit_commission - swap
```

---

## Риск-менеджмент

| Поле | Тип | Описание |
|------|-----|----------|
| `stop_loss` | Numeric | Цена стоп-лосса |
| `take_profit` | Numeric | Цена тейк-профита |
| `risk_amount` | Numeric | Риск в валюте (напр. 1000₽) |
| `mae_price` | Numeric | Maximum Adverse Excursion — худшая цена во время сделки |
| `mfe_price` | Numeric | Maximum Favorable Excursion — лучшая цена во время сделки |
| `r_multiple` | Float | R-мультипликатор = PnL / Risk |

---

## Метаданные и аналитика

| Поле | Тип | Описание |
|------|-----|----------|
| `setup_name` | String | Название стратегии/тактики (напр. "Breakout", "Reversal") |
| `timeframe` | String | Таймфрейм: `1m`, `5m`, `15m`, `1H`, `4H`, `1D`, `1W` |
| `news_event` | String | Событие (напр. "Отчётность", "Ставка ЦБ", "Дивиденды") |
| `screenshot_url` | String | Ссылка на скриншот графика |
| `emotions` | String | Эмоциональное состояние |
| `confidence` | Integer | Уверенность при входе (1-10) |
| `notes` | String | Заметки к сделке |
| `tags` | JSON Array | Теги: `["FOMO", "NEWS", "TREND"]` |
| `ai_analysis` | JSON | Результат ИИ-анализа: `{verdict, analysis, advice, score}` |

---

## Поля группировки

| Поле | Тип | Описание |
|------|-----|----------|
| `position_id` | Integer | ID позиции (группирует несколько операций в одну сделку) |
| `operations` | JSON Array | Детали входных/выходных операций для аккордеона |
| `holding_time_minutes` | Integer | Время удержания позиции в минутах |

### Структура operations

```json
[
  {
    "type": "entry",
    "direction": "short",
    "date": "11.12.2025",
    "time": "09:50:45",
    "price": 14.117,
    "qty": 2000,
    "commission": 11.29
  },
  {
    "type": "entry",
    "direction": "short",
    "date": "11.12.2025", 
    "time": "09:50:45",
    "price": 14.116,
    "qty": 3000,
    "commission": 16.94
  },
  {
    "type": "exit",
    "direction": "buy",
    "date": "11.12.2025",
    "time": "10:42:45",
    "price": 14.088,
    "qty": 7000,
    "commission": 39.44
  }
]
```

---

## Логика импорта (FIFO)

### Источник данных
Брокерский отчёт Тинькофф (Excel `.xlsx`)

### Алгоритм

1. **Парсинг Excel:**
   - Находим заголовок "Номер сделки" (row 8)
   - Читаем строки операций до пустой строки

2. **Группировка по позициям:**
   ```
   Группа = (symbol, direction)
   ```
   - Все операции одного тикера в одном направлении объединяются

3. **FIFO (First In, First Out):**
   - Продажи (для short) — открывают позицию
   - Покупки (для short) — закрывают позицию
   - И наоборот для long

4. **Расчёт средневзвешенной цены:**
   ```python
   weighted_sum = sum(price * qty for each operation)
   total_qty = sum(qty for each operation)
   avg_price = weighted_sum / total_qty
   ```

5. **Определение времени удержания:**
   ```python
   holding_time = exit_datetime - entry_datetime
   holding_time_minutes = holding_time.total_seconds() / 60
   ```

6. **Сохранение:**
   - Одна запись Trade = одна закрытая (или открытая) позиция
   - Все операции сохраняются в поле `operations`

---

### Особенности расчёта цены для разных типов активов

#### Акции (Stock)
```python
# Цена = Сумма сделки / Количество
entry_price = deal_sum / quantity  # в рублях
```

#### Фьючерсы (Futures)
```python
# Цена = Цена за единицу (в нативных единицах: пункты, USD и т.д.)
entry_price = price_per_unit  # в пунктах/USD
```

**Важно:** Для фьючерсов на товары (PLD, GD, SI и т.д.) цена котируется в USD, а не в рублях!

---

### Конвертация ISIN → Тикер

Акции на СПБ Бирже имеют ISIN-коды вместо тикеров. Система автоматически конвертирует:

| ISIN | Тикер | Название |
|------|-------|----------|
| RU0009062285 | AFLT | Аэрофлот |
| RU0009033591 | GAZP | Газпром |
| RU0009084396 | SBER | Сбербанк |
| RU0007288411 | NVTK | Новатэк |
| RU0007661625 | TATN | Татнефть |
| ... | ... | ... |

---

### Плата за маржинальную торговлю (Margin Fee)

Система парсит раздел **3.4 "Информация по начисленной и неудержанной брокерской комиссии"**:

```
Колонка 5:  Вид комиссии = "MARGIN \ Комиссия за маржинальную торговлю"
Колонка 28: Дата начисления
Колонка 44: Сумма
```

**Правила распределения:**
1. **Только для позиций overnight** — комиссия берётся за перенос позиции через ночь
2. **Приоритет: акции > фьючерсы** — если есть акции, комиссия идёт на них
3. **Пропорционально стоимости** — если несколько позиций, комиссия делится по стоимости

```python
# Позиция подходит для margin fee если:
entry_date < fee_date  # открыта СТРОГО ДО даты комиссии
and (exit_date is None or exit_date >= fee_date)  # не закрыта или закрыта в этот день/позже
```

---

### Расчёт Unrealized P&L для открытых позиций

#### Акции
```python
if direction == 'LONG':
    pnl = (current_price - entry_price) * quantity
else:
    pnl = (entry_price - current_price) * quantity
```

#### Фьючерсы (с учётом шага цены)
```python
# Параметры контракта с MOEX:
# - MINSTEP: минимальный шаг цены
# - STEPPRICE: стоимость шага в рублях

price_diff = current_price - entry_price
if direction == 'SHORT':
    price_diff = -price_diff

pnl = price_diff * (stepprice / minstep) * quantity
```

**Пример для PDH6 (палладий):**
```python
entry_price = 1803.56  # USD/унция (средняя)
current_price = 1790.80  # USD/унция
minstep = 0.01
stepprice = 0.77692  # руб

pnl = (1790.80 - 1803.56) * (0.77692 / 0.01) * 4
pnl = -3,963.85 руб  # Правильный расчёт
```

---

**Входные данные (7 операций из брокерского отчёта):**

| Время | Направление | Цена | Объём | Комиссия |
|-------|-------------|------|-------|----------|
| 09:50:45 | Продажа | 14.117 | 2000 | 11.29 |
| 09:50:45 | Продажа | 14.116 | 3000 | 16.94 |
| 09:50:45 | Продажа | 14.116 | 2000 | 11.29 |
| 10:42:45 | Покупка | 14.088 | 2000 | 11.27 |
| 10:42:45 | Покупка | 14.088 | 2000 | 11.26 |
| 10:42:45 | Покупка | 14.088 | 3000 | 16.91 |

**Результат (1 закрытая позиция):**

```
symbol: AFKS
direction: short
entry_price: 14.116 (средневзвешенная)
exit_price: 14.088
quantity: 7000
entry_commission: 39.52
exit_commission: 39.44
pnl: 198₽
net_pnl: 119.04₽
holding_time_minutes: 52
operations: [...6 операций...]
```

---

## Отображение в UI

### Таблица истории (/history)

**Колонки (18 шт):**

| # | Колонка | Описание |
|---|---------|----------|
| 1 | Дата | entry_at / exit_at |
| 2 | Тикер | symbol |
| 3 | Название | asset_name |
| 4 | Тип | asset_type |
| 5 | Стор. | direction (`LONG`/`SHORT`/`ADD` для entry, `SELL`/`BUY` для exit) |
| 6 | Сетап | setup_name |
| 7 | Событие | news_event |
| 8 | Причина | entry_reason (для entry) / exit_reason (для exit) |
| 9 | Увер. | confidence (1-10) |
| 10 | Цена | entry_price / exit_price |
| 11 | Кол-во | quantity |
| 12 | Комис. | entry_commission / exit_commission |
| 13 | Своп | swap |
| 14 | PnL | pnl (валовая прибыль) |
| 15 | Чист. PnL | net_pnl |
| 16 | ⏱️ Время | holding_time_minutes (формат: "52м", "1ч 30м", "2д 5ч") |
| 17 | Теги | tags |
| 18 | Действия | Edit / Delete / Close buttons |

### Аккордеон операций

При развороте строки показываются все операции из поля `operations`:
- Entry операции: зелёная полоска слева
- Exit операции: акцентная (cyan) полоска слева
- Отдельные строки с временем, ценой, объёмом и комиссией каждой операции

---

## API Endpoints

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/trades/` | Список всех сделок |
| GET | `/trades/{id}` | Получить сделку по ID |
| POST | `/trades/` | Создать сделку |
| PATCH | `/trades/{id}` | Обновить сделку |
| DELETE | `/trades/{id}` | Удалить сделку |
| PATCH | `/trades/{id}/close` | Закрыть сделку |
| POST | `/trades/import` | Импорт из Excel (FIFO) |
| GET | `/trades/export` | Экспорт в Excel |
| GET | `/trades/unrealized-pnl` | Нереализованная прибыль открытых позиций |

---

## Индексы базы данных

```python
Index('ix_trades_account_symbol', 'account_id', 'symbol')
Index('ix_trades_symbol_entry_at', 'symbol', 'entry_at')
Index('ix_trades_entry_at', 'entry_at')
Index('ix_trades_exit_at', 'exit_at')
Index('ix_trades_direction', 'direction')
```

---

## Changelog

- **2025-12-29**: Добавлена документация по расчёту unrealized P&L для фьючерсов (STEPPRICE/MINSTEP)
- **2025-12-29**: Добавлена логика распределения маржинальной комиссии (overnight, приоритет акций)
- **2025-12-29**: Добавлена таблица конвертации ISIN → тикер
- **2025-12-29**: Исправлен расчёт entry_price для фьючерсов (price_per_unit вместо deal_sum/qty)
- **2025-12-29**: Добавлено поле `entry_reason` для ИИ-анализа логики входа
- **2025-12-29**: Добавлена колонка "⏱️ Время" для отображения holding_time_minutes
- **2025-12-29**: Стилизован скроллбар с градиентом
- **2025-12-29**: Исправлен FIFO-импорт (7 операций → 1 позиция)
- **2025-12-29**: Добавлен аккордеон с деталями операций
