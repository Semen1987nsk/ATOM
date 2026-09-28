# Positions = editing surface для open trades, журнал = только closed — design

**Дата:** 2026-05-19
**Контекст:** UI семантическое разделение open vs closed
**Связан с:** [2026-05-19-position-source-of-truth-design.md](./2026-05-19-position-source-of-truth-design.md) (архитектурный курс: Position table = open, Trade table = closed history)
**Branch:** `feature/positions-editing-surface` (после merge feature/costs-breakdown-card)

## Проблема

Сейчас `/history` («Дневник сделок») показывает **и open, и closed** Trade rows. Это даёт три неудобства:

1. **Семантически грязно** — журнал в индустрии (Tradervue, TraderSync, TradeZella, Edgewonk) всегда содержит закрытые round-trip; открытые — отдельный экран.
2. **Phantom trades путают пользователя** — open Trade.exit_at=None, но позиции у брокера нет → в журнале висит «призрак», пока следующая sync не пройдёт стадию `_stage_close_phantom_trades`.
3. **Italic-PnL для open** — спецрежим отрисовки в журнале (PnL курсивом, "open" badge) усложняет UI и не даёт пользователю места для записи плана прямо при открытии (note/setup/screenshot пишутся уже после закрытия).

При этом `/positions` сейчас — read-only снапшот Position table. Трейдер видит позицию, но не может написать «почему вошёл», прикрепить скрин входа, выбрать setup.

## Цель

Сделать **семантическое разделение**:

- `/positions` (sidebar → **«Открытые позиции»**) — read+write surface для **открытых** позиций. Здесь трейдер видит, что у него сейчас в портфеле, **и редактирует metadata** (note, setup, screenshot, confidence, mood, discipline, tags, timeframe, risk, R-multiple) для каждого открытого Trade row.
- `/history` (остаётся **«Дневник сделок»**) — только **закрытые** Trade rows. Round-trip aggregation работает без специальных кейсов «what if open».

## Архитектура

### До

```
/history (Дневник)
    ↓ GET /trades/positions?status=all
    ↓ PositionJournalView aggregates → Position[] (open + closed)
    ↓ StatusBadge: open | closed
    ↓ EditTradeModal на любую execution

/positions (Позиции)
    ↓ GET /positions (Position table snapshot)
    ↓ Read-only таблица
```

### После

```
/history (Дневник сделок)
    ↓ GET /trades/positions?status=closed
    ↓ PositionJournalView (только closed)
    ↓ Без StatusBadge (всё closed) — упрощение UI
    ↓ EditTradeModal как сейчас

/positions (Открытые позиции)
    ↓ GET /positions (Position table)  ─┐
    ↓ GET /trades/positions?status=open ─┴─→ join по instrument_uid на клиенте
    ↓ Expand row → список executions (open Trade rows) с preview метаданных
    ↓ Кнопка «редактировать» на execution → EditTradeModal (тот же что в /history)
```

## Components

### Backend

#### Изменения minimal — endpoint уже есть

