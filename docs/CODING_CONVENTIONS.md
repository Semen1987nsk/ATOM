# Eqio Coding Conventions

> Code conventions для backend (Python 3.11+, FastAPI, SQLAlchemy 2.0)
> и frontend (Next.js 16, React 19, TypeScript). Каждое правило с
> обоснованием WHY и opt-out при весомой причине.

**Принцип**: rules > taste. Если конвенция противоречит готовому
паттерну в codebase — следуй существующему паттерну, не вводи новый стиль.

---

## Backend (Python 3.11+, FastAPI, SQLAlchemy)

### 1. Imports order

```python
# 1. stdlib
import asyncio
from datetime import datetime
from decimal import Decimal

# 2. third-party
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel

# 3. local
from config import settings
from models import User, BrokerConnection
from services.reconciliation_service import reconcile_account
```

**Why**: isort default order. Облегчает diff review и предотвращает
circular imports.

**Opt-out**: lazy imports внутри функций (импорт SDK, dotenv loading) — OK.

---

### 2. Naming

| Element | Convention | Example |
|---|---|---|
| Variables, functions | `snake_case` | `user_id`, `compute_balance` |
| Constants | `UPPER_CASE` | `ABS_TOLERANCE_RUB`, `METRIC_KEYS` |
| Classes | `PascalCase` | `BrokerConnection`, `StreamConsumer` |
| Private methods/vars | `_prefix` | `_load_connection`, `self._cache` |
| Dataclass fields | `snake_case` | `account_id`, `period_start` |
| Domain Enum values | `lowercase_snake` | `"buy_card"`, `"futures"` |

**Why**: PEP 8 + Python community standard.

---

### 3. Docstrings — Google-style

```python
def reconcile_account(
    db: Session,
    account_id: int,
    *,
    period_start: datetime,
    period_end: datetime,
) -> ReconciliationResult:
    """Запускает 3-way reconciliation для аккаунта за период.

    Args:
        db: SQLAlchemy session (caller manages transaction).
        account_id: Наш internal account ID.
        period_start: Начало периода (включительно, UTC).
        period_end: Конец периода (включительно, UTC).

    Returns:
        ReconciliationResult с 8 метриками + transformation warnings.

    Raises:
        ValueError: Если account не найден или disabled.
        BrokerError: Если broker_report fetch failed.
    """
```

**Why**: Google-style — наиболее distin. Easy для IDE preview + readable.
NumPy-style тоже OK но требует больше boilerplate.

**Opt-out**: trivial one-liners (`def _format(s): return s.upper()`) —
без docstring OK.

---

### 4. Type hints

```python
# ✅ Mandatory для public functions:
def fetch_operations(account_id: int, *, since: datetime) -> list[Operation]:
    ...

# ✅ Optional vs new-style union:
old_style: Optional[str] = None     # legacy code
new_style: str | None = None        # new code (Python 3.10+)

# ✅ Generic collections:
list[int], dict[str, Decimal], tuple[Operation, str, int]
# НЕ: List[int], Dict[str, Decimal] (typing module legacy)

# ✅ Pydantic models в endpoints:
@router.post("/account")
def create_account(payload: AccountCreateRequest) -> AccountResponse:
    ...
```

**Why**: Type hints — single source of truth для IDE + mypy + читателей.
PEP 604 new-style union (X | None) после 3.10 — стандарт.

**Opt-out**: lambdas в comprehensions, internal small helpers без public usage.

---

### 5. Error handling

```python
# ✅ Domain exceptions в domain/exceptions.py
class BrokerError(Exception): ...
class TokenInvalid(BrokerError): ...

# ✅ Raise rather than return None при ошибке:
def decrypt_token(ciphertext: str) -> str:
    if not ciphertext:
        raise TokenEncryptionError("empty ciphertext")
    # ... NOT: return None или return ""

# ✅ Catch specific, not bare except:
try:
    result = await api_call()
except BrokerUnavailable:
    # retry logic
except TokenInvalid:
    # deactivate
# Бare `except Exception:` only на boundary (router handlers, lifespan)

# ✅ Logging вместо silent swallow:
try:
    risky_op()
except Exception:
    log.exception("risky_op_failed")  # exc_info=True автоматически
    # Re-raise или явный fallback — никогда silent
```

**Why**: Domain exceptions делают error handling explicit на API
boundary. Bare except глотает baseline issues типа memory error.

---

### 6. Async patterns

```python
# ✅ to_thread для sync I/O в async context:
async def process(self):
    data = await asyncio.to_thread(self._load_from_db)  # SQLAlchemy sync
    await self._async_persist(data)

# ✅ asyncio.gather для parallel независимых:
results = await asyncio.gather(
    fetch_a(), fetch_b(), fetch_c(),
    return_exceptions=True,  # не aborts on first error
)

# ✅ asyncio.Lock per resource для coordination:
self._account_locks: dict[int, asyncio.Lock] = {}
async with self.get_account_lock(account_id):
    # exclusive access
    ...

# ✅ async with для cleanup (gRPC channels, DB sessions):
async with client_factory.async_client(token) as services:
    # services auto-closed на exit
    ...
```

