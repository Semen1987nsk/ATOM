# ADR-0004: MOEX ISS — централизованный парсер + jitter в retry

**Статус:** Принято и реализовано (PR2 от 2026-05-07)
**Контекст PR:** Аудит выявил риск thundering herd под gunicorn 4 workers + 4 дублирующихся парсера column-oriented JSON.

## Контекст

MOEX ISS API возвращает данные в **column-oriented** формате:

```json
{
  "marketdata": {
    "columns": ["SECID", "LAST"],
    "data": [["SBER", 250.1], ["GAZP", 180.5]]
  }
}
```

В коде Eqio было **4 копии** парсера этой структуры (`market_service.py:172, 226, 397` + `moex_service.py:111`). Каждая копия — потенциальная точка для расхождения логики.

Также `_MOEX_BACKOFF = (1.0, 3.0)` — фиксированные задержки **без jitter**. Под gunicorn 4 workers при 429 все 4 спят ровно 1 секунду и одновременно ретрят → второй 429 → thundering herd.

ISS API rate-limit: ≤10 req/sec sustained, ≤5 RPS рекомендуется.

## Решение

### `_normalize_iss_block(data, block_name)` — единственный парсер

```python
def _normalize_iss_block(data: dict, block: str) -> List[Dict]:
    """columns + data → list of dicts. Возвращает [] на любом мусоре."""
```

- Один источник истины. Используется для marketdata, securities, candles.
- Возвращает `[]` если блок отсутствует, columns/data битые, рассинхронизированы по длине → вызывающему не нужно делать дополнительных проверок.

### `_backoff_with_jitter(base)` — рандом ±20% к каждому sleep

```python
def _backoff_with_jitter(base: float) -> float:
    return base * (0.8 + random.random() * 0.4)
```

- Размазывает повторные запросы во времени.
- Применён в `_moex_get` для всех 5xx/429/timeout кейсов.

## Последствия

**Плюсы:**

- Убраны **3 из 4** копий парсера (marketdata + securities + candles). Применили `_normalize_iss_block` во всех 3 местах в `market_service.py`.
- Безопасность под нагрузкой через jitter ±20%
- 363 теста зелёные после обоих этапов рефактора

**Что осталось (намеренно не трогаем):**

- `moex_service.py:104` — **special case**: парсит **одну** строку (`rows[0]`) для одного тикера. Применение `_normalize_iss_block(...)[0]` сделало бы код длиннее, не короче. Оставляем как есть.

## История пересмотров

| Дата | Что |
| --- | --- |
| 2026-05-07 (PR2) | Первая версия. Унифицированы marketdata и securities в `market_service.py`. Добавлен jitter. |
| 2026-05-07 (PR2.5) | Унифицирован candles-парсер (~40 строк → 15). 3 из 4 дублей закрыты. |

## Поведенческие правила

1. **Любой новый ISS-вызов** использует `_moex_get(url)` (с jitter+retry) и `_normalize_iss_block(data, block)` (с защитой от мусора).
2. **Не использовать прямой `requests.get(...)`** для ISS — это обходит retry.
3. **Не парсить ISS-блоки в коде вручную** — только через `_normalize_iss_block`.
4. **Sustained RPS ≤ 5.** Если сервис делает batch — добавить `aiolimiter` или искусственный sleep.
5. **Board в URL обязателен.** `/securities.json` без `boards/TQBR` может вернуть пустой массив для ОФЗ/ETF.

## Что нужно сделать в следующих PR

- Добавить board fallback для stocks (`TQBR` → `TQOB` → `RFUD`)
- Async-обёртка через `aiolimiter` (раздел 6 SKILL.md)
- Тесты с моками 429 → проверить что jitter реально размазывает повторные запросы

## Связанные

- skill `moex-iss-api-patterns` — базовая методичка
- `examples/moex_client.py` — production-ready async-обёртка (для ADR-NNNN миграции на async)
