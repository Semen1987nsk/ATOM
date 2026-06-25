# Empirik Error Catalog

> Каталог известных ошибок и их фиксов. **Обращайся сюда ДО того как
> расследовать новую ошибку** — большая часть pitfall'ов уже задокументирована.

**Format**: каждая запись — ERR-NNN, immutable tracking id. Если фикс
устарел/не работает — добавь `(deprecated YYYY-MM-DD)` в начало записи,
не удаляй (history matters).

**Index by tracking ID**:
- [Infrastructure (ERR-001..010)](#infrastructure)
- [API/SDK quirks (ERR-101..112)](#apisdk-quirks)
- [Database/migration (ERR-201..206)](#databasemigration)
- [Frontend/sync UX (ERR-301..306)](#frontendsync-ux)

---

## Infrastructure

### ERR-001: TLS CERTIFICATE_VERIFY_FAILED для invest-public-api.tbank.ru

**Категория:** infrastructure | **Severity:** P0

**Symptom:**
```
domain.exceptions.BrokerUnavailable: failed to connect to all addresses;
last error: UNKNOWN: ipv4:178.130.128.33:443: Tls handshake failed
(TSI_PROTOCOL_FAILURE): SSL_ERROR_SSL: error:1000007d:SSL routines:
OPENSSL_internal:CERTIFICATE_VERIFY_FAILED: self signed certificate
in certificate chain
```

**Root cause:** После санкций T-Bank использует Russian Trusted Root CA
(Минцифры). В Mozilla/certifi bundle её нет. grpcio (BoringSSL stack)
НЕ использует Windows trust store и НЕ читает certifi автоматически.

**Fix:**
```powershell
pwsh scripts\build_grpc_ca_bundle.ps1
# Outputs: backend\.local\combined_ca_bundle.pem
# Затем set env-var:
$env:TINKOFF_GRPC_CA_BUNDLE = "C:\Users\Administrator\Empirik\ATOM\backend\.local\combined_ca_bundle.pem"
# config.py:35-43 транслирует в GRPC_DEFAULT_SSL_ROOTS_FILE_PATH до import grpc
```

**Prevention:** На каждой prod-машине добавить env var в systemd
unit / docker-compose. См. `docs/RUNBOOK.md §12`.

**Reference:** `docs/RUNBOOK.md §12`, ADR-0010 (если будет).

---

### ERR-002: grpcio 1.59 → 1.80 cert chain breakage (после AU10)

**Категория:** infrastructure | **Severity:** P0

**Symptom:** До AU10 sync работал, после — TLS падает (см. ERR-001).

**Root cause:** Старый `grpcio 1.59.x` имел legacy CA bundle (включая
Russian CA). После bump до `1.75+` (требование `t-tech-investments 0.3.5`)
bundle обновился и Russian CA убрали.

**Fix:** см. ERR-001 (Russian CA через combined bundle).

**Prevention:** При любом grpcio major bump на проде — проверить
TLS handshake к ключевым endpoints через smoke test.

---

### ERR-003: PYTHONIOENCODING на Windows console падает на cp1251

**Категория:** infrastructure | **Severity:** P1

**Symptom:**
```
UnicodeEncodeError: 'charmap' codec can't encode characters in position 0-69:
character maps to <undefined>
```

**Root cause:** Default Windows console encoding `cp1251` не может выводить
кириллицу/box-drawing/UTF символы. Python writes log/print падают.

**Fix:**
```powershell
$env:PYTHONIOENCODING = "utf-8"
python -X utf8 -m <module>
# ОБА флага: env var И -X utf8 (передаются по-разному в subprocesses)
```

**Prevention:**
- Diagnostic tools — пиши raw ASCII вместо Unicode (`===` вместо `─────`)
- Если нужна кириллица в логах — explicit utf-8 через `-X utf8` в command line
- НЕ полагайся только на env var — PowerShell Start-Process иногда не передаёт

---

### ERR-004: `.env.local` в sandbox-mode не читается

**Категория:** infrastructure | **Severity:** P1

**Symptom:** При попытке прочитать `.env.local` через Read tool — permission denied.

**Root cause:** Correct security behavior — `.env.local` исключён из read
для предотвращения утечки токенов. Это feature, не bug.

**Fix:** Не читай `.env.local` напрямую. Передавай через env переменные:
```python
# В Python tool:
from dotenv import load_dotenv
load_dotenv(".env.local")  # внутри subprocess — OK
token = os.getenv("TINKOFF_LIVE_TOKEN")
```

**Prevention:** Если нужны секреты в diagnostics — спрашивай user'а
runtime значение, не файл.

---

### ERR-005: AUTO_INIT_DB в prod = silent schema drift

**Категория:** infrastructure | **Severity:** P0

**Symptom:** Модели обновили, миграцию не сделали → `SQLAlchemy create_all()`
тихо добавляет колонки или НЕ добавляет (если столбец удалён) → schema
mismatch с production data.

**Root cause:** `AUTO_INIT_DB=True` в prod вызывает `Base.metadata.create_all()`
который IDEMPOTENT — не выполняет ALTER, только CREATE TABLE IF NOT EXISTS.
Изменения существующих таблиц теряются.

**Fix:** В prod ОБЯЗАТЕЛЬНО `AUTO_INIT_DB=False` + Alembic migration on deploy:
```bash
alembic upgrade head
```

**Prevention:** `main.py:lifespan` имеет `_check_alembic_head()` для prod
(см. ERR-202).

---

### ERR-006: PowerShell `Start-Process -Environment` не работает

**Категория:** infrastructure | **Severity:** P2

**Symptom:**
```
Start-Process : A parameter cannot be found that matches parameter name 'Environment'.
```

**Root cause:** Windows PowerShell 5.1 (наш default) не имеет `-Environment`
параметра. Только PowerShell Core (7+) поддерживает.

**Fix:** Использовать `[System.Environment]::SetEnvironmentVariable()` для
параметров user level, потом process наследует:
```powershell
[System.Environment]::SetEnvironmentVariable("MY_VAR", "value", "User")
$env:MY_VAR = "value"  # also for current session
Start-Process -FilePath "python.exe" -ArgumentList "..."
```

**Prevention:** Не использовать `-Environment` если непонятно какая версия PS.

---

### ERR-007: `Stop-Process -Name python` убивает все Python процессы

**Категория:** infrastructure | **Severity:** P1

**Symptom:** Хотел убить только backend uvicorn, killed all `python.exe`
включая IDE language servers, MCP servers etc.

**Root cause:** `Stop-Process -Name` matches ANY process с этим именем.

**Fix:** Используй Get-CimInstance с фильтром по CommandLine:
```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -match 'uvicorn|main:app' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

**Prevention:** Сохраняй PID при `Start-Process -PassThru | Select-Object Id`
и killаешь по PID, не по имени.

---

### ERR-008: T-Bank IP cooldown при burst >30 RPC/sec

**Категория:** infrastructure | **Severity:** P1

**Symptom:**
```
BrokerUnavailable failed to connect to all addresses;
last error: UNKNOWN: ipv4:178.130.128.33:443: tcp handshaker shutdown
```
**ВСЕ** последующие RPC падают, не только bursty ones.

**Root cause:** T-Bank имеет IP-level rate-limiting (не только per-token).
~30+ RPC в секунду триггерит cooldown ~5-15 минут.

**Fix:** Throttle между RPC:
```python
INTER_RPC_DELAY_S = 1.5
for entry in items:
    if not first:
        await asyncio.sleep(INTER_RPC_DELAY_S)
    await api_call(entry)
```

**Prevention:**
- Tools типа `refresh_missing_instrument_specs.py` — throttled by default
- AU1 per-RPC limiter (150/min) защищает базовый sync
- Если хитнули cooldown — ждать 5-15 минут, не retry'ить immediately

---

### ERR-009: pip quarantine для t-tech-investments на public PyPI

**Категория:** infrastructure | **Severity:** P0 (deployment blocker)

**Symptom:** `pip install t-tech-investments` находит пакет но падает на download.

**Root cause:** PyPI quarantined пакет (security review). Официальный
источник — T-Bank GitLab PyPI index.

**Fix:**
```bash
pip install t-tech-investments==0.3.5 \
  --extra-index-url https://opensource.tbank.ru/api/v4/projects/238/packages/pypi/simple
```
В CI/CD — pin `--extra-index-url` в `pip.conf` или `poetry.toml`.

**Prevention:** Никогда не полагайся на public PyPI для T-Bank SDK.

---

### ERR-010: sentry-sdk floor 2.47 при установке t-tech-investments

**Категория:** infrastructure | **Severity:** P2

**Symptom:** `pip install t-tech-investments` auto-upgrades sentry-sdk.

**Root cause:** T-Bank SDK 0.3.x хардкодит requirement `sentry-sdk>=2.47.0`
для ErrorHub integration.

**Fix:** Совместимо с нашим Sentry (нет breaking changes от 2.x → 2.47).
В `requirements.txt` поднять floor до 2.47.0 явно.

**Prevention:** При SDK migration в будущем — проверять transitive deps
через `pip install --dry-run`.

---

## API/SDK quirks

### ERR-101: Tinkoff `op.quantity` ≠ executed quantity

**Категория:** api-sdk | **Severity:** P0

**Symptom:** В БД сохраняется wrong quantity (например saved=900 vs actually
executed=15) для лимитных ордеров (особенно OTC по выходным).

**Root cause:** Tinkoff `op.quantity` = **ЗАЯВЛЕННОЕ** количество в ордере,
не executed. Часть может быть отменена (`quantityRest`).

**Fix:** `_compute_executed_quantity()` в proto_to_domain.py:
```python
trades_info = getattr(op, "trades_info", None)
if trades_info and trades_info.trades:
    return sum(t.quantity for t in trades_info.trades)
# Fallback: quantity - quantity_rest
qty_rest = int(getattr(op, "quantity_rest", 0) or 0)
if qty_rest > 0 and qty_declared > qty_rest:
    return qty_declared - qty_rest
return qty_declared  # legacy
```

**Prevention:** Документировано в `docs/TINKOFF_OPERATIONS.md:12-44`.
AU4 fix verified live (XIM6 saved=3255 → 3 после re-sync).

**Reference:** AU4, ADR в `.business/tech/decisions/`.

---

### ERR-102: broker_report API error 30058 = REPORT_NOT_READY

**Категория:** api-sdk | **Severity:** P1

**Symptom:** `OperationParseError: 30058` при fetch broker_report.

**Root cause:** Отчёт ещё генерируется (большие периоды могут занять
до 60 секунд).

**Fix:** Retry с exponential backoff (учитывая 5/min лимит):
```python
_POLL_BACKOFF = [2.0, 5.0, 10.0, 15.0, 30.0, 30.0, 30.0, 30.0]
for attempt in range(max_attempts):
    try:
        rows, _, pages = await fetch_broker_report_page(task_id, page=0)
        if pages > 0:
            break
    except BrokerError as exc:
        msg = str(exc).lower()
        if "30058" in msg or "not_ready" in msg:
            await asyncio.sleep(_POLL_BACKOFF[min(attempt, len(_POLL_BACKOFF)-1)])
            continue
        raise
```

**Prevention:** AU2 broker_report sub-limiter (5/min) + exponential backoff.

---

### ERR-103: get_broker_report возвращает task_id + first page в одном RPC

**Категория:** api-sdk | **Severity:** P1

**Symptom:** Первый RPC с `generate_broker_report_request=...` возвращает
`generate_broker_report_response=None`, но `get_broker_report_response`
заполнен с готовой страницей.

**Root cause:** SDK 0.3.5 (и T-Bank API) для маленьких периодов сразу
отдаёт данные в первом ответе, не требуя отдельного polling.

**Fix:** В `generate_broker_report` парсить ОБА:
```python
gen_resp = getattr(response, "generate_broker_report_response", None)
task_id = getattr(gen_resp, "task_id", "") if gen_resp else ""
page_resp = getattr(response, "get_broker_report_response", None)
if not task_id and page_resp is not None:
    task_id = getattr(page_resp, "task_id", "")
# Если page_resp.pagesCount > 0 — отчёт уже готов, polling skip
```

**Prevention:** При работе с oneof gRPC payload — всегда проверяй все варианты.

---

### ERR-104: futures `min_price_increment_amount` это Quotation, не MoneyValue

**Категория:** api-sdk | **Severity:** P0

**Symptom:** `point_value = Decimal(1)` fallback в `domain/pnl/futures.py`
→ P&L занижен в 100× для SiH6, RTS и других.

**Root cause:** SDK schema (`t_tech/invest/schemas.py:1042`) объявляет
`min_price_increment_amount: Quotation` (без currency). Мы использовали
`money_to_decimal()` который ожидает `.currency` → возвращает None →
fallback на 1.0.

**Fix:** В `proto_to_domain.py:388`:
```python
# WRONG: money_to_decimal(getattr(raw, "min_price_increment_amount", None))
# CORRECT:
min_pi_amount = quotation_to_decimal(getattr(raw, "min_price_increment_amount", None))
```

**Prevention:** При работе с SDK schemas — проверяй type hint в
`site-packages/t_tech/invest/schemas.py` (grep по полю).

---

### ERR-105: T-Bank API возвращает amount=0 для всех российских futures

**Категория:** api-sdk | **Severity:** P0

**Symptom:** После ERR-104 fix всё равно `amount=0` для SiH6 и других
российских futures.

**Root cause:** T-Bank API сам возвращает мусорное значение (видимо
backend bug для определённых контрактов).

**Fix:** MOEX ISS fallback в `tools/refresh_missing_instrument_specs.py`:
```python
spec = moex.get_futures_spec(ticker)
if spec is not None:
    minstep, stepprice = spec["minstep"], spec["stepprice"]
else:
    # KNOWN_FUTURES_SPECS таблица в moex_service.py (24 base codes)
    from moex_service import KNOWN_FUTURES_SPECS
    base = ticker[:-2].upper()
    if base in KNOWN_FUTURES_SPECS:
        ks = KNOWN_FUTURES_SPECS[base]
        minstep, stepprice = ks["minstep"], ks["stepprice"]
```

**Prevention:** Регулярно проверять что новые base_codes покрыты
в `KNOWN_FUTURES_SPECS`. Лог WARNING если ticker не покрыт.

---

### ERR-106: `pagesCount` (camelCase!) в response, не `pages_count`

**Категория:** api-sdk | **Severity:** P1

**Symptom:** `pages_count = 0` хотя в response показывает `pagesCount=1`.

**Root cause:** SDK 0.3.5 для broker_report response использует
camelCase атрибуты (proto-generated). Большинство других fields в
SDK — snake_case, поэтому easy miss.

**Fix:**
```python
pages_count = int(
    getattr(wrapper, "pagesCount", None)
    or getattr(wrapper, "pages_count", 0)
    or 0
)
```

**Prevention:** При сомнении — `print(repr(response))` чтобы увидеть
реальные имена атрибутов.

---

### ERR-107: BROKER_FEE child operations vs op.commission — duplicate sum

**Категория:** api-sdk | **Severity:** P0 (financial accuracy)

**Symptom:** Reconciliation `broker_commission_total` ours = 2× broker.

**Root cause:** Для cursor-based Tinkoff API commission присутствует
**и** в `op.commission` на BUY/SELL, **и** как отдельная `BROKER_FEE` op
с `parent_operation_id` на родительский trade. Если суммировать оба —
получаешь 2× реальную commission.

**Fix:** В reconciliation_service считай только из `BROKER_FEE` ops,
не суммируй `op.commission` отдельно:
```python
if op_type in {"broker_fee", "broker_commission"}:
    broker_commission += abs(payment)
# elif buy/sell: НЕ суммируй commission_units (дублирует BROKER_FEE child)
```

**Prevention:** AU15 verified live (ratio 1.0000). См. `tools/diagnose_commissions.py`
для диагностики.

---

### ERR-108: futures op.quantity = базовый актив, portfolio.quantity = контракты

**Категория:** api-sdk | **Severity:** P1

**Symptom:** XIM6 (Xiaomi futures) в op.quantity=3255, portfolio.quantity=3.

**Root cause:** Two different semantics:
- `operation.quantity` = базовый актив (3255 акций Xiaomi эквивалент)
- `portfolio.position.quantity` = количество контрактов (3)
- Ratio = `basic_asset_size` (1 контракт = 1085 акций для XIM6)

**Fix:** При сравнении нормализуй один в другой:
```python
if inst.instrument_type == "futures":
    bas = inst.basic_asset_size
    normalized_fifo_qty = int(Decimal(fifo_qty) / Decimal(bas))
```

**Prevention:** Документировать в комментариях везде где сравнивается
futures qty. См. T7 audit в `transformation_audit.py`.

---

### ERR-109: `t.direction` это Enum (TradeDirectionORM), не str

**Категория:** api-sdk | **Severity:** P2

**Symptom:**
```python
AttributeError: 'TradeDirection' object has no attribute 'lower'
```

**Root cause:** Trade.direction → `Enum(TradeDirectionORM)`. Вызов
`.lower()` на enum падает.

**Fix:**
```python
dir_str = getattr(t.direction, "value", t.direction) or ""
dir_str = str(dir_str).lower()
direction_sign = 1 if dir_str == "long" else -1
```

**Prevention:** При работе с ORM enum-fields — всегда .value перед
строковыми операциями.

---

### ERR-110: MOEX ISS не находит Tinkoff-tickers напрямую

**Категория:** api-sdk | **Severity:** P2

**Symptom:** `iss.moex.com/iss/engines/futures/markets/forts/securities/CCJ6.json`
returns empty data для tickers типа CCJ6, BSH6, S0H6.

**Root cause:** MOEX security_id namespace отличается от Tinkoff ticker.
Например MOEX обозначение для Cocoa April 2026 может быть "CC-4.26", не "CCJ6".

**Fix:** Использовать `KNOWN_FUTURES_SPECS` таблицу с base_codes как
fallback (см. ERR-105). Маппинг MOEX ↔ Tinkoff — отложен на Phase 2+.

**Prevention:** Не полагаться на 1:1 MOEX/Tinkoff ticker mapping.

---

### ERR-111: T-Bank Sentry ErrorHub auto-init конфликтует с нашим Sentry

**Категория:** api-sdk | **Severity:** P1

**Symptom:** Наши ошибки попадают в `error-hub.tbank.ru` вместо нашего
SENTRY_DSN, или vice versa.

**Root cause:** SDK 0.3.x при первом использовании вызывает
`sentry_sdk.init(dsn="https://invest-piapi-errorhub@error-hub.tbank.ru/...")`.
sentry_sdk default Hub один на процесс → последний init wins.

**Fix:** `observability.block_third_party_sentry_init()` — monkey-patch
`sentry_sdk.init` чтобы no-op'ить вызовы с DSN содержащим `error-hub.tbank.ru`.
Вызывать ПОСЛЕ нашего `init_sentry()`.

**Prevention:** Любой third-party SDK с auto-Sentry → блокировать через
guard. См. `main.py:lifespan`.

---

### ERR-112: tinkoff.invest → t_tech.invest (AU10 rename)

**Категория:** api-sdk | **Severity:** P0

**Symptom:** `ModuleNotFoundError: No module named 'tinkoff'` после установки
`t-tech-investments`.

**Root cause:** SDK переименован 2025-12-11. namespace `tinkoff.invest.*`
заменён на `t_tech.invest.*`.

**Fix:** Find-and-replace `tinkoff.invest` → `t_tech.invest` в:
- `*.py` (imports)
- `requirements.txt` (`tinkoff-investments` → `t-tech-investments==0.3.5`)
- `pytest.ini` (test ignore paths)
- patch paths в тестах (`monkeypatch.setattr("tinkoff.invest...")`)

**Prevention:** Backward-compat alias НЕ существует. Migration mandatory.

---

### ERR-113: broker_report API error 30064 = period > 31 days

**Категория:** api-sdk | **Severity:** P1

**Symptom:**
```
OperationParseError: 30064
broker_report fetch failed: OperationParseError: 30064
```
В UI Reconciliation Run показывает `ERROR` со стрелкой к этому сообщению.

**Root cause:** T-Bank API restriction:
> "the required period should not exceed 31 days"

`GenerateBrokerReport` отказывает если `from..to > 31 days`. Это hard limit
не документированный в SDK schema — обнаружен только через ответ API.

**Fix:**
1. UI селектор cap'нут на 31 день (`admin/users/[id]/page.tsx`)
2. Backend validation: `days: int = Query(30, ge=1, le=31)` в `admin_run_reconciliation`

**Prevention:**
Для full-period validation требуется chunked-reconciliation:
- Поделить запрашиваемый период на чанки по 31 дню
- Для каждого: `generate_broker_report(from=chunk_start, to=chunk_end)`
- Aggregate metrics (Σ realized_pnl, Σ commissions, etc) across chunks
- Это backlog задача, ~3-4h работы в `services/reconciliation_service.py`

**Reference:**
- T-Bank error codes: https://tinkoff.github.io/investAPI/errors/ (поиск "30064")
- AU16 в plan file

---

### ERR-114: sync «Failed to fetch» = tuple-arity краш в FIFO на неразрешимом инструменте

**Категория:** api-sdk | **Severity:** P0

**Symptom:**
```
# В браузере (модалка «Авто-синхронизация»):
Failed to fetch
# В logs/atom.log:
ValueError: not enough values to unpack (expected 3, got 2)
  application/sync/pipeline.py:_stage_fifo_match
```
Счёт «0 операций · 0 сделок / ни разу», sync падает всегда. Легко
ошибочно списать на SDK-бамп — это НЕ SDK.

**Root cause:** Два слоя.
1. `pipeline.py` `_stage_fifo_match._run_for_one`: ранняя ветка
   `if instrument is None: return 0, 0` отдавала 2 значения, а success/except
   ветки и вызывающий код — 3 (`trades, positions, mae_ids`). Триггер: у счёта
   есть операция по инструменту, который T-Bank не резолвит (`GetInstrumentBy
   NOT_FOUND 50002`, enrich его skip → `get_by_uid`=None). `ValueError` валил
   весь sync. Недо-рефактор: при добавлении `need_mae_ids` (MAE-05) ветку забыли.
2. `routers/broker.py sync_now` ловил только `TokenInvalid/RateLimitExceeded/
   BrokerError` — прочее исключение не превращалось в HTTP-ответ, а рвало коннект
   через BaseHTTPMiddleware → браузер видит «Failed to fetch» (плановый путь
   `_guard_one` это переживал, ручной — нет).

**Fix:**
1. `pipeline.py`: ранняя ветка → `return 0, 0, []` (3 значения; неразрешимый
   инструмент молча пропускается).
2. `broker.py`: catch-all `except Exception` в `sync_now` → чистый 500;
   аналогично `get_portfolio` (парсинг убран под guarded-try) → 502.

**Prevention:**
- «Failed to fetch» на sync = браузерный fetch TypeError (оборванный коннект),
  НЕ таймаут. Сначала `curl -m5 /health` (200 = backend жив), затем РЕАЛЬНЫЙ
  traceback из `logs/atom.log` — не предполагать SDK.
- HTTP-эндпоинты, дёргающие orchestrator/SDK, обязаны иметь catch-all →
  структурный ответ (как `_guard_one`), а не полагаться на узкий список except.
- Тесты: `tests/integration/test_fifo_match_missing_instrument.py`,
  `test_broker_sync_error_handling.py`.

**Reference:** memory `tools_workflow_atom_sync_failed_fetch_diagnosis.md`.

---

## Database/migration

### ERR-201: SQLAlchemy `IndexError: tuple index out of range` = schema mismatch

**Категория:** database | **Severity:** P0

**Symptom:**
```
IndexError: tuple index out of range
  in result.resultproxy._apply_processors
```

**Root cause:** Backend запущен ДО применения новой Alembic миграции.
SQLAlchemy ORM models ожидают N столбцов, БД имеет N-1. Чтение строки
падает на extra column.

**Fix:**
```bash
alembic upgrade head
# Restart backend (Python кэширует metadata)
```

**Prevention:** В prod main.py `_check_alembic_head()` падает рано
если schema drift. В dev — внимательно применять миграции после
git pull.

---

### ERR-202: Alembic head mismatch

**Категория:** database | **Severity:** P0

**Symptom:** Backend startup падает с `RuntimeError: alembic head mismatch`.

**Root cause:** Несколько Alembic heads (концы веток) или БД не на head.

**Fix:**
```bash
alembic current   # текущая версия БД
alembic heads     # все доступные heads
alembic upgrade head  # применить недостающие
# Если несколько heads:
alembic merge head1 head2 -m "merge branches"
```

**Prevention:** Каждая миграция имеет single `down_revision`. Не
создавай parallel ветки без явной причины + merge.

---

### ERR-203: SQLite vs PostgreSQL `ON CONFLICT` синтаксис различается

**Категория:** database | **Severity:** P1

**Symptom:** UPSERT работает на SQLite, падает на PostgreSQL (или наоборот).

**Root cause:** SQLite: `INSERT OR REPLACE INTO`. PostgreSQL:
`INSERT ... ON CONFLICT (cols) DO UPDATE`. Не взаимозаменяемы.

**Fix:** Используй `sqlalchemy.dialects.{sqlite,postgresql}.insert` —
dialect-specific builder:
```python
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert

dialect = session.bind.dialect.name
if dialect == "postgresql":
    stmt = pg_insert(table).values(rows)
    stmt = stmt.on_conflict_do_update(index_elements=[...], set_={...})
else:
    stmt = sqlite_insert(table).values(rows)
    stmt = stmt.on_conflict_do_update(...)
```

**Prevention:** OperationRepository.upsert_many() — пример dialect-aware
UPSERT с chunking.

---

### ERR-204: JSON column в SQLite требует explicit dumps/loads

**Категория:** database | **Severity:** P2

**Symptom:** На PostgreSQL `obj.json_column` — это dict. На SQLite — str.

**Root cause:** SQLAlchemy `JSON` column type — на PG native JSONB, на
SQLite TEXT с manual encoding.

**Fix:** SQLAlchemy 2.0 автоматически serialize/deserialize при использовании
`Column(JSON)`. Если используешь `Column(Text)` — manual `json.dumps/loads`.

**Prevention:** Всегда используй `JSON` column type, не `Text` для JSON
data. На SQLite получится compat.

---

### ERR-205: UNIQUE constraint с NULL — NULL != NULL в SQL

**Категория:** database | **Severity:** P1

**Symptom:** Можно вставить несколько Trade rows с `exit_at=NULL` для
одного instrument даже при `UNIQUE(account_id, symbol, entry_at, exit_at, ...)`.

**Root cause:** В SQL `NULL != NULL` (three-valued logic). UNIQUE
constraint считает каждый NULL уникальным.

**Fix:** Это **feature, не bug** для open trades (T7 architectural fix):
позволяет иметь несколько open lots для одного instrument. UNIQUE на
exit_at защищает закрытые trades с одинаковыми entry_at.

**Prevention:** Документируй в model docstring если используешь NULL в
UNIQUE intentionally.

---

### ERR-206: idempotency — INSERT OR REPLACE vs UPSERT по диалекту

**Категория:** database | **Severity:** P2

**Symptom:** Sync iteration #2 удаляет/перезаписывает данные #1.

**Root cause:** `INSERT OR REPLACE` (SQLite) удаляет старую row + insert
новую → CASCADE deletes на referenced FKs (Trade.id, например). UPSERT
(PostgreSQL `ON CONFLICT DO UPDATE`) сохраняет primary key.

**Fix:** В диалект-aware UPSERT используй `ON CONFLICT DO UPDATE`
с явным `set_={...}` для нужных колонок. На SQLite — `INSERT OR IGNORE`
+ separate `UPDATE` если нужно сохранять id.

**Prevention:** OperationRepository — пример правильного UPSERT.
TradeRepository.replace_for_instrument — другой паттерн (DELETE all + INSERT).

---

## Frontend/sync UX

### ERR-301: Next.js Turbopack HMR не подхватывает изменения

**Категория:** frontend | **Severity:** P2

**Symptom:** Сохранил `.tsx` файл, в браузере старая версия.

**Root cause:** Turbopack cache в `.next/cache` иногда stale.

**Fix:**
```bash
# Frontend dir
rm -rf .next/cache
# Или kill + restart
Stop-Process -Name node -Force -ErrorAction SilentlyContinue
cmd.exe /c npm run dev
```

**Prevention:** Если HMR странный — сразу cache clear, не дебажь долго.

---

### ERR-302: BrokerConnectModal toast НЕ должен auto-disappear

**Категория:** frontend | **Severity:** P2

**Symptom:** Юзер не успевает прочитать "Завершено успешно — 245 ops".

**Root cause:** Раньше был `setTimeout(() => setSyncResult(null), 8000)`.
User feedback: «Завершено или нет? Всё как-то непонятно».

**Fix:** Убрать setTimeout. Toast остаётся пока юзер не закроет или не
сделает другое действие.

**Prevention:** Long-running operations с результатом → результат
persistent до явного dismiss или next action.

---

### ERR-303: Sync progress UX — нужны явные состояния кнопки + live timer

**Категория:** frontend | **Severity:** P1

**Symptom:** Юзер не понимает что происходит во время sync (10-30 сек).

**Root cause:** Кнопка "Синхронизировать" не меняет состояние, нет
прогресса. UX feels frozen.

**Fix:**
- During sync: button → "Идёт синхронизация… 0:08" с live timer
- Disable button во время sync
- После success: button → "Готово — перейти в журнал" (large CTA)
- Show real counts в результате (ops fetched, trades built, positions)

**Prevention:** Любая operation >2s должна иметь visual feedback.
См. `frontend/src/components/BrokerConnectModal.tsx` как референс.

---

### ERR-304: Account #N с zeros = wrong run opened

**Категория:** frontend | **Severity:** P2

**Symptom:** Юзер открыл reconciliation run и видит "broker=0, ours=0",
думает что данных нет.

**Root cause:** Account #5 (empty default account) vs Account #4 (real with broker).
Юзер случайно открыл run для account которого фактически нет данных.

**Fix:** В Admin Reconciliation UI показывать account name + broker_account_id
рядом с account_id. Filter UI чтобы показывать только accounts с broker_connection.

**Prevention:** AU5 defensive check в connect_broker уже предотвращает
multi-account под одним local Account. Старые случаи (когда были дубли)
требуют admin cleanup.

---

### ERR-305: PowerShell не может .ps1 через Start-Process напрямую

**Категория:** frontend | **Severity:** P2 (deployment)

**Symptom:**
```
Start-Process -FilePath "scripts\my-script.ps1"
# → Error: Cannot find application matching '.ps1'
```

**Root cause:** Windows shell не имеет default handler для .ps1.

**Fix:** Используй `cmd.exe /c` или `pwsh` (PowerShell Core) explicitly:
```powershell
Start-Process -FilePath "cmd.exe" -ArgumentList "/c","pwsh","scripts\my-script.ps1"
# Or:
pwsh -File scripts\my-script.ps1
```

**Prevention:** Не используй .ps1 для launch scripts в production —
используй Python entry points или bash.

---

### ERR-306: PYTHONIOENCODING не передаётся во все subprocesses

**Категория:** frontend | **Severity:** P2

**Symptom:** Установил `$env:PYTHONIOENCODING = "utf-8"`, но subprocess
всё равно падает на cp1251.

**Root cause:** `Start-Process` в PS 5.1 не передаёт окружение полностью.
Также `subprocess.Popen` в Python ignores parent env var если в коде есть
manual handling encoding.

**Fix:** Двойная защита:
```python
# В command line:
python -X utf8 -m my_module  # flag устанавливает encoding процесса
# В env:
$env:PYTHONIOENCODING = "utf-8"
```

**Prevention:** Всегда используй `python -X utf8` для tools с
non-ASCII output, не полагайся на env var.

---

## Maintenance

### Adding new entries

Когда обнаружишь bug который не покрыт catalog'ом:

1. Назначь tracking ID: следующий свободный в категории
   (ERR-011 для infrastructure, ERR-113 для api-sdk, etc.)
2. Заполни 6 полей: Symptom, Root cause, Fix, Prevention, Reference, Severity
3. Если связан с AU/Phase fix — link на план: `ADR-NNNN`,
   `.business/tech/decisions/0005-reverse-trial-model.md`,
   `.claude/plans/https-kontur-ru-jiggly-bachman.md`
4. Update index в начале файла

### Deprecating entries

Если fix устарел (например, после PostgreSQL migration некоторые
SQLite-specific ERR-2XX уйдут):

1. **НЕ удаляй запись** (history matters)
2. Добавь в начало: `(deprecated YYYY-MM-DD) — reason`
3. Если есть новая запись заменяющая — link на неё

### Cross-references

- `docs/RUNBOOK.md` — operational procedures (rollback, deploy, incidents)
- `docs/PREFLIGHT_CHECKLIST.md` — что читать перед сессией
- `docs/CODING_CONVENTIONS.md` — coding standards
- `.business/tech/decisions/` — ADR (architectural decisions)
- `.claude/plans/` — implementation plans
- `memory/` — кросс-сессионные уроки
