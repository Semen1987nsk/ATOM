# ADR-0009: MVP — плоский Free / Pro 399₽; reverse-trial переносится в fast-follow

**Статус:** Принято (2026-06-23).
**Связь:** Дополняет (НЕ отменяет) [`ADR-0005`](0005-reverse-trial-model.md). Reverse-trial остаётся целевой моделью, но **секвенируется**: MVP стартует плоским Free/Pro, reverse-trial включается fast-follow после приёма платежей.

## Контекст

Идём в MVP при ограниченном ресурсе. Владелец предложил модель: «Free = ручной ввод + 4-5 ключевых метрик; всё остальное = 399₽/мес». Оценка 4-линзовой панелью (активация / монетизация / стоимость сборки / конкуренты) + сверка с каноном дали единогласный вердикт `needs_adjustment` с двумя поправками (ниже).

Проверка кода (2026-06-23) подтвердила: reverse-trial-машинерия **написана, но висит орфаном** —
`backend/services/subscription_service.py` содержит `start_trial`/`expire_trials`/`to_status_payload`/`free_plus`, есть миграция `0019_reverse_trial.py`, модели и фронт-компоненты (`SubscriptionContext`, `FrozenFeatureBadge`, `TrialCountdownBanner`, `TrialEndedDialog`), **но**: `start_trial` не вызывается при регистрации, `expire_trials` не в планировщике, а живые роутеры (`trades.py`, гейтинг-тесты) сидят на **старом** `backend/subscription_service.py` (plan-enum). Две параллельные подписочные системы, новая не подключена. ЮKassa — заглушка (общий блокер запуска).

## Решение

**MVP = плоский Free / Pro 399₽ / Corporate.** Граница ценности: **импорт ВСЕГДА бесплатен** (это aha-момент активации и двигатель виральности, а не depth-gate); платный гейт — автоматизация и risk-adjusted глубина.

| План | Цена | Что входит | Роль |
|---|---|---|---|
| **Free** | 0₽ навсегда | Безлимит сделок; ручной ввод **+ импорт CSV/Excel (Тинькофф/Финам/БКС)**; 6 базовых метрик (PnL, WinRate, Profit Factor, Expectancy, R-Multiple, Equity curve); 1 счёт; экспорт CSV | Активация + виральность; бьёт бесплатный Тинькофф |
| **Pro** | 399₽/мес (3990₽/год) | Всё из Free + **API-автосинк Тинькофф** + AI-инсайты + live MAE/MFE + Trade Replay + продвинутые метрики (Sharpe/Sortino/Calmar/Ulcer/K-Ratio, Optimal f/SQN/Monte Carlo) + до 5 счетов + безлимит PDF + приоритетная поддержка | Depth-gate: «привык к автоматизации → на Free снова CSV руками → платит» |
| **Corporate** | по запросу | Командное (multi-account, white-label, SSO, SLA) | B2B |

### Поправки к исходной идее владельца (зафиксировано)

1. **Импорт остаётся бесплатным** — НЕ «ручной ввод only». Платный импорт = стена на входе → Free мёртв при рождении (проигрывает бесплатному автозаполненному Тинькоффу), обрывается виральная петля. Гейтим **непрерывный автосинк**, а не разовый импорт.
2. **6 базовых метрик, а не 4-5.** Урезание ничего не экономит, но ослабляет Free против Тинькоффа. Все 6 дёшевы и не создают upgrade-давления — отдаём смело. Equity curve обязателен (главный share-объект).

### 6 бесплатных метрик

PnL · WinRate · Profit Factor · Expectancy · R-Multiple · Equity curve.

### Что в Pro как depth-gate (явно)

API-автосинк Тинькофф (триггер №1) · AI-инсайты (на Free — тизер: видны 2 последних) · live MAE/MFE из MOEX · продвинутые/risk-adjusted метрики · Trade Replay · >1 счёт.

## Reverse-trial (ADR-0005) — НЕ отменён, перенесён в fast-follow

Reverse-trial остаётся целевой моделью ради конверсии **7-10% vs 3-5%** у плоского freemium (главная причина ADR-0005). Поскольку машинерия уже написана (см. контекст), включение = **подключение орфана**, а не стройка с нуля:

1. вызвать `start_trial` в регистрации (`auth.py`);
2. повесить `expire_trials` (ежечасно) в планировщик;
3. **унифицировать две подписочные системы** (старый plan-enum ↔ `services/subscription_service`) — главный риск, требует аккуратности;
4. развесить `FrozenFeatureBadge` на Pro-виджеты, capability-гейтинг в живых роутерах;
5. вебхук ЮKassa → `upgrade_to_pro`.

**Условие старта fast-follow:** после закрытия ЮKassa (54-ФЗ чеки) и стабилизации MVP. До этого reverse-trial не трогаем — два десинхронизированных слоя опасно сводить под нагрузкой запуска.

## Что меняется в коде на MVP

- **Снять FREE-лимит 50 сделок** (`backend/subscription_service.py`): Free безлимитен по сделкам (соответствует ADR-0005 «лимит 50 больше не существует» + новой модели). `enforce_trade_limit` → no-op-seam. AI остаётся за `require_pro`.
- **`frontend/src/app/pricing/page.tsx`** переписана под Free (безлимит+импорт+6 метрик) / Pro 399 / Corporate; сравнительная таблица и FAQ выровнены; убрано «50 сделок» и обещание trial.
- **Лендинг (`Landing.tsx`) + `help/page.tsx`**: убраны «50 сделок» и неподкреплённое «21 день Pro в подарок» (на MVP trial не выдаём → честная копирайт-граница).
- `pricing/page-v2.tsx` (черновик reverse-trial Trial/Free+/Pro) **оставлен как заготовка** для fast-follow, в роутинг не включён.
- Полное enforcement-гейтинг MAE/MFE/advanced/autosync на уровне роутеров — **не в MVP** (платежей нет, два слоя десинхронизированы); приходит вместе с reverse-trial-подключением.

## Последствия

**Плюсы:** честный быстрый запуск без trial-машинерии; одна понятная граница (импорт free / автосинк Pro); конфигурация совместима с reverse-trial поверх того же feature-split.

**Минусы / риски:** конверсия на MVP ниже целевой reverse-trial (3-5% vs 7-10%) — принимаем как временную цену простоты; фактическое feature-gating (MAE/MFE/advanced) на MVP не enforced на бэкенде — но это безвредно, т.к. платный тариф нельзя активировать без ЮKassa.

## Связанное

- [`ADR-0005`](0005-reverse-trial-model.md) — целевая reverse-trial модель (секвенирована этим ADR)
- [`sales/pricing.md`](../../sales/pricing.md) — действующая сетка
- [`sales/tariff-comparison.md`](../../sales/tariff-comparison.md) — сравнение с конкурентами
- [`product/personas.md`](../../product/personas.md) — P1, aha-момент импорта
- [`strategy/roadmap.md`](../../strategy/roadmap.md) — Q2 2026 (ЮKassa → fast-follow reverse-trial)
