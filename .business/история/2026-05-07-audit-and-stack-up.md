# 2026-05-07 — Аудит, stack-up, 4 PR, база знаний

Большая стартовая сессия. Условно «день нулевой» Eqio как зрелого проекта.

## 1. Какая задача была поставлена

Несколько задач каскадом:

1. **Глубокий аудит** проекта по 30+ метрикам с независимой senior-уровня оценкой и сравнением с конкурентами на рынке РФ.
2. **Подобрать инструменты** (MCP-серверы, скиллы, VS Code расширения) под наш стек: FastAPI / Next.js / PostgreSQL / MOEX / 152-ФЗ / дизайн.
3. **Выполнить установку** всех рекомендаций (полный stack-up).
4. **Реализовать 4 PR** в очередь:
   - PR1: 152-ФЗ compliance (consent + delete + privacy)
   - PR2: MOEX `_normalize_iss_block` + jitter
   - PR3: Расщепление `stats.py` (вынести `stats_tags.py`)
   - PR4: Server Components demo (`/dashboard-demo`)
5. **Создать базу знаний** `.business/` с подпапками по направлениям и якорем в CLAUDE.md, чтобы Claude всегда сверялся с ней перед задачей.

## 2. Как решал

### Аудит
- 3 параллельных агента: backend, frontend, инфра+безопасность
- Сборка отчёта на 33 метрики с сопоставлением 6 конкурентов (3 РФ + 3 глобальных)
- Источник: web-research через WebSearch + чтение исходников

### Stack-up
- Делегировал research в claude-code-guide (MCP + скиллы) и WebSearch (VS Code расширения)
- Из 13 рассмотренных MCP — выбрали 5 для подключения (PostgreSQL, Sentry, Yandex Cloud, YouTrack, YooKassa)
- Из 30 рассмотренных скиллов — отобрали 7 уже имеющихся + написали 4 новых
- Из 25 рассмотренных VS Code-расширений — отобрали 23

### 4 PR
- PR1+PR2 делал сам (меняли схему БД, не делегируешь)
- PR3+PR4 — параллельные агенты (разные файлы, не пересекаются)
- 363 backend-теста зелёные после всего
- Frontend `npm run build` success после PR4

### База знаний
- 9 доменов: strategy / product / marketing / sales / compliance / tech / operations / finance / history
- 30+ файлов: полные где есть материал из сессии, скелеты для будущего
- 4 ADR из реальных решений сессии (SQLite, pd-consent versioning, Server Components, MOEX rate-limit)
- 3 эталона feature-canon (dashboard, mae-mfe, trade-replay)
- Skill `eqio-context-bridge` — мостик-якорь к базе

## 3. Решил ли — да / нет / частично

### Да полностью
- ✅ Аудит (33 метрики, 6 конкурентов, 10 критичных находок)
- ✅ PR1 (152-ФЗ): миграция 0002, 363/0 тестов, smoke 5/5
- ✅ PR2 (MOEX): jitter + `_normalize_iss_block`, 363/0 тестов
- ✅ PR3 (stats split): tags-роутер вынесен, 363/0 тестов
- ✅ PR4 (Server Components): `/dashboard-demo` собирается как `ƒ Dynamic`, build success
- ✅ База знаний: 30+ файлов, навигация, скилл-bridge

### Частично
- 🟡 Stack-up — установлены файлы конфигурации (`.vscode/extensions.json`, `settings.json`, `launch.json`), но **сами расширения не ставил автоматически** — пользователь должен открыть VS Code и нажать «Install recommended»
- 🟡 5 MCP-серверов — отложены до получения ответов про Sentry / YouTrack / Yandex Cloud / YooKassa / Postgres credentials

### Не делал
- Sentry self-hosted / Yandex Cloud / YouTrack / YooKassa MCP подключения — заблокированы вопросами пользователя
- Реальные платежи через ЮKassa — это отдельный спринт (PR2 из аудита C2)

## 4. Эффективно ли решение, что можно было лучше

### Что прошло хорошо
- **Параллельные агенты** для аудита и stack-up'а сэкономили ~40 минут контекста и времени
- **Тестирование скиллов на реальных задачах** до использования — окупилось дважды: и проверили скиллы, и получили готовый план для 4 PR
- **Pyramid of testing** в PR1: сначала схема БД, потом миграция, потом smoke-тест из 5 шагов с проверкой состояния — поймали 3 нюанса (cwd для alembic, csrf cookie name, TestClient.delete без json)
- **Скелеты + полные файлы** в базе знаний: не утонул в документации, но дал основу для расширения

