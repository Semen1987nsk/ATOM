# Eqio Stack — Tools, MCP-серверы, Скиллы

Реестр всех инструментов проекта. Отвечает на вопросы:
«Чем мы пользуемся?», «Когда что включать?», «Что для чего».

Дата последнего обновления: 2026-05-06.

---

## 1. Production-стек

### Backend
| Что | Версия | Где |
|---|---|---|
| Python | 3.11+ | `backend/` |
| FastAPI | 0.109+ | `backend/main.py` |
| SQLAlchemy | 2.0+ | `backend/models.py` |
| Pydantic | v2 | `backend/schemas.py` |
| Alembic | 1.13+ | `backend/alembic/` |
| PostgreSQL | 16 | `docker-compose.yml` |
| Redis | 7 | `docker-compose.yml` |
| Sentry SDK | 2.0+ | `backend/observability.py` |
| structlog / json-logger | latest | `backend/logger.py` |

### Frontend
| Что | Версия | Где |
|---|---|---|
| Next.js | 16.1+ | `frontend/next.config.ts` |
| React | 19.2+ | `frontend/package.json` |
| TypeScript | strict | `frontend/tsconfig.json` |
| Tailwind CSS | v4 | `frontend/postcss.config.mjs` |
| TanStack Query | 5.59+ | `frontend/src/contexts/` |
| Recharts | 3.6+ | `frontend/src/components/dashboard/` |
| cmdk | latest | `frontend/src/components/CommandPalette.tsx` |
| dompurify | latest | `frontend/src/app/blog/` |

### Инфраструктура
| Что | Где |
|---|---|
| Docker Compose | `docker-compose.yml` |
| nginx | `nginx/nginx.conf` |
| gunicorn + uvicorn workers | `backend/Dockerfile` |
| **Хостинг (план):** Yandex Cloud | по 152-ФЗ требуется хостинг в РФ |

---

## 2. Скиллы Claude Code

Скиллы лежат в **`.claude/skills/`** репозитория Eqio (командные, в git).
Активируются автоматически по триггерам в описании.

### Скиллы для Eqio (написаны под этот проект)

| Скилл | Когда триггерится | Содержание |
|---|---|---|
| **`152-fz-compliance-checklist`** | Работа с согласием на ОПД, политикой конфиденциальности, удалением аккаунта, РКН, локализацией хостинга | 7-шаговый чеклист, шаблоны Politики, CookieConsent компонент, account deletion handler |
| **`fastapi-sqlalchemy-patterns`** | Новый роутер, модель, миграция Alembic, Pydantic-схема, проверка N+1 | 13 разделов: Pydantic v2, SQLAlchemy 2.0, Alembic safe migrations, anti-god-router, cookbook |
| **`moex-iss-api-patterns`** | Работа с MOEX ISS API, котировками, свечами, IMOEX, MAE/MFE | 13 разделов: endpoints, paging, retry, кэш, calendar, MAE/MFE расчёт. MoexClient async-класс. |
| **`nextjs-react19-server-patterns`** | Server Components, Server Actions, Suspense, streaming, кэш Next 16 | 14 разделов: SC vs CC, Server Actions, Suspense boundaries, streaming, TanStack-граница |

### Глобальные скиллы (`~/.claude/skills/`)

Из набора Anthropic — используются в Eqio при необходимости.

| Скилл | Когда вызывать |
|---|---|
| `frontend-design` | Каждый новый компонент дашборда — дизайн в стиле Linear/Stripe |
| `claude-api` | При работе с `backend/ai_service.py` (Anthropic SDK) |
| `review` | Перед commit нетривиальной логики |
| `security-review` | Перед платным запуском, перед каждым релизом с auth-изменениями |
| `simplify` | После большой фичи — почистить дубли |
| `update-config` | Когда меняется `~/.claude/settings.json` |
| `init` | Уже сделано — есть `CLAUDE.md` |

### Игнорировать (от других проектов)

`django-*`, `dart-flutter-*`, `celery-patterns`, `htmx-patterns`, `pdf`, `pptx`, `docx`, `xlsx`, `build-methodology`, `new-lab-section`, `new-sim-module`, `extract-docx-images`, `owasp-mobile-security-checker`, `flutter-tester`, `keybindings-help`, `pytest-django-patterns`.

---

## 3. MCP-серверы

### Подключены сейчас (4)

| Сервер | Назначение |
|---|---|
| **context7** | Документация библиотек (FastAPI, Next.js, Tailwind, etc.) |
| **deepwiki** | Изучение чужих GitHub-репозиториев |
| **github** | Issues / PR / code search в репозиториях |
| **playwright** | E2E-тесты браузера |

### План подключения (5 серверов, ждут ответов)

| Сервер | URL | Когда |
|---|---|---|
| **YooKassa MCP** | github.com/theYahia/yookassa-mcp | Когда зарегистрируется shop |
| **Sentry MCP self-hosted** | github.com/ddfourtwo/sentry-selfhosted-mcp | Когда поднимется Sentry в Yandex Cloud |
| **Yandex Cloud MCP** | github.com/yandex-cloud/mcp | Когда заведётся аккаунт + `yc init` |
| **YouTrack MCP** | jetbrains.com/help/youtrack/server/mcp | Когда определимся с инстансом (Cloud или self-hosted) |
| **PostgreSQL MCP (pgEdge)** | github.com/pgedge/pgedge-mcp | Когда определимся с режимом БД (локальный или docker) |

### Не подключаем

