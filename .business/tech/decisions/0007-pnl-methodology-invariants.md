# ADR-0007: P&L methodology — инварианты и контрольная формула

**Статус:** Принято и реализовано (зафиксировано 2026-05-19, после серии багов с раздутым journal_pnl и phantom_sweep'ом)
**Контекст PR:** Серия инцидентов 2026-05-17 — 2026-05-19: double-count varmargin (TR1.3), stale cursor пропуск SELL операций, cached pv = 1000 для индексных фьючерсов, phantom-swept Trades с exit=entry → body=0.

## Контекст

Empirik показывает пользователю P&L в нескольких местах (дашборд, журнал, позиции, графики), и **журнал не сходится с реальным движением денег** — это **главный класс багов** в проекте. Симптомы — расхождение journal vs cash в 100×, equity curve с "обрывами", дашборд показывает -10M₽ при балансе 50K₽.

До этого ADR правила были разбросаны:
- В docstrings (Phase 7/8/9 в `pipeline.py`, `futures.py`, `fee_attribution.py`)
- В feedback memory (`feedback_pnl_cash_sanity_check`)
- В specs (`position-source-of-truth-design.md`)
- В одноразовых tools (`tools/reconcile_journal_vs_cash.py`)

Любой co-pilot/developer, открывающий код, **не имеет единой точки входа** в P&L methodology и неизбежно ломает что-то.

## Решение — 8 инвариантов

### Инвариант 1. Reconciliation формула (контрольный тест)

**Перед merge'ом любой P&L работы:**

```
journal_pnl = Σ Trade.net_pnl(closed) + Σ Position.unrealized_pnl
cash_pnl    = Account.last_portfolio_value − Σ NET_DEPOSITS
                where NET_DEPOSITS = input + inp_multi − output − out_multi
diff_pct    = |journal − cash| / |cash| × 100

ACCEPTANCE: diff_pct < 5% (status OK)
WARNING:    5% ≤ diff_pct < 25%
BLOCK:      diff_pct ≥ 25% или > 50,000 ₽
```

**Источник:** `services/pnl_health_service.py`. Запускается при каждом sync; результат хранится в `Account.last_pnl_health_*`.

**Manual run:** `python -m tools.reconcile_journal_vs_cash --user-id 2`

### Инвариант 2. Single source of truth для unrealized

Unrealized PnL **открытых позиций** = `Tinkoff.expected_yield_rub` из `getPortfolio`. **Мы не вычисляем сами.**

- Поле в БД: `PositionORM.expected_yield_rub` (Phase 7, 2026-05-17)
- Поле в UI: `PositionORM.unrealized_pnl` ← копия `expected_yield_rub`
- **Fallback** (если Tinkoff не вернул): `(current − avg_entry) × qty × cached_pv`

**Почему:** для USD-denominated/FX-зашитых фьючерсов наша формула расходится с broker. Tinkoff единственный знает clearing-курс и contract multiplier.

### Инвариант 3. Single source of truth для realized

Realized PnL **закрытых сделок** = `FuturesPnLCalculator.compute()` через FIFO matcher по операциям из `OperationORM`.

Формула:
```
body = (exit_price − entry_avg_price) × qty × pv × sign
commissions = Σ commission_per_unit × qty
net = body + commissions + attributed_fees(margin_fee + service_fee + other)

где sign = +1 для LONG, −1 для SHORT
pv — см. Инвариант 5
attributed_fees для closed futures: varmargin_attributed = 0 (см. Инвариант 6)
```

**Источник:** `domain/pnl/futures.py:FuturesPnLCalculator.compute()`

### Инвариант 4. Position table = source of truth для open positions

После 2026-05-19 (`position-source-of-truth-design.md`):

- **Position table** содержит снимок реальных открытых позиций от Tinkoff `getPortfolio`.
- **Trade table** — **только history** закрытых сделок. Trade.exit_at=None — это «phantom», требует phantom_sweep.
- **Endpoint `/trades/unrealized-pnl` УДАЛЁН** — не использовать никогда.
- Pipeline: `_stage_mark_to_market` → `_stage_phantom_sweep` → `_stage_health_audit`.

### Инвариант 5. PV resolution policy (Phase 8/9 + fix 2026-05-19)

```
cached_pv     = instrument.min_price_increment_amount / min_price_increment
empirical_pv  = |first_entry.payment_per_unit| / first_entry.price_per_unit
drift         = |empirical − cached| / cached

IF drift > 5%   → use empirical (truth от Tinkoff payments)
ELSE            → use cached    (стабильность на MOEX-доморощенных)
```

**Почему:** Tinkoff metadata `min_pi_amt` для **индексных/foreign фьючерсов** (DAX, Brent, foreign futures) misleading. Cached даёт 1000, реальный payment не применяет этот множитель → empirical wins и автоматически содержит **FX-курс** на момент сделки.

**Источники:** `domain/pnl/futures.py:_resolve_pv()` и `application/fifo_matching.py:_compute_point_value_snapshot()`. **Логика должна быть identical** в обоих местах.

### Инвариант 6. Telescoping identity (НЕ дублировать varmargin)

Для closed futures trade:
```
Σ daily varmargin (entry → exit) ≡ (exit − entry) × qty × pv
```

→ `body` уже включает всю накопленную варм-маржу. Поэтому **для closed Trade**:
```
Trade.varmargin_attributed = 0
```

**Где enforce:** `application/sync/fee_attribution.py` (Phase 8.2 skip для closed). **НЕ менять** без нового ADR — это была главная причина double-count бага 2026-05-17.

### Инвариант 7. Phantom-sweep policy

Если позиция исчезла из Tinkoff portfolio, но Trade.exit_at=None в БД → закрыть fallback'ом.

```
exit_price  = last_known_price (Position.current_price) OR entry_price (fallback)
exit_at     = now
exit_reason = 'phantom_sweep'
tags        += 'phantom_sweep'
```

**Источник:** `application/sync/phantom_sweep.py`. Запускается в `_stage_phantom_sweep` после `_stage_mark_to_market`.

**Caveat:** phantom_sweep — это **last resort**. Если SELL operation придёт позже (Инвариант 8 fix'нет), FIFO replace strategy перезапишет фантомный Trade правильным.

### Инвариант 8. Cursor sync должен быть self-healing

Tinkoff `get_operations_by_cursor` может вернуть stale data (старые ops + `next_cursor=''`) если cursor устарел. Pipeline должен это **детектировать** и сам fall back на from_dt-fetch.

**Триггеры fallback (AU3+):**
- `cursor != "" AND all_ops == []` (original AU3)
- `cursor != "" AND max(batch.executed_at) < max(db.executed_at) − 1h` (NEW 2026-05-19)

**Manual recovery:** `bc.sync_cursor = ''` + trigger sync.

**Источник:** `application/sync/pipeline.py:_stage_fetch()`.

---

## Что НЕЛЬЗЯ менять без нового ADR

| Изменение | Почему опасно |
|---|---|
| Включить varmargin в Trade.net_pnl для closed futures | Double-count (Инвариант 6 — telescoping) |
| Вычислять unrealized через `(current−avg)×qty×pv` для futures как primary | Расходится с broker для FX-зашитых (Инвариант 2) |
| Восстановить endpoint `/trades/unrealized-pnl` | Сломает Position = source of truth (Инвариант 4) |
| Использовать только cached_pv в body formula | 1000x раздутие для DAX/Brent (Инвариант 5) |
| Убрать AU3+ stale-batch detection | Cursor застрянет на года (Инвариант 8) |
| Изменить формулу `cash_pnl` без обновления reconciliation tolerance | Diff_pct станет misleading |

---

## Сценарии-грабли (исторические)

1. **2026-05-17 TR1.3 double-count varmargin** — Position.unrealized + Trade.varmargin_attributed дублировались для open futures → diff 91K ₽. Fix: Инвариант 6 (skip closed) + Инвариант 4 (Position = SoT).
2. **2026-05-19 phantom_sweep body=0** — broker закрыл позицию, SELL operation задержалась, exit=entry fallback → body=0₽ при реальном убытке -7K через varmargin. Симптом: «P&L = 0 ₽, % = −12.83%». Real fix: Инвариант 8 (stale cursor self-heal) + Инвариант 7 (sweep с last_known).
3. **2026-05-19 cached pv 1000x** — DAX/Brent trades с body в миллионах ₽ при балансе в тысячах. Fix: Инвариант 5 (empirical wins при drift>5%).
4. **2026-05-19 stale cursor 2 года** — incremental sync застрял на cursor сентября 2024, пропускал все новые SELL. Fix: Инвариант 8.

---

## Контрольный чек-лист перед merge P&L работы

- [ ] Прогнал `pnl_health_service` (sync trigger): `diff_pct < 5%` (status OK)?
- [ ] Если изменялась формула body/net_pnl — обновил docstring в `futures.py` или соответствующем calculator
- [ ] Если изменялся attribute_fees — telescoping identity не нарушена (closed varmargin=0)?
- [ ] Если изменялась логика open positions — `expected_yield_rub` всё ещё primary source?
- [ ] Если изменялся `_resolve_pv` — синхронизировал с `_compute_point_value_snapshot` (логика identical)?
- [ ] Прогнал tests `test_pnl_calculators.py`, `test_pnl_health.py`, `test_journal_cash_reconcile.py`?
- [ ] На реальном acc#4 в dev DB: top-worst trades реалистичны (не миллионы при балансе в тысячах)?

---

## Связанные документы

- **Cheatsheet ежедневный:** `docs/PNL_PLAYBOOK.md` — куда смотреть когда числа не сходятся
- **Pre-flight:** `docs/PREFLIGHT_CHECKLIST.md` — общий ритуал старта
- **Phantom architecture:** `docs/superpowers/specs/2026-05-19-position-source-of-truth-design.md`
- **Memory (private):** `~/.claude/projects/.../memory/feedback_pnl_cash_sanity_check.md`,
  `.../memory/tools_workflow_futures_pv_resolution.md`,
  `.../memory/tools_workflow_stale_cursor_detection.md`

## Последствия

**Плюсы:**
- Любой co-pilot читая ADR-0007 за 5 минут понимает что НЕ ломать
- Контрольная формула (Инвариант 1) — единственный объективный gate перед merge
- Сценарии-грабли документированы — повторных багов того же типа не будет

**Минусы:**
- Дисциплина обновления при следующем рефакторинге: если меняется формула, нужно обновлять ADR (supersede новым ADR)
- Документ длинный — нужно прочитать целиком, не выборочно

**Точка изменения:** при следующей крупной P&L работе (например, addition опционных греков, или multi-currency support) — создать ADR-0008 с `Supersedes: 0007` если правила фундаментально меняются.
