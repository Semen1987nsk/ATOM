# Инструкции патчей: Reverse-Trial для общих файлов

> **Когда применять.** После того как параллельный агент (Tinkoff v2 / YooKassa / 152-ФЗ) сольёт свои изменения в main. До этого момента — **не трогать** перечисленные ниже файлы (см. координацию в `.business/tech/decisions/0005-reverse-trial-model.md` и плане Reverse-Trial).
>
> **Связанные документы:**
> - [`ADR-0005`](../tech/decisions/0005-reverse-trial-model.md) — обоснование Reverse-Trial
> - [`alembic/versions/0019_reverse_trial.py`](../../backend/alembic/versions/0019_reverse_trial.py) — миграция (уже создана)
> - [`services/subscription_service.py`](../../backend/services/subscription_service.py) — service-логика (уже создана)
> - [`feature-canon/04-downgrade-experience.md`](../product/feature-canon/04-downgrade-experience.md) — UX-эталон

---

## 1. `backend/models.py:Subscription` — новые поля

В существующий класс `Subscription` (около строки 61, см. EXPLORE-отчёт от 2026-05-14) добавить столбцы под миграцию 0019. Не менять существующие поля.

```python
# (внутри class Subscription)
status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="none")
trial_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
trial_ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
trial_summary_shown: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
frozen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

Если в проекте старый стиль (Column(...) без Mapped) — использовать его. Главное чтобы имена и типы совпали с миграцией `0019_reverse_trial.py`.

Существующий enum `SubscriptionPlan` (FREE/PRO/CORPORATE) **не менять** — он остаётся как ортогональная ось «целевой план». Новое поле `status` отслеживает жизненный цикл trial (см. `subscription_service.py` константы `STATUS_*`).

## 2. `backend/models.py:Trade` — флаг trial

В класс `Trade` (около строки 259) добавить:

```python
created_during_trial: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("0"))
```

Использование: фронт показывает Trade Replay только для сделок с `created_during_trial=True` на Free+ (через `<FrozenFeatureBadge />` на остальных).

## 3. `backend/models.py` — новая модель `AiRequestLog`

```python
class AiRequestLog(Base):
    __tablename__ = "ai_request_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    requested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    plan_at_request: Mapped[str] = mapped_column(String(32), nullable=False)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_rub: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
```

Используется `subscription_service.check_and_log_ai_request()` для cap'а 30 AI-запросов за trial.

## 4. `backend/sync_scheduler.py` — фильтр sync_enabled

Поле `BrokerConnection.auto_sync_enabled` **уже существует** (default=True). Нужно только использовать его в фильтре:

```python
# В методе _check_broker_sync() (или его v2-аналоге)
stmt = select(BrokerConnection).where(
    BrokerConnection.auto_sync_enabled == True,  # noqa: E712
    BrokerConnection.is_active == True,
)
```

`subscription_service.expire_trials()` уже выставляет `auto_sync_enabled = False` при downgrade — поэтому после фильтра Free+ юзеры автоматически выпадают из sync-цикла.

## 5. `backend/sync_scheduler.py` — cron-задача expire_trials

Добавить периодический вызов раз в час (по аналогии с уже существующим `_check_pd_finalizations` раз в 24h):

```python
from services import subscription_service

async def _check_trial_expirations(self) -> None:
    with self._session_factory() as db:
        try:
            downgraded = subscription_service.expire_trials(db)
            db.commit()
            if downgraded:
                # TODO: запустить email-flow D+21 с PDF для каждого user_id
                # (см. feature-canon/04-downgrade-experience.md §«Email-шаблоны»)
                log.info(f"trial expirations: notify {len(downgraded)} users")
        except Exception:
            db.rollback()
            log.exception("expire_trials failed")
```

Зарегистрировать в основном цикле scheduler'а — рядом с PD-finalize.

## 6. `backend/routers/auth.py:register` — старт trial при регистрации

В конце успешной регистрации (после создания юзера, после записи pd_consent — см. ADR-0002):

```python
from services import subscription_service

# ... после создания user, добавления pd_consent
subscription_service.start_trial(db, user)
db.commit()
```

`start_trial` идемпотентен — повторный вызов не сбрасывает уже идущий trial.

## 7. `backend/routers/payments.py` — upgrade при оплате

В webhook YooKassa (или там, где сейчас обрабатывается успешная оплата `payment.succeeded`):

```python
from services import subscription_service

# После того как Payment записан как succeeded и подписка должна стать pro:
subscription_service.upgrade_to_pro(db, user)
db.commit()
```

Эта функция: status → pro_active, frozen_at → None, auto_sync_enabled у всех брокеров → True (включает sync **мгновенно без повторного ввода токена** — ключевой UX по ADR-0005).

## 8. Новый роутер `backend/routers/subscription.py`

```python
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from db import get_db
from auth_deps import get_current_user
from services import subscription_service
import models

