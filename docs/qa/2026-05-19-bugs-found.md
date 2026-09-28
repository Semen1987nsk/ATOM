# Bugs found during QA walk-through — 2026-05-19

**Tester:** Claude (chrome-devtools MCP)
**Account:** sarvanidi87@gmail.com (Семен), 296 closed trades, 1 open position
**Branch:** `feature/costs-breakdown-card`
**HEAD:** `445313f` (post-Task 6 fix)
**Domains tested:** Auth, Dashboard, Journal, Positions, Анализ (6 страниц), Профиль, Брокеры
**Console errors found:** 0

---

## Verified working ✅

- **Backend `GET /trades/{trade_id}`** — реальный smoke: GET /trades/6313 → 200, modal заполнен реальными данными (SiM6, entry 72686.5, commission 218.05, qty 12, entry_at 2026-05-19T13:04). Critical fix `445313f` подтверждён.
- **Sidebar nav** — «Дневник сделок», «Открытые позиции» рендерятся корректно (Tasks 3 + 4cf729c).
- **`/positions`** — expand row → executions list → кнопка «Редактировать» → modal. Полный flow работает.
- **`/history`** фильтр — нет «ОТКРЫТА» badge, нет status-toggle (Task 1 + 994de2a).
- 0 client-side console errors на 8 страницах.

---

## Bugs sorted by severity

### 🔴 Critical

#### BUG-002: «не число ₽» в карточке «Портфель» на Dashboard
**Where:** Dashboard → правая карточка «Портфель» → строка под Валютой.
**Actual:**
```
52 514 ₽   Валюта
"не число ₽"   нереализ.    ← BUG
```
**Expected:** Числовое значение unrealized PnL (например `-19 086 ₽`).
**Cause:** Helper formatMoney/похожий получает NaN/undefined и возвращает строку `"не число"` вместо `—` или `0 ₽`.
**Probable location:** [`frontend/src/components/dashboard/`](../../frontend/src/components/dashboard/) — карточка Portfolio*. Grep по строке `"не число"` найдёт сразу.
**Fix:** Защитный formatter — для NaN/undefined возвращать `—`.

