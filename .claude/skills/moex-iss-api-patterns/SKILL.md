---
name: moex-iss-api-patterns
description: Use when integrating with MOEX ISS API (Moscow Exchange Information & Statistical Server) for quotes, candles, securities metadata, or trading calendar in the Empirik project. Triggers on "MOEX", "ISS API", "котировки", "свечи", "candles", "тикер", "IMOEX", "торговый календарь биржи", "MAE/MFE расчёт", "iss.moex.com".
---

# MOEX ISS API Patterns для Empirik

Скилл описывает корректную работу с публичным API Московской биржи в проекте
Empirik (торговый дневник РФ-инструментов на FastAPI). Empirik тянет с ISS:
котировки для портфеля, минутные свечи для расчёта MAE/MFE, дневную историю
индекса IMOEX (бенчмарк на equity-кривой) и спецификации фьючерсов
(MINSTEP/STEPPRICE для PnL фьючерсов).

Ссылочные файлы текущего кода:
- `backend/moex_service.py` — основной клиент MOEX (futures specs, candles, index history).
- `backend/market_service.py` — обёртка с TTL-кэшем, retry, торговым календарём, MAE/MFE.
- `backend/analytics/mae_mfe.py` — агрегатная аналитика MAE/MFE по портфелю.
- `backend/routers/replay.py` — endpoint `/trades/{id}/replay`, потребитель `get_candles`.
- `backend/routers/market.py` — публичный API `/market/prices`, `/market/futures-specs`.

---

## 1. Что такое ISS API и почему это важно для Empirik

**ISS** = Information & Statistical Server, бесплатное публичное API Московской
биржи. Основные свойства:

- **Корневой URL:** `https://iss.moex.com/iss/`
- **Не требует авторизации** для open data (котировки, свечи, спецификации,
  торговый календарь). Авторизация нужна только для обезличенного стакана
  глубины и intraday-данных без задержки.
- **Бесплатные данные идут с ~15-минутной задержкой** для real-time котировок.
  Для дневок и истории задержки нет.
- **Документация:** `iss.moex.com/iss/reference/` (список endpoints + параметры).

**Что Empirik тащит с ISS:**

| Данные | Где используется | Чувствительность к задержке |
|---|---|---|
| LAST по тикеру | `/market/prices`, dashboard | 30 сек кэш — приемлемо |
| Минутные свечи | `analytics.mae_mfe`, `replay.py` | для прошедших сделок задержка не важна |
| История IMOEX (дневки) | overlay на equity-кривой | 1 час кэш |
| Спецификации фьючерсов | `pnl_service.get_point_value` | 5–60 мин кэш, меняются раз в квартал |
| Торговая сессия / календарь | `market_service.is_trading_day` | статика, hard-coded на 2 года |

---

## 2. Структура URL и формат ответа

**Иерархия endpoint'ов:**

```
/iss/engines/{engine}/markets/{market}/boards/{board}/securities/{secid}[/candles].{format}
```

- `engine`: `stock` (фондовый), `futures`, `currency`, `commodity`, `agro`.
- `market`: для `stock` — `shares`, `bonds`, `etf`, `index`, `foreign_shares`;
  для `futures` — `forts`; для `currency` — `selt`.
- `board`: главные стаканы `TQBR` (акции T+2), `TQOB` (ОФЗ), `TQTF` (ETF),
  `RFUD` (фьючерсы основной сессии), `CETS` (валюта).
- `format`: `.json`, `.xml`, `.csv`. Используем **`.json`** везде.

**Column-oriented ответ.** ISS возвращает данные не как массив объектов, а как
матрицу:

```json
{
  "securities": {
    "columns": ["SECID", "SHORTNAME", "LAST", "BID", "ASK"],
    "data": [
      ["SBER", "Сбер", 312.45, 312.40, 312.50],
      ["GAZP", "Газпром", 142.10, 142.05, 142.15]
    ]
  },
  "marketdata": { "columns": [...], "data": [...] }
}
```