**Why**: AsyncIO правила — нельзя блокировать event loop. SQLAlchemy
sync → `to_thread`. Locks — за explicit coordination (см. AU14 + AU-stream).

**Opt-out**: trivial sync-only modules (CLI tools без gRPC) — `asyncio.run(main())` достаточно.

---

### 7. SQLAlchemy patterns

```python
# ✅ UNIQUE constraints — explicit + name:
__table_args__ = (
    UniqueConstraint(
        "account_id", "operation_id",
        name="uq_operations_account_opid",  # обязательно name
    ),
    Index("ix_operations_account_executed_at", "account_id", "executed_at"),
)

# ✅ Numeric для денег, не Float:
amount = Column(Numeric(precision=18, scale=8), nullable=False)
# НЕ: Column(Float)  # потеря precision при умножении

# ✅ Session management — caller commits:
def create_user(db: Session, payload: UserCreate) -> User:
    user = User(**payload.dict())
    db.add(user)
    db.flush()  # получить id без commit
    return user
# commit() делает caller (router endpoint или test fixture)

# ✅ Query: filter по indexed columns:
db.query(Trade).filter(
    Trade.account_id == account_id,  # indexed
    Trade.exit_at >= since,  # indexed
).all()
# AVOID: filter по non-indexed column на больших таблицах
```

**Why**: Decimal preserves precision (критично для финансов). Session
management — за caller'ом (test isolation, transaction control).

---

### 8. Alembic migrations

```python
# Имя файла: NNNN_<purpose>.py
# Пример: 0020_broker_conn_stream_enabled.py

# ✅ Обязательно upgrade() + downgrade():
def upgrade() -> None:
    with op.batch_alter_table("broker_connections", schema=None) as batch:
        batch.add_column(
            sa.Column(
                "stream_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),  # для existing rows
            )
        )

def downgrade() -> None:
    with op.batch_alter_table("broker_connections", schema=None) as batch:
        batch.drop_column("stream_enabled")
```

**Правила**:
- `op.batch_alter_table` для SQLite compat (SQLite не поддерживает
  ALTER COLUMN в полной форме)
- `server_default` для NOT NULL columns с дефолтом (иначе existing rows не имеют value)
- Single `down_revision` — не создавай parallel ветки без merge

**Why**: Reversibility — обязательно для prod safety. Batch operations
для cross-dialect compat.

---

## Frontend (Next.js 16, React 19, TypeScript)

### 1. Folder structure

```
frontend/src/
├── app/                    # App Router pages
│   ├── (dashboard)/        # Route groups
│   ├── admin/
│   │   └── reconciliation/
│   │       ├── page.tsx
│   │       └── [id]/page.tsx
│   └── api/                # API routes (NOT for backend logic)
├── components/             # Shared React components
│   ├── BrokerConnectModal.tsx
│   ├── admin/              # Admin-only components
│   └── ui/                 # Generic primitives
└── lib/                    # Utils, API client, types
    ├── apiClient.ts        # Централизованный fetch
    └── types.ts
```

**Why**: Co-location pages and route-specific helpers под `app/`.
Shared components в `components/`. Utils — `lib/`.

---

### 2. Server vs Client Components

```tsx
// ✅ Server Component default (no "use client"):
// frontend/src/app/admin/page.tsx
import { getServerSession } from '@/lib/auth';
export default async function AdminPage() {
  const session = await getServerSession();
  return <div>Admin: {session.user.email}</div>;
}

// ✅ Client Component только когда нужно (state, effects, browser API):
// frontend/src/components/BrokerConnectModal.tsx
"use client";
import { useState } from 'react';
export function BrokerConnectModal() {
  const [open, setOpen] = useState(false);
  // ...
}

// ❌ AVOID: useState + useEffect в Server Component (runtime error)
```

**Why**: Server Components — default в Next.js 16. Меньше JS bundle,
direct DB access (через `lib/`). Client только для interactivity.

---

### 3. Naming

| Element | Convention | Example |
|---|---|---|
| Components | `PascalCase` | `BrokerConnectModal`, `ReconciliationTable` |
| Files | `PascalCase.tsx` для components | `BrokerConnectModal.tsx` |
| Hooks | `useXxx` | `useApi`, `useAuth` |
| Variables, functions | `camelCase` | `fetchUserData`, `isLoading` |
| Types/interfaces | `PascalCase` | `User`, `ApiResponse<T>` |
| Constants | `UPPER_CASE` | `MAX_RETRIES`, `API_BASE_URL` |

**Why**: React community standard. Hooks naming — mandatory React
convention (linter rule).

---

### 4. API client централизован