#### BUG-PREV-001: Journal expand-all — 1 клик → 39 строк
**Where:** `/history` — клик одной строки → 39 строк развернулись (verified script).
**Root cause:** [`PositionJournalView.tsx:1003`](../../frontend/src/components/PositionJournalView.tsx#L1003):
```ts
const stateKey = parseInt(`${p.position_id}${p.account_id}`) || p.position_id;
```
Для legacy сделок (без `position_id`) → `parseInt("undefinedNN")` = `NaN` → `|| p.position_id` (тоже undefined) → все undefined-ключи попадают в один Set.
**Fix:**
```ts
const stateKey = p.position_id != null ? p.position_id : `legacy-${p.symbol}-${p.first_entry_at}`;
```
Или используй `key` ([line 1002](../../frontend/src/components/PositionJournalView.tsx#L1002)) который уже уникален: `const key = \`${p.instrument_uid || p.symbol}-${p.position_id}\`;` — но Set<number> придётся менять на Set<string>.

### 🟠 Important

#### BUG-003: Equity curve tooltip — устаревшая дата
**Where:** Dashboard → «Кривая капитала» → tooltip на точке.
**Actual:** «27 декабря 2024 г. ... Баланс: -163 923 ₽».
**Issue:** Точка из 2024 г. с балансом -163k. Currently 2026-05-19. Либо данные ошибочные (старые сделки в журнале не помеченные), либо tooltip формат показывает чужую запись.
**Fix:** Проверить equity curve build-up на acc=2 (Семен). Likely это первая сделка в журнале (пользователь импортировал старые годы) — тогда корректно. Если нет — bug в equity_curve generator.

#### BUG-PREV-002: Журнал — нет видимой кнопки «Редактировать» в expanded карточке
**Where:** `/history` → expanded row → «Исполнения» таблица.
**Issue:** `EditTradeModal` импортирован и монтируется ([history/page.tsx:633](../../frontend/src/app/history/page.tsx#L633)), но точка входа неочевидна. На /positions кнопка есть; на /history — нет.
**Fix:** Добавить «Редактировать» кнопку в `ExecutionList` row или в TradeCard. Унифицировать UX с /positions.

#### BUG-006: Календарь P&L открыт не на текущем месяце
**Where:** `/analysis/calendar` — landing.
**Actual:** Открывается на «Март 2026» (-75 741 ₽, 6 сделок). «Следующий месяц» disabled.
**Expected:** Открыться на текущем (Май 2026) или последнем месяце с активностью.
**Issue:** Disabled «Следующий месяц» при Маrte указывает что компонент думает что март — это последний месяц с данными. Но dashboard показывает Май 19 → -64k. Либо БД rows за май не релевантны calendar source, либо логика последнего месяца неверная.
**Fix:** Calendar должен landing на `max(trade.exit_at)` месяц, либо на current month если активность есть.

### 🟡 Minor

#### BUG-001: `/signin` → 404 (нет alias на `/login`)
**Fix:** Add `app/signin/page.tsx` → `redirect('/login')`. 5 строк.

#### BUG-004: Dashboard «ROI -95.01%» — нужна проверка
**Where:** Dashboard → «Портфель» → «-95.01% ROI».
**Issue:** Баланс 52k + позиции 853k = 905k. Вложения 1051k. ROI должен быть ~-13.8%, не -95.01%. Подозрительно.
**Fix:** Verify ROI formula in [`backend/`](../../backend/) или dashboard component. Возможно "позиции 853k" неверно (notional vs equity).

#### BUG-005: EditTradeModal `asset_type=Stock` для фьючерса
**Where:** /positions → expand → Редактировать → select «Тип актива».
**Actual:** Select показывает «Stock» для SiM6 (фьючерс USD/RUB).
**Cause:** API ответ не содержит `asset_type` (или null), EditTradeModal `buildInitialFormData` использует fallback `'Stock'` ([EditTradeModal.tsx:73](../../frontend/src/components/EditTradeModal.tsx#L73)).
**Risk:** При save без изменения select — overwrite реального типа на "Stock" в БД (если PATCH принимает поле и trade_update.dict(exclude_unset=True) включает его).
**Fix:** 1) Backend `schemas.Trade.asset_type` должен возвращать real value (`futures`); 2) или защитный fallback на `trade.instrument_type_v2` если есть; 3) или сделать поле read-only для брокерских сделок.

#### BUG-PREV-003: Default visible columns в /history — горизонтальный overflow
**Where:** `/history` table.
**Issue:** 12 default columns включая commission, varmargin, margin_fee, service_fee, other_fees, confidence, mood — слишком широко для 1080p.
**Fix:** Сузить `DEFAULT_VISIBLE_COLUMNS` до 8 ключевых (Дата, Тикер, Сторона, Объём, Вход→Выход, P&L, %, Длительность). Остальные через column-picker.

#### BUG-007: EditTradeModal — нет кнопки «Отмена»
**Where:** EditTradeModal footer.
**Actual:** Только «Обновить сделку» + X (icon) в углу.
**Expected:** Явная «Отмена» рядом с «Обновить сделку».
**Fix:** [`EditTradeModal.tsx`](../../frontend/src/components/EditTradeModal.tsx) — добавить secondary button «Отмена» → `onClose()`.

#### BUG-008: `/profile?tab=brokers` — URL param не активирует таб
**Where:** Профиль → клик «Брокеры» в footer sidebar.
**Issue:** Контент страницы идентичен `/profile` (same bodyLen 876, same h1, same content). Url-driven tab routing не работает.
**Fix:** [`/profile/page.tsx`](../../frontend/src/app/profile/page.tsx) — читать `useSearchParams().get('tab')` и устанавливать initial tab.

---

## Domains not deeply tested (out of scope for this pass)

- `/journal/screenshots` — не открыт
- `/review` (Daily Review) — не открыт
- `/help` — не открыт
- 152-ФЗ: cookie banner, удаление аккаунта, политика — не проверены
- Broker connect modal flow — не открывался
- Команды быстрого доступа `Ctrl+K` — не тестировались
- Импорт XLSX — не пробовался
- Мобильный viewport — не симулировался

---

## Bugs to fix in this session (priority)

Recommend tackling **Critical first**, then Important, then Minor. Each ~15-30 min via subagent-driven flow.

**Order:**

1. **BUG-002** (NaN в Портфеле) — 15 мин. Defensive formatter.
2. **BUG-PREV-001** (expand-all journal) — 15 мин. Один-строка fix `stateKey`.
3. **BUG-PREV-002** (нет «Редактировать» в /history) — 20 мин. Добавить кнопку.
4. **BUG-005** (asset_type default Stock) — 20 мин. Backend + fallback.
5. **BUG-001** (/signin 404) — 5 мин. Add redirect.

Затем (если time-budget remaining):
6. BUG-006 (calendar month) — 10 мин.
7. BUG-007 (Cancel button) — 5 мин.
8. BUG-PREV-003 (default columns) — 5 мин.
9. BUG-008 (profile tab) — 10 мин.

Defer to отдельной сессии:
- BUG-003 (equity curve old date) — нужна data-level investigation
- BUG-004 (ROI -95%) — нужна formula verification
- /journal/screenshots, /review, /help — full QA pass
- 152-ФЗ compliance — отдельный security pass
- mobile/responsive — отдельный pass
