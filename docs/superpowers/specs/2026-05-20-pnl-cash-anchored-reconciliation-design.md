# Spec: P&L «без расхождения» — клиринговая корректировка как first-class строка + реформа health-бейджа

**Дата:** 2026-05-20
**Статус:** Draft (на ревью пользователя)
**Связано:** [ADR-0007](../../../.business/tech/decisions/0007-pnl-methodology-invariants.md) (амендмент Инв.1), `services/pnl_health_service.py`, `domain/pnl/dashboard_pnl.py`, `routers/real_pnl.py`, `domain/pnl/cash_flow_classification.py`, `domain/enums.py`

## Контекст (что выяснили расследованием)

На acc#4 дневник (Σ net_pnl + unrealized = −249 072.79) расходится с кассой (портфель − депозиты = −271 684.40) на **+22 611.61 ₽ (8.32%)**, и бейдж `pnl_health` показывает это как `mismatch` (тревога).

Декомпозиция расхождения (проверено по БД, касса реконструирована до 23 ₽):
- **−20 953 ₽ (93%)** — дрейф фьючерсной вариационной маржи: журнал считает фьючерс по `body=(exit−entry)×qty×pv` (цены сделок), а брокер реализует через дневную вармаржу по расчётной цене 19:00. Телескопирование ломается на мульти-дневных FX-фьючерсах (BBZ4 и пр.: 81/131 фьючерсов мульти-дневные, pv плавает день-в-день).
- **−1 460 ₽** — account-level сборы (margin/service), не привязанные к сделке.
- остальное — income/налоги/округления.