### Что можно было лучше
- **PR1 smoke-тест слишком сложный** — 5 шагов с manual CSRF, можно было упростить до 3 шагов или использовать pytest fixture
- **Запуск alembic из неправильной cwd** — потерял ~5 минут на дебаг. Надо было сразу `Push-Location backend`. Запомнил.
- **Версия Python 3.14** на dev-машине — может конфликтовать с requirements.txt (там обычно ≤3.12). Это TODO.
- **Docker не установлен** — расширения Docker и Dev Containers поставлены «впрок», но без Docker daemon работать не будут. Нужно явно отметить пользователю.
- **Длинные ответы пользователю** в финальных отчётах. Можно было сжать.

## 5. Как было и как стало

### Было (08:00, начало сессии)
- Бренд расщеплён: `Eqio` (UI) vs `ATOM` (репо)
- BUSINESS_PLAN противоречит коду (крипта vs MOEX)
- 1874 строки в `routers/stats.py` (god-router)
- Регистрация без согласия на ОПД (152-ФЗ нарушение)
- Только 1 Alembic миграция (`0001_initial_baseline`)
- Frontend `app/page.tsx` 1013 строк, всё `'use client'`
- 152 backend-теста (passed)
- MOEX retry без jitter (риск thundering herd)
- 4 копии парсера ISS-JSON
- Никакой базы знаний

### Стало (~22:00, после 14 часов работы)

**Код:**
- Бренд обозначен (нужно решение, но проблема видна)
- 4 ADR фиксируют решения
- `routers/stats.py` 1835 строк (-39), вынесен `stats_tags.py`
- Регистрация с обязательным `pd_consent` + журнал согласий + DELETE /auth/me
- 2 Alembic миграции (добавлена 0002 для pd_consents)
- Server Components demo на `/dashboard-demo` (build success)
- 363 backend-теста (passed) — 211 новых, 0 регрессий
- MOEX retry с jitter ±20%
- 2 копии парсера ISS убраны (осталось ещё 2 для будущего PR)

**Контекст:**
- `.business/` с 30+ файлами в 9 доменах
- Корневой `CLAUDE.md` с якорем на базу
- Skill `eqio-context-bridge` для авто-маршрутизации
- 4 рабочих скилла (`152-fz`, `fastapi-sqla`, `moex-iss`, `nextjs-react19`)
- 23 VS Code расширения через `extensions.json` (recommended)
- Smoke-тесты в `backend/scripts/` для проверочных запусков
- Frontend `/privacy` страница и `<CookieConsent />` баннер

**Готовность к запуску:**
- Compliance: было 3/10, стало 5/10 (см. `compliance/152-fz-status.md`)
- Тестируемость: 363 backend-теста против 152
- Архитектурная зрелость: 4 ADR против 0

## Что узнал на будущее

### Технические грабли
- **`alembic` зависит от cwd**: `DATABASE_URL=sqlite:///./atom.db` — относительный путь. Запускать **только** из `backend/`.
- **CSRF в TestClient**: `client.cookies.get("atom_csrf_token")` — имя берётся из `config.CSRF_COOKIE_NAME`. И передаётся в header `X-CSRF-Token`.
- **TestClient.delete()** не принимает `json=` — использовать `client.request("DELETE", ..., json=...)`.
- **Email validator Pydantic** блокирует `.test`, `.example`, `.invalid` TLD — для тестов использовать `gmail.com`.
- **PowerShell + emoji в логах** ломаются на cp1251. Запускать через `python -X utf8` + `$env:PYTHONIOENCODING="utf-8"`.

### Подход который работает
- **Делегирование в агенты независимых сегментов работы** — 3 агента на аудит, 2 на параллельные PR — экономит контекст и время
- **Skill-driven workflow**: skills сначала тестируются на реальных задачах (proof-of-concept), потом применяются — это даёт уверенность что они полезны
- **Полные файлы для накопленного материала + скелеты для будущего** — лучший компромисс. Не пытаться написать «всё сразу качественно» — это ловушка.
- **Канон по образцу (feature-canon/)** — отлично работает для дисциплины UI: новый виджет всегда копирует ближайший эталон.

### Что усвоить долговременно (memory candidates)
- **Eqio — РФ-фондовый, не крипта.** Документ BUSINESS_PLAN устарел. (project-факт)
- **Цена 399₽/мес — заниженная**, рекомендован тест 590-790₽ (project-факт)
- **MOEX MAE/MFE = hero-фича Eqio**, в РФ ни у кого нет автоматически (project-факт)
- **PostgreSQL MCP отложен** — пока на SQLite (project-факт)
- **Pylance/Ruff — основная связка**, не Black/Pylint (feedback)