router = APIRouter(prefix="/subscription", tags=["subscription"])


@router.get("/status")
def get_status(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Глобальный план юзера для фронта (SubscriptionContext)."""
    sub = current_user.subscription  # backref/relationship
    return subscription_service.to_status_payload(sub)


@router.post("/trial-summary-shown")
def mark_summary_shown(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Фронт вызывает после показа D+21 dialog, чтобы он не повторялся."""
    subscription_service.mark_trial_summary_shown(db, current_user)
    db.commit()
    return {"ok": True}


@router.get("/trial-summary")
def get_trial_summary(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Содержимое D+21 dialog: количество сделок trial-периода, 0-3 AI-инсайта,
    URL PDF-отчёта. TODO: реализовать на основе trade.created_during_trial."""
    return {
        "trades_count": 0,  # TODO: count where created_during_trial=True
        "insights": [],     # TODO: последние 3 AI-инсайта из trial
        "pdf_url": None,    # TODO: ссылка на PDF-отчёт trial-периода
    }
```

Зарегистрировать в `main.py` рядом с другими роутерами:

```python
from routers import subscription
app.include_router(subscription.router)
```

## 9. Frontend — провайдер и интеграция

Параллельный агент **не трогает** frontend. После создания компонентов (уже сделано: `SubscriptionContext.tsx`, `FrozenFeatureBadge.tsx`, `TrialCountdownBanner.tsx`, `TrialEndedDialog.tsx`, `pricing/page-v2.tsx`) — нужно:

1. **`frontend/src/app/layout.tsx`** или `Providers.tsx` — обернуть приложение в `<SubscriptionProvider>` после `<AuthProvider>`:

```tsx
<AuthProvider>
  <SubscriptionProvider>
    {children}
  </SubscriptionProvider>
</AuthProvider>
```

2. **`frontend/src/app/dashboard/layout.tsx`** или эквивалент — добавить `<TrialCountdownBanner />` и `<TrialEndedDialog />` в верх dashboard'а.

3. **Заменить `pricing/page.tsx`** на содержимое `page-v2.tsx` (после слияния параллельного агента). Удалить `page-v2.tsx`.

4. **На детальной странице сделки** — на Free+ оборачивать AI-секцию, MAE/MFE-секцию, Trade Replay секцию в `<FrozenFeatureBadge />` + `<FrozenFeatureCTA feature="...">`. Использовать `useSubscription().can('new_ai_insight')` для проверки прав.

## 10. ЮKassa блокер

До запуска reverse-trial — должна быть закрыта ЮKassa интеграция (блокер C2, см. `.business/tech/audit-report.md`). Без приёма платежей upgrade-flow не работает.

---

## Чек-лист применения патчей

- [ ] Параллельный агент слил Tinkoff v2 / YooKassa / 152-ФЗ изменения в main
- [ ] §1-3: модели `Subscription`, `Trade`, `AiRequestLog` обновлены
- [ ] Миграция `0019_reverse_trial.py` запущена (`alembic upgrade head`)
- [ ] §4-5: `sync_scheduler.py` — фильтр и cron expire_trials
- [ ] §6: `auth.py:register` вызывает `start_trial`
- [ ] §7: `payments.py` webhook вызывает `upgrade_to_pro`
- [ ] §8: роутер `subscription.py` создан и зарегистрирован
- [ ] §9: `SubscriptionProvider` добавлен в Providers, баннеры в dashboard, pricing.tsx заменён
- [ ] ЮKassa интеграция завершена
- [ ] E2E-тест: регистрация → trial 21d → симуляция конца → free_plus → upgrade → pro_active, sync мгновенно
- [ ] Policy v2 опубликована (см. `.business/compliance/policy-versions.md`)
- [ ] Feature-flag `reverse_trial_v1_enabled` готов для отката

## Что НЕ делать при патчах

- ❌ Не зануляют API-токен брокера при downgrade — это явный анти-паттерн, см. ADR-0005. Токен остаётся зашифрованным, только `auto_sync_enabled = False`.
- ❌ Не показывать модальные окна «Купи Pro» — только inline-CTA, см. `feature-canon/04`.
- ❌ Не запрашивать карту при старте trial — анти-паттерн TradeZella.
- ❌ Не использовать эмодзи в кнопках/заголовках — только lucide-react (см. design-system).
- ❌ Не использовать purple-indigo градиенты — DS-анти-паттерн «Discord».
