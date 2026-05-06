# Refactoring Guide — Phase 3

Этот документ — **навигатор для следующих рефакторингов**. Phase 3 поставила
инфраструктуру, дальше команда мигрирует страницы постепенно.

---

## ✅ Что уже сделано в Phase 3

| Артефакт | Где лежит | Статус |
|---|---|---|
| `analytics/` package (6 модулей вместо 1456-строчного файла) | [backend/analytics/](../backend/analytics/) | Done. Внешний API сохранён 1:1 |
| `services/stats_cache.py` (вынесен из stats.py) | [backend/services/stats_cache.py](../backend/services/stats_cache.py) | Done + 12 unit-тестов |
| `services/__init__.py` — каркас под будущие сервисы | [backend/services/](../backend/services/) | Done |
| OpenAPI → TS types pipeline | [backend/scripts/dump_openapi.py](../backend/scripts/dump_openapi.py), [frontend/src/types/api.ts](../frontend/src/types/api.ts) | Done. Запусти `npm run gen:api-types:from-file` после изменений API |
| TanStack Query provider + 6 готовых хуков | [frontend/src/lib/QueryProvider.tsx](../frontend/src/lib/QueryProvider.tsx), [frontend/src/lib/queries.ts](../frontend/src/lib/queries.ts) | Done. Бери `useTradesQuery`, `useStatsQuery`, ... |
| `useModalState` хук-замена для 13 useState-модалок | [frontend/src/lib/useModalState.ts](../frontend/src/lib/useModalState.ts) | Done. Drop-in для page.tsx |

---

## 📋 Что осталось (по убыванию приоритета)

### 1. Мигрировать страницы на TanStack Query (низкий риск, высокая выгода)

**Стратегия:** ОДНА страница за раз, в отдельном PR. Не пытайся за один присест.

**Порядок:**
1. `frontend/src/app/page.tsx` (главный дашборд) — самые дорогие запросы.
2. `frontend/src/app/history/page.tsx` — самый шумный fetch (фильтры → race conditions).
3. `frontend/src/app/admin/*` — низкий трафик, но много дублей запросов.

**Шаблон миграции одного fetch:**
```diff
- const [trades, setTrades] = useState<Trade[]>([]);
- const [isLoading, setIsLoading] = useState(true);
- useEffect(() => {
-   fetch("/trades/").then(r => r.json()).then(setTrades).finally(() => setIsLoading(false));
- }, []);
+ const { data: trades = [], isLoading } = useTradesQuery({ limit: 500 });
```

**Что это даёт:** dedupe одинаковых запросов в одном render-tree, автоматический
retry, автоматический abort при unmount, синхронизация между компонентами,
готовность к offline-mode.

### 2. Заменить 13 модалок в `page.tsx` на `useModalState`

**Зачем:** сейчас `Home` держит 11+ `useState<boolean>` + `useState<Trade | null>` —
любое изменение модального флоу = ритуальное изменение 5 строк. После миграции
один объект `modal.is("close")` / `modal.payload.trade`.

**Шаблон:**
```typescript
type Modals = {
  add: undefined;
  edit: { trade: Trade };
  close: { trade: Trade };
  settings: undefined;
  filters: undefined;
};

const modal = useModalState<Modals>();

// Вместо setShowAdd(true):
modal.open("add");

// Вместо setShowClose(true); setTradeToClose(t);
modal.open("close", { trade: t });

// В JSX:
{modal.is("add") && <AddTradeModal onClose={modal.close} />}
{modal.is("close") && <CloseTradeModal trade={modal.state.payload.trade} onClose={modal.close} />}
```

### 3. Сгенерировать реальные TS-типы из OpenAPI

```bash
cd backend
python scripts/dump_openapi.py > openapi.json

cd ../frontend
npm install        # подтянет openapi-typescript
npm run gen:api-types:from-file
```

После этого `import type { Trade } from "@/types/api"` начнёт давать
**настоящие** типы, а не placeholder.

Добавь в pre-commit hook (или GitHub Actions step):
```yaml
- name: Regenerate API types
  run: |
    cd backend && python scripts/dump_openapi.py > openapi.json
    cd ../frontend && npm run gen:api-types:from-file
    git diff --exit-code src/types/api.generated.ts
```
— тогда любая забытая регенерация будет ловиться в CI.

### 4. Разбить `frontend/src/app/manual/page.tsx` (3987 строк)

**Решение: оставить как есть.**

Это статический help-контент. Ценность разбивки = 0 (он не редактируется
часто, не имеет state, не падает в проде). Если когда-нибудь захочется —
переехать на MDX или CMS, а не выжимать React-компоненты.

### 5. Разбить `tinkoff_service.py` (~1577 строк)

**Решение: отложено до Phase 4 + рост покрытия тестами.**

Этот файл — единственный источник правды для синхронизации с брокером.
Текущее тестовое покрытие интеграции — 13 тестов (`test_tinkoff_sync.py`),
этого мало для уверенного split'а. Сначала довести покрытие до 25–30
тестов, потом разбивать на:
- `tinkoff/api_client.py` — REST-вызовы
- `tinkoff/sync.py` — основной flow
- `tinkoff/parser.py` — парсинг операций
- `tinkoff/models.py` — dataclasses (ClosedTrade, OpenPosition, ...)

### 6. Repository-паттерн для query-уровня

**Решение: пропускаем.**

При текущем размере backend (~30 endpoint'ов, ~5000 LOC) repository-паттерн —
это бюрократия без выгоды. Возвращаемся к нему когда:
- Будут 2+ команды в backend (нужны контракты).
- Появится ORM-абстракция (миграция SQLAlchemy → SQLModel или drop-in).
- Запросы превысят 50+ уникальных паттернов и появится устойчивая дублирующаяся логика.

---

## Анти-паттерны, которые мы НЕ применяем

- **Большой плановый refactor «ребрендинг проекта»** — кладбище open-source;
  всегда предпочитаем инкрементальный путь по одной странице.
- **Разделение «по слоям» (controllers/services/repositories) до подтверждённой нужды** —
  для small-to-medium app это создаёт больше плюмбинга, чем экономии.
- **Полный переход на TanStack Query за один PR** — большой surface, легко
  сломать UX в незаметных местах. Только постранично.

---

## Метрики успеха Phase 3

| До | После |
|---|---|
| `analytics.py` 1456 строк | 6 модулей, max 350 строк, тот же external API |
| Cache + fingerprint в роутере | Отдельный сервис + 12 unit-тестов |
| Нет TS-типов из OpenAPI | Pipeline настроен, есть placeholder + реген одной командой |
| Нет TanStack Query | Provider + 6 готовых хуков на основные ресурсы |
| 13 useState для модалок | `useModalState` готов, страницы могут принимать инкрементально |
| 286 тестов | **298 тестов** (12 новых на stats_cache) |
