# Inferred Opening-Balance Anchor — Design

**Дата:** 2026-06-26
**Статус:** Draft (на ревью)
**Amends:** ADR-0008 (cash-anchored P&L) — вводит баланс открытия для broker-юзеров с неполной историей депозитов. Будет зафиксировано как **ADR-0010**.

---

## 1. Проблема

При подключении уже торговавшего брокерского счёта Tinkoff `getOperationsByCursor` отдаёт историю только с некоторой даты, а **стартовое финансирование счёта в это окно не попадает** (происходит раньше или приходит переводом бумаг, не cash-операцией).

**Воспроизведено на acc#2 (Артём, 2135909232):**
- Первая операция истории — `buy −93 029,60 ₽` от 05.01.2026, безо всякого пополнения перед ней. `Account.initial_balance = 0`.
- Все `input`-операции = 9 600 ₽ и все за 24–26 июня; `output` −1 044 (январь). `net_deposits = 8 556`.
- ADR-0008 headline P&L = `portfolio − net_deposits = 32 938 − 8 556 = +24 383` — **ложно положительный**.
- Журнал (mark-to-market) = −74 713 ₽ — **корректен** (подтверждено независимо: реальная варм-маржа по операциям = −86 799 ₽ живых денег).
- `clearing_adjustment = cash − journal = +99 096` мис-помечен как «неразложимая вармаржа», хотя это **пропущенный стартовый депозит**.
- Badge: «Расхождение 406%»; доходность «−873%» (= −74 713 / 8 556).

**Корень:** ADR-0008 молча предполагает, что `net_deposits` полные. Когда стартовый капитал вне окна синхронизации, `cash_truth = portfolio − net_deposits` недостоверен → раздувает `clearing_adjustment`, ломает headline и проценты.

**Это норма, а не край:** баланс открытия для уже торговавшего счёта узнать неоткуда при любом подключении. Пользователь его не помнит. Решение обязано быть автоматическим.

**Почему нельзя просто вернуть старый autoset:** PR 21 `_autoset_initial_balance_if_needed` (pipeline) считал `portfolio − cumulative_realized` и **не вычитал депозиты** → систематически завышал старт; его выпилили в PR 22. Наша формула вычитает депозиты и проходит safety-gate (см. §4).

---

## 2. Цель

Сделать так, чтобы для счёта с неполной историей депозитов система **автоматически** восстанавливала опорный баланс открытия, после чего headline P&L, проценты и badge сверки были корректны — **без ввода данных пользователем** и **без сокрытия реальных багов расчёта журнала**.

Не-цели (YAGNI): пер-сделочный пересчёт фьючерсной варм-маржи (ADR-0008 §«вне scope»); поддержка не-Tinkoff брокеров; ручной импорт истории.

---

## 3. Архитектура

### 3.1 Кандидат-якорь (deposit-aware, не как сломанный PR 21)

```
candidate_anchor = portfolio_value − net_deposits − journal_pnl
  где journal_pnl = Σ Trade.net_pnl(closed) + Σ PositionORM.unrealized_pnl
```

Для acc#2: `32 938 − 8 556 − (−74 713) = 99 095 ₽` ≈ пропущенный стартовый депозит (первая сделка — buy 93K, правдоподобно).

По построению `candidate_anchor` приравнивает кассу к журналу в точке T0 → сверка дальше работает **инкрементально** (дрейф ПОСЛЕ T0 ловится; доисторическое прошлое поглощается якорем). Это и есть «сверка-вперёд».

### 3.2 Safety-gate (deposit-независимый — сохраняет защиту ADR-0008)

