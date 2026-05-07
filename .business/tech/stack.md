# Технологический стек Eqio

## Подключённые MCP-серверы

| Сервер | Статус | Зачем нужен |
|---|---|---|
| `context7` | ✅ активен | Актуальная документация библиотек (FastAPI, Next.js, Tailwind…) |
| `deepwiki` | ✅ активен | Изучение чужих репозиториев (TradeZella forks, MOEX-клиенты) |
| `github` | ✅ активен | Issues / PR / search code |
| `playwright` | ✅ активен | E2E-тесты фронта (когда напишем) |

## MCP-серверы к подключению (отложено)

Ждут решений пользователя по Sentry / YouTrack / Yandex Cloud / YooKassa:

| Сервер | URL | Когда подключаем |
|---|---|---|
| Sentry MCP self-hosted | github.com/ddfourtwo/sentry-selfhosted-mcp | После поднятия self-hosted Sentry в Yandex Cloud |
| Yandex Cloud MCP | github.com/yandex-cloud/mcp | После регистрации аккаунта YC |
| YouTrack MCP | jetbrains.com/help/youtrack/server/model-context-protocol-server | После выбора JetBrains Cloud vs self-hosted |
| YooKassa MCP | github.com/theYahia/yookassa-mcp | После регистрации shop в ЮKassa |
| PostgreSQL MCP (pgEdge) | github.com/pgedge/pgedge-mcp | Когда уйдём с SQLite |

## НЕ подключать

- Stripe MCP (РФ-санкции)
- Memory / sequential-thinking MCP (плацебо для архитектуры)
- Browserbase / Puppeteer (Playwright уже есть)
- AWS MCP (нельзя для РФ-данных по 152-ФЗ)
- Linear MCP (определились на YouTrack)

## Скиллы Eqio (`.claude/skills/`)

Активны и протестированы на реальных задачах:

| Skill | Назначение | Триггеры |
|---|---|---|
| `152-fz-compliance-checklist` | Соответствие 152-ФЗ для РФ | «согласие на ОПД», «РКН», «удаление аккаунта», «персональные данные» |
| `fastapi-sqlalchemy-patterns` | Паттерны FastAPI + SQLAlchemy 2.0 + Alembic | «новый роутер», «миграция», «N+1», «pydantic» |
| `moex-iss-api-patterns` | Работа с MOEX ISS API | «MOEX», «свечи», «ISS», «MAE/MFE» |
| `nextjs-react19-server-patterns` | Server Components + Suspense + streaming | «Server Component», «Suspense», «streaming», «page.tsx» |

Дополнительные глобальные скиллы (доступны из `~/.claude/skills/`):
`frontend-design`, `claude-api`, `review`, `security-review`, `simplify`, `update-config`, `init`.

## VS Code расширения (`.vscode/extensions.json`)

23 рекомендации в 5 группах:
- **Python**: ms-python.python, vscode-pylance, mypy-type-checker, charliermarsh.ruff, FastAPILabs.fastapi-vscode
- **TypeScript/React**: dbaeumer.vscode-eslint, esbenp.prettier-vscode, yoavbls.pretty-ts-errors, usernamehw.errorlens, bradlc.vscode-tailwindcss, heybourn.headwind
- **БД/DevOps**: mtxr.sqltools (+ driver-pg), ms-azuretools.vscode-docker, ms-vscode-remote.remote-containers, rangav.vscode-thunder-client
- **Git**: eamodio.gitlens, mhutchie.git-graph, editorconfig.editorconfig, gruntfuggly.todo-tree
- **Документация**: yzhang.markdown-all-in-one, bpruitt-goddard.mermaid-markdown-syntax-highlighting, hediet.vscode-drawio

`unwantedRecommendations`: ms-python.black-formatter, ms-python.flake8, ms-python.pylint, humao.rest-client (Ruff и Thunder Client их заменяют).

## VS Code конфигурация

- `.vscode/settings.json` — Ruff format-on-save для Python, Prettier для TS, Tailwind IntelliSense, исключения `__pycache__`, `.next`, `node_modules` из поиска
- `.vscode/launch.json` — debug-конфиги для backend (FastAPI debugpy), pytest, frontend (Next.js + Chrome), compound «Full Stack»
- `.vscode/tasks.json` — задачи `Run Backend` / `Run Frontend` (быстрый запуск)

## Среда разработки (по факту на 07.05.2026)

| Что | Версия | Статус |
|---|---|---|
| VS Code | 1.117 | ✅ |
| Python | 3.14.4 | ✅ (новейший — но осторожно, requirements проекта могут лимитировать) |
| Node.js | 24.15 | ✅ |
| npm | 11.12 | ✅ |
| git | 2.54 | ✅ |
| Docker | — | ❌ **не установлен** (расширения поставлены, но не работают) |
