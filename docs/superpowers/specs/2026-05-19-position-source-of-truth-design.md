# Position table = source of truth для unrealized PnL — design

**Дата:** 2026-05-19
**Контекст:** dashboard / equity curve / unrealized P&L
**Branch:** `feature/costs-breakdown-card` (продолжение текущей серии фиксов)

## Проблема

В acc#4 после того как пользователь закрыл 5 позиций в Тинькофф:
- Dashboard показал **−596,163 ₽ Общий PnL** (с unrealized −421,700 ₽)
- На самом деле realized = −174,422, реально открыта одна позиция с unrealized −2,082
- Расхождение journal vs cash: 30.92%

Источник: рассинхрон **двух источников state**, между которыми нет двусторонней связи:

| Источник | Что отслеживает | Как обновляется |
|---|---|---|
| `Trade table` (Operations → FIFO matcher) | closed + **open** trades (open = `exit_at IS NULL`) | Через FIFO matcher по income/outgoing operations Тинькофф |
| `Position table` (Tinkoff Portfolio API snapshot) | Только реально живые позиции у брокера | При sync вызовом `getPortfolio` API |

Когда брокер закрывает позицию, но соответствующая SELL operation в Operations API задерживается / не приходит — FIFO matcher не закрывает Trade. `Trade.exit_at` остаётся NULL. Появляется **phantom open Trade**.

`/trades/unrealized-pnl` (Phase 6.5) применяет формулу `(live_price − entry_price) × effective_pv × qty` ко **всем** open Trade rows. Для phantom'ов нет matching Position snapshot → fallback на MOEX stepprice без FX adjustment → большое мусорное число. Frontend Phase 6.6 принудительно подставляет этот мусор в last point equity_curve → весь dashboard ломается.

Сейчас в acc#4: **Trade.exit_at IS NULL для 11 rows**, а в Position table — **1 row**. 10 phantoms.

## Цель

Сделать `Position table` единственной правдой для **открытых позиций и unrealized PnL**. Trade table становится историей закрытых сделок (realized PnL). При sync если Position table не подтверждает что Trade открыт — закрыть его как phantom.

Не меняем: Дневник сделок (per-trade view закрытых), FIFO matcher для realized, fee attribution, headline P&L формулу (она уже использует `Σ Position.unrealized_pnl`).

## Архитектура

### До (текущая)

```
Operations (Tinkoff /getOperations)
   ↓
FIFO matcher (Trade rows: closed + open)
   ↕  ← рассинхрон, нет связи
Position snapshot (Tinkoff /getPortfolio)
   ↓
/trades/unrealized-pnl (Phase 6.5 formula × open Trades)
   ↓
Frontend Phase 6.6: override last_point equity_curve через (live − snapshot)
```

### После

```
Operations
   ↓
FIFO matcher (Trade rows: closed history only)
   ↑ sweep ↓
Position snapshot ← единственный источник для open / unrealized
   ↓
stats.py: unrealized_pnl = Σ Position.unrealized_pnl
   ↓
equity_curve last point + unrealized (backend-side, как сейчас работает)
   ↓
Frontend читает напрямую — БЕЗ Phase 6.5/6.6 override
```

## Components

### Backend

#### Новый этап pipeline: `_stage_close_phantom_trades`

В [`application/sync/pipeline.py`](backend/application/sync/pipeline.py) добавить этап **после** `_stage_mark_to_market` (где обновляется Position table):

```python
def _stage_close_phantom_trades(session, account_id, point_value_for, now):
    """Phantom sweep: Trade.exit_at=None + позиции нет в Position table → закрыть.

    Tinkoff API иногда задерживает SELL operation. FIFO matcher не получает
    выходное событие, Trade остаётся open. Position sync ловит это: позиции
    physically нет у брокера — значит закрыта.

    Best-effort exit_price: последняя known price (Position.last_known_price
    history) или fallback на Trade.entry_price (P&L=0).

    Идемпотентно: повторный запуск не двигает уже закрытые Trade rows.
    """
    live_uids = {
        p.instrument_uid for p in session.query(Position)
        .filter(Position.account_id == account_id, Position.quantity != 0)
        .all()
    }

    open_trades = session.query(Trade).filter(
        Trade.account_id == account_id,
        Trade.exit_at.is_(None),
    ).all()

    # Защита от blip: если Position table пуста, а в Operations недавно были
    # активные операции — пропустить sweep (Tinkoff мог отдать пустой Portfolio).
    if not live_uids and _has_recent_operations(session, account_id, hours=24):
        log.warning("phantom_sweep.skipped_empty_positions", extra={"account_id": account_id})
        return 0

    phantoms = [t for t in open_trades if t.instrument_uid not in live_uids]
    if not phantoms:
        return 0

    closed_count = 0
    for trade in phantoms:
        exit_price = _last_known_price(session, trade.instrument_uid) or trade.entry_price
        pv = point_value_for(trade.instrument_uid) if trade.instrument_uid else Decimal(1)
        body_pnl = (Decimal(str(exit_price)) - Decimal(str(trade.entry_price))) \
                   * Decimal(str(trade.quantity)) * pv
        if trade.direction and trade.direction.value == 'SHORT':
            body_pnl = -body_pnl

        trade.exit_at = now
        trade.exit_price = exit_price
        trade.pnl = body_pnl
        # Net P&L = body − |commission| + attributed (varmargin/margin/service/other)
        trade.net_pnl = body_pnl - abs(Decimal(str(trade.commission_total or 0))) \
                        + Decimal(str(trade.varmargin_attributed or 0)) \
                        + Decimal(str(trade.margin_fee_attributed or 0)) \
                        + Decimal(str(trade.service_fee_attributed or 0)) \
                        + Decimal(str(trade.other_fees_attributed or 0))
        # Audit tagging — используем existing поля Trade
        trade.exit_reason = "phantom_sweep"
        existing_tags = list(trade.tags or [])
        if "phantom_sweep" not in existing_tags:
            existing_tags.append("phantom_sweep")
        trade.tags = existing_tags

        log.warning(
            "phantom_trade_swept",
            extra={
                "trade_id": trade.id, "instrument_uid": trade.instrument_uid,
                "entry_price": str(trade.entry_price), "exit_price": str(exit_price),
                "net_pnl": str(trade.net_pnl),
            },
        )
        closed_count += 1

    session.flush()
    return closed_count
```