**Нельзя** использовать слой 2 (`ratio_sanity`) и слой 4 (`trade_outliers`) как гейт: они зависят от сломанной кассы/`net_deposits` (для acc#2 ratio=3.06 уже RED, outliers ложно срабатывают из-за заниженной базы 8 556) → заблокировали бы якорь именно там, где он нужен.

Якорим **только если ВСЕ** гейты пройдены (иначе `initial_balance` остаётся 0, badge показывает реальную проблему — баг журнала не прячется):

- **G1 — знак:** `candidate_anchor > ANCHOR_MIN` (`ANCHOR_MIN = 1 ₽`). `≤0` означает, что журнал ≥ кассы → пропущенного депозита нет, якорить нечего.
- **G2 — телескопирование фьючерсов (главный независимый гейт):** журнальный body фьючерсов должен совпадать с фактической варм-маржой из операций (обе из `OperationORM`, не зависят от депозитов):
  ```
  body_closed   = Σ Trade.pnl где instrument_type_v2='futures' AND exit_at IS NOT NULL
  varmargin_net = Σ payment(accruing_varmargin) + Σ payment(writing_off_varmargin)
  open_settled  = Σ PositionORM.var_margin_rub (futures, осевшая ВМ открытых)
  telescope_residual = | body_closed − (varmargin_net − open_settled) |
  GATE: telescope_residual ≤ TELESCOPE_TOL_PCT × |varmargin_net|   (TELESCOPE_TOL_PCT = 0.25)
  ```
  Для acc#2: `|−70 754 − (−86 799 − (−7 920))| = |−70 754 + 78 879| = 8 125`; `8 125 / 86 799 = 9.4% ≤ 25%` → **PASS**. При баге pv×1000 body ушёл бы в миллионы → residual ≫ 25% → **FAIL** → не якорим, реальный баг виден.
- **G3 — правдоподобная граница (страховка):** `candidate_anchor ≤ ANCHOR_MAX_FACTOR × gross_buy_peak`, где `gross_buy_peak` = крупнейшая `buy`-операция по модулю (deposit-независимая оценка задействованного капитала; `ANCHOR_MAX_FACTOR = 50`). Грубо ловит абсурдно большой якорь, переживший G2.

Если `varmargin_net ≈ 0` (счёт без фьючерсов, чистые акции) — G2 тривиально проходит (residual≈body_closed≈0 на не-фьючерсах), основная защита для акций — G3 + слой 1 (cash reconstruction уже существует).

### 3.3 Когда якорить (детект неполной истории)

```
incomplete_history = первая по executed_at executed-операция счёта НЕ в CashFlowCategory.NET_DEPOSIT
```

То есть счёт начал с торговли/иного события, а не с пополнения → финансирование вне окна. Если первая операция — `input` → история полна, `initial_balance` остаётся 0, `source="complete"`.

### 3.4 Фиксация и источник

- При первом успешном sync, если `incomplete_history AND gate passed AND initial_balance_source ∈ {None, '', 'complete'}`:
  `Account.initial_balance = round(candidate_anchor, 2)`, `Account.initial_balance_source = 'inferred_anchor'`.
- **Заморозка:** на последующих sync якорь не пересчитываем (иначе «гонится за хвостом»). Пересчёт только если: (a) пользователь ввёл реальную сумму → `source='manual'` (приоритет, не перетираем); (b) в новой истории появилась реальная стартовая `input`-операция раньше первой сделки → `source='complete'`, `initial_balance=0`.
- Если гейт НЕ пройден: `initial_balance=0`, `source='inferred_blocked'` (для UI-сигнала «журнал требует проверки»), badge показывает реальный разрыв.

### 3.5 Применение к расчётам

Везде, где сейчас `cash = portfolio − net_deposits`, база депозитов становится **эффективной**:
```
effective_deposits = net_deposits + initial_balance
cash_truth = portfolio_value − effective_deposits
```

Тождество ADR-0008 сохраняется (с корректным cash_truth):
`realized + unrealized + clearing_adjustment == cash_truth`, `clearing_adjustment = cash_truth − journal`. **Следствие back-computed якоря:** в точке T0 `cash_truth ≡ journal` → `clearing_adjustment ≈ 0`, `diff_pct ≈ 0` (якорь поглощает и пропущенный депозит ~91K, и структурный фьюч-дрейф ~8K). Дальше badge растёт по мере НОВОГО фьюч-дрейфа после T0 («сверка-вперёд»). Независимую проверку журнала в T0 берёт на себя **safety-gate G2 (телескоп)**, не badge — осознанный размен, одобренный при согласовании.

**Точки изменения (caller'ы, чистые функции не трогаем):**
- `services/pnl_health_service.py:195-197` — `cash_pnl = portfolio_value − net_deposits − initial_balance`. Слой 1 (`cash_reconstruction_residual`, :229) кормить `net_deposits + initial_balance` как базу.
- `domain/pnl/dashboard_pnl.py:48` (`compute_pnl_headline`) — caller передаёт `net_deposits + initial_balance` в параметр `net_deposits` (функция остаётся чистой).
- `routers/stats.py` — доходность/Calmar/drawdown базируются на `initial_balance + net_deposits` (уже частично через `base_initial_balance`, :346/:384/:532); убрать −873%-артефакт (база была 8 556 → станет ~107 651).

### 3.6 Новая стадия pipeline

`_stage_autoset_inferred_anchor` в `application/sync/pipeline.py`, вызывается в `run()` **после** `_stage_phantom_sweep` (:239, журнал финализирован) и `_stage_mark_to_market` (:224, `last_portfolio_value` свеж), **до** `_stage_pnl_health_check` (:248, чтобы badge считался уже с якорем). Не-фатальна (как health-стадии): исключение логируется, sync не падает.

### 3.7 UI-честность

- Badge/popover сверки и блок доходности: при `source='inferred_anchor'` — подпись «База открытия восстановлена автоматически (не подтверждена депозитами)». При `source='inferred_blocked'` — «Журнал требует проверки: автоякорь не применён».
- Возможность ввести реальную стартовую сумму (→ `source='manual'`). Использует существующий механизм `initial_balance` (поле уже в API: `routers/stats.py:821` отдаёт `initial_balance_source`).

---

## 4. Компоненты и границы

| Юнит | Ответственность | Зависит от |
|---|---|---|
| `domain/pnl/opening_anchor.py` (NEW, чистые функции) | `compute_candidate_anchor()`, `anchor_gate()` (G1/G2/G3) → `AnchorDecision{should_anchor, value, source, reason}` | только Decimal-входы |
| `pipeline._stage_autoset_inferred_anchor` (NEW) | собрать входы из БД, вызвать domain-функцию, записать `Account.initial_balance`+`source` (заморозка/приоритет manual) | opening_anchor, repos |
| `pnl_health_service.compute_health` (MODIFY :195-197,:229) | `effective_deposits` в cash_pnl + слой 1 | Account.initial_balance |
| `dashboard_pnl` caller (MODIFY) | передать effective_deposits | — |
| `routers/stats.py` (MODIFY) | база % = initial_balance+net_deposits; вернуть source для UI | — |
| frontend reconciliation/доходность (MODIFY) | лейблы по `initial_balance_source` | API |
| `ADR-0010` (NEW) | зафиксировать решение, amends ADR-0008 | — |

---

## 5. Edge cases

- **Полная история** (первая op = `input`): не якорим, `source='complete'`, текущее поведение.
- **Чистые акции, без фьючерсов:** G2 тривиален; защита через G1/G3 + слой 1. Кандидат-якорь = пропущенный депозит, безопасно.
- **Гейт заблокировал** (реальный pv-баг): не якорим, `source='inferred_blocked'`, badge честно красный — баг не спрятан.
- **Re-sync:** якорь заморожен; `manual` имеет приоритет и не перетирается.
- **Появился реальный стартовый депозит** в новой истории: `source='complete'`, `initial_balance=0`.
- **`candidate_anchor ≤ 0`** (журнал ≥ кассы): не якорим (нечего восстанавливать).
- **`abs(cash) < NA_CASH_TRUTH_RUB`:** существующая защита diff_pct=0 сохраняется.

---

## 6. Тестирование (TDD)

Unit (`domain/pnl/opening_anchor.py`):
- candidate-формула: acc#2-числа → 99 095.
- G1: anchor ≤0 → no-anchor.
- G2: телескоп в допуске → pass; body×1000 → fail.
- G3: абсурдный якорь → fail.
- чистые акции (varmargin=0) → pass.

Integration (`tests/integration/`):
- pipeline-прогон со сценарием acc#2 (incomplete history + healthy futures) → `initial_balance≈99095`, `source='inferred_anchor'`, последующий `pnl_health` diff_pct < 25%.
- complete-history аккаунт → `initial_balance=0`, `source='complete'`, поведение неизменно.
- pv×1000 сценарий → `source='inferred_blocked'`, badge investigate (баг не спрятан).
- re-sync → якорь не меняется; manual override сохраняется.

Регрессия (ОБЯЗАТЕЛЬНО зелёные, ADR-0007/0008): `test_pnl_calculators.py`, `test_pnl_health.py`, `test_journal_cash_reconcile.py`, `test_dashboard_pnl_headline.py`, `test_pipeline_idempotency.py`.

Sanity (ADR-0007 Инвариант 1 / mandatory): `reconcile_journal_vs_cash --account-id 2` → diff_pct падает с 406% к <25% (ожидаем ~9% фьюч-дрейф), clearing_adjustment ≈ реальная ВМ, headline cash ≈ −74 713.

---

## 7. ADR-0010 (outline, пишется на этапе реализации)

- **Решение:** для broker-юзера с неполной историей депозитов вводится `Account.initial_balance` (`source='inferred_anchor'`) как опорная база; `cash_truth = portfolio − (net_deposits + initial_balance)`.
- **Amends ADR-0008:** §1 (headline cash теперь учитывает initial_balance), §3 (пороги без изменений, но diff_pct теперь меряет дрейф-от-якоря).
- **Что нельзя менять без нового ADR:** убирать safety-gate (G2 телескоп — защита от pv×1000, заменяет роль слоёв 2/4 для anchored-кейса); back-computing якоря без вычитания депозитов (повтор бага PR 21); авто-перетирание `manual`.
- **Гонка с ADR-0008:** identity `realized+unrealized+clearing_adjustment==cash_truth` сохраняется; знак clearing_adjustment не меняется.

---

## 8. Эффект на acc#2

| Показатель | Сейчас | После |
|---|---|---|
| `initial_balance` | 0 | ~99 095 (inferred_anchor) |
| headline cash | +24 383 (ложь) | ≈ −74 713 (верно) |
| badge diff_pct | 406% (investigate) | ≈0% в T0 (ok), растёт с новым фьюч-дрейфом |
| доходность | −873% | ~−69% (база = initial_balance+net_deposits) |
| clearing_adjustment | +99 096 (мис-метка) | ≈0 в T0 (журнал=касса по построению) |
| telescope_residual (gate G2) | — | ~8 125 ₽ / 9% (реальный фьюч-дрейф, проверка журнала) |
