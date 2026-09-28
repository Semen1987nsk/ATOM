# ADR-0008: P&L cash-anchored + 6-слойный контроль качества данных

**Статус:** Принято и реализовано (2026-05-21). **Amends ADR-0007** Инвариант 1 (пороги).

---

## Контекст

Расследование 2026-05-20/21. Журнал на фьючерсном счёте структурно расходится с кассой (~8% на acc#4).

Причина — фьючерсный P&L реализуется через дневную вариационную маржу (расчётная цена 19:00 МСК), а **API T-Invest НЕ привязывает вармаржу к контракту** (проверено вживую: фильтр `instrument_id` исключает вармаржу; gRPC брокер-отчёт вармаржи не содержит `instrument_uid`). Значит, пер-контрактную фьючерсную P&L из API получить **НЕВОЗМОЖНО**.

Это не баг синхронизации, не баг attribution — это фундаментальное ограничение API. Расхождение ~8% на фьючерсном счёте является нормой, а не сигналом тревоги.

---

## Решение

### 1. Headline P&L = касса

Основной показатель P&L = `portfolio_value − net_deposits` (кассовая правда брокера).

**Тождество:**

```
realized + unrealized + clearing_adjustment == cash_truth
```

где:
- `realized` = Σ Trade.net_pnl (closed)
- `unrealized` = Σ Position.unrealized_pnl (open)
- `clearing_adjustment` = `cash_truth − (realized + unrealized)` = `cash − journal`

`clearing_adjustment` — честная строка «неразложимая фьючерсная вармаржа»: сумма, которую брокер зачислил/списал через клиринг и которую невозможно привязать к конкретному контракту через API T-Invest.

**Знак:** `clearing_adjustment = cash − journal`. Положительное значение означает, что касса опережает журнал (вармаржа сыграла в плюс); отрицательное — журнал опережает кассу (нереализованный убыток по вармарже ещё не прошёл через клиринг). Изменение знака ломает тождество.

**Реализовано в:** `services/pnl_health_service.py::compute_health`, `domain/pnl/dashboard_pnl.py::compute_dashboard_pnl`.

### 2. 6-слойный контроль качества (defense-in-depth)

Вместо единого флага «mismatch» — шесть независимых слоёв. Итоговый статус = худший из слоёв с указанием сработавшего.

| Слой | Назначение | Источник |
|------|-----------|---------|
| 1. Касса-реконструкция | `portfolio = net_deposits + non_deposit_cash + residual`; residual > порога → RED | `domain/pnl/data_quality.py::cash_reconstruction_residual` |
| 2. Ratio-санити анти-×1000 | `|journal / cash| > 100` → RED (громкая страховка от cached_pv=1000 на DAX/Brent) | `domain/pnl/data_quality.py::ratio_sanity` |
| 3. Клиринг-band (diff_pct) | `<5% ok`, `5–25% warning`, `≥25% investigate` | `services/pnl_health_service.py::_status_from_diff_pct` |
| 4. Per-trade outlier | `|net_pnl| > 50% × net_deposits` по одной сделке → warning | `domain/pnl/data_quality.py::trade_outliers` |
| 5. Трёхсторонняя сверка | operations ↔ broker_report ↔ portfolio; последний `ReconciliationRunORM.status` | `services/pnl_health_service.py` (surface only) |
| 6. Unknown operation types | op_type не в `CASH_FLOW_MAP` с cash-эффектом → warning | `services/pnl_health_service.py` (GROUP BY op_type) |

### 3. Пороги слоя 3 (амендмент Инварианта 1 ADR-0007)

**ADR-0007 Инвариант 1 заменяется на:**

```
ACCEPTANCE: diff_pct < 5%  (status ok)
WARNING:    5% ≤ diff_pct < 25%
INVESTIGATE: diff_pct ≥ 25% или |diff_rub| > 50 000 ₽
```

Статус-литерал `mismatch` (ADR-0007) → `investigate` (ADR-0008). Смена обоснована: «mismatch» подразумевал баг, «investigate» — требует анализа (может быть нормой для фьючерсных счетов).

### 4. Расширение CASH_FLOW_MAP

Добавлены 4 типа операций: `OTHER_FEE`, `OTHER`, `DFA_REDEMPTION`, `PRIMARY_ORDER`. Источник: `domain/pnl/cash_flow_classification.py`.

---

## Что НЕЛЬЗЯ менять без нового ADR

| Изменение | Почему опасно |
|-----------|--------------|
| Убрать слой 2 (ratio-санити) | Это громкая страховка от ×1000 cached_pv на DAX/Brent/foreign futures; без неё раздутый journal пройдёт все остальные проверки |
| Изменить знак `clearing_adjustment` на `journal − cash` | Ломает тождество `realized + unrealized + clearing_adjustment == cash_truth`; dashboard и health check перестанут сходиться |
| Вернуть статус-литерал `mismatch` | Введёт пользователей в заблуждение при структурно-нормальных фьючерсных расхождениях |
| Изменить порог слоя 3 без обновления reconciliation tolerance | Diff_pct станет misleading; пройдёт merge P&L работы с реальной проблемой |

---

## Вне scope (будущее)

Самостоятельный пересчёт фьючерсной вармаржи по дневным расчётным ценам 19:00 МСК + FX (свечи MOEX) — только если потребуется **пер-сделочная** фьючерсная точность. Потребует: `settlement_price` snapshots из MOEX ISS, FX курс ЦБ на каждый клиринг, сопоставление с `OperationORM.accruing_varmargin` по дате. Цена: значительная сложность + риск расхождения с broker при корпоративных событиях. ADR-0008 сознательно откладывает это.

---

## Связанные документы

- `docs/superpowers/specs/2026-05-20-pnl-cash-anchored-reconciliation-design.md`
- `domain/pnl/data_quality.py`
- `services/pnl_health_service.py`
- `domain/pnl/dashboard_pnl.py`
- **Supersedes (частично):** ADR-0007 Инвариант 1 (пороги и статус-литерал)
