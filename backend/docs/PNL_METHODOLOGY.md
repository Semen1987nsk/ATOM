# P&L Methodology

Формальная спецификация расчёта P&L в Empirik/ATOM. Обновлена 2026-05-17
(Plan `lazy-meandering-bonbon`).

## 1. Основные формулы

### 1.1 Cash truth (ground truth)

```
cash_pnl = Account.last_portfolio_value − net_deposits(period)
```

Где `net_deposits` — Σ payment всех операций с категорией `NET_DEPOSIT`
из единого классификатора ([cash_flow_classification.py](../domain/pnl/cash_flow_classification.py)):

- `input`, `output`
- `input_swift`, `output_swift`
- `input_acquiring`, `output_acquiring`
- `inp_multi`, `out_multi`

НЕ включает:
- `trans_iis_bs`, `trans_bs_bs` — внутренние переводы между счетами (зеркальная запись)
- `input_securities`, `output_securities` — paper transfers без cash impact

### 1.2 Journal P&L

```
journal_pnl = Σ closed Trade.net_pnl
            + Σ open PositionORM.unrealized_pnl
            + Σ open Trade.margin_fee_attributed
            + Σ open Trade.service_fee_attributed
            + Σ open Trade.other_fees_attributed
```

**Не включает open Trade.varmargin_attributed** — для futures variation margin
уже captured в `Position.unrealized_pnl = (current - avg_entry) × qty × point_value`,
double-count исключён.

### 1.3 Verification invariant

```
|journal_pnl − cash_pnl| < max(100₽, 1% × |cash_pnl|)
```

Запуск: `python -X utf8 -m tools.reconcile_journal_vs_cash --user-id N`.

Для аккаунтов с pre-sync state используется flag `--baseline-date YYYY-MM-DD`
+ опциональный `--initial-portfolio-value`.

## 2. Per-trade computation

### 2.1 FIFO matching → Trade.pnl (body)

#### Shares / ETF / Currency / Bonds / Options
Для каждого закрытого trade:
```
pnl_body = exit_payment_total + entry_payment_total
```
Это эквивалентно `(exit_price − entry_price) × qty` (payments уже с правильным знаком).

#### Futures (Phase 8, 2026-05-17)
```
pnl_body = (exit_price − entry_avg_price) × quantity × point_value × sign(direction)
```
- `point_value = min_price_increment_amount / min_price_increment` (T-Bank docs)
- `sign = +1` для LONG, `−1` для SHORT
- Цены в **пунктах** (Tinkoff API), `point_value` переводит в рубли

**Почему НЕ payment-based для futures**: Tinkoff API отправляет BUY/SELL
payment для futures в формате `qty × price` (или близком), но реальный
cash flow по фьючерсу проходит через variation margin clearing'и MOEX.
Использование payments в body давало бы double-count с varmargin attribution.

**Почему НЕ body=0 (как было в Phase 6)**: MOEX post-clearing settlements
(приходящие ПОСЛЕ exit_at — типично через 1-4 часа) падали в orphan
varmargin вместо конкретного trade. Journal терял per-trade точность.

**Математическое тождество** (telescoping sum):
```
Σ daily_varmargin(entry → exit + post_clearing) = (exit − entry) × qty × pv
```
Daily varmargin = `(clearing_today − clearing_yesterday) × qty × pv`.
Сумма от entry_clearing до exit_clearing + финальный post-exit settlement
тождественно равна (exit_price − entry_price) × qty × pv.

#### Verification observability
`tools/verify_futures_body.py` — для каждого closed futures trade
сравнивает `Trade.pnl` с Σ varmargin ops в окне `[entry_at, exit_at + 4h]`
per-instrument (если Tinkoff отправляет varmargin с instrument_uid/figi).
Diff > 5% или > 100 ₽ — flag для investigation.

### 2.2 Trade.net_pnl recompute (после attribution)

```
base = Trade.pnl − |Trade.commission|
net_pnl = base + varmargin_attributed + margin_fee_attributed + service_fee_attributed + other_fees_attributed
```

Хранится отдельно `Trade.pnl` (gross body) и `Trade.commission` (per-trade
broker commission, abs), чтобы recompute был идемпотентен.