```typescript
// ✅ lib/apiClient.ts
import { redirect } from 'next/navigation';

export const api = {
  get: async <T>(url: string): Promise<T> => {
    const res = await fetch(`/api/proxy${url}`, { credentials: 'include' });
    if (res.status === 401) redirect('/login');
    if (!res.ok) throw new ApiError(res.status, await res.text());
    return res.json();
  },
  post: async <T>(url: string, body: unknown): Promise<T> => { ... },
};

// ✅ В компоненте:
const user = await api.get<User>('/auth/me');

// ❌ AVOID: fetch напрямую в компонентах
const res = await fetch('/api/proxy/auth/me');  // bypasses auth/error handling
```

**Why**: Single source для auth redirect, error parsing, base URL.
Изменения политики (например JWT refresh) — в одном месте.

---

### 5. TanStack Query — explicit staleTime

```typescript
// ✅ Per-query staleTime:
const { data } = useQuery({
  queryKey: ['user', userId],
  queryFn: () => api.get<User>(`/users/${userId}`),
  staleTime: 5 * 60 * 1000,  // 5 min — explicit
});

// ❌ AVOID: Default staleTime=0 (refetch on every render — spam API)
```

**Why**: TanStack default staleTime=0 → агрессивные refetch'и. Для
рекомендуем 1-5 min для user data, 30s для near-realtime (sync status).

---

## Tests (pytest)

### 1. Given-When-Then комментарии

```python
def test_classify_diff_per_metric_tolerance():
    # Given: realized_pnl с 4% diff (в пределах 5% tolerance)
    our = Decimal("100000")
    broker = Decimal("104000")

    # When: classify с metric=realized_pnl
    _, _, status, note = classify_diff(our, broker, metric="realized_pnl")

    # Then: status=ok (5% tolerance) + methodology note attached
    assert status == "ok"
    assert "Trade.net_pnl" in note
```

**Why**: Given-When-Then делает test intent явным. Easy для review
и для понимания при failure.

---

### 2. Naming: `test_<what>_<condition>_<expected>`

```python
def test_dedup_first_call_is_new():           # ✅
def test_dedup_cached_returns_not_new():       # ✅
def test_dedup_different_account_independent(): # ✅

# ❌ AVOID: vague names
def test_dedup_works():
def test_basic():
```

**Why**: Имя теста — first line of failure message. Хорошее имя =
половина дебага.

---

### 3. Mocks: AsyncMock для async, MagicMock для sync

```python
# ✅ Async function:
from unittest.mock import AsyncMock
mock_client = AsyncMock()
mock_client.get_accounts.return_value = AccountsResponse(...)

# ✅ Sync function:
from unittest.mock import MagicMock
mock_session = MagicMock()
mock_session.query.return_value.filter.return_value.first.return_value = user

# ❌ AVOID: MagicMock для async (вернёт coroutine wrapper, не значение):
mock_client = MagicMock()
result = await mock_client.get_accounts()  # ← TypeError or wrong type
```

**Why**: Python 3.8+ AsyncMock — proper async simulation. MagicMock —
sync only.

---

### 4. Factories или fixtures, не inline объекты

```python
# ✅ Fixture:
@pytest.fixture
def user(db: Session) -> User:
    user = User(email="test@example.com", ...)
    db.add(user)
    db.flush()
    return user

def test_user_action(user: User):
    # use user
    ...

# ✅ factory_boy если много вариаций:
class UserFactory(factory.alchemy.SQLAlchemyModelFactory):
    class Meta:
        model = User
    email = factory.Sequence(lambda n: f"user{n}@example.com")
```

**Why**: DRY. Mutation между тестами (один меняет email → next test
видит updated value) — отсекается через factory.

---

## Git

### 1. Commit message format

```
<type>: <short subject, imperative, ≤72 chars>

[optional body explaining WHY, not WHAT]

[optional footer: refs, breaking changes]

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

**Types**: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`.

**Examples**:
- `feat: AU16 per-metric tolerance + methodology notes`
- `fix: AU15 reconciliation commission double-count (ratio 1.0000)`
- `refactor: AU10 surgical rename tinkoff.invest → t_tech.invest`

**Why**: Conventional commits — readable changelog + tooling friendly.

---

### 2. Branch naming

```
feat/au16-per-metric-tolerance
fix/au15-commission-double-count
refactor/au10-sdk-migration
docs/error-catalog
```

**Why**: Type prefix + AU/Phase reference + short description.
Easy фильтровать branches по type.

---

### 3. Co-author Claude Opus 4.7

В commit message footer:
```
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

**Why**: Attribution + transparency. См. root CLAUDE.md.

---

## Cross-references

- `docs/ERROR_CATALOG.md` — known issues + fixes
- `docs/PREFLIGHT_CHECKLIST.md` — что читать перед сессией
- `docs/RUNBOOK.md` — operational procedures
- `.business/tech/decisions/` — ADR (architectural decisions)
- `CLAUDE.md` (root) — высокоуровневые принципы работы Claude