Helpers:
- `_has_recent_operations(session, account_id, hours=24)` — проверка что в последние 24h были Operations (защита от Tinkoff Portfolio blip).
- `_last_known_price(session, instrument_uid)` — `Position.current_price` если есть recent row, иначе fallback `None`.

Регистрация этапа в `pipeline.execute`: вызвать `_stage_close_phantom_trades` между `_stage_mark_to_market` и `_stage_persist`.

#### FIFO matcher: handle late SELL для swept trades

В [`application/fifo_matching.py`](backend/application/fifo_matching.py) добавить проверку при processing SELL operation:

```python
# При попытке match SELL operation к open Trade row:
# Если existing matching trade has metadata.closed_reason == 'phantom_sweep',
# это значит мы его закрыли best-effort, а теперь пришла настоящая SELL op.
# Log conflict для admin, перетереть phantom_sweep значения настоящим.
if existing_trade.metadata_json and \
   existing_trade.metadata_json.get("closed_reason") == "phantom_sweep":
    log.warning("phantom_sweep_resolved_by_late_sell", extra={
        "trade_id": existing_trade.id,
        "swept_exit_price": str(existing_trade.exit_price),
        "actual_exit_price": str(real_exit_price),
        "delta_pnl": str(real_pnl - existing_trade.pnl),
    })
    # Перетереть phantom_sweep cleanup значения настоящими данными от operation
    existing_trade.exit_price = real_exit_price
    existing_trade.pnl = real_pnl
    existing_trade.net_pnl = real_net_pnl
    meta = dict(existing_trade.metadata_json)
    meta["closed_reason"] = "sell_op_after_sweep"
    meta["sweep_corrected_at"] = now.isoformat()
    existing_trade.metadata_json = meta
```

#### Удалить /trades/unrealized-pnl endpoint

В [`backend/routers/trades.py`](backend/routers/trades.py) удалить функцию-обработчик `/trades/unrealized-pnl` и все связанные импорты.

Удалить файл [`backend/domain/pnl/per_trade_unrealized.py`](backend/domain/pnl/per_trade_unrealized.py) и `backend/tests/unit/test_per_trade_unrealized.py`.

#### stats.py не меняется

Существующая логика уже корректная:
```python
unrealized_pnl_position_based = float(unrealized_sum) if unrealized_sum is not None else 0.0
unrealized_pnl = unrealized_pnl_position_based  # это Σ Position.unrealized_pnl
# ...
_curve_tail_adjustment = unrealized_pnl
# применяется к last point equity_curve на backend-side
```

### Frontend

#### `EquityCurveCard.tsx`

Удалить props и логику:
```ts
// УДАЛИТЬ из Props:
liveUnrealizedSum?: number | null;
snapshotUnrealized?: number;

// УДАЛИТЬ useMemo dataAdjusted (Phase 6.6 override):
const dataAdjusted = useMemo(() => { ... });

// Все usage dataAdjusted заменить на data напрямую
```

`merged` и `stats` useMemo'и читают `data` напрямую (backend уже добавил unrealized в last point).

#### `StatsGrid.tsx`

```ts
// УДАЛИТЬ:
liveUnrealizedSum?: number | null;
const headlineUnrealized = (liveUnrealizedSum !== null && liveUnrealizedSum !== undefined) ? ... : ...;

// ЗАМЕНИТЬ:
const displayTotalPnlWithUnrealized = (displayTotalPnl ?? 0) + (stats?.unrealized_pnl ?? 0);
```