**Проверено вживую (read-only, токен acc#4):** пер-контрактную вариационную маржу T-Invest API **не отдаёт никак** — при фильтре `instrument_id` вармаржа исчезает (0 ops), gRPC брокер-отчёт вармаржи не содержит вовсе. Значит сделать фьючерсную P&L «как у брокера» по каждой сделке из API **технически невозможно**.

Касса (`portfolio − net_deposits`) — достоверна (сходится до 23 ₽). Это и есть истина.

## Решение

Раз пер-контрактную вармаржу получить нельзя, а касса точна — **делаем расхождение нулём по построению**: неразложимую фьючерсную вармаржу показываем отдельной честной строкой, а бейдж перестаёт называть её «ошибкой».

Кодовая база уже частично готова: `dashboard_pnl.compute_pnl_headline()` уже считает `natural_residual = cash_truth − (realized+unrealized)`. Нужно сделать его **видимой именованной строкой** и реформировать health-бейдж.

### Компонент 1 — «Клиринговая корректировка» как first-class строка P&L

Разложение, которое **сходится к кассе тождественно**:

```
P&L итог (= касса)        = portfolio_value − net_deposits        ← истина
  ├─ Реализованный (сделки) = Σ Trade.net_pnl(closed)
  ├─ Открытые позиции       = Σ Position.unrealized_pnl
  └─ Вармаржа фьючерсов
     (клиринговая корректировка) = natural_residual                ← НОВАЯ строка
```

где `natural_residual = (portfolio_value − net_deposits) − (Σ net_pnl + Σ unrealized)`.

- Дашборд/журнал: показываем все 4 строки; сумма первых трёх + корректировка = касса (видимая сверка для пользователя).

**РЕШЕНО: headline = касса (реальные деньги).** Главное число дашборда = `portfolio_value − net_deposits`. Ниже разложение `realized + unrealized + clearing_adjustment = headline`. Причина: пользователь сверяется именно с реальными деньгами на счёте; корректировка названа честно отдельной строкой. (Отход от Phase 6.4 journal-headline сознательный; журнал-страница сходится к headline с учётом строки корректировки.)

### Компонент 2 — 6-слойный контроль качества данных (defense in depth)

Проблема текущего бейджа: валит в ОДНО число и нормальный ~8% фьючерсный дрейф, и катастрофу ×1000 → не отличает шум от беды (либо ложно орёт, либо проспит). Разделяем тревоги по классу поломки. Каждый слой независим и ловит своё.

| # | Слой | Что ловит | Механизм | Порог тревоги |
|---|---|---|---|---|
| 1 | **Касса-реконструкция** | пропущенные/задвоенные операции, неполный импорт | `net_deposits + Σ категорий` vs `portfolio_value` брокера | \|невязка\| > 100 ₽ и > 0.5% → RED |
| 2 | **Ratio-санити (анти-×1000)** | грубый расчёт: pv ×1000, знак, единицы | `\|journal\| / \|cash\|` | вне [0.3 .. 3.0] → RED |
| 3 | **Клиринг-band** | аномальный рост клиринговой корректировки | `clearing_adjustment / \|cash\|` % | < 5% ok · 5–25% warning · ≥ 25% или > 50 000 ₽ investigate (пороги ADR-0007) |
| 4 | **Outlier по сделке** | один кривой инструмент | топ \|net_pnl\|; \|net_pnl\| > N×\|deposits\| ИЛИ подразумеваемое движение цены нереалистично | configurable, дефолт N=0.5 → флаг |
| 5 | **Трёхсторонняя сверка** | рассинхрон источников | operations ↔ broker_report ↔ portfolio: Σ комиссий, число сделок | расхождение комиссий > 1% или счётчик сделок ≠ → break (уже в `reconciliation_service`) |
| 6 | **Unknown-типы** | новый тип операции от брокера | `real_pnl.unknown_operation_types` лог + полнота `CASH_FLOW_MAP` | любой UNKNOWN с cash-эффектом → warning |

Реализация:
- Слой 3 заменяет текущую «mismatch»-семантику `pnl_health_service`: пороги → ADR-0007 (5/25), `diff` трактуется как «нераспределённая клиринговая вармаржа», не «ошибка».
- Слои 1, 2 — добавить в `pnl_health_service` (дешёвые SQL + деление); это и есть громкая страховка от ×1000-класса.
- Слой 5 — переиспользовать существующие `reconciliation_service` / `reconciliation_runs` / `broker_reports` (комиссии уже сходятся до 7 ₽, число сделок сверяемо); вынести в общий health-сводный статус.
- Слой 6 — уже логируется; добавить в health как warning-флаг + закрыть 4 типами (Компонент 3).
- Итоговый статус health = худший из слоёв, с указанием КАКОЙ слой сработал (а не одно безликое число).

Сценарий-проверка ×1000: pv=1000 на индексном фьючерсе → journal в миллионах при кассе в тысячах → слой 2 (ratio) RED мгновенно + слой 1 показывает гигантскую невязку. Катастрофа громко поймана; нормальные 8% — тихо, отдельной строкой.

### Компонент 3 — 4 новых типа операций (анти-silent-orphan)

SDK 0.3.5 enum содержит типы, которых нет в нашем `domain/enums.py:OperationType` и `CASH_FLOW_MAP`:
`OTHER_FEE`(66), `OTHER`(67), `DFA_REDEMPTION`(68), `PRIMARY_ORDER`(69).
Если придут — попадут в `UNSPECIFIED → UNKNOWN`, не учтутся → тихий orphan, раздув корректировки.

Классификация:
- `OTHER_FEE` → `ATTRIBUTABLE_FEE` (это сбор)
- `OTHER` → `UNKNOWN` (намеренно: семантика неизвестна, пусть видно в unknown-мониторинге)
- `DFA_REDEMPTION` (погашение ЦФА) → `INCOME`
- `PRIMARY_ORDER` (первичное размещение) → `TRADE`

`assert_complete_coverage()` тест гарантирует полноту.

## Файлы к изменению

| Файл | Изменение | Слой |
|---|---|---|
| `domain/enums.py` | +4 значения OperationType | 6 |
| `domain/pnl/cash_flow_classification.py` | +4 записи в CASH_FLOW_MAP | 6 |
| `domain/pnl/data_quality.py` *(new)* | чистые функции слоёв 1,2,4: cash-reconstruction невязка, ratio-санити, per-trade outlier | 1,2,4 |
| `services/pnl_health_service.py` | агрегатор статуса из 6 слоёв; пороги слоя 3 → ADR-0007 (5/25); `clearing_adjustment`; статус указывает сработавший слой | 1,2,3,6 |
| `services/reconciliation_service.py` | вынести Σ комиссий + число сделок (operations↔broker_report↔portfolio) в общий health-сводный статус | 5 |
| `domain/pnl/dashboard_pnl.py` | `natural_residual` → именованное `clearing_adjustment`; headline = cash_truth | — |
| `routers/real_pnl.py` / dashboard endpoint | отдать `clearing_adjustment` строкой + per-layer health в ответе | все |
| frontend (PnLHealthBadge + breakdown card) | headline = касса; строка «Вармаржа фьючерсов (клиринг)»; бейдж показывает какой слой сработал | все |
| `.business/tech/decisions/0008-*.md` | ADR-0008 (амендмент Инв.1: пороги + 6-слойный контроль; фиксация «per-contract VM API недоступна») | — |

## Тесты (TDD)

1. `test_journal_cash_reconcile`: для acc#4 `Σ net_pnl + Σ unrealized + clearing_adjustment == cash_truth` (тождество, до копейки).
2. **Слой 1** `test_cash_reconstruction`: `net_deposits + Σ категорий == portfolio_value` (невязка < 100 ₽); искусственно удалить операцию → RED.
3. **Слой 2** `test_ratio_sanity`: journal=cash → ok; journal = cash×1000 (симуляция pv-бага) → RED; нормальный 8% дрейф → НЕ триггерит.
4. **Слой 3** `test_pnl_health_thresholds`: 8.32% → `ok`/`warning` (не `mismatch`); 30% → `investigate`.
5. **Слой 4** `test_trade_outlier`: трейд с \|net_pnl\| > 0.5×deposits → флаг; нормальные — нет.
6. **Слой 5** `test_threeway_recon`: Σ комиссий operations vs broker_report сходится; рассинхрон числа сделок → break.
7. **Слой 6** `test_cash_flow_classification`: `assert_complete_coverage()` зелёный с 4 новыми типами; каждый маппится в ожидаемую категорию; UNKNOWN с cash-эффектом → warning.
8. `test_dashboard_pnl_headline`: headline == cash_truth; `realized+unrealized+clearing_adjustment == headline`.
9. Регрессия: существующие `test_pnl_calculators`, `test_pnl_health`, `test_dashboard_pnl_headline`, `test_journal_cash_reconcile` зелёные.

## Acceptance

- На acc#4: дневник + строка корректировки = касса (расхождение 0).
- Бейдж не показывает «mismatch» на здоровом фьючерсном счёте; показывает «investigate» только при аномальном росте корректировки.
- `reconcile_journal_vs_cash` и health отражают одну и ту же декомпозицию.

## Вне scope (сознательно НЕ делаем сейчас)

- Самостоятельный пересчёт фьючерсной вармаржи по дневным расчётным ценам 19:00 + FX (свечи MOEX). Большой и хрупкий; делать только если потребуется пер-сделочная фьючерсная точность для аналитики. Зафиксировано в ADR-0008 как возможное будущее.
- Изменение формулы `body`/Инв.6 (telescoping остаётся как есть для пер-сделочного отображения).
