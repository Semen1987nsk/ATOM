---
name: fastapi-sqlalchemy-patterns
description: Use when writing or refactoring FastAPI routers, SQLAlchemy 2.0 models, Pydantic v2 schemas, or Alembic migrations in the Eqio project. Triggers on "новый роутер", "новый эндпоинт", "новая модель", "alembic", "миграция", "pydantic", "session", "dependency injection", "fastapi", "sqlalchemy", "select query", "N+1".
---

# FastAPI + SQLAlchemy 2.0 — патчи и паттерны для Eqio

Skill адресован коду в `C:\Users\Administrator\Eqio\ATOM\backend\`. Все примеры опираются на реальные модули проекта; ссылки даны в формате `backend/<file>:<symbol>`.

## 1. Контекст проекта Eqio

Eqio — торговый дневник для трейдеров MOEX, FastAPI-бэкенд (`backend/main.py`), SQLAlchemy 2.0 поверх sync-сессии (`backend/database.py:get_db`), Pydantic v2 (`backend/schemas.py`), Alembic с одним baseline-ревижном (`backend/alembic/versions/0001_initial_baseline.py`), PostgreSQL в проде и SQLite локально (`atom.db`). Текущие конвенции: модели в `backend/models.py` пока в legacy-стиле `Column(...)` (см. `User`, `Trade`, `Account`, `BalanceSnapshot`, `Subscription`, `Payment`); схемы в `backend/schemas.py` уже на Pydantic v2 с `ConfigDict(from_attributes=True)`; роутеры лежат в `backend/routers/*.py`, регистрируются в `main.py` через `app.include_router(...)`; auth-зависимости — в `backend/auth_service.py:get_current_user` и `get_current_user_optional`; settings — единственный источник истины через `from config import settings` (`backend/config.py`). Деньги хранятся как `Numeric(precision=18, scale=8)` для цен и `Numeric(precision=10, scale=2)` для рублёвых сумм платежей. Все datetime — naive UTC через `utils.datetime_utils.utc_now_naive` (legacy-выбор, новые поля можно делать tz-aware, см. раздел 9).

## 2. Pydantic v2 — схемы

Эталон стиля живёт в `backend/schemas.py` (`UserResponse`, `BalanceSnapshotResponse`, `DepositOperationResponse`).

### Что делать

- `model_config = ConfigDict(from_attributes=True)` вместо устаревшего `class Config:`.
- `Field(...)` для валидации и метаданных, `validation_alias`/`serialization_alias` для несовпадения имён.
- `computed_field` для производных значений вместо `@property` + `@validator`.
- `Decimal` для денег, не `float` (см. раздел 9).
- `Literal["a", "b"]` или `enum.Enum` для статусов — Pydantic v2 валидирует их без дополнительных валидаторов.
- `TypeAdapter(list[ItemSchema]).validate_python(...)` для разовой валидации списка без обёртки в модель.

### Пример: Create + Response

```python
from decimal import Decimal
from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, computed_field

class TradeCreate(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=16, examples=["SBER"])
    direction: Literal["long", "short"]
    entry_price: Decimal = Field(..., gt=0, max_digits=18, decimal_places=8)
    quantity: Decimal = Field(..., gt=0, max_digits=18, decimal_places=8)
    entry_at: datetime
    notes: Optional[str] = Field(None, max_length=2000)

class TradeResponse(BaseModel):
    id: int
    symbol: str
    direction: str
    entry_price: Decimal
    quantity: Decimal
    pnl: Optional[Decimal] = None
    entry_at: datetime
    exit_at: Optional[datetime] = None

    @computed_field
    @property
    def is_open(self) -> bool:
        return self.exit_at is None

    model_config = ConfigDict(from_attributes=True)
```

### Антипаттерны

- `class Config: orm_mode = True` — это Pydantic v1, в проекте Pydantic v2.
- `float` для цены/количества/PnL — теряется точность.
- `dict` как response_model — нарушает контракт OpenAPI; используйте отдельную схему типа `MessageResponse` из `backend/schemas.py`.

## 3. SQLAlchemy 2.0 — современный стиль

Текущие модели в `backend/models.py` написаны в legacy 1.x-стиле (`Column(Integer, ...)`). Новые модели пишите в стиле 2.0: `Mapped[X]` + `mapped_column(...)`. Legacy не трогаем без необходимости — миграция всех моделей это отдельная задача.

```python
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_tags_user_name"),
        Index("ix_tags_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    color: Mapped[Optional[str]] = mapped_column(String(7), default=None)
    created_at: Mapped[datetime] = mapped_column(default=utc_now_naive)

    trades: Mapped[list["Trade"]] = relationship(
        secondary="trade_tags",
        back_populates="tag_objects",
        lazy="selectin",
    )
```

### Запросы

```python
from sqlalchemy import select

# Один объект
stmt = select(models.Trade).where(models.Trade.id == trade_id)
trade = db.scalar(stmt)

# Список
stmt = (
    select(models.Trade)
    .where(models.Trade.account_id == account_id)
    .order_by(models.Trade.entry_at.desc())
    .limit(limit)
    .offset(offset)
)
trades = db.scalars(stmt).all()

# Скаляр (count и т.п.)
from sqlalchemy import func
total = db.scalar(select(func.count()).select_from(models.Trade).where(...))
```

### Migration tip

Существующий код на `db.query(models.Trade).filter(...)` (см. `backend/auth_service.py:get_user_by_email`, `backend/routers/trades.py:create_trade`) пока оставляем — он работает. Все новые сервисы и эндпоинты пишите через `select()` + `db.scalars()`. Точечный рефакторинг старого кода допустим, когда меняется его логика.

## 4. Загрузка relationships — избегаем N+1

| Стратегия | Когда |
|---|---|
| `selectinload` | Коллекции (one-to-many, many-to-many). Один доп. запрос на коллекцию через `IN (...)` |
| `joinedload` | Один-к-одному, FK на родителя (many-to-one). LEFT OUTER JOIN |
| `lazy="raise"` | Дисциплина: рушит код на implicit lazy load; ставится в `relationship(...)`, заставляет всегда явно указывать стратегию загрузки |
| `noload` | Когда явно не нужно тянуть |

```python
from sqlalchemy.orm import selectinload, joinedload

stmt = (
    select(models.Trade)
    .where(models.Trade.account_id == account_id)
    .options(
        joinedload(models.Trade.setup),       # FK на Setup — JOIN
        selectinload(models.Trade.account),   # обычно не нужно, но если нужно много trades
    )
)
```

### Реальный риск N+1 в Eqio

`backend/routers/stats.py` агрегирует сделки и часто читает `trade.setup.name`/`trade.account.currency`. Если эти атрибуты дёргаются в цикле без `joinedload`, получаем по запросу на каждую сделку — на счёте с 5000 сделками это 5000 SELECTов. Лечится одним `.options(joinedload(...))` в исходном `select()`.

### Как обнаружить N+1 локально

1. Включить SQL-эхо: `SQL_ECHO=true` в `.env` (используется в `backend/database.py`).
2. Сделать запрос, посчитать SELECTы в логе. Линейная зависимость от размера коллекции = N+1.
3. Альтернатива — счётчик через event:
   ```python
   from sqlalchemy import event
   counter = {"n": 0}
   @event.listens_for(engine, "before_cursor_execute")
   def _(*_): counter["n"] += 1
   ```

## 5. Dependency Injection FastAPI

### Базовые зависимости в Eqio

- `database.get_db` — sync `Session`, генератор. Сделан синхронным сознательно: вся ORM-логика sync, нет смысла переходить на async-сессию без миграции всего слоя данных. CPU-блокирующие или sync-IO куски в async-эндпоинтах оборачиваем в `asyncio.to_thread(...)` — пример `_build_imoex_overlay_async` в `backend/routers/stats.py`.
- `auth_service.get_current_user` — обязательный пользователь, кидает 401/403.
- `auth_service.get_current_user_optional` — для публичных эндпоинтов с опциональным контекстом.

### Settings и request_id

```python
from functools import lru_cache
from config import Settings

@lru_cache
def get_settings() -> Settings:
    return Settings()

# В роутере:
def handler(s: Settings = Depends(get_settings)): ...
```

`request_id` уже устанавливается `RequestContextMiddleware` (см. `backend/middleware`); внутри хендлеров его можно достать через `get_request_id_from_request(request)` из `middleware`.

### Кастомные зависимости

```python
from fastapi import Depends, HTTPException, status
from auth_service import get_current_user
import models

def require_pro(user: models.User = Depends(get_current_user)) -> models.User:
    """Требует активную PRO-подписку."""
    sub = next(
        (s for s in user.subscriptions if s.is_active == 1), None
    )
    if not sub or sub.plan != models.SubscriptionPlan.PRO:
        raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED, "PRO subscription required")
    return user

def get_admin_user(user: models.User = Depends(get_current_user)) -> models.User:
    if user.is_admin != 1:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user
```

Готовая утилита `subscription_service.require_pro` и `enforce_trade_limit` уже есть в проекте — используйте их как референс при добавлении похожих гард-зависимостей.

## 6. Структура роутера — anti-god-router

### Правила

- Один роутер = один ресурс. `prefix="/trades"`, `tags=["trades"]`.
- Размер файла < 500 строк. `backend/routers/stats.py` — 1874 строки — антипример: десятки эндпоинтов аналитики, MOEX-overlay, кэш, теги. Разделить на `routers/stats_overview.py`, `routers/stats_equity.py`, `routers/stats_distribution.py`, `routers/tags.py`.
- `response_model` указан на каждом эндпоинте. Никаких голых `dict`/`list` в return.
- `status_code`: POST = 201, DELETE = 204 (без тела), всё остальное по дефолту 200.
- Порядок path-операций: GET list → GET one → POST → PATCH → PUT → DELETE.
- Зависимости только в сигнатуре через `Depends(...)`; никаких `db = next(get_db())` в теле.

### Скелет

```python
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

import database, auth_service, models, schemas
from services import tag_service

router = APIRouter(prefix="/tags", tags=["tags"])

@router.get("", response_model=list[schemas.TagResponse])
def list_tags(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(database.get_db),
    user: models.User = Depends(auth_service.get_current_user),
):
    return tag_service.list_tags(db, user.id, limit=limit, offset=offset)

@router.post("", response_model=schemas.TagResponse, status_code=status.HTTP_201_CREATED)
def create_tag(
    payload: schemas.TagCreate,
    db: Session = Depends(database.get_db),
    user: models.User = Depends(auth_service.get_current_user),
):
    return tag_service.create_tag(db, user.id, payload)
```

## 7. Сервисный слой

Правило: **тонкий роутер, толстый сервис**.

- `routers/*.py` делает: validation (через Pydantic), authorization (через зависимости), вызов сервиса, маппинг исключений в `HTTPException`, возврат response_model.
- `services/*.py` (или legacy `*_service.py` рядом с роутерами) делает: всю domain-логику, работу с моделями и сессией.

### Кто открывает и кто коммитит

- Сессию открывает FastAPI через `Depends(get_db)` — сервис её принимает аргументом.
- Коммитит **сервис**, потому что только он знает границы транзакции (один эндпоинт может вызвать 2-3 сервиса).
- Откатывает: либо сервис вручную, либо глобальный exception handler в `main.py` для `SQLAlchemyError`.

### Транзакции

```python
def create_trade_with_position(db: Session, ...) -> models.Trade:
    try:
        trade = models.Trade(...)
        db.add(trade)
        db.flush()  # получаем id, ещё без коммита
        position = models.Position(trade_id=trade.id, ...)
        db.add(position)
        db.commit()
        db.refresh(trade)
        return trade
    except Exception:
        db.rollback()
        raise
```

Для атомарных блоков можно использовать `with db.begin():` если сессия с `autocommit=False` и без активной транзакции — но в Eqio `SessionLocal` уже `autoflush=False, autocommit=False, expire_on_commit=False`, так что обычно достаточно явного `commit/rollback`.

## 8. Alembic — миграции

### Текущее состояние Eqio

В `backend/alembic/versions/` лежит **один** файл — `0001_initial_baseline.py`, делающий `Base.metadata.create_all(...)`. Это сознательная консолидация (см. docstring файла), но в долгосрочной перспективе это плохо: любая новая колонка ломает прод, потому что `create_all` не применяется к существующей БД. **Все новые изменения схемы — отдельной инкрементной миграцией с `down_revision = "0001_initial_baseline"` (или предыдущей в цепочке).**

### autogenerate vs ручная

- `alembic revision --autogenerate -m "add_tags_table"` подходит для CREATE TABLE и добавления колонок.
- **Не замечает**: добавление значений в `Enum`, `server_default` изменения, изменение типа в Postgres без `USING`, индексы поверх частичных условий, `CHECK`-констрейнты на данных, RENAME column.
- Всегда читайте сгенерированный файл целиком и дописывайте недостающее руками.

### Безопасная миграция большой таблицы

`Trade` уже растёт; миллионы строк не редкость для активного трейдера. Прямой `ALTER TABLE ADD COLUMN ... NOT NULL` берёт лок и кладёт API.

Безопасный паттерн на 3 миграции:

1. **Миграция A**: добавить колонку nullable + default-значение — это быстро на Postgres 11+.
2. **Миграция B**: backfill отдельным шагом, батчами (chunked update в data-миграции, не в DDL).
3. **Миграция C**: `ALTER COLUMN ... SET NOT NULL` после backfill.

### Rename column без даунтайма

1. Добавить новую колонку.
2. Dual-write: писать в обе на уровне приложения (одна миграция кода).
3. Backfill старых строк.
4. Переключить чтение на новую (вторая миграция кода).
5. DROP старой колонки (последняя миграция БД).

### Batch mode

Eqio локально использует SQLite (`atom.db`). SQLite не поддерживает большинство ALTER, поэтому для совместимости — `with op.batch_alter_table("trades") as bop: bop.alter_column(...)`. На Postgres batch_mode превращается в обычный ALTER, на SQLite — в copy-and-swap. Если миграция должна работать на обеих БД (тесты идут на SQLite), пишем через batch.

### Команды

```bash
# Создать пустую миграцию
alembic revision -m "add_tags_table"

# Автогенерация по diff моделей
alembic revision --autogenerate -m "add_tags_table"

# Применить
alembic upgrade head

# Откатить на одну
alembic downgrade -1

# История
alembic history --verbose

# Stamp без выполнения (для dev-БД, бутстрапленных через AUTO_INIT_DB)
alembic stamp 0001_initial_baseline
```

## 9. Типизация — strict mode для финансов

- **Деньги — только `Decimal`**, никогда `float`. `0.1 + 0.2 != 0.3` — для PnL это катастрофа.
- В SQLAlchemy: `Numeric(precision=18, scale=8)` для цен и количеств (см. `Trade.entry_price` в `backend/models.py`), `Numeric(precision=10, scale=2)` для рублёвых сумм платежей (см. `Payment.amount`).
- В Pydantic: `Decimal = Field(..., gt=0, max_digits=18, decimal_places=8)`.
- При сериализации в JSON Pydantic v2 умеет выдавать `Decimal` как строку (`model_dump_json()`), что предотвращает потерю точности в JS-фронте. Если фронт ждёт строку — добавить `Field(..., json_schema_extra={"type": "string"})` или кастомный `field_serializer`.

### Datetime

- В легаси-коде Eqio — `utc_now_naive()` из `backend/utils/datetime_utils.py` (naive UTC). Это исторический выбор; уважайте его при работе с существующими полями (иначе сравнения `entry_at < ...` сломаются).
- Новые поля делайте tz-aware: `datetime.now(timezone.utc)`. Отдельные модули (новые миграции, новые модели) можно сразу строить tz-aware с `DateTime(timezone=True)` в SQLAlchemy.
- **Никогда** `datetime.utcnow()` — deprecated с Python 3.12, удаляется.

## 10. Обработка ошибок

### HTTPException

```python
raise HTTPException(status.HTTP_404_NOT_FOUND, "Tag not found")
raise HTTPException(status.HTTP_409_CONFLICT, "Tag with this name already exists")
raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Symbol must be uppercase")
```

### Exception handlers

Уже зарегистрированы в `backend/main.py`:
- `RequestValidationError` → 422 с детализацией полей.
- `SQLAlchemyError` → 500, с `request_id` в headers и body.
- `Exception` → 500 для всего непойманного.

Не дублируйте эту обработку в роутерах — только маппинг доменных ошибок в `HTTPException`.

### IntegrityError → 409

```python
from sqlalchemy.exc import IntegrityError

try:
    db.commit()
except IntegrityError as exc:
    db.rollback()
    raise HTTPException(status.HTTP_409_CONFLICT, "Duplicate tag name") from exc
```

### Bare except — нельзя

`except Exception:` запрещён в хендлерах. В фоновых задачах (`sync_scheduler`, импорт) допустим **только** с `log.exception(...)` и явным rationale в комментарии.

### Retry

Сетевые вызовы (MOEX ISS, Tinkoff API) оборачивайте через `tenacity`:

```python
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, max=4),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError)),
)
def fetch_imoex(...): ...
```

## 11. Тестирование

- `TestClient` из `fastapi.testclient` для интеграционных.
- В `conftest.py` — фикстура временной SQLite БД и override `database.get_db` через `app.dependency_overrides`.
- Параметризованные тесты для валидации (`@pytest.mark.parametrize`).
- Auth-фикстура: `logged_user` создаёт пользователя + токен, возвращает заголовок `Authorization`.
- Миграции в тестах: `Base.metadata.create_all(engine)` для скорости; alembic-цепочку гонять отдельным джобом.

## 12. Чек-лист перед коммитом

- [ ] `ruff check backend/` чисто.
- [ ] `mypy backend/` без новых ошибок.
- [ ] `pytest backend/tests/` зелёный локально.
- [ ] Если изменена модель — есть Alembic-миграция и `down_revision` указывает на актуальный head.
- [ ] У всех эндпоинтов указан `response_model`.
- [ ] В новом коде `select()` вместо `query()`.
- [ ] Нет sync-IO в async-хендлере без `asyncio.to_thread`.
- [ ] Деньги хранятся и принимаются как `Decimal`, не `float`.
- [ ] Кастомные исключения превращены в `HTTPException` с осмысленным status code.

## 13. Cookbook

### Добавить эндпоинт GET /something

```python
@router.get("/something", response_model=schemas.SomethingResponse)
def get_something(
    db: Session = Depends(database.get_db),
    user: models.User = Depends(auth_service.get_current_user),
):
    obj = db.scalar(select(models.Something).where(models.Something.user_id == user.id))
    if not obj:
        raise HTTPException(404, "Not found")
    return obj
```

### Добавить новую модель

1. Описать класс в `backend/models.py` (новые — в стиле `Mapped`/`mapped_column`).
2. Прописать relationship на обеих сторонах + cascade.
3. Добавить индексы и `UniqueConstraint` в `__table_args__`.
4. Сгенерировать миграцию (раздел 8).
5. Добавить Pydantic-схему в `backend/schemas.py`.

### Добавить миграцию

```bash
cd backend
alembic revision --autogenerate -m "add_<feature>"
# Прочитать файл, дописать что autogenerate не заметил
alembic upgrade head
```

### Добавить Pydantic-схему

В `backend/schemas.py` создать `XCreate` (input для POST), `XUpdate` (input для PATCH, все поля Optional), `XResponse` (output, с `model_config = ConfigDict(from_attributes=True)`).

### Кастомная dependency для plan='pro'

См. раздел 5 — `require_pro`. Используется как `user: models.User = Depends(require_pro)` в защищённых эндпоинтах. Уже есть готовая в `backend/subscription_service.py`.

### Paginated list endpoint

```python
@router.get("", response_model=schemas.PaginatedTrades)
def list_trades(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(database.get_db),
    user: models.User = Depends(auth_service.get_current_user),
):
    account_id = auth_service.get_account_id(db, user)
    base = select(models.Trade).where(models.Trade.account_id == account_id)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    items = db.scalars(base.order_by(models.Trade.entry_at.desc()).limit(limit).offset(offset)).all()
    return {"items": items, "total": total, "limit": limit, "offset": offset}
```

Cursor-based — для больших коллекций: курсор = `(entry_at, id)` пары, передавать в base64. Limit/offset — для UI с явными страницами; cursor — для бесконечного скролла и стабильности при вставках.

---

См. примеры в `examples/`:
- `new_router.py` — полный CRUD-роутер для нового ресурса (Tags).
- `new_service.py` — соответствующий сервисный слой.
- `new_migration.py` — Alembic-миграция для добавления таблицы tags.
