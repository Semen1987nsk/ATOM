# ADR-0010: Inferred Opening-Balance Anchor для broker-счетов с неполной историей депозитов

**Статус:** Принято (2026-06-26). **Amends ADR-0008** §1 (headline cash теперь учитывает `initial_balance`), §3 (пороги без изменений, но `diff_pct` теперь меряет дрейф-от-якоря, а не от нуля).

---

## Контекст

Брокерский счёт подключается в Polistata после начала торговли. T-Bank `getOperationsByCursor` отдаёт историю только с некоторой даты — **стартовое финансирование счёта в это окно не попадает** (происходит раньше или приходит переводом бумаг, не cash-операцией).

**Воспроизведено на acc#2 (Артём, 2135909232):**

- Первая операция истории — `buy −93 029,60 ₽` от 05.01.2026, без предшествующего пополнения. `Account.initial_balance = 0`.
- Все `input`-операции = 9 600 ₽ (24–26 июня); `output` −1 044 ₽ (январь). `net_deposits = 8 556 ₽`.
- ADR-0008 headline P&L = `portfolio − net_deposits = 32 938 − 8 556 = +24 383 ₽` — **ложно положительный**.
- Журнал (mark-to-market) = −74 713 ₽ — **корректен** (независимо подтверждён: варм-маржа по операциям ≈ −86 799 ₽ живых денег).
- `clearing_adjustment = +99 096 ₽` помечается как «неразложимая вармаржа», хотя это **пропущенный стартовый депозит**.
- Badge: «Расхождение 406%»; доходность «−873%» (= −74 713 / 8 556).

**Корень:** ADR-0008 молча предполагает, что `net_deposits` полные. Когда стартовый капитал вне окна синхронизации — `cash_truth = portfolio − net_deposits` недостоверен: раздувает `clearing_adjustment`, ломает headline и проценты.

Это норма при любом подключении уже торговавшего счёта, а не граничный случай. Решение обязано быть автоматическим: пользователь не помнит точный стартовый депозит.

**Почему нельзя просто вернуть старый autoset (PR 21 `tinkoff_derived`):** он считал `portfolio − cumulative_realized`, **не вычитая депозиты** → систематически завышал старт. Выпилен в PR 22 как ненадёжный.

---

## Решение

### 1. Headline cash теперь учитывает `initial_balance` (amends ADR-0008 §1)

```
effective_deposits = net_deposits + initial_balance
cash_truth = portfolio_value − effective_deposits
```

**Тождество ADR-0008 сохраняется:**

```
realized + unrealized + clearing_adjustment == cash_truth
```

где `clearing_adjustment = cash_truth − journal`. Знак не меняется: положительное значение — касса опережает журнал. Изменение знака ломает тождество.

**Следствие back-computed якоря:** в точке T0 `cash_truth ≡ journal` → `clearing_adjustment ≈ 0`. Дальше badge растёт только от нового фьючерсного дрейфа после T0 («сверка-вперёд»).

### 2. Кандидат-якорь (deposit-aware)

```
candidate_anchor = portfolio_value − net_deposits − journal_pnl
  где journal_pnl = Σ Trade.net_pnl(closed) + Σ PositionORM.unrealized_pnl
```

Для acc#2: `32 938 − 8 556 − (−74 713) = 99 095 ₽` ≈ пропущенный стартовый депозит (правдоподобно: первая сделка — buy 93K). По построению приравнивает кассу к журналу в точке T0.

### 3. Safety-gate — deposit-независимый (amends ADR-0008 §3 для anchored-кейса)

Якорь устанавливается **только если ВСЕ гейты пройдены**; иначе `initial_balance = 0`, `source = 'inferred_blocked'`, badge честно показывает реальную проблему.

