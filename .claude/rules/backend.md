---
paths:
  - "backend/**"
  - "postgres/**"
  - "docker-compose*.yml"
---

# Backend: FastAPI, SQLAlchemy 2.0, Alembic, брокеры

- **P&L — сначала инварианты:** любая правка журнала, cash, reconcile, FIFO, вармаржи или формулы фьючерсов начинается с чтения [ADR-0007](../../.business/tech/decisions/0007-pnl-methodology-invariants.md); куда смотреть, когда числа не сходятся, — [docs/PNL_PLAYBOOK.md](../../docs/PNL_PLAYBOOK.md). P&L — денежное число: работа, меняющая его расчёт, — риск Р2.
- **Известные ошибки** — перед расследованием grep по [docs/ERROR_CATALOG.md](../../docs/ERROR_CATALOG.md): TLS и grpcio — ERR-001..010, T-Bank и broker_report — ERR-101..112, Alembic — ERR-201..206.
- **Контракты внешних API** — `docs/TINKOFF_*.md`, `docs/MOEX_*.md`; скиллы репо `fastapi-sqlalchemy-patterns`, `moex-iss-api-patterns`, `152-fz-compliance-checklist` срабатывают по триггерам.
- **Стиль** — [docs/CODING_CONVENTIONS.md](../../docs/CODING_CONVENTIONS.md); противоречит готовому паттерну кода — следуй паттерну.
- **Готово, по типу правки** (на добросовестности):

| Тип | Что зелёное до «готово» |
|---|---|
| Код backend | `pytest tests/unit -q` и `python -c "from main import app"` |
| Миграция | `alembic upgrade head`, `alembic check`, проход вверх-вниз |
| Эндпоинт | smoke-запрос плюс тест на успех и тест на ошибку |
| Интеграция T-Bank | живой smoke на sandbox с `TINKOFF_GRPC_CA_BUNDLE` |
| Сверка и аудит | сверка счёта даёт audit=0 и ни одного нового HARD-разрыва |

- После правки Pydantic-схем очищай `backend/__pycache__`: `--reload` иначе отдаёт старую `response_model`.
