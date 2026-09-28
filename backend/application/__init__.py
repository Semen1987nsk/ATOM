"""
Application слой (use cases / orchestrators). Тонкий координирующий слой
между API endpoint'ами (`routers/`) и domain/adapter слоями.

- `sync/`             — TinkoffSyncOrchestrator + pipeline (PR 5).
- `fifo_matching.py`  — FIFO-движок (PR 7).
- `token_management.py` — подключение/echo-валидация токенов (PR 4+12).
- `events/`           — in-process event bus (PR 5+).
"""
