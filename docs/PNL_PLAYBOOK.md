# P&L PLAYBOOK — практический cheatsheet

> **Когда читать:** перед любой работой над журналом, attribute_fees, FIFO, дашбордом, расходами, реконсиляцией. Формальные инварианты — в [ADR-0007](../.business/tech/decisions/0007-pnl-methodology-invariants.md). Этот файл — быстрые рецепты «куда смотреть».

## Карта истины

```
┌─────────────────────────────────────────────────────────────────┐
│  OPERATIONS (Tinkoff API getOperations_by_cursor)               │
│  → OperationORM (raw stream)                                    │
└────────────────────────┬────────────────────────────────────────┘
                         │
       ┌─────────────────┼─────────────────────┐
       ▼                 ▼                     ▼
  ┌─────────┐      ┌──────────┐         ┌─────────────┐
  │ FIFO    │      │ attribute│         │ Tinkoff     │
  │ matcher │      │ _fees    │         │ getPortfolio│
  └────┬────┘      └──────┬───┘         └──────┬──────┘
       │                  │                    │
       ▼                  ▼                    ▼
  Trade (closed)    Trade.*_attributed   Position.unrealized
  pnl, net_pnl      margin/service/      = expected_yield_rub
  exit_price        varmargin (open only) (truth от broker)
       │                  │                    │
       └────────────┬─────┴────────────────────┘
                    ▼
            journal_pnl
            = Σ Trade.net_pnl(closed) + Σ Position.unrealized_pnl

            cash_pnl = Account.last_portfolio_value − Σ NET_DEPOSITS

            CHECK: diff_pct < 5% → OK
```

## Когда числа не сходятся — куда смотреть

### Симптом: дашборд показывает миллионы при балансе в тысячах

**Проверь:**
1. Top-10 worst trades — это **futures с body в миллионах**?
2. Их `point_value_source` — `cache` или `empirical_payment`?
3. Если `cache` для индексных/foreign фьючерсов (DAX, Brent, BB*, DX*, etc) — **Инвариант 5 нарушен**.

**Fix:** убедись что `domain/pnl/futures.py:_resolve_pv()` синхронизирован с `_compute_point_value_snapshot()` в FIFO. После fix — force rebuild trades (см. рецепт ниже).

### Симптом: P&L = 0 ₽ но % = −12.83% (или другой ненулевой)

**Проверь:**
1. Эти Trade имеют `exit_reason='phantom_sweep'`?
2. У них `exit_price == entry_price`?
3. `varmargin_attributed != 0` (накопленная варм-маржа)?

**Это означает** что SELL operation НЕ дошла из Tinkoff API → phantom_sweep закрыл fallback'ом. **Не баг логики**, баг **синхронизации**.

**Fix:** проверь cursor через **Инвариант 8** — если stale → reset:
```python
from database import SessionLocal
from models import BrokerConnection
s = SessionLocal()
bc = s.query(BrokerConnection).filter_by(account_id=ACCT, is_active=True).first()
bc.sync_cursor = ''
s.commit()
```
Затем trigger sync через `POST /broker/connections/{id}/sync`.

### Симптом: журнал и cash расходятся > 5%

**Проверь по убыванию вероятности:**
1. Все ли operations в БД? `latest OperationORM.executed_at vs Tinkoff API getOperations` (см. Инвариант 8)
2. Phantom Trades в БД? `Trade.exit_at IS NULL AND instrument_uid NOT IN active_positions`
3. Top outliers — реалистичные? (раздел выше)
4. attribute_fees запустился? `Trade.margin_fee_attributed` non-zero для periods где были margin fees?
5. `last_pnl_health_breakdown` — что в components?

### Симптом: открытая позиция показывает странный unrealized

**Проверь:**
1. `PositionORM.expected_yield_rub` пришёл от Tinkoff (не NULL)?
2. Если NULL — мы упали на fallback formula `(current − avg) × qty × cached_pv` — для FX-фьючерсов это даёт ошибку (см. Инвариант 2).
3. `PositionORM.unrealized_pnl == expected_yield_rub`?

## Force-rebuild всех closed trades (один-разовая операция)

После изменения formula в `FuturesPnLCalculator.compute()` или `_resolve_pv()`:

```python
from database import SessionLocal
from models import OperationORM
from adapters.persistence.operation_repo import OperationRepository
from adapters.persistence.instrument_repo import InstrumentRepository
from adapters.persistence.trade_repo import TradeRepository
from application.fifo_matching import FIFOMatchingService

ACCOUNT_ID = 4

s = SessionLocal()
instrument_repo = InstrumentRepository()
op_repo = OperationRepository()
trade_repo = TradeRepository()
fifo = FIFOMatchingService()

uids = [r[0] for r in s.query(OperationORM.instrument_uid).filter(
    OperationORM.account_id == ACCOUNT_ID,
    OperationORM.instrument_uid.isnot(None),
).distinct().all()]

for uid in uids:
    instrument = instrument_repo.get_by_uid(s, uid)
    if instrument is None: continue
    all_ops = op_repo.fetch_for_instrument(s, account_id=ACCOUNT_ID, instrument_uid=uid)
    if not all_ops: continue
    result = fifo.match(
        account_id=ACCOUNT_ID, instrument=instrument,
        operations=all_ops, existing_open_lots=(),
    )
    open_trades = FIFOMatchingService.open_trades_from_lots(
        lots=result.open_lots, instrument=instrument, account_id=ACCOUNT_ID,
    )
    trade_repo.replace_for_instrument(
        s, account_id=ACCOUNT_ID, instrument_uid=uid,
        trades=list(result.closed_trades) + list(open_trades),
        instrument=instrument,
    )
s.commit()
```

Затем — trigger sync (через API) чтобы запустить `attribute_fees` + `pnl_health_check`.

## Diagnostic queries (быстрые)

```python
from database import SessionLocal
from models import Trade, Account, OperationORM, BrokerConnection
from sqlalchemy import func
s = SessionLocal()

# Total journal P&L
sum_closed = s.query(func.sum(Trade.net_pnl)).filter(
    Trade.account_id==ACCT, Trade.exit_at.isnot(None)
).scalar()

# Cash truth
acc = s.query(Account).filter_by(id=ACCT).first()
print(f'last_portfolio_value: {acc.last_portfolio_value}')
print(f'last_pnl_health: {acc.last_pnl_health_status} diff_pct={acc.last_pnl_health_diff_pct}')

# Phantom trades
phantoms = s.query(Trade).filter_by(account_id=ACCT, exit_reason='phantom_sweep').count()
print(f'Phantom-swept trades: {phantoms}')

# Top worst trades
worst = s.query(Trade).filter(
    Trade.account_id==ACCT, Trade.exit_at.isnot(None)
).order_by(Trade.net_pnl.asc()).limit(5).all()
for t in worst:
    print(f'  {t.symbol} qty={t.quantity} body={t.pnl} net={t.net_pnl} pv={t.point_value} src={t.point_value_source}')

# Stale cursor check
bc = s.query(BrokerConnection).filter_by(account_id=ACCT, is_active=True).first()
print(f'sync_cursor: {bc.sync_cursor[:30] if bc.sync_cursor else None}')
latest_op = s.query(OperationORM.executed_at).filter_by(account_id=ACCT).order_by(
    OperationORM.executed_at.desc()
).first()
print(f'latest op: {latest_op[0] if latest_op else None}')
```

## Файлы — кто за что отвечает

| Файл | Ответственность |
|---|---|
| `domain/pnl/futures.py` | Body formula для closed futures + pv resolution |
| `domain/pnl/shares.py`, `bonds.py`, `options.py` | Body для не-futures |
| `application/fifo_matching.py` | FIFO matcher → Trade rows + pv snapshot |
| `application/sync/fee_attribution.py` | Распределение margin/service/varmargin/other по trades |
| `application/sync/pipeline.py:_stage_mark_to_market` | Position snapshot from Tinkoff portfolio |
| `application/sync/pipeline.py:_stage_phantom_sweep` | Закрытие фантомных Trade |
| `application/sync/pipeline.py:_stage_fetch` | Operations sync + AU3+ stale-cursor fallback |
| `services/pnl_health_service.py` | Reconciliation: journal vs cash check |
| `routers/stats.py`, `routers/trades.py` | API endpoints для дашборда + журнала |
| `tools/reconcile_journal_vs_cash.py` | Manual reconcile script |

## Тесты которые ОБЯЗАНЫ остаться зелёными

```bash
pytest tests/unit/test_pnl_calculators.py
pytest tests/unit/test_pnl_health.py
pytest tests/unit/test_journal_cash_reconcile.py
pytest tests/integration/test_pipeline_idempotency.py
pytest tests/integration/test_cursor_stale_fallback.py
```

## Ссылки

- **Формальные инварианты (immutable):** [ADR-0007](../.business/tech/decisions/0007-pnl-methodology-invariants.md)
- **Position = source of truth:** [spec 2026-05-19](superpowers/specs/2026-05-19-position-source-of-truth-design.md)
- **Coding conventions:** [CODING_CONVENTIONS.md](CODING_CONVENTIONS.md)
- **Pre-flight:** [PREFLIGHT_CHECKLIST.md](PREFLIGHT_CHECKLIST.md)
