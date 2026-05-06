# ATOM — AI-Powered Trading Journal

**Умный торговый дневник** для серьёзных трейдеров с продвинутой аналитикой и real-time данными с Московской биржи.

## 🚀 Быстрый старт

### Требования
- Python 3.11+
- Node.js 18+
- npm или yarn

### Установка

```bash
# Клонирование репозитория
git clone <repo-url>
cd ATOM

# Backend
cd backend
pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000

# Frontend (в новом терминале)
cd frontend
npm install
npm run dev
```

Приложение будет доступно на:
- **Frontend:** http://localhost:3000
- **Backend API:** http://localhost:8000
- **API Docs:** http://localhost:8000/docs

### VS Code Tasks
Проект содержит готовые задачи для запуска:
- `Run Backend` — запуск FastAPI сервера
- `Run Frontend` — запуск Next.js dev server

---

## 📁 Структура проекта

```
ATOM/
├── backend/
│   ├── main.py              # FastAPI endpoints (все API)
│   ├── models.py            # SQLAlchemy models (User, Trade, Article, Subscription...)
│   ├── schemas.py           # Pydantic schemas (валидация)
│   ├── database.py          # SQLite connection
│   ├── analytics.py         # Торговые метрики (Optimal f, SQN, Z-Score...)
│   ├── market_service.py    # MOEX API интеграция
│   ├── import_service.py    # Парсер Excel/PDF (Тинькофф, ФИНАМ)
│   ├── auth_service.py      # JWT аутентификация, bcrypt
│   ├── oauth_service.py     # OAuth2 (Google, Yandex, Sber, Tinkoff)
│   ├── admin_service.py     # Аналитика для админ-панели
│   ├── blog_service.py      # CRUD для блога
│   ├── ai_service.py        # OpenAI интеграция
│   ├── logger.py            # Логирование
│   └── tests/               # Pytest тесты
│
├── frontend/
│   ├── src/
│   │   ├── app/             # Next.js 14 App Router
│   │   │   ├── page.tsx          # Главный дашборд
│   │   │   ├── login/            # Страница входа
│   │   │   ├── register/         # Регистрация
│   │   │   ├── profile/          # Профиль пользователя
│   │   │   ├── admin/            # Админ-панель
│   │   │   ├── blog/             # Блог (список + статья)
│   │   │   ├── help/             # Центр помощи (FAQ)
│   │   │   ├── pricing/          # Тарифы
│   │   │   ├── history/          # Дневник сделок
│   │   │   └── manual/           # Мануал
│   │   ├── components/      # React компоненты
│   │   ├── contexts/        # React Context (Auth, Settings)
│   │   └── i18n/            # Локализация (ru, en)
│   └── package.json
│
├── docs/
│   ├── TRADE_MODEL.md       # Документация модели Trade
│   └── DEVELOPER_GUIDE.md   # Гайд для разработчиков
│
├── PRODUCT_SPEC.md          # Product Requirements Document
├── BUSINESS_PLAN.md         # Бизнес-план
└── README.md                # Этот файл
```

---

## 🔐 Аутентификация

### JWT + bcrypt
- Регистрация: `POST /auth/register`
- Вход: `POST /auth/login`
- Профиль: `GET /auth/me` (требует токен)

### OAuth2 провайдеры
- Google
- Яндекс
- Сбер ID
- Тинькофф ID

### Создание админа

Тестовый seed-аккаунт **больше не задаётся в репозитории** — это был security-ляп.
Чтобы создать первого администратора, задай переменные окружения и запусти init-скрипт:

```bash
export ADMIN_BOOTSTRAP_EMAIL="you@example.com"
export ADMIN_BOOTSTRAP_PASSWORD="$(python -c 'import secrets; print(secrets.token_urlsafe(24))')"
python -m scripts.create_admin   # см. docs/DEVELOPER_GUIDE.md
```

Если в .env эти переменные не заданы — в проде admin не создаётся, а в DEBUG-режиме
выводится предупреждение в логи.

---

## 📊 Ключевые метрики

| Метрика | Описание |
|---------|----------|
| **Optimal f** | Оптимальная доля капитала по Ralph Vince |
| **SQN** | System Quality Number по Van Tharp |
| **Z-Score** | Анализ последовательностей |
| **Profit Factor** | Отношение прибыли к убыткам |
| **R-Expectancy** | Мат. ожидание в единицах риска |
| **MAE/MFE** | Просадка и потенциал сделок (из MOEX) |
| **Recovery Factor** | Скорость восстановления |
| **Sortino Ratio** | Доходность с учётом риска |
| **Monte Carlo** | Симуляция 10,000 сценариев |

---

## 💳 Тарифы

| План | Цена | Описание |
|------|------|----------|
| **Free** | 0₽ | До 50 сделок, базовая аналитика |
| **Pro** | 399₽/мес | Безлимит, AI-анализ, MAE/MFE |
| **Corporate** | Индивидуально | Для проп-трейдинг компаний |

---

## 📝 API Reference

### Auth
| Метод | Endpoint | Описание |
|-------|----------|----------|
| POST | `/auth/register` | Регистрация |
| POST | `/auth/login` | Вход |
| GET | `/auth/me` | Текущий пользователь |
| PUT | `/auth/me` | Обновить профиль |
| GET | `/auth/subscription` | Подписка пользователя |

### Trades
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/trades/` | Список сделок |
| POST | `/trades/` | Создать сделку |
| PATCH | `/trades/{id}` | Обновить сделку |
| PATCH | `/trades/{id}/close` | Закрыть сделку |
| DELETE | `/trades/{id}` | Удалить сделку |
| GET | `/stats/` | Статистика и аналитика |
| POST | `/import/tinkoff` | Импорт из Тинькофф |

### Blog
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/blog/articles` | Список статей |
| GET | `/blog/article/{slug}` | Статья по slug |
| GET | `/blog/categories` | Категории |
| GET | `/blog/popular` | Популярные статьи |

### Admin (требует is_admin=true)
| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/admin/stats` | Общая статистика |
| GET | `/admin/users` | Список пользователей |
| GET | `/admin/revenue` | Выручка и MRR |
| GET/POST/PUT/DELETE | `/admin/articles` | Управление блогом |

---

## 🧪 Тестирование

```bash
cd backend
python -m pytest tests/ -v
```

---

## 🔧 Environment Variables

```env
# База данных (по умолчанию SQLite)
DATABASE_URL=sqlite:///./atom.db

# AI-анализ (опционально)
OPENAI_API_KEY=sk-...

# OAuth (опционально)
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
YANDEX_CLIENT_ID=...
YANDEX_CLIENT_SECRET=...
```

---

## 🛠️ Для разработчиков

### Добавление нового API endpoint

1. Добавить модель в `models.py` (если нужно)
2. Добавить схему в `schemas.py`
3. Создать сервис в `*_service.py`
4. Добавить endpoint в `main.py`

### Добавление новой страницы

1. Создать папку в `frontend/src/app/`
2. Создать `page.tsx`
3. При необходимости добавить в навигацию

### Стилизация

- Tailwind CSS с кастомными классами
- `cyber-card` — основная карточка
- `btn-primary`, `btn-secondary` — кнопки
- Цветовая палитра в `globals.css`

---

## 📄 Документация

- [TRADE_MODEL.md](docs/TRADE_MODEL.md) — модель сделок
- [DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md) — гайд разработчика
- [PRODUCT_SPEC.md](PRODUCT_SPEC.md) — спецификация продукта
- [BUSINESS_PLAN.md](BUSINESS_PLAN.md) — бизнес-план

---

## 🛡️ Лицензия

MIT
