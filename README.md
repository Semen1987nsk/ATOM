# Eqio — AI-Powered Trading Journal

**Smart Tradebook** для серьёзных трейдеров с продвинутой аналитикой и real-time данными с Московской биржи.

## 🚀 Быстрый старт

### Требования
- Python 3.11+
- Node.js 18+
- npm или yarn

### Установка

```bash
# Клонирование репозитория
git clone <repo-url>
cd Eqio

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

## 📊 Функционал

### Аналитика
- **Optimal f** — оптимальная доля капитала (по Ralph Vince)
- **SQN** — System Quality Number (по Van Tharp)
- **Z-Score** — анализ последовательностей побед/поражений
- **Profit Factor** — отношение прибыльных сделок к убыточным
- **R-Expectancy** — математическое ожидание в единицах риска
- **MAE/MFE анализ** — максимальное неблагоприятное/благоприятное отклонение
- **Recovery Factor** — скорость восстановления после просадок

### Real-time данные
- Интеграция с **MOEX ISS API**
- Поддержка: акции (TQBR), фьючерсы (RFUD), валюты (CETS)
- Автообновление нереализованного PnL каждые 10 секунд

### Управление сделками
- FIFO-логика автозакрытия при flip
- Группировка связанных сделок (усреднение)
- Импорт из Тинькофф Excel
- Экспорт в CSV

## 🧪 Тестирование

```bash
cd backend
python -m pytest tests/ -v
```

## 📁 Структура проекта

```
Eqio/
├── backend/
│   ├── main.py          # FastAPI endpoints
│   ├── models.py        # SQLAlchemy models
│   ├── analytics.py     # Trading metrics
│   ├── market_service.py # MOEX API
│   ├── import_service.py # Excel parser
│   ├── logger.py        # Centralized logging
│   └── tests/           # Pytest tests
├── frontend/
│   ├── src/
│   │   ├── app/         # Next.js pages
│   │   └── components/  # React components
│   └── package.json
└── README.md
```

## 🔧 Конфигурация

### Environment Variables
```env
DATABASE_URL=sqlite:///./eqio.db   # По умолчанию SQLite
OPENAI_API_KEY=sk-...              # Для AI-анализа (опционально)
```

## 📝 API Endpoints

| Метод | Endpoint | Описание |
|-------|----------|----------|
| GET | `/trades/` | Список всех сделок |
| POST | `/trades/` | Создать сделку |
| PATCH | `/trades/{id}/close` | Закрыть сделку |
| DELETE | `/trades/{id}` | Удалить сделку |
| GET | `/stats/` | Статистика и аналитика |
| GET | `/trades/unrealized-pnl` | Нереализованный PnL |
| POST | `/import/tinkoff` | Импорт из Тинькофф |

## 🛡️ Лицензия

MIT
