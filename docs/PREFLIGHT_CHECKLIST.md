# Pre-flight Checklist — что делать перед стартом сессии

> **Target time**: ≤ 90 секунд на steps 1-5 (быстрый load context).
> Steps 6-7 — зависят от типа задачи.

Этот checklist предотвращает повторение ошибок прошлых сессий
(см. `memory/feedback_*.md`) и грузит весь нужный контекст до того
как начать кодить.

---

## Step 1 — Identify Project (5 sec)

**Что делать**: Прочти ПЕРВЫЙ упомянутый file path в запросе user'а.

- Если `C:\Users\Administrator\Empirik\ATOM\*` → это **Empirik/ATOM**, продолжай.
- Если другой проект (например `C:\dev\digitalLab\*`, `C:\dev\Inter_OGE\*`) →
  **STOP**. Сообщи user'у: "Это не задача Empirik. Запрос относится к
  <other project>. Активируй соответствующий agent (flutter-digitallab,
  inter-oge-experiment) или confirm что делать."

**Source**: `memory/feedback_not_my_task.md` — урок: молчаливое
переключение между проектами теряет контекст.

---

## Step 2 — Read Navigation Hub (30 sec)

**Что делать**: `Read C:\Users\Administrator\Empirik\ATOM\.business\index.md`.

Это карта 9 доменов + триггеры. Для каждой задачи там указан конкретный
файл который нужно открыть. Например:

| Trigger в запросе | Open |
|---|---|
| "152-ФЗ", "удаление аккаунта", "ПД" | `.business/compliance/152-fz-status.md` + ADR-0002 |
| "тариф", "Pro", "Free+", "trial" | `.business/sales/pricing.md` + ADR-0005 |
| "MOEX", "котировки", "MAE/MFE" | `.business/tech/decisions/0004-moex-rate-limit.md` + `docs/MOEX_ISS_API.md` |
| "новая фича", "виджет", "UI" | `.business/product/design-system.md` + `feature-canon/0X-*.md` |
| "Tinkoff", "broker_report", "operations_stream" | `docs/TINKOFF_OPERATIONS.md` |
| "deploy", "rollback", "incident" | `docs/RUNBOOK.md` |

**Skip если**: ты уже в этой сессии открывал `.business/index.md` —
не перечитывай.

---

## Step 3 — Read Recent Memories (30 sec)

**Что делать**:
1. `Read C:\Users\Administrator\.claude\projects\c--Users-Administrator-Empirik\memory\MEMORY.md`
2. Из index — 5 most-recent (или всех если меньше 5) memory files.

**Особое внимание**: feedback_*.md files — там зафиксированы corrections
от user'а из прошлых сессий. Не повторяй ошибок.

**Auto-memory categories** (см. `MEMORY.md` rules):
- `feedback_*.md` — corrections + validated approaches
- `project_state_*.md` — snapshot текущей фазы
- `tools_workflow_*.md` — common command patterns
- `references_*.md` — external URL bank

---

## Step 4 — Map Task to Skills (10 sec)

**Что делать**: Определи categorу задачи и активируй соответствующий skill.

| Task category | Skill to activate | Trigger keywords |
|---|---|---|
| Backend FastAPI/SQLAlchemy | `fastapi-sqlalchemy-patterns` | "новый роутер", "новая модель", "alembic", "миграция", "pydantic" |
| MOEX integration | `moex-iss-api-patterns` | "MOEX", "ISS API", "котировки", "свечи", "IMOEX", "MAE/MFE" |
| Next.js 16 | `nextjs-react19-server-patterns` | "Server Component", "Server Action", "Suspense", "page.tsx" |
| 152-ФЗ / ПД | `152-fz-compliance-checklist` | "152-ФЗ", "согласие на ОПД", "ПД", "РКН", "удаление аккаунта" |
| Любой Empirik-context | `empirik-context-bridge` | "Empirik", "ATOM", "трейдер" (auto-activated) |

**Important**: Skills загружают специализированные инструкции. Если
задача попадает в category — обязательно активируй ДО кодинга.

---

## Step 5 — Check Error Catalog (15 sec)

**Что делать**: Сканируй `docs/ERROR_CATALOG.md` по ключевым словам task'а.

| Keywords в запросе | Section |
|---|---|
| "TLS", "cert", "grpcio", "handshake" | ERR-001..010 (Infrastructure) |
| "Tinkoff", "broker_report", "operations", "futures" | ERR-101..112 (API/SDK) |
| "alembic", "migration", "schema" | ERR-201..206 (Database) |
| "UI", "modal", "sync", "HMR", "PowerShell" | ERR-301..306 (Frontend) |

Если запрос matches — открой соответствующую запись и применяй
known fix. Не дебажь то что уже задокументировано.

---

## Step 6 — Validate Environment (varies, only if needed)

**Что делать**: Только если задача требует runtime среды (sync test,
reconciliation, refresh tools).

```bash
# Backend running?
Test-NetConnection 127.0.0.1 -Port 8000 -InformationLevel Quiet

# Python version (need 3.11+)
python --version

# Alembic on head?
cd backend && alembic current
# Expected: <hash> (head)

# Если работа с Tinkoff API:
echo $env:TINKOFF_GRPC_CA_BUNDLE
# Expected: C:\Users\...\backend\.local\combined_ca_bundle.pem
# Если пусто — см. ERR-001 + RUNBOOK §12

# Если работа с reconciliation:
Get-ChildItem "C:\Users\Administrator\AppData\Local\Temp\recon_*.json" -ErrorAction SilentlyContinue
# Recent runs для сравнения
```

**Если что-то не настроено** — сообщи user'у явно. Не запускай tools
"ожидая что заработает".

---

## Step 7 — Acknowledge Phase Status (5 sec)

**Что делать**: Прочти latest `project_state_*.md` в memory/.

Сообщи user'у краткое summary текущей фазы (1-2 предложения):
- Какие AU/Phase закрыты
- Recent verified fixes (TLS CA, MOEX fallback, FIFO open trades, etc.)
- Текущее количество tests passing
- Что in-progress / pending

**Пример**:
> "Текущая фаза: Phase 1++, последние закрытые блоки — AU16 reconciliation
> methodology + AU-stream pipeline integration (327/327 tests). TLS CA setup,
> MOEX fallback, FIFO open trades verified live на acc#4. Что нужно делать?"

Это даёт user'у уверенность что Claude в курсе, и помогает быстро
заметить если контекст устарел.

---

## Когда чеклист можно пропустить

- **Continue from interrupted session**: уже выполнил pre-flight в этой
  conversation, продолжаешь — skip.
- **Trivial single-file edit**: typo fix, comment change — overhead не оправдан.
- **User explicitly says "skip preflight"**: respect, но если задача
  выглядит non-trivial — попроси confirm.

---

## Когда чеклист обязателен

- **Fresh conversation** (после compact или /clear).
- **Task spans multiple files** или unclear initial scope.
- **Task involves**: TLS, Tinkoff API, migrations, prod deployment, 152-ФЗ.
- **User mentions** specific phase/AU без context (например "продолжаем AU10").
- **Reading error logs** или debugging existing issue (Step 5 first).

---

## Self-check после чеклиста

После steps 1-7 ты должен иметь ответ на:

- [ ] **What project?** (Empirik/ATOM или другой)
- [ ] **What domain?** (compliance, product, tech, ...)
- [ ] **What skill активирован?**
- [ ] **Есть ли known errors** связанные с задачей?
- [ ] **Environment ready** для работы?
- [ ] **Current phase** статус понят?

Если на любой пункт ответ "нет" — вернись к соответствующему step.