`GET /trades/positions?status=open|closed|all` уже существует в [`backend/routers/trades.py:535`](../../../backend/routers/trades.py#L535) и поддерживает фильтрацию по статусу через `any_open` логику в строках 577-579.

Никаких новых endpoints не добавляем. Никаких миграций. Frontend просто меняет query param.

`PATCH /trades/{trade_id}` уже умеет обновлять любое manual поле (см. `update_trade` на строке 964) — переиспользуем как есть.

### Frontend

#### `/history/page.tsx` — менять filter и убрать StatusBadge

В fetch к `/trades/positions` явно передавать `?status=closed`:

```ts
const data = await api.get<PositionResponse[]>('/trades/positions?status=closed');
```

В `PositionJournalView.tsx`:
- Удалить компонент `StatusBadge` (строка 277) и все usage'и — все позиции closed, индикатор лишний.
- Удалить ветки `isOpen` (строки 452, 511) и связанный rendering.
- В `RowExecution` (строка 377) удалить `isClosed` checks — все execution.exit_at !== null.
- Italic-PnL ветка для open — выпиливаем.

Документировать в шапке файла: "В журнале только closed trades. Open trades редактируются на /positions."

#### `/positions/page.tsx` — превратить в editing surface

Расширение существующей страницы (не переписывание):

1. **Параллельно с `GET /positions` тянуть `GET /trades/positions?status=open`**:
   ```ts
   const [snap, openPos] = await Promise.all([
     api.get<PositionResponse[]>('/positions'),
     api.get<PositionJournalRow[]>('/trades/positions?status=open'),
   ]);
   ```
   `PositionJournalRow` — тот же тип что в журнале (с массивом `executions: TradeExecution[]`).

2. **Join по `instrument_uid`** на клиенте: каждой Position-строке привязываем `open_trades: TradeExecution[]` (executions из соответствующего PositionJournalRow). Если Position есть, а Trade rows нет — позиция отображается, но expand пуст (показываем плейсхолдер «Trade row не найден — будет создан при следующей синхронизации»).

3. **Добавить expand-механизм**: chevron слева от Тикер-колонки (как в [PositionJournalView.tsx:377](../../../frontend/src/components/PositionJournalView.tsx#L377) — паттерн уже отработан). Expand раскрывает sub-row со списком executions:

   ```
   ┌─ ▶ SBER  Сбербанк-ао  Акция  +10  300.00  305.20  +52.00 ₽  +1.73%  10:42
   │   (expanded)
   │   ├─ Entry 2026-05-15 10:42  qty +10 @ 300.00  ▸ note: "пробой 295" • setup: "Breakout" [Редактировать]
   │   └─ (если scale-in: Entry 2026-05-16 14:20  qty +5 @ 302.50  ▸ note: "" • setup: — [Редактировать]
   ```

4. **Кнопка «Редактировать» → EditTradeModal**: переиспользуем существующий компонент. Передаём ему `Trade` row из executions. После save — refetch обоих списков (`/positions` и `/trades/positions?status=open`) для freshness.

5. **Header странички**: оставить summary card (количество позиций + совокупный unrealized PnL). Кнопку «Обновить» (sync) тоже оставить.

6. **Pagetitle/h1**: уже «Открытые позиции» в pageTitle и h1 — менять не надо.

#### `AppShell.tsx` — переименовать sidebar item

`AppShell.tsx:85`:

```diff
- { label: "Позиции", href: "/positions", icon: <Wallet size={18} /> },
+ { label: "Открытые позиции", href: "/positions", icon: <Wallet size={18} /> },
```

Иконку оставляем.

#### `EditTradeModal.tsx` — без изменений (но проверить)

Должен корректно работать на open Trade (exit_at=null). Проверить:
- Поле `exit_at` / `exit_price` — должно либо быть disabled для open, либо отсутствовать в форме. Сейчас (см. [EditTradeModal.tsx](../../../frontend/src/components/EditTradeModal.tsx)) форма содержит `entry_*` поля + manual fields, exit поля отдельно через `close_trade` endpoint. → ОК, без изменений.
- Поле `tags` (split по запятой) — работает универсально.
- `mood`, `discipline` — если их нет в текущей форме, добавить (входит в "полный набор manual fields" по решению пользователя).

Если `mood`/`discipline` не редактируются в текущем EditTradeModal — это **separately tracked item** в impl plan, **не** часть этого spec'а.

## Data flow

```
User opens /positions
  ↓
Promise.all([
  GET /positions (Position table),
  GET /trades/positions?status=open (Trade rows aggregated by instrument_uid)
])
  ↓
Join client-side по instrument_uid
  ↓
Render table (1 row per Position)
  ↓
User clicks expand on row → show executions list with note/setup preview
  ↓
User clicks "Редактировать" on execution → EditTradeModal(trade)
  ↓
User saves → PATCH /trades/{id} → refetch обе подписки
```

```
User opens /history
  ↓
GET /trades/positions?status=closed
  ↓
PositionJournalView render (только closed, без StatusBadge / open branches)
  ↓
Round-trip aggregation работает без edge cases
```

## Error handling

| Сценарий | Поведение |
|---|---|
| Position есть, open Trade row нет (рассинхрон) | Expand показывает плейсхолдер «Trade row не создан — будет при следующей sync» + кнопку «Принудительная синхронизация». |
| Open Trade row есть, Position нет | Не показываем (Position table = source of truth для отображения). Sweep на следующем sync закроет phantom. |
| EditTradeModal save fails | Toast с ошибкой, форма не закрывается, refetch не запускается. |
| Backend /trades/positions?status=open отвалился, /positions ОК | Показываем Position'ы read-only без expand (graceful degradation), warning toast. |
| Множественные open Trade rows на один instrument_uid (scale-in) | Все показываются в expand, у каждого свой блок editing. Per-execution metadata (по решению пользователя). |

## Testing

### Backend

Не меняется. Существующие тесты `/trades/positions?status=open|closed|all` остаются (если их нет — добавить unit тест на фильтрацию, но это не входит в скоуп этого design'а если уже покрыто).

### Frontend (manual smoke + unit)

1. **Smoke /positions**: open позиция → expand → видны executions → click «Редактировать» → modal открывается → save → данные обновились.
2. **Smoke /history**: открыть журнал → проверить что НЕТ open позиций (только closed) → StatusBadge не отображается → EditTradeModal работает на closed.
3. **Smoke scale-in**: создать (вручную / через test fixture) 2 open Trade rows на один instrument → /positions показывает 1 строку → expand → 2 executions с независимыми metadata.
4. **Phantom case**: Position есть, Trade row нет → expand показывает плейсхолдер.
5. **Unit `PositionJournalView`**: удалить open-related ветки → проверить что render для closed без регрессии.
6. **Unit join logic на /positions**: тест на join Position[] × PositionJournalRow[] по instrument_uid (без backend).

## Migration / Rollout

1. Merge feature ветки.
2. Frontend rebuild (Next.js auto).
3. **Не требует force-resync** — endpoint уже работает, меняется только UI.
4. После deploy: smoke check `/history` и `/positions` на acc#4.
5. Если у пользователя open Trade rows с метаданными (note/setup) которые он ранее редактировал в /history — они автоматически появятся в expand на /positions (тот же Trade row, тот же `note` field).

## Risks

- **Регрессия в журнале**: удаление open-branch кода в `PositionJournalView` может сломать рендеринг для legitimate edge cases (e.g. позиция со всеми exit_at, но last_priced_at в будущем). Mitigation: thorough manual smoke + сохранить git diff на review.
- **Discoverability**: пользователь, который раньше шёл в журнал чтобы записать заметку на открытую сделку, может не догадаться что теперь это на /positions. Mitigation: при первом deploy показать однократный onboarding-tooltip на /history («Открытые позиции переехали — теперь редактируются на странице Открытые позиции») — но это **out of scope** этого spec'а.
- **Двойной запрос на /positions**: parallel `GET /positions` + `GET /trades/positions?status=open` = +1 запрос. На acc с 5-20 открытыми позициями — overhead незаметен. Если станет проблемой — серверный JOIN endpoint позже.

## Что НЕ в скоупе

- Onboarding-tooltip / migration banner («заметки переехали») — отдельная задача.
- Серверный JOIN endpoint `/positions/with-trades` — оптимизация на будущее.
- Поля mood/discipline в EditTradeModal — если их нет, отдельный issue/PR.
- Per-position aggregated note (общая заметка на инструмент) — пользователь явно выбрал per-execution.
- UI для создания нового open Trade row вручную из /positions (без брокера) — out of scope; manual add остаётся в /history через AddTradeModal.
- Уведомление пользователю «у вас open Trade без Position snapshot — возможно phantom» — отдельный admin feature.

## Open questions для review

1. **Default sort на executions в expand**: по `entry_at` asc или desc? Я предполагаю **desc** (новейший вход сверху — релевантнее для активной позиции), но это решает пользователь.
2. **Preview длины note**: 1 строка с truncate или 2 строки? Default — 1 строка truncate, full в EditTradeModal.
3. **Скриншот thumbnail в expand**: показывать ли preview thumbnail (24x24) screenshot_url рядом с note или только иконку 📷? Default — иконка с tooltip-preview по hover.