## 3. Fee attribution

Account-level cash flows без `instrument_uid` распределяются пропорционально
по active trades в момент `op.executed_at`. Notional weight:
```
weight(trade) = |qty × entry_price × point_value|
```

### 3.1 Категории и колонки

| Category | OperationType примеры | Trade column |
|----------|----------------------|--------------|
| `VARMARGIN` | accruing_varmargin, writing_off_varmargin | `varmargin_attributed` |
| `ATTRIBUTABLE_FEE` (margin-like) | margin_fee, overnight, over_com | `margin_fee_attributed` |
| `ATTRIBUTABLE_FEE` (service-like) | service_fee, track_mfee, track_pfee, success_fee, cash_fee, out_fee, out_stamp_duty, output_penalty, advice_fee | `service_fee_attributed` |
| `TAX` | tax, tax_progressive, benefit_tax, benefit_tax_progressive, tax_correction*, tax_repo* (6 типов) | `other_fees_attributed` |
| `INCOME` | dividend, dividend_transfer, div_ext, coupon, bond_repayment*, future_expiration, option_expiration, over_income, over_placement | `other_fees_attributed` (с положительным знаком) |
| `INCOME_TAX` | dividend_tax*, bond_tax*, tax_correction_coupon | `other_fees_attributed` |
| `BROKER_COMMISSION` | broker_fee | Direct в Trade.commission (per-trade match) |
| `NET_DEPOSIT`, `INTERNAL_TRANSFER`, `SECURITY_TRANSFER`, `TRADE`, `DELIVERY` | n/a | Не attributable, обрабатываются отдельно |

### 3.2 VARMARGIN-only-to-FUTURES правило (Phase 3c, 2026-05-17)

Если varmargin op БЕЗ `instrument_uid` (account-aggregated, обычное
поведение Tinkoff API), то filter active trades = **только `instrument_type == FUTURES`**.

**Зачем**: до фикса акции получали "phantom varmargin" — варм-маржа
распределялась пропорционально и на shares (т.к. их notional weight ненулевой).
На acc#4 это давало -9,174₽ phantom loss. Теперь shares получают 0.

Edge case: если на момент varmargin op нет active FUTURES trade —
операция считается **orphan** (logged in reconcile report).

### 3.3 VARMARGIN-skip-for-closed правило (Phase 8.2, 2026-05-17)

VARMARGIN op для **closed futures trade с `Trade.pnl != 0`** (Phase 8
body уже вычислена) НЕ распределяется — иначе double-count с body
по telescoping identity.

Conditional check:
```python
if category == VARMARGIN and trade.exit_at is not None
   and trade.pnl is not None and trade.pnl != 0:
    skip  # body уже включает варм-маржу
```

**Backwards-compat**: для legacy trades с `Trade.pnl = 0` (Phase 6 state
или pre-sync history без надёжных pv) varmargin продолжает attribute'ться
как раньше. Это позволяет miграцию accounts постепенно: Phase 8 recompute
переключает аккаунт на новую модель, без recompute — legacy behavior.

## 4. Известные orphan categories

`reconcile_journal_vs_cash` явно показывает orphans — cash flows которые не
попали ни в Trade, ни в Position, ни в attribution:

- **varmargin orphan** — варм-маржа в моменты без active futures (например,
  пользователь закрыл все futures перед клирингом, варм-маржа дня ещё пришла).
- **attributable_fee orphan** — fee ops без active trades.
- **income orphan** — dividend/coupon когда уже нет owning trade (например,
  дивы пришли после закрытия позиции).
- **broker_commission_extra** — broker_fee которые не попали в Trade.commission
  (обычно из-за FIFO match miss).

Orphan не блокирует launch, но требует мониторинга. Cumulative orphan > 5%
от total cash flows = повод для investigation.

## 5. Account.last_portfolio_value semantics

Snapshot `portfolio.total_amount_portfolio` из Tinkoff API, обновляется
после каждого sync через `_stage_mark_to_market`. Для futures Tinkoff
формула aggregation — special:
- `total_amount_currencies` (cash + frozen margin)
- `total_amount_futures` (intraday MTM since last settle ИЛИ full notional —
  зависит от typecode; точное documentation: developer.tbank.ru)