Это экономит 30–40% размера ответа, но требует парсера. См. раздел 5.

**Параметры для уменьшения трафика:**

- `iss.meta=off` — убрать описание метаданных колонок.
- `iss.only=securities,marketdata` — оставить только нужные блоки.
- `securities.columns=SECID,LAST,LASTCHANGEPRC` — выбрать конкретные колонки.

В `moex_service.py` мы это уже используем:

```python
params = {"iss.meta": "off", "iss.only": "candles", ...}
```

---

## 3. Главные endpoints для Empirik

| Что нужно | URL (после `/iss/`) | Возвращает |
|---|---|---|
| Котировки одной бумаги | `engines/stock/markets/shares/securities/{secid}.json` | `securities` (статика) + `marketdata` (LAST, BID, ASK) |
| Список всех акций TQBR | `engines/stock/markets/shares/boards/TQBR/securities.json` | весь стакан, batch-обновление |
| Свечи (для MAE/MFE) | `engines/stock/markets/shares/securities/{secid}/candles.json?from=&till=&interval=` | OHLCV-свечи |
| История IMOEX | `history/engines/stock/markets/index/securities/IMOEX.json?from=&till=` | дневки CLOSE |
| Спецификации фьючерса | `engines/futures/markets/forts/securities/{secid}.json` | MINSTEP, STEPPRICE, LOTSIZE, ASSETCODE |
| Список фьючерсов RFUD | `engines/futures/markets/forts/boards/RFUD/securities.json` | batch-спецификации |
| Метаданные тикера | `securities/{secid}.json` | где торгуется (boards), ISIN, name |
| Календарь работы биржи | `engines/stock/dates.json` | первая/последняя торговые даты по движку |
| Список стаканов (boards) | `engines/stock/markets/shares/boards.json` | какие boards есть |

**Интервалы свечей (`interval`):** `1` (1 мин), `10` (10 мин), `60` (1 час),
`24` (1 день), `7` (1 неделя), `31` (1 месяц), `4` (1 квартал).

В Empirik есть готовый маппер строковых интервалов в коды MOEX:

```python
# backend/moex_service.py
_INTERVAL_MAP = {"1m": 1, "10m": 10, "1h": 60, "1d": 24, "1w": 7, "1mo": 31}
```

Используй его, не вводи свой.

---

## 4. Распространённые подводные камни

### Часовой пояс

Все времена в ответе ISS — **MSK без TZ-маркера**. Свечи возвращают `begin`,
`end` как `"2025-04-15 10:01:00"` без суффикса `+03:00` или `Z`.
Это легко спутать с UTC. В Empirik это обработано в `market_service._to_msk()`:

```python
# backend/market_service.py
def _to_msk(self, dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return MSK_TZ.localize(dt)  # naive → трактуем как MSK
    return dt.astimezone(MSK_TZ)
```

При этом **сделки пользователя** в БД хранятся в UTC. Перед запросом свечей и
при сравнении с `begin/end` свечи **обязательно конвертировать в MSK** —
иначе сместишься на 3 часа и MAE/MFE возьмёшь по чужим свечам. См. баг,
который описан в `calculate_post_exit_analysis` (`exit_time` в UTC,
свечи в MSK).

### Boards (`@TQBR`, `@TQOB`)

Один тикер торгуется на нескольких стаканах. SBER присутствует на:
- `TQBR` (T+2, основной)
- `EQOB` (внебиржевые сделки)
- `SMAL` (small lots)

По умолчанию ISS отдаёт PrimaryBoard, но **не для всех endpoint'ов**. Для
свечей и спецификаций лучше **явно указывать board в URL**:

```
engines/stock/markets/shares/boards/TQBR/securities/{secid}/candles.json
```

Empirik в `market_service.get_candles` уже использует board в URL, в
`moex_service.get_candles` — нет. Это работает для большинства случаев, но
изредка может вернуть пустой массив для ОФЗ или ETF.

### Paging