Используем `stats.unrealized_pnl` (= Σ Position.unrealized_pnl) напрямую.

#### `page.tsx`

```ts
// УДАЛИТЬ useEffect/Promise.all для fetch /trades/unrealized-pnl
// УДАЛИТЬ state liveUnrealizedSum
// УДАЛИТЬ props liveUnrealizedSum и snapshotUnrealized из <EquityCurveCard>, <StatsGrid>
```

## Data flow

```
trigger sync (manual ↻ button или scheduled)
    ↓
pipeline:
  1. fetch operations → upsert OperationORM
  2. _stage_attribute_fees → fee attribution к Trade rows
  3. _stage_fifo_match → Trade rows (closed получают net_pnl)
  4. _stage_mark_to_market → Position snapshot + Position.unrealized_pnl
  5. _stage_close_phantom_trades [NEW] → закрыть Trade rows без matching Position
  6. _stage_persist
    ↓
/stats/ endpoint
  - total_pnl = Σ closed Trade.net_pnl
  - unrealized_pnl = Σ Position.unrealized_pnl
  - equity_curve: last point + unrealized
    ↓
Frontend dashboard (без overrides, читает endpoint напрямую)
```

## Error handling

| Сценарий | Поведение |
|---|---|
| Tinkoff Portfolio API blip (пустой list при наличии операций) | Skip sweep, log warning. Position table остаётся как есть. |
| Phantom trade без price history | exit_price = entry_price → pnl = -commission (трейд закрылся "в ноль" body) |
| Late SELL op после sweep | FIFO matcher перетирает swept values реальными + log conflict, metadata `sweep_corrected_at` |
| Sweep + concurrent FIFO closing | Sweep runs AFTER mark_to_market, FIFO runs BEFORE. Не пересекаются в pipeline. |
| Position table snapshot stale | unrealized_pnl показывается из stale snapshot. Не проблема — UI badge помечает stale (>10 min). |

## Testing

### Unit (backend)

1. `test_sweep_closes_open_trade_without_position` — seed Trade.exit_at=None + Position table без этого instrument_uid → after sweep, trade.exit_at set + net_pnl recomputed.
2. `test_no_sweep_when_position_exists` — Trade open + matching Position → trade not changed.
3. `test_sweep_uses_entry_price_when_no_known` — phantom без price history → exit_price = entry_price → body_pnl = 0.
4. `test_sweep_metadata_tagged` — closed_reason='phantom_sweep' в metadata_json + swept_at timestamp.
5. `test_skip_sweep_when_positions_empty_but_recent_ops` — Position table пуста, в Operations recent ops → skip + log warning.
6. `test_late_sell_corrects_swept_trade` — Trade swept с exit_price=100. Затем SELL operation с price=110 — Trade should update exit_price + log conflict.
7. `test_sweep_handles_short_direction` — phantom SHORT trade → body_pnl = -(exit - entry) × qty × pv.

### Integration

8. `test_full_pipeline_with_phantoms` — seed acc with 5 open Trades, 2 имеют matching Position. Run pipeline. Expected: 3 phantoms closed, 2 остаются open, total_pnl + unrealized совпадают с broker truth.

### Frontend

Manual smoke check после deploy:
- Открыть Дашборд acc#4
- Должны быть `Total PnL ≈ -176k` (realized -174k + unrealized -2k), не -596k
- Equity curve last point не спайкает в -600k
- Расхождение journal vs cash в районе 1-3% (orphan'ы)

## Migration / Rollout

После merge feature ветки:
1. `git pull` на staging/prod.
2. Restart uvicorn.
3. Frontend rebuild (Next.js auto).
4. **Manual force-resync acc#4** через admin endpoint (или sync UI ↻) — sweeper закроет accumulated phantom'ы.
5. User делает Ctrl+Shift+R → dashboard корректный.
6. Monitor logs: `phantom_trade_swept` events первые 24h — sanity check что sweep работает на реальных данных.

## Risks

- **Tinkoff API недетерминизм**: SELL operation иногда может прийти через несколько часов или дней. Sweep может закрыть trade слишком рано. Mitigation: log conflict + auto-correct в FIFO matcher (см. error handling выше).
- **Best-effort exit_price approximate**: realized PnL для swept trades менее точен чем для FIFO-matched. Compromise: лучше phantom-closed (с tag) чем phantom-open (с фиктивным unrealized −421k).
- **Frontend breakage**: удаляем активно используемый Phase 6.5/6.6 код. Mitigation: thorough manual smoke check после deploy.

## Что НЕ в скоупе

- Полный architectural rewrite sync pipeline (transactional Position + Trade.exit_at update в одной транзакции) — отдельная задача.
- Per-trade live unrealized в Журнале сделок — мы решили оставить как есть для closed trades. Open trades в Журнале просто покажут «открыта» без PnL колонки.
- UI для admin диагностики swept trades — отдельный feature.
- Migration script для historic phantom'ов на других acc'ах — sweep сделает это автоматически при первом sync.