- **Stripe MCP** — РФ-санкции, используем YooKassa
- **AWS MCP** — нельзя для РФ-данных по 152-ФЗ
- **Memory / sequential-thinking MCP** — Claude Code и так держит контекст
- **Browserbase / Puppeteer** — Playwright уже есть
- **Linear MCP** — выбираем YouTrack

---

## 4. VS Code расширения

Recommended-список лежит в **`.vscode/extensions.json`**. При открытии проекта VS Code предложит установить.

### Python / FastAPI (5)
- `ms-python.python`
- `ms-python.vscode-pylance`
- `ms-python.mypy-type-checker`
- `charliermarsh.ruff` — единственный форматтер+линтер. Не устанавливать Black/flake8/Pylint.
- `FastAPILabs.fastapi-vscode` — Path Operation Explorer

### TypeScript / Next.js / React (6)
- `dbaeumer.vscode-eslint`
- `esbenp.prettier-vscode`
- `yoavbls.pretty-ts-errors` — обязательно для Next 16
- `usernamehw.errorlens`
- `bradlc.vscode-tailwindcss`
- `heybourn.headwind`

### База данных и DevOps (5)
- `mtxr.sqltools` + `mtxr.sqltools-driver-pg`
- `ms-azuretools.vscode-docker`
- `ms-vscode-remote.remote-containers`
- `rangav.vscode-thunder-client` (REST-клиент в IDE)

### Опционально (preview, ставить вручную через GUI)
- `ms-ossdata.vscode-pgsql` — Microsoft Postgres extension с AI-фичами. Не устанавливается через CLI (preview-баг). Поставить через VS Code Marketplace.

### Git и продуктивность (4)
- `eamodio.gitlens`
- `mhutchie.git-graph`
- `editorconfig.editorconfig`
- `gruntfuggly.todo-tree`

### Документация и архитектура (3)
- `yzhang.markdown-all-in-one`
- `bpruitt-goddard.mermaid-markdown-syntax-highlighting`
- `hediet.vscode-drawio`

### Не ставить
- `ms-python.black-formatter` — Ruff заменяет
- `ms-python.flake8` / `ms-python.pylint` — Ruff заменяет
- `humao.rest-client` — Thunder Client удобнее
- `GitHub Copilot` — у нас Claude Code, не платим дважды

---

## 5. Конфигурация VS Code

### `.vscode/settings.json` (главное)

- `editor.formatOnSave: true` — все файлы форматятся при сохранении
- Python форматер: Ruff (включая organize imports и fix-all)
- TypeScript/JS/JSON форматер: Prettier
- Markdown форматер: Markdown All in One
- `tailwindCSS.experimental.classRegex` — поддерживает `cva`, `cx`, `clsx` хелперы
- `headwind.runOnSave: false` — Headwind не сортирует при сохранении (агрессивен)
- `sqltools.connections` — preset подключения к локальному Postgres `localhost:5432/atom`

### `.vscode/launch.json`

Готовые конфигурации запуска отладки:
- **Backend: FastAPI (debug)** — uvicorn с `--reload`, breakpoints в Python
- **Backend: pytest current file** — отладка одного теста
- **Backend: pytest all** — все тесты в `backend/tests/`
- **Frontend: Next.js (debug server)** — npm run dev с node-debugger
- **Frontend: Next.js (browser)** — Chrome для дебага в Sources
- **Compound: Full Stack** — backend + frontend одной кнопкой

### `.vscode/tasks.json` (предсуществовал)

- **Run Backend** — uvicorn без debugger (просто запуск)
- **Run Frontend** — npm run dev

---

## 6. Workflow «как делать новую фичу»

1. **Создать ветку:** `git checkout -b feat/<name>`
2. **Если фича Backend:** скилл `fastapi-sqlalchemy-patterns` сам предложит pattern (роутер, сервис, миграция)
3. **Если фича Frontend:** скилл `nextjs-react19-server-patterns` подскажет, делать Server или Client
4. **Если касается ПД:** скилл `152-fz-compliance-checklist` напомнит про consent / удаление
5. **Если касается котировок MOEX:** скилл `moex-iss-api-patterns` даст готовый MoexClient
6. **Code review:** скилл `review` перед commit
7. **Security:** скилл `security-review` если касается auth или платежей
8. **Cleanup:** скилл `simplify` чтобы не оставлять дубли

---

## 7. Известные ограничения

- **Docker не установлен на разработческой машине** — `docker-compose up` пока не запустится локально. План: установить Docker Desktop (требует перезагрузки Windows).
- **Microsoft Postgres extension** — preview, не ставится через CLI. Установить вручную через Marketplace при необходимости (SQLTools+pg-driver уже работают).
- **Скиллы не активны на разработческих сессиях, не открывших Eqio** — потому что они в `.claude/skills/` репо, а не в `~/.claude/skills/`. При работе вне репо нужно либо открыть Eqio, либо скопировать в personal-папку.
- **Python 3.14** на машине — может конфликтовать с `requirements.txt` если там лимиты. Проверить при первом `pip install`.

---

## 8. Roadmap расширения стека

### Месяц 1
- Подключить YouTrack Cloud + создать YouTrack MCP
- Установить Docker Desktop
- Зарегистрировать Yandex Cloud + подключить Yandex Cloud MCP

### Месяц 2
- Поднять self-hosted Sentry в Yandex Cloud + подключить MCP
- Зарегистрировать YooKassa shop + подключить MCP
- Написать `yookassa-acquiring-patterns` skill

### Месяц 3
- Написать `playwright-vitest-eqio-e2e` skill (когда тестов фронта будет ≥30)
- Написать `typescript-domain-types` skill (когда понадобится branded types для денег)
- Подключить Figma MCP (если возьмём дизайнера)