ISS возвращает максимум **500 записей** за запрос для свечей и **100 записей**
для history. Дальше через `start=N`:

```python
params["start"] = offset  # offset = 0, 500, 1000, ...
```

Empirik уже пагинирует в `market_service.get_candles` (по 500) и
`moex_service.get_index_history` (по 100). Сторожевой `if start_offset > 5000:
break` — обязателен, чтобы кривой ответ ISS не привёл к бесконечному циклу.

### Нерабочие дни

ISS не отдаёт свечи в выходные/праздники. Запрос за 9 мая возвращает
`{"candles": {"columns": [...], "data": []}}`. Это **не ошибка** — просто
пустой массив. Логика «нет данных» должна это переваривать, не падать с
HTTP 500.

В Empirik есть `MOEX_HOLIDAYS` — set дат на 2025–2026, и
`market_service.is_trading_day(date)`. **Не вводи свою копию, переиспользуй.**

### 15-минутная задержка real-time

Бесплатные `LAST`, `BID`, `ASK` идут с задержкой ~15 минут. В торговые часы
пользователь видит «вчерашнюю» цену — это нормально. Для критичных алертов
(например, «цена пробила стоп») это **неприемлемо**, но Empirik такие алерты
строит на исторических свечах, не на real-time.

### Rate limit

Официально ISS rate limit не задокументирован. Эмпирические данные:

- **Sustained ≤5 RPS** с одного IP — безопасно, никогда не блокировали.
- **Burst до 10 RPS** — проходит, но получишь 429 если злоупотреблять.
- **>20 RPS** — блок IP на несколько минут (ответы по 503).

Поэтому для batch-обновления цен (50 тикеров) — **один запрос к
`boards/TQBR/securities.json`**, а не 50 отдельных. Empirik так и делает в
`get_current_prices`.

---

## 5. Парсер column-oriented JSON

Базовая утилита, без неё все остальные функции уродливы. В `moex_service.py`
этот код размазан по 3 местам — централизуй.

```python
def _normalize_iss_block(block: dict) -> list[dict]:
    """
    Превращает ISS column-oriented блок в список dict'ов.

    Вход:  {"columns": ["SECID", "LAST"], "data": [["SBER", 312], ["GAZP", 142]]}
    Выход: [{"SECID": "SBER", "LAST": 312}, {"SECID": "GAZP", "LAST": 142}]

    Безопасно к пустому/невалидному блоку — возвращает [].
    """
    if not block or not isinstance(block, dict):
        return []
    columns = block.get("columns") or []
    rows = block.get("data") or []
    if not columns or not rows:
        return []
    return [dict(zip(columns, row)) for row in rows]
```

После этого код становится читаемым:

```python
data = response.json()
quotes = _normalize_iss_block(data.get("marketdata", {}))
for q in quotes:
    price = q.get("LAST")
    secid = q.get("SECID")
    ...
```

Сравни с текущим вариантом из `market_service.get_current_prices`:

```python
secid_idx = columns.index('SECID')
last_idx = columns.index('LAST')
for row in rows:
    ticker = row[secid_idx]
    price = row[last_idx]
```

Парсер на 5 строк выигрывает.

---

## 6. Кэширование и ETag

ISS **не поддерживает ETag**, но поддерживает `If-Modified-Since` —
возвращает `304 Not Modified` если контент не изменился. Это снижает трафик,
но **не снижает количество запросов**. Поэтому всё равно нужен прикладной
TTL-кэш.

**TTL-стратегия для разных типов данных:**

| Тип | TTL | Обоснование |
|---|---|---|
| `LAST`, `BID`, `ASK` | 30 сек | торговая логика терпит 30 сек |
| Минутные свечи прошедшего дня | 24 часа | данные уже не изменятся |
| Минутные свечи текущего дня | 5 минут | свежие свечи добавляются |
| История IMOEX (дневки) | 1 час | новый close один раз в день |
| Спецификации фьючерсов | 5–60 мин | меняются раз в квартал |
| Метаданные (ISIN, name) | 7 дней | статика |