Слои 2 (`ratio_sanity`) и 4 (`trade_outliers`) ADR-0008 **нельзя** использовать как гейт для anchored-кейса: они зависят от сломанной кассы/`net_deposits` (для acc#2 ratio=3.06 уже RED — заблокировали бы якорь именно там, где он нужен). Их роль для anchored-кейса берут G1/G2/G3:

| Гейт | Условие | Назначение |
|------|---------|-----------|
| **G1 — знак** | `candidate_anchor > 1 ₽` | ≤0 → журнал ≥ кассы → якорить нечего |
| **G2 — телескоп фьючерсов** | `telescope_residual ≤ 0.25 × \|varmargin_net\|` | независимая проверка журнала; ловит pv×1000 (body уходит в миллионы → FAIL) |
| **G3 — правдоподобность** | `candidate_anchor ≤ 50 × gross_buy_peak` | страховка против абсурдно большого якоря, пережившего G2 |

`telescope_residual = |body_closed − (varmargin_net − open_settled)|`, где все входы берутся из `OperationORM` — deposit-независимы.

Для acc#2: telescope_residual = 8 125 ₽ / 86 799 ₽ = 9.4% ≤ 25% → PASS.

### 4. Когда якорить (детект неполной истории)

```
incomplete_history = первая по executed_at выполненная операция НЕ в CashFlowCategory.NET_DEPOSIT
```

Если первая операция — `input` → история полна, `initial_balance = 0`, `source = 'complete'`.

### 5. Заморозка и приоритет

- При первом успешном sync, если `incomplete_history AND gate_passed AND source ∈ {None, '', 'complete'}`: `Account.initial_balance = round(candidate_anchor, 2)`, `source = 'inferred_anchor'`.
- **Заморозка:** последующие sync не пересчитывают якорь («не гнаться за хвостом»).
- **`manual` — приоритет:** пользователь ввёл реальную сумму → `source = 'manual'`; auto-overwrite запрещён.
- Если в новой истории появился реальный стартовый `input` раньше первой сделки → `source = 'complete'`, `initial_balance = 0`.

### 6. Пороги слоя 3 — без изменений (amends ADR-0008 §3, только интерпретация)

```
ACCEPTANCE: diff_pct < 5%   (status ok)
WARNING:    5% ≤ diff_pct < 25%
INVESTIGATE: diff_pct ≥ 25% или |diff_rub| > 50 000 ₽
```

Пороги неизменны; меняется то, что `diff_pct` теперь меряет дрейф **от якоря**, а не от нуля.

---

## Реализующие модули

- `domain/pnl/opening_anchor.py` — чистые функции `compute_candidate_anchor()`, `anchor_gate()` → `AnchorDecision{should_anchor, value, source, reason}`
- `services/opening_anchor_service.py` — собирает входы из БД, вызывает domain-функцию, записывает `Account.initial_balance` + `source`
- `application/sync/pipeline.py::_stage_autoset_inferred_anchor` — pipeline-стадия (после `_stage_phantom_sweep` + `_stage_mark_to_market`, до `_stage_pnl_health_check`); не-фатальна
- `services/pnl_health_service.py` — `effective_deposits = net_deposits + initial_balance` в cash_pnl и слое 1
- `domain/pnl/dashboard_pnl.py` — caller передаёт `effective_deposits`
- `routers/stats.py` — база % = `initial_balance + net_deposits`

---

## Что НЕЛЬЗЯ менять без нового ADR

| Изменение | Почему опасно |
|-----------|--------------|
| Убрать safety-gate G2 (телескоп фьючерсов) | Это единственная deposit-независимая проверка журнала; без неё pv×1000-баг (DAX/Brent/foreign) пройдёт G1/G3 и получит якорь → скроет реальный расчётный баг |
| Back-computing якоря без вычитания депозитов | Повтор бага PR 21 (`tinkoff_derived`): систематическое завышение стартовой базы |
| Авто-перетирание `manual` при каждом sync | Нарушает явный ввод пользователя; единственный способ исправить неверный якорь — перепишет пользовательские данные |
| Изменить знак `clearing_adjustment` на `journal − cash` | Ломает тождество `realized + unrealized + clearing_adjustment == cash_truth` (ADR-0008 §1) |

---

## Связанные документы

- `docs/superpowers/specs/2026-06-26-inferred-opening-balance-anchor-design.md`
- [`ADR-0008`](0008-pnl-cash-anchored-6layer-control.md) — cash-anchored P&L, 6-слойный контроль (amendится этим ADR)
- `docs/ERROR_CATALOG.md` — ERR-115 (false-positive reconcile badge на новых счетах)
- **Supersedes (частично):** ADR-0008 §1 (headline cash формула), ADR-0008 §3 (интерпретация diff_pct)