Это означает что для leveraged futures portfolio с FX-adjusted price scale,
наша Position.unrealized_pnl (`(current - avg_entry) × qty × static_pv`) может
отличаться от того что Tinkoff показывает в portfolio. Residual diff на acc#4
~84k частично обусловлен этим расхождением.

## 6. Pre-sync state handling

Если аккаунт подключён к Tinkoff после периода активной торговли, операции
ДО `BrokerConnection.sync_from_date` нам не доступны. `Account.initial_balance`
(source=`tinkoff_derived`) может содержать оценку pre-sync portfolio, но
для cash truth она не используется.

Mitigation: запуск reconcile с `--baseline-date` + `--initial-portfolio-value`
для аккаунтов с pre-sync history. Residual diff < 1k₽ после baseline = release-ready.

### 6.1 Data quirk: acc#4 historical futures pv (2026-05-17)

При исследовании Phase 8 на acc#4 обнаружено: для исторических контрактов
DXH5 (Dollar Index, март 2025) и BBZ4 (Brent, декабрь 2024) применение
формулы `body = (exit − entry) × qty × pv` даёт суммарный loss ~10M ₽,
что катастрофически расходится с broker truth (-248,553 ₽) и Σ varmargin
в БД (-268,317 ₽).

**Корень**: для этих контрактов `min_price_increment_amount/min_price_increment`
в `InstrumentORM` даёт pv=1000, но фактический cash impact (через
varmargin clearing) показывает что real pv для этих типов контрактов
существенно меньше (или varmargin для них поступал агрегированно и/или
часть pre-sync history варм-маржи не реплицирована Tinkoff'ом).

**Decision (2026-05-17)**: Phase 8 code (compute() + conditional skip)
deployed, но **recompute Trade.pnl для существующих acc#4 closed futures
НЕ применяется**. Аккаунт остаётся в legacy state (Trade.pnl = 0,
varmargin distributed как раньше). Новые closed futures на этом аккаунте
(после sync с момента deploy) будут использовать Phase 8 formula
автоматически.

**Detection**: `tools/verify_futures_body --account-id N --show-all` —
если outliers > 5% от total — НЕ запускать recompute_closed_futures_body.
Расследовать причину (pv data integrity, sync coverage).

Acc#4 текущий результат (2026-05-17, conditional Phase 8.2):
- Dashboard "Общий PnL" = -249,560 ₽
- Broker truth = -248,553 ₽
- Natural diff = -1,007 ₽ (0.41%) ✅

## 7. Multi-currency

Текущая реализация: **RUB-only**. Trade.currency = "rub" по умолчанию для
всех MOEX операций. Futures denominated в USD/CNY (например ETM6 Brent, XIM6
USDRUB) хранят `min_price_increment_amount` в RUB (на момент сделки), но
точная FX-adjusted текущая цена через Tinkoff API может различаться.

Для запуска USD/CNY positions потребуется отдельный feature — FX rate snapshots
+ multi-currency P&L консолидация. Не блокирует launch на 1000 RU-юзеров.

## 8. Coverage invariant test

`tests/unit/test_cash_flow_classification.py::test_coverage_invariant` —
проверяет что **каждый** `OperationType.value` имеет запись в `CASH_FLOW_MAP`.
При добавлении нового типа в `domain/enums.py` без записи в классификатор —
pytest падает. Защита от silent regression.

## 9. Cross-references

- Plan: `C:\Users\Administrator\.claude\plans\lazy-meandering-bonbon.md`
- Phase 1 audit: `C:\Users\Administrator\Empirik\audit_phase1_summary.md`
- Classifier: `domain/pnl/cash_flow_classification.py`
- Attribution: `domain/pnl/fee_attribution.py`
- Reconcile tool: `tools/reconcile_journal_vs_cash.py`
- Real_pnl router: `routers/real_pnl.py`
- Pipeline stage: `application/sync/pipeline.py:_stage_attribute_fees`
- Tests:
  - `tests/unit/test_cash_flow_classification.py` (45 tests, coverage invariant)
  - `tests/unit/test_journal_cash_reconcile.py` (19 tests, scenarios)
  - `tests/unit/test_fee_attribution.py` (existing, обновлены под новый API)