**В Empirik** есть `_TTLCache` в `market_service.py` (in-memory dict + monotonic
time, thread-safe). Используй его, или подключи Redis через
`services/stats_cache.py` если нужна общая память между worker'ами FastAPI.

```python
# backend/market_service.py — пример
_price_cache = _TTLCache(default_ttl=30.0)
_specs_cache = _TTLCache(default_ttl=300.0)

cached = _price_cache.get(f"price:{ticker}")
if cached is not None:
    return cached
```

**Кэш-ключ** должен включать board и interval, иначе свечи 1m и 1h
смешаются:

```python
cache_key = f"candles:{secid}:{board}:{interval}:{from_ts}:{till_ts}"
```

---

## 7. Rate limiting и retry

**Sustained ≤5 RPS** — лимит, который безопасно держать. Burst до 10 RPS
переживёт без 429, дальше — лотерея.

**Retry-стратегия (что есть в `market_service._moex_get`):**

```python
_MOEX_MAX_RETRIES = 2
_MOEX_BACKOFF = (1.0, 3.0)

for attempt in range(_MOEX_MAX_RETRIES + 1):
    try:
        resp = requests.get(url, timeout=timeout)
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (429, 500, 502, 503) and attempt < _MOEX_MAX_RETRIES:
            time.sleep(_MOEX_BACKOFF[attempt])
            continue
        return None
    except (requests.Timeout, requests.ConnectionError):
        if attempt < _MOEX_MAX_RETRIES:
            time.sleep(_MOEX_BACKOFF[attempt])
            continue
        return None
```

**Что улучшить:**

1. **Jitter ±20%.** Если три worker'а FastAPI стартуют одновременно и оба
   получают 429, они через ровно 1 секунду оба ретрят и снова получают 429.
   `sleep(backoff * (0.8 + random() * 0.4))`.
2. **Экспонента до 4 шагов.** `(1, 2, 4, 8)` секунд, max 4 попытки. Текущие
   `(1, 3)` достаточны для коротких всплесков, но не для длинных провалов
   ISS (а они бывают по 5–10 минут раз в квартал).
3. **Retry только на 5xx и 429.** На 4xx (404, 400) — НЕ ретрай, это наша
   ошибка (неправильный board, опечатка в тикере).
4. **Rate-limiter перед `httpx`.** Пакеты типа `aiolimiter` (`AsyncLimiter(5, 1)`)
   гарантируют ≤5 RPS даже при burst-нагрузке. Без него на батч-операциях
   (post-exit analysis по 100 сделкам) можно словить блок.

**Для async-кода** используй `tenacity` с `wait_exponential_jitter`:

```python
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type

@retry(
    stop=stop_after_attempt(4),
    wait=wait_exponential_jitter(initial=1, max=8),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
)
async def _fetch_iss(client, url, params):
    resp = await client.get(url, params=params)
    if resp.status_code in (429, 500, 502, 503):
        raise httpx.NetworkError(f"ISS {resp.status_code}")
    resp.raise_for_status()
    return resp.json()
```

---

## 8. Маппинг тикеров: суффикс `.MOEX` и boards

Брокерские отчёты приходят в разных форматах:

- `SBER` (чистый)
- `SBER@TQBR` (с board)
- `SBER.MOEX` (Финам, Тинькофф)
- `SBER.RU` (Bloomberg)
- `SBERP` (привилегированные — отдельный тикер)
- `SiH5`, `RIM5` (фьючерсы)

**Pattern: нормализация перед сохранением в `Trade.symbol`:**

