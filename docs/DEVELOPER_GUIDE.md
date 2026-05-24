# ATOM Developer Guide

Руководство для разработчиков проекта ATOM — торгового дневника для трейдеров.

**Последнее обновление:** 4 января 2026

---

## 📋 Содержание

1. [Архитектура](#архитектура)
2. [Backend](#backend)
3. [Frontend](#frontend)
4. [Аутентификация](#аутентификация)
5. [База данных](#база-данных)
6. [API Reference](#api-reference)
7. [Добавление функционала](#добавление-функционала)
8. [Стилизация](#стилизация)
9. [Тестирование](#тестирование)

---

## Архитектура

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Frontend      │────▶│   Backend       │────▶│   SQLite DB     │
│   Next.js 14    │     │   FastAPI       │     │   atom.db       │
│   Port: 3000    │     │   Port: 8000    │     │                 │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                        ┌────────▼────────┐
                        │   MOEX ISS API  │
                        │   (котировки)   │
                        └─────────────────┘
```

### Ключевые принципы
- **Монолитный бэкенд** — все эндпоинты в `main.py`
- **Сервисный слой** — бизнес-логика в `*_service.py` файлах
- **SQLite** — простая БД, легко мигрировать на PostgreSQL
- **JWT токены** — stateless аутентификация
- **Изоляция данных** — каждый пользователь видит только свои сделки

---

## Backend

### Структура файлов

| Файл | Назначение |
|------|------------|
| `main.py` | Все FastAPI endpoints, middleware |
| `models.py` | SQLAlchemy ORM модели |
| `schemas.py` | Pydantic схемы валидации |
| `database.py` | Подключение к БД, сессии |
| `analytics.py` | Торговые метрики (Optimal f, SQN...) |
| `market_service.py` | Интеграция MOEX ISS API |
| `import_service.py` | Парсинг Excel/PDF брокеров |
| `auth_service.py` | JWT, bcrypt, работа с пользователями |
| `oauth_service.py` | OAuth2 провайдеры |
| `admin_service.py` | Аналитика для админ-панели |
| `blog_service.py` | CRUD статей блога |
| `ai_service.py` | Интеграция OpenAI |
| `logger.py` | Centralized logging |

### Основные модели (models.py)

```python
# Пользователь
class User(Base):
    id, email, name, hashed_password
    is_active, is_admin
    oauth_provider, oauth_provider_id
    registration_source, utm_source...

# Сделка
class Trade(Base):
    id, account_id, symbol, direction
    entry_price, exit_price, quantity
    pnl, net_pnl, commission, swap
    mae_price, mfe_price, r_multiple
    tags, notes, ai_analysis...

# Подписка
class Subscription(Base):
    id, user_id, plan (FREE/PRO/CORPORATE)
    is_active, expires_at, auto_renew
    max_trades, max_accounts, ai_analysis_enabled

# Платёж
class Payment(Base):
    id, user_id, amount, currency, status
    payment_method, card_last4...

# Статья блога
class Article(Base):
    id, slug, title, excerpt, content
    category (news/guides/analytics/tips/updates)
    tags, author_id, is_published, is_featured
    views_count, likes_count...
```

### Добавление нового endpoint

```python
# main.py

@app.get("/my-new-endpoint", tags=["category"])
def my_new_endpoint(
    param: str = Query(default="value"),
    db: Session = Depends(database.get_db),
    current_user: models.User = Depends(auth_service.get_current_user)  # если нужна авторизация
):
    """Описание endpoint для документации"""
    # Бизнес-логика
    result = my_service.do_something(db, param)
    return result
```

### Защита endpoint

```python
# Только авторизованные
current_user: models.User = Depends(auth_service.get_current_user)

# Авторизация опционально (для гибридных страниц)
current_user: Optional[models.User] = Depends(auth_service.get_current_user_optional)

# Только админы
admin: models.User = Depends(require_admin)
```

---

## Frontend

### Структура App Router

```
src/app/
├── page.tsx              # Главный дашборд (/)
├── layout.tsx            # Root layout, провайдеры
├── globals.css           # Tailwind + кастомные стили
├── login/page.tsx        # /login
├── register/page.tsx     # /register
├── profile/page.tsx      # /profile (защищённая)
├── admin/page.tsx        # /admin (только для админов)
├── blog/
│   ├── page.tsx          # /blog (список статей)
│   └── [slug]/page.tsx   # /blog/:slug (статья)
├── help/page.tsx         # /help (FAQ)
├── pricing/page.tsx      # /pricing (тарифы)
├── history/page.tsx      # /history (сделки)
└── manual/page.tsx       # /manual
```

### Контексты (React Context)

```typescript
// AuthContext — авторизация
const { user, token, login, logout, isLoading } = useAuth();

// SettingsContext — настройки пользователя
const { settings, formatCurrency, updateSettings } = useSettings();

// LanguageContext — локализация
const { t, language, setLanguage } = useLanguage();
```

### Защита страниц

```tsx
// Требует авторизации
import { RequireAuth } from '@/contexts/AuthContext';

export default function ProtectedPage() {
  return (
    <RequireAuth>
      <MyContent />
    </RequireAuth>
  );
}
```

### API вызовы

```typescript
// Получение API URL (с поддержкой Codespaces)
const getApiUrl = (path: string) => {
  if (typeof window !== 'undefined' && window.location.hostname.includes('github.dev')) {
    const codespaceName = window.location.hostname.split('-3000')[0];
    return `https://${codespaceName}-8000.app.github.dev${path}`;
  }
  return `http://localhost:8000${path}`;
};

// Запрос с авторизацией
const { token } = useAuth();
const res = await fetch(getApiUrl('/endpoint'), {
  headers: { Authorization: `Bearer ${token}` }
});
```

---

## Аутентификация

### Поток регистрации/входа

```
1. POST /auth/register → создаёт User + Account + Subscription(FREE)
2. POST /auth/login → возвращает JWT токен
3. Клиент сохраняет токен в localStorage
4. Все запросы с заголовком: Authorization: Bearer <token>
5. GET /auth/me → возвращает текущего пользователя
```

### JWT токен

```python
# Генерация (auth_service.py)
payload = {
    "sub": user.id,
    "email": user.email,
    "exp": datetime.utcnow() + timedelta(days=30)
}
token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
```

### OAuth2 провайдеры

| Провайдер | Callback URL | Примечания |
|-----------|--------------|------------|
| Google | `/auth/google/callback` | Полностью рабочий |
| Яндекс | `/auth/yandex/callback` | Полностью рабочий |
| Сбер ID | `/auth/sber/callback` | Требует сертификацию |
| Тинькофф ID | `/auth/tinkoff/callback` | Требует договор |

---

## База данных

### SQLite (по умолчанию)

```python
# database.py
DATABASE_URL = "sqlite:///./atom.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
```

### Миграция на PostgreSQL

```python
# Изменить в database.py
DATABASE_URL = "postgresql://user:pass@localhost/atom"
engine = create_engine(DATABASE_URL)  # убрать check_same_thread
```

### Создание таблиц

```python
# При запуске приложения
Base.metadata.create_all(bind=engine)
```

### Seed данные

```bash
cd backend
python seed_data.py  # Создаёт тестового админа
```

---

## API Reference

### Группы эндпоинтов

| Группа | Prefix | Описание |
|--------|--------|----------|
| Auth | `/auth/` | Регистрация, вход, профиль |
| Trades | `/trades/` | CRUD сделок |
| Stats | `/stats/` | Аналитика и метрики |
| Import | `/import/` | Импорт из брокеров |
| Market | `/market/` | Котировки MOEX |
| Blog | `/blog/` | Публичные статьи |
| Admin | `/admin/` | Управление (только админы) |

### Swagger документация

Доступна по адресу: `http://localhost:8000/docs`

---

## Добавление функционала

### Новая метрика аналитики

1. Добавить расчёт в `analytics.py`:
```python
def calculate_new_metric(trades: list) -> float:
    # логика
    return result
```

2. Добавить в `get_dashboard_stats()`:
```python
return {
    ...existing,
    "new_metric": calculate_new_metric(trades)
}
```

3. Добавить в схему `schemas.py`:
```python
class DashboardStats(BaseModel):
    ...
    new_metric: float = 0
```

4. Добавить карточку в `frontend/src/app/page.tsx`

### Новая страница

1. Создать `frontend/src/app/my-page/page.tsx`:
```tsx
'use client';

export default function MyPage() {
  return <div>My Content</div>;
}
```

2. Добавить в навигацию (если нужно)

### Новая модель данных

1. Добавить в `models.py`
2. Добавить схемы в `schemas.py`
3. Создать сервис `my_service.py`
4. Добавить endpoints в `main.py`
5. Перезапустить бэкенд (таблицы создадутся автоматически)

---

## Стилизация

### Tailwind классы

| Класс | Описание |
|-------|----------|
| `cyber-card` | Основная карточка с рамкой |
| `btn-primary` | Зелёная кнопка (accent) |
| `btn-secondary` | Серая кнопка (secondary) |
| `card` | Алиас для cyber-card |

### Цветовая схема (globals.css)

```css
:root {
  --background: #0a0a0a;
  --foreground: #ededed;
  --card: #141414;
  --border: #262626;
  --accent: #22c55e;        /* Зелёный */
  --accent-secondary: #8b5cf6; /* Фиолетовый */
  --muted-foreground: #888;
}
```

### Иконки

Используем **Lucide React**:
```tsx
import { Plus, Upload, Settings } from 'lucide-react';
<Plus size={16} />
```

---

## Тестирование

### Backend тесты

```bash
cd backend
python -m pytest tests/ -v
```

### Структура тестов

```
tests/
├── conftest.py          # Fixtures (db, client)
├── test_trades.py       # CRUD сделок
├── test_analytics.py    # Метрики
├── test_mae_mfe.py      # MAE/MFE расчёты
└── test_market_service.py # MOEX API
```

### Пример теста

```python
def test_create_trade(client, db):
    response = client.post("/trades/", json={
        "symbol": "SBER",
        "direction": "long",
        "entry_price": 250.0,
        "quantity": 10,
        "entry_at": "2025-01-01T10:00:00",
        "account_id": 1
    })
    assert response.status_code == 200
    assert response.json()["symbol"] == "SBER"
```

---

## Полезные команды

```bash
# Запуск бэкенда
cd backend && python -m uvicorn main:app --reload --port 8000

# Запуск фронтенда
cd frontend && npm run dev

# Тесты
cd backend && python -m pytest tests/ -v

# Проверка типов
cd frontend && npx tsc --noEmit

# Линтинг
cd frontend && npm run lint
```

---

## FAQ для разработчиков

**Q: Как добавить нового OAuth провайдера?**
A: Добавить функции в `oauth_service.py`, добавить endpoints в `main.py`, добавить кнопку на странице входа.

**Q: Как изменить лимиты тарифов?**
A: Изменить в `auth_service.py` → `create_subscription()` и `PLAN_LIMITS`.

**Q: Как добавить новую категорию блога?**
A: Добавить в enum `ArticleCategory` в `models.py`, обновить UI.

**Q: Как подключить OpenAI?**
A: Установить `OPENAI_API_KEY` в env, использовать `ai_service.py`.

---

## Контакты

- **Поддержка:** support@empirik.app
- **Telegram:** @atom_support_bot