```python
import re
from dataclasses import dataclass

@dataclass(frozen=True)
class MoexSymbol:
    secid: str       # "SBER"
    board: str       # "TQBR"
    asset_type: str  # "share" | "future" | "bond" | "etf" | "currency"


_SUFFIXES = (".MOEX", ".MX", ".RU", ".MM")
_BOARD_SEP = re.compile(r"[@:]")


def normalize_ticker(raw: str) -> MoexSymbol:
    """
    Парсит любой формат тикера в MoexSymbol.
    Не валидирует существование на бирже — это делает MoexClient.
    """
    s = raw.strip().upper()
    for suf in _SUFFIXES:
        if s.endswith(suf):
            s = s[: -len(suf)]
            break

    # Разделение SECID@BOARD
    parts = _BOARD_SEP.split(s, maxsplit=1)
    secid = parts[0]
    board = parts[1] if len(parts) > 1 else _guess_primary_board(secid)
    asset_type = _classify_asset(secid)
    return MoexSymbol(secid=secid, board=board, asset_type=asset_type)


def _guess_primary_board(secid: str) -> str:
    """Эвристика для board по виду тикера."""
    # Фьючерс: SiH5, RIM5 — base+month+year
    if re.fullmatch(r"[A-Z]{2,3}[FGHJKMNQUVXZ]\d", secid):
        return "RFUD"
    # ОФЗ: SU26238RMFS4
    if secid.startswith("SU") and len(secid) == 12:
        return "TQOB"
    # Валютные пары: USDRUB_TOM, EURRUB_TOM
    if "_" in secid:
        return "CETS"
    # ETF: FXRL, TMOS — обычно 4 буквы, начинается с F или T
    # Не точная эвристика — по умолчанию даём TQBR, fallback внутри клиента
    return "TQBR"
```

**Список валидных boards:**

| Board | Что |
|---|---|
| `TQBR` | Акции T+2 (основной) |
| `TQOB` | ОФЗ |
| `TQCB` | Корп. облигации |
| `TQTF` | ETF |
| `CETS` | Валюта (selt) |
| `RFUD` | Фьючерсы FORTS, основная сессия |
| `EQOB` | Внебиржевые сделки |
| `TQBE` | Иностранные акции |

**Fallback-логика:** если `get_candles(secid, board="TQBR")` вернул пустоту,
а пользователь точно знает что тикер торгуется — пробовать `RFUD`, потом
`CETS`. Empirik это делает в `moex_service.get_candles`:

```python
if self.is_futures_ticker(ticker):
    urls = [futures_url, stock_url]
else:
    urls = [stock_url, futures_url]
```

---

## 9. Календарь рабочих дней биржи

**Фиксированные праздники МOEX:**

- 1–8 января (Новый год + Рождество)
- 23 февраля (День защитника)
- 8 марта
- 1 мая (Праздник весны и труда)
- 9 мая (День Победы)
- 12 июня (День России)
- 4 ноября (День народного единства)

**Переносы.** Если праздник попадает на субботу/воскресенье, переносится на
ближайший рабочий день. На 2025 МOEX закрыт 24 февраля (перенос с 23 февраля
воскресенья), 10 марта (перенос с 8 марта субботы). Полный календарь
публикуется ежегодно на `moex.com/s1194`.

**Сокращённые предпраздничные дни.** Закрытие в 17:50 MSK вместо 18:50.
Влияют на расчёт MAE/MFE для сделок последнего часа дня (нет данных после
17:50, хотя ожидали бы до 18:50).

В Empirik:

```python
# backend/market_service.py
MOEX_HOLIDAYS = {
    datetime(2025, 1, 1).date(),
    datetime(2025, 1, 2).date(),
    ...
    datetime(2026, 11, 4).date(),
}

def is_trading_day(self, date) -> bool:
    if date.weekday() >= 5: return False
    if date in MOEX_HOLIDAYS: return False
    return True
```

**Альтернатива:** библиотека `russian_holidays` или pyworkalendar
(`workalendar.europe.Russia`). Но в обеих **нет специфики MOEX** (например,
МOEX закрыт 31 декабря, а в обычный рабочий календарь это рабочий день).
Поэтому Empirik держит свой `MOEX_HOLIDAYS` set.

**`next_trading_day(date)`** для post-exit analysis:

```python
def next_trading_day(date):
    d = date + timedelta(days=1)
    while not is_trading_day(d):
        d += timedelta(days=1)
        if d - date > timedelta(days=14):
            raise RuntimeError("More than 14 non-trading days")
    return d
```

---

## 10. MAE/MFE расчёт через свечи MOEX

**Определения:**

- **MAE (Maximum Adverse Excursion)** — худшая цена против позиции в ходе
  сделки. Для LONG: минимум `low` всех свечей в окне. Для SHORT: максимум
  `high`.
- **MFE (Maximum Favorable Excursion)** — лучшая цена в нашу сторону. Для
  LONG: максимум `high`. Для SHORT: минимум `low`.

**Шаги расчёта:**

1. Получить свечи `[entry_at, exit_at]` с интервалом, подобранным под длину
   сделки (короткая — 1m, недельная — 1h, и т.д.). Empirik в `calculate_mae_mfe`:

   ```python
   if duration_hours <= 2:        interval = 1
   elif duration_hours <= 24:     interval = 10
   elif duration_hours <= 24*7:   interval = 60
   else:                          interval = 24
   ```

2. Конвертировать `entry_at`, `exit_at` в MSK (см. раздел 4 о часовых поясах).

3. **Фильтровать только свечи ПОЛНОСТЬЮ внутри окна** — `begin >= entry`
   AND `end <= exit`. Иначе захватишь high/low соседних свечей, которые
   произошли до входа или после выхода.

   ```python
   if entry_str <= candle_begin and candle_end <= exit_str:
       relevant_candles.append(candle)
   ```

4. Извлечь `min(low)` и `max(high)`. Учесть `exit_price`: если выход был по
   цене выше `max(high)` свечей (gap-выход на отчёте), скорректировать.

5. Сохранить **цены**, не проценты. Проценты пересчитываются в `analytics/mae_mfe.py`
   из `entry_price` уже накопленной средневзвешенной.

**Edge cases:**

| Ситуация | Что делать |
|---|---|
| Сделка <1 минуты | MAE/MFE невозможны (1 свеча не покрывает интервал) — записать `None` |
| Открытие через ночь | окно покроет несколько торговых дней, между ними gap (внеторговое время) — это OK, свечи просто отсутствуют там |
| Сделка через выходной | свечей нет за субботу–воскресенье; не вводим warning, это норма |
| Тикер делистнут | свечи частично есть, после делистинга `[]` — расчёт по тому что есть, `note` про неполные данные |
| `exit_price` за пределами `[low, high]` | gap, скорректировать по `exit_price` (см. пример в Empirik) |

**Текущая реализация в Empirik** (`market_service.calculate_mae_mfe`) корректна
по сути, но громоздка — 170 строк, несколько уровней вложенности. Кандидат
на расщепление:

- `_get_relevant_candles(ticker, entry_msk, exit_msk, interval)` — чистый
  fetch + filter.
- `_extract_mae_mfe(candles, direction, entry_price)` — чистая математика.
- `calculate_mae_mfe(...)` — оркестратор, обработка `operations` и edge cases.

Это сделает unit-тесты возможными (сейчас функция бьётся только с реальным
ISS, что хрупко).

---

## 11. Длинные периоды: paging и нарезка диапазона

ISS возвращает **максимум 500 свечей** за запрос. Лимиты по интервалам:

| Интервал | Свечей в дне | Дней в 500 свечах |
|---|---|---|
| 1m | ~525 (8:50–18:50 + вечерка для фьючерсов) | <1 день |
| 10m | ~53 | ~9 дней |
| 60m | ~9 | ~55 дней |
| 24h | 1 | 500 дней |

**Для интервала 1 (минута)** одна сделка через ночь покроет 2 дня = 1050+
свечей — ОДНОГО запроса не хватит. Нужна пагинация:

```python
async def fetch_candles_paged(client, secid, board, from_dt, till_dt, interval):
    all_candles = []
    offset = 0
    while True:
        params = {
            "iss.meta": "off",
            "iss.only": "candles",
            "from": from_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "till": till_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "interval": interval,
            "start": offset,
        }
        url = f"{MOEX_BASE}/engines/stock/markets/shares/boards/{board}/securities/{secid}/candles.json"
        data = await _fetch_iss(client, url, params)
        page = _normalize_iss_block(data.get("candles", {}))
        if not page:
            break
        all_candles.extend(page)
        if len(page) < 500:
            break  # последняя страница
        offset += len(page)
        if offset > 50_000:
            raise RuntimeError("Too many candles, suspect ISS bug")
    return all_candles
```

**Альтернатива пагинации — нарезка диапазона по дням.** Менее эффективна по
запросам, но более устойчива к глюкам paging:

```python
async def fetch_candles_chunked(client, secid, board, from_dt, till_dt, interval):
    all_candles = []
    chunk_days = {1: 1, 10: 7, 60: 30, 24: 365}.get(interval, 30)
    cur = from_dt
    while cur < till_dt:
        chunk_end = min(cur + timedelta(days=chunk_days), till_dt)
        page = await fetch_candles_paged(client, secid, board, cur, chunk_end, interval)
        all_candles.extend(page)
        cur = chunk_end
    return all_candles
```

Для Empirik предпочтительнее **paging** — меньше запросов = меньше шанс на rate
limit.

---

## 12. Чек-лист перед использованием в production

- [ ] Все вызовы ISS обёрнуты в retry с экспонентой и jitter
- [ ] TTL-кэш с подходящим TTL (30 сек для quotes, 24 ч для прошлых свечей,
      5 мин для текущего дня, 1 ч для индекса, 5 мин для futures specs)
- [ ] Rate-limiter sustained ≤5 RPS (для batch-операций особенно)
- [ ] Логирование каждого запроса: URL, время ответа, статус, размер результата
- [ ] Sentry на 5xx, на исключения парсинга, на «ожидаемый блок отсутствует»
- [ ] Fallback на «нет данных» — UI показывает «Данные недоступны», не падает
- [ ] Часовой пояс корректно: ISS отдаёт в MSK, БД хранит в UTC,
      конвертация явная и единая (`market_service._to_msk`)
- [ ] Тикеры нормализованы при входе (брокерские отчёты — разный формат)
- [ ] Сторожевые лимиты на циклы пагинации (`if offset > 50_000: raise`)
- [ ] Тесты с замоканным ISS (`pytest-httpx`, `respx`, `vcr.py`).
      Не ходить в реальный ISS из CI.
- [ ] Чёткая обработка пустого `data: []` — это **не ошибка**, это
      нерабочий день / неторговое окно.

---

## 13. Полезные ссылки

- `https://iss.moex.com/iss/reference/` — официальный справочник endpoints.
- `https://iss.moex.com/iss/index.json` — root navigation, можно ходить
  из браузера.
- `https://www.moex.com/s1194` — правила торгов и календарь нерабочих дней.
- `https://www.moex.com/a2193` — список boards с описанием.
- `https://github.com/WLM1ke/aiomoex` — async-клиент на Python (можно подсмотреть
  паттерны).
- `https://iss.moex.com/iss/securities.json?q=SBER` — поиск тикеров по
  подстроке (полезно для UI выбора инструмента).

---

## Примеры

В папке `examples/` лежат три файла:

1. **`moex_client.py`** — production-ready async-клиент с retry, кэшем,
   пагинацией, нормализацией column-oriented JSON.
2. **`candles_fetch_example.py`** — практический скрипт: качаем минутные
   свечи SBER за вчерашний день, конвертируем в pandas, пишем в CSV.
   Демонстрирует edge cases (пустой ответ, неполные свечи).
3. **`mae_mfe_calculator.py`** — функция расчёта MAE/MFE для конкретной
   сделки, использует `MoexClient` из примера 1. Обрабатывает edge cases
   (короткая сделка, через выходной, gap-открытие).
