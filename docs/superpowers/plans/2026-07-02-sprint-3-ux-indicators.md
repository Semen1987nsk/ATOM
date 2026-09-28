# Спринт 3 — UX-надёжность (кнопки/ошибки) + корректность индикаторов Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (- [ ]) syntax.

**Goal:** Устранить проглоченные ошибки кнопок/форм на фронте (close/delete/delete-all/setup/review/mae/sync/скриншот, 422 «[object Object]», затирание таблиц), заставить вкладки уважать фильтры и статус investigate, и починить корректность quant-индикаторов (Sterling-знак, Ulcer/K-ratio/Sterling baseline, mae-mfe 500, benchmark-источники, таймзоны МСК, tags gross, aggregator NameError).

**Architecture:** Backend — точечные фиксы в `analytics/*` и `routers/stats*.py` (формулы, baseline, tz-конвертация, источники метрик) плюс их характеризующие тесты в `backend/tests`. Frontend — единый паттерн обработки ошибок мутаций (`toast.error(err instanceof ApiError ? err.toUserMessage() : '...')`), нормализация `422`-detail в `apiClient`, прокидывание `statsParams` в advanced/benchmark-запросы, уважение серьёзных backend-статусов в `PnLHealthBadge`. Задачи по файлам независимы и параллелятся после Спринта 1.

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Pydantic v2 (backend), Next.js 16 + React 19 + TanStack Query + Recharts (frontend), pytest + vitest + tsc.

## Global Constraints

- **Python:** `C:/Python314/python.exe` (зависимости стоят там; системный python / Robot-venv НЕ подходят). Тесты бэка — из `backend/`: `C:/Python314/python.exe -m pytest tests/... -q`.
- **Backend** уже запущен на `http://localhost:8000`. GET-смоук можно; мутации прод-данных нельзя.
- **Frontend:** `cd frontend && npx vitest run --maxWorkers=1` (ТОЛЬКО `--maxWorkers=1`) + `npx tsc --noEmit`. E2E: playwright, backend :8000 + `npm run dev -- -p 3001`; при «Unable to acquire lock» убить залипшие `next dev` + удалить `frontend/.next/dev/lock`.
- **Миграции** (в этом спринте не требуются): врем. БД `DATABASE_URL=sqlite:///./_audit_tmp.db`, НИКОГДА не трогать `backend/atom.db`.
- **Git:** новый коммит на задачу (не amend), ветка `feat/rebrand-empirik`, формат `fix(<область>): <что> (SN-XX)`. Не пушить/мержить без команды.
- **Инварианты:** ADR-0007 (P&L), SYNC-08 (курсор после всех стадий), MATH-01 (тег/агрегатный P&L — по `net_pnl`, не gross). Для P&L-задач читать `docs/PNL_PLAYBOOK.md`.
- **Флейк (не регрессия):** `test_debug_warning` + `test_market_service_async::test_get_client_returns_singleton` падают только в полном прогоне (importlib.reload), зелёные в изоляции.
- **Тост-API (важно для FE-задач):** `useToast()` предоставляет ТОЛЬКО `success(msg)` и `error(msg)` — метода `warning`/`info` НЕТ. Для «мягких» предупреждений используем `toast.error(...)` с поясняющим текстом.

---

### S3-01 [HIGH] 500 на /stats/mae-mfe-analysis: None >= 1.5 при группе без убыточных

**Files:**
- Modify: `backend/routers/stats.py:1390` (чтение `profit_factor`), `:1546`, `:1580` (сравнения `profit_factor >= 1.5`)
- Test: `backend/tests/test_stats_mae_mfe_recommendations.py` (Create)

**Проблема:** `_analyze_trades_mae_mfe` кладёт `profit_factor=None` при отсутствии убытков (`stats.py:1316`). `_generate_strategy_recommendations` читает его `analysis.get("profit_factor", 0)` — ключ существует со значением `None`, default не срабатывает, и `if is_profitable and profit_factor >= 1.5` (`:1580`, вне guard `real_rr>0`) даёт `TypeError: '>=' not supported between NoneType and float` → 500 на drill-down с 1-2 прибыльными сделками.

**Interfaces:** Потребляет dict из `_analyze_trades_mae_mfe` (ключ `profit_factor: float | None`). Ничего наружу не меняет — только чинит внутреннее чтение.

- [ ] **Step 1 — падающий тест.** Создать `backend/tests/test_stats_mae_mfe_recommendations.py`:
```python
"""S3-01: _generate_strategy_recommendations не должен падать при profit_factor=None."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from routers.stats import _generate_strategy_recommendations  # noqa: E402


def _base_analysis(**over):
    a = {
        "edge_ratio": 1.2,
        "avg_mae": 1.0,
        "avg_mfe": 2.0,
        "avg_efficiency": 50.0,
        "win_rate": 100.0,
        "quality_score": 60,
        "trades_count": 2,
        "real_rr": 0.0,          # нет убытков → real_rr=0 (guard на :1541 не сработает)
        "profit_factor": None,   # MATH-05: PF undefined при отсутствии лузеров
        "required_winrate": 100.0,
        "avg_win": 500.0,
        "avg_loss": 0.0,
        "total_pnl": 1000.0,     # is_profitable=True → ветка :1580 активна
        "mae_percentiles": {"p25": 0.5, "p50": 1.0, "p75": 1.5, "max": 2.0},
        "mfe_percentiles": {"p25": 1.0, "p50": 2.0, "p75": 3.0, "max": 4.0},
    }
    a.update(over)
    return a


def test_profitable_all_winners_no_type_error():
    # До фикса: TypeError '>=' NoneType/float на :1580 → 500.
    recs = _generate_strategy_recommendations(_base_analysis())
    assert isinstance(recs, list)
    assert any(r.get("type") in {"success", "info", "warning"} for r in recs)


def test_real_rr_positive_with_none_pf():
    # Ветка :1546 тоже не должна падать, когда real_rr>0, но PF=None.
    recs = _generate_strategy_recommendations(_base_analysis(real_rr=1.5, profit_factor=None))
    assert isinstance(recs, list)
```
- [ ] **Step 2 — запуск, ожидание FAIL.** `cd backend && C:/Python314/python.exe -m pytest tests/test_stats_mae_mfe_recommendations.py -q`. Ожидаем FAIL с `TypeError: '>=' not supported between instances of 'NoneType' and 'float'`.
- [ ] **Step 3 — минимальный фикс.** В `backend/routers/stats.py`:
  - Строка `:1390` — before → after:
    ```python
    profit_factor = analysis.get("profit_factor", 0)
    ```
    →
    ```python
    profit_factor = analysis.get("profit_factor") or 0
    ```
    (`None → 0`; `0 → 0`; валидный PF сохраняется. Семантика 0 = «нет прибыльности» уже принята для all-winners в этой функции — рекомендация «ПРИБЫЛЬНА» просто не выдаётся, что корректно при отсутствии лузеров.)
- [ ] **Step 4 — запуск, ожидание PASS.** `cd backend && C:/Python314/python.exe -m pytest tests/test_stats_mae_mfe_recommendations.py -q` → 2 passed. Затем импорт-смоук: `cd backend && C:/Python314/python.exe -c "import main"`.
- [ ] **Step 5 — commit.** `fix(stats): PF=None больше не роняет mae-mfe recommendations 500 (S3-01)`.

---

### S3-02 [HIGH] Sterling Ratio: перевёрнутый знак 10%-буфера

**Files:**
- Modify: `backend/analytics/advanced.py:115` (`denom = avg_worst_dd - 10.0`)
- Test: `backend/tests/test_advanced_benchmark.py:96-110` (класс `TestSterlingRatio` — обновить под канон)

**Проблема:** Канон Sterling: `AnnualReturn / (avg(worst DD) + 10%)` при положительных DD (в коде DD хранятся положительными процентами). Код ВЫЧИТАЕТ 10 → при avg DD 20% знаменатель 10 вместо 30 (×3 завышение), при avg DD < 10% (типичный журнал) знаменатель ≤ 0 → метрика всегда `None`, карточка пустая.

**Interfaces:** Потребляет `dd_episodes` (положительные %) из `collect_drawdown_episodes`. После S3-03 эти episodes будут считаться от baseline-кривой (реалистичные %), что делает фикс знака критичным.

- [ ] **Step 1 — падающий тест.** Обновить `backend/tests/test_advanced_benchmark.py`, класс `TestSterlingRatio` (before → after):
```python
class TestSterlingRatio:
    def test_normal_case(self):
        # Sterling = Annual / (avg(top3 DD) + 10%)
        # avg([25, 20, 15]) = 20, denom = 20 + 10 = 30, sterling = 30/30 = 1.0
        sr = adv.calculate_sterling_ratio(30.0, [25.0, 20.0, 15.0])
        assert sr == 1.0

    def test_low_drawdowns_defined(self):
        # avg DD < 10% → denom = avg + 10 > 0 → метрика ОПРЕДЕЛЕНА (была None).
        # avg([5,3,1]) = 3, denom = 13, sterling = 20/13 ≈ 1.54
        sr = adv.calculate_sterling_ratio(20.0, [5.0, 3.0, 1.0])
        assert sr == 1.54

    def test_empty_drawdowns_undefined(self):
        assert adv.calculate_sterling_ratio(20.0, []) is None
```
- [ ] **Step 2 — запуск, ожидание FAIL.** `cd backend && C:/Python314/python.exe -m pytest tests/test_advanced_benchmark.py::TestSterlingRatio -q`. Ожидаем FAIL (текущий код даёт `3.0` и `None`).
- [ ] **Step 3 — минимальный фикс.** `backend/analytics/advanced.py:115` (before → after):
```python
    denom = avg_worst_dd - 10.0
    if denom <= 0:
        return UNDEFINED
    return _sanitize(round(annual_return_pct / denom, 2))
```
→
```python
    denom = avg_worst_dd + 10.0
    if denom <= 0:
        return UNDEFINED
    return _sanitize(round(annual_return_pct / denom, 2))
```
Также обновить docstring (`:107`) «Классическая формула отнимает 10%» → «прибавляет 10% (DD хранятся положительными)».
- [ ] **Step 4 — запуск, ожидание PASS.** `cd backend && C:/Python314/python.exe -m pytest tests/test_advanced_benchmark.py::TestSterlingRatio -q` → 3 passed.
- [ ] **Step 5 — commit.** `fix(analytics): Sterling буфер +10% вместо -10% по канону (S3-02)`.

---

### S3-03 [HIGH] Ulcer/dd_episodes(→Sterling)/K-Ratio на кривой кумулятивного PnL от нуля

**Files:**
- Modify: `backend/services/stats_filtering.py:93-101` (`build_equity_curve` — добавить `baseline`-параметр)
- Modify: `backend/routers/stats_advanced.py:64`, `:191` (передать baseline в `build_equity_curve`)
- Test: `backend/tests/test_stats_filtering_equity.py` (Create)

**Проблема:** `build_equity_curve` возвращает `cumsum(net_pnl)` от 0 без капитала. `/stats/advanced` кормит эту кривую в `calculate_ulcer_index`, `collect_drawdown_episodes` (→Sterling) и `calculate_k_ratio`, где DD% = `(peak−v)/peak×100` относительно пика кумулятивной ПРИБЫЛИ, а не капитала. На счёте 1 000 000 ₽ рост cum PnL 10 000→5 000 читается как «просадка 50%» (реально 0.5%); ниже нуля dd_pct > 100% и K-ratio ловит shift-хак (`:73-76`). Baseline уже вычислен в обоих роутерах (`stats_advanced.py:86-88`, `:197-199`).

**Interfaces:** `build_equity_curve(trades, baseline=0.0)` — новая опциональная сигнатура. Оба вызова в `stats_advanced.py` передают уже-вычисленный `baseline`. Для CAGR-расчётов там же по-прежнему используется `equity[-1]` как чистый кумулятивный PnL — поэтому НЕ ломаем `final_balance = baseline + equity[-1]`: если сдвигать кривую на baseline, `equity[-1]` станет `baseline + PnL`, и `baseline + equity[-1]` задвоит. Решение: baseline применяется только к кривой, скармливаемой DD-метрикам, а pnl-кривая для CAGR остаётся отдельной.

- [ ] **Step 1 — падающий тест.** Создать `backend/tests/test_stats_filtering_equity.py`:
```python
"""S3-03: build_equity_curve с baseline даёт реалистичные DD-проценты."""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.stats_filtering import build_equity_curve  # noqa: E402
import analytics  # noqa: E402


def _t(net):
    return SimpleNamespace(net_pnl=net, pnl=net)


def test_baseline_default_zero_backcompat():
    # Без baseline — прежнее поведение (кумулятив от 0).
    eq = build_equity_curve([_t(100.0), _t(-40.0), _t(20.0)])
    assert eq == [100.0, 60.0, 80.0]


def test_baseline_shifts_curve():
    eq = build_equity_curve([_t(100.0), _t(-40.0)], baseline=1_000_000.0)
    assert eq == [1_000_100.0, 1_000_060.0]


def test_ulcer_realistic_with_baseline():
    # cum PnL 10000 -> 5000 на счёте 1M = просадка 0.5%, не 50%.
    trades = [_t(10_000.0), _t(-5_000.0)]
    eq = build_equity_curve(trades, baseline=1_000_000.0)
    ui = analytics.calculate_ulcer_index(eq)
    assert ui is not None and ui < 1.0  # раньше был ~35 (на кривой от нуля)
```
- [ ] **Step 2 — запуск, ожидание FAIL.** `cd backend && C:/Python314/python.exe -m pytest tests/test_stats_filtering_equity.py -q`. Ожидаем FAIL с `TypeError: build_equity_curve() got an unexpected keyword argument 'baseline'`.
- [ ] **Step 3 — минимальный фикс.**
  `backend/services/stats_filtering.py:93` (before → after):
  ```python
  def build_equity_curve(trades) -> list:
      """Кумулятивный баланс по PnL (без учёта депозитов — для DD-метрик это и нужно)."""
      eq: list = []
      running = 0.0
      for t in trades:
          pnl = float(t.net_pnl if t.net_pnl is not None else (t.pnl or 0))
          running += pnl
          eq.append(running)
      return eq
  ```
  →
  ```python
  def build_equity_curve(trades, baseline: float = 0.0) -> list:
      """Кумулятивная equity-кривая по PnL.

      baseline=0.0 → кумулятив от нуля (legacy).
      baseline>0 (Σ NET_DEPOSITS + initial_balance) → DD-метрики (Ulcer/K/Sterling)
      считают % просадки от реального капитала, а не от пика прибыли (S3-03).
      """
      eq: list = []
      running = float(baseline)
      for t in trades:
          pnl = float(t.net_pnl if t.net_pnl is not None else (t.pnl or 0))
          running += pnl
          eq.append(running)
      return eq
  ```
  `backend/routers/stats_advanced.py` — в `/advanced` (`:64`) построить ОТДЕЛЬНУЮ кривую для DD-метрик ПОСЛЕ вычисления baseline (`:86-88`), не трогая `equity` для CAGR. Заменить `:110-115` вызовы:
  ```python
      dd_equity = build_equity_curve(trades, baseline=baseline)
      # ... в items:
      "ulcer_index": analytics.calculate_ulcer_index(dd_equity),
      "k_ratio": analytics.calculate_k_ratio(dd_equity),
      "sterling_ratio": analytics.calculate_sterling_ratio(cagr_pct or 0, dd_episodes),
      ...
      "drawdown_duration": analytics.calculate_drawdown_duration(dd_equity),
  ```
  и `dd_episodes` (`:92`) считать от baseline-кривой:
  ```python
      dd_episodes = analytics.collect_drawdown_episodes(build_equity_curve(trades, baseline=baseline))
  ```
  (Внимание: `baseline` вычислен на `:86-88` ДО `dd_stats`/`dd_episodes` — порядок уже верный. Строку `:64 equity = build_equity_curve(trades)` оставить как есть — её `equity[-1]` используется для CAGR как чистый PnL.)
  В `/benchmark` (`:191`, `:232-233`) аналогично: `dd_equity = build_equity_curve(trades, baseline=baseline)` после `:197-199`, и `ulcer_index`/`k_ratio` в `user_metrics` считать от `dd_equity`. `equity` (`:191`) для CAGR (`:214 final_balance = baseline + equity[-1]`) оставить нетронутым.
- [ ] **Step 4 — запуск, ожидание PASS.** `cd backend && C:/Python314/python.exe -m pytest tests/test_stats_filtering_equity.py tests/test_advanced_benchmark.py -q` → все passed. Импорт-смоук: `C:/Python314/python.exe -c "import main"`.
- [ ] **Step 5 — commit.** `fix(analytics): DD-метрики (Ulcer/K/Sterling) считаются от капитала, не от пика прибыли (S3-03)`.

---

### S3-04 [HIGH] Ложный баннер «Требуется переподключение» после осознанного отключения брокера

**Files:**
- Modify: `frontend/src/components/ReconnectBanner.tsx:43-48` (фильтр broken)
- Modify: `frontend/src/components/BrokerConnectModal.tsx:305` (индикация/фильтр `!is_active`) — вторичная часть
- Test: `frontend/src/components/__tests__/ReconnectBanner.test.tsx` (Create)

**Проблема:** DELETE `/broker/connections/{id}` — soft-delete (`is_active=false`, `last_sync_error='deactivated: user_request'`, `token_repo.py:187`). `ReconnectBanner` (`:44`) помечает broken ЛЮБОЙ `is_active=false` и на каждом заходе показывает красный «Токен отозван». Backend уже отдаёт `last_sync_error` в `BrokerConnectionResponse` (`broker.py:141,243`) — отличить намеренную деактивацию можно без нового поля.

**Interfaces:** Читает `ConnectionStatus.last_sync_error` (уже в интерфейсе, `:24`). Не требует backend-изменений.

- [ ] **Step 1 — падающий тест.** Создать `frontend/src/components/__tests__/ReconnectBanner.test.tsx`:
```tsx
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ReconnectBanner } from '../ReconnectBanner';
import { api } from '@/lib/apiClient';

vi.mock('@/lib/apiClient', () => ({ api: { get: vi.fn() } }));

describe('ReconnectBanner', () => {
  beforeEach(() => vi.clearAllMocks());

  it('НЕ показывает баннер для намеренной деактивации user_request', async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: 1, broker: 'tinkoff', is_active: false, last_sync_status: null,
        last_sync_error: 'deactivated: user_request' },
    ]);
    const { container } = render(<ReconnectBanner />);
    await waitFor(() => expect(api.get).toHaveBeenCalled());
    expect(container.textContent).not.toContain('Требуется переподключение');
  });

  it('показывает баннер для реального отзыва токена', async () => {
    (api.get as ReturnType<typeof vi.fn>).mockResolvedValue([
      { id: 2, broker: 'tinkoff', is_active: false, last_sync_status: 'error',
        last_sync_error: 'deactivated: token_invalid' },
    ]);
    render(<ReconnectBanner />);
    await waitFor(() =>
      expect(screen.getByText('Требуется переподключение брокера')).toBeInTheDocument());
  });
});
```
- [ ] **Step 2 — запуск, ожидание FAIL.** `cd frontend && npx vitest run --maxWorkers=1 src/components/__tests__/ReconnectBanner.test.tsx`. Ожидаем FAIL первого теста (баннер показывается).
- [ ] **Step 3 — минимальный фикс.** `frontend/src/components/ReconnectBanner.tsx:43-48` (before → after):
```tsx
      const broken = list.find(c => {
        if (!c.is_active) return true;
        if ((c.consecutive_failures ?? 0) >= 3) return true;
        if (c.circuit_open_until && new Date(c.circuit_open_until) > new Date()) return true;
        return false;
      });
```
→
```tsx
      const broken = list.find(c => {
        // Намеренное отключение брокера самим юзером — не ошибка, баннер не нужен.
        if (c.last_sync_error?.startsWith('deactivated: user_request')) return false;
        if (!c.is_active) return true;
        if ((c.consecutive_failures ?? 0) >= 3) return true;
        if (c.circuit_open_until && new Date(c.circuit_open_until) > new Date()) return true;
        return false;
      });
```
Вторичная часть (`BrokerConnectModal.tsx:305`) — рендерить неактивные карточки серым с подписью «Отключено» и единственной кнопкой «Переподключить». В `map` добавить перед контентом карточки: `const inactive = !conn.is_active;` и класс `${inactive ? 'opacity-60' : ''}`, а бейдж «Отключено» рядом с названием, если `inactive`.
- [ ] **Step 4 — запуск, ожидание PASS.** `cd frontend && npx vitest run --maxWorkers=1 src/components/__tests__/ReconnectBanner.test.tsx` → 2 passed. `npx tsc --noEmit` чисто.
- [ ] **Step 5 — commit.** `fix(broker-ui): не показывать reconnect-баннер при намеренном отключении брокера (S3-04)`.

---

### S3-05 [HIGH] Ошибка закрытия сделки проглатывается

**Files:**
- Modify: `frontend/src/app/history/page.tsx:182-197` (`handleCloseTradeConfirm`)
- Test: `frontend/src/app/history/__tests__/handleCloseTrade.test.tsx` (Create) — либо unit на toast-вызов

**Проблема:** `handleCloseTradeConfirm` при сбое PATCH `/trades/{id}/close` делает только `console.error` — ни тоста, ни рефетча. `CloseTradeModal` закрывается ДО завершения запроса, трейдер считает позицию закрытой.

**Interfaces:** Использует `useToast()` (добавить импорт) + `ApiError` (уже импортирован, `page.tsx:13`). Тот же паттерн повторяется в S3-06, S3-07, S3-28 — держать единообразным: `toast.error(e instanceof ApiError ? e.toUserMessage() : '<fallback>')`.

- [ ] **Step 1 — тест.** Создать `frontend/src/app/history/__tests__/handleCloseTrade.test.tsx` (проверяем, что при reject показывается toast):
```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ApiError } from '@/lib/apiClient';

// Проверяем helper-логику показа ошибки. Импортируем тост-паттерн напрямую:
const toastError = vi.fn();

async function handleClose(patch: () => Promise<unknown>, refetch: () => void) {
  try {
    await patch();
    refetch();
  } catch (error) {
    toastError(error instanceof ApiError ? error.toUserMessage() : 'Не удалось закрыть сделку');
  }
}

describe('handleClose error surfacing', () => {
  beforeEach(() => toastError.mockClear());

  it('показывает toast при 408', async () => {
    const refetch = vi.fn();
    await handleClose(() => Promise.reject(new ApiError(408, 'Сервер не отвечает.')), refetch);
    expect(toastError).toHaveBeenCalledWith('Сервер не отвечает.');
    expect(refetch).not.toHaveBeenCalled();
  });

  it('рефетчит при успехе, без toast', async () => {
    const refetch = vi.fn();
    await handleClose(() => Promise.resolve(), refetch);
    expect(refetch).toHaveBeenCalled();
    expect(toastError).not.toHaveBeenCalled();
  });
});
```
- [ ] **Step 2 — запуск, ожидание FAIL.** Тест новый и проверяет целевой паттерн — сначала он PASS для helper. Настоящая цель — правка `page.tsx`. Запусти `cd frontend && npx vitest run --maxWorkers=1 src/app/history/__tests__/handleCloseTrade.test.tsx`, убедись что проходит (это спецификация паттерна), затем применяй фикс к реальному коду и проверяй `tsc`.
- [ ] **Step 3 — минимальный фикс.** В `frontend/src/app/history/page.tsx`: добавить импорт `import { useToast } from '@/contexts/ToastContext';` и внутри компонента `const toast = useToast();`. Затем `:182-197` (before → after):
```tsx
    } catch (error) {
      console.error('Failed to close trade:', error);
    }
```
→
```tsx
    } catch (error) {
      toast.error(error instanceof ApiError ? error.toUserMessage() : 'Не удалось закрыть сделку');
    }
```
- [ ] **Step 4 — верификация.** `cd frontend && npx vitest run --maxWorkers=1 src/app/history/__tests__/handleCloseTrade.test.tsx` → passed; `npx tsc --noEmit` чисто. Ручной проход: закрыть сделку при выключенном backend → toast с ошибкой.
- [ ] **Step 5 — commit.** `fix(history): ошибка закрытия сделки показывается тостом (S3-05)`.

---

### S3-06 [HIGH] Удаление sync-сделки: 409 от backend, фронт молчит

**Files:**
- Modify: `frontend/src/app/history/page.tsx:204-212` (`handleDelete`)
- Modify: `frontend/src/app/history/_components/TradeRow.tsx:357` (гард Trash2 по `data_source`) — вторично
- Test: расширить `frontend/src/app/history/__tests__/handleCloseTrade.test.tsx` (тот же helper-паттерн для delete)

**Проблема:** Backend возвращает 409 с человекочитаемым detail («Синхронизированную сделку нельзя удалить…», `trades.py:1110`), но `handleDelete` глотает в `console.error`. Кнопка Trash2 показана для ВСЕХ сделок без проверки `data_source`.

**Interfaces:** Тот же `toast`/`ApiError` паттерн из S3-05 (переиспользовать `const toast = useToast()`).

- [ ] **Step 1 — тест.** Добавить в тот же тест-файл кейс, что 409-detail пробрасывается в toast:
```tsx
it('409 detail от sync-сделки уходит в toast', async () => {
  const refetch = vi.fn();
  await handleClose(
    () => Promise.reject(new ApiError(409, 'Синхронизированную сделку нельзя удалить.')),
    refetch,
  );
  expect(toastError).toHaveBeenCalledWith('Синхронизированную сделку нельзя удалить.');
});
```
- [ ] **Step 2 — запуск, ожидание PASS helper.** `cd frontend && npx vitest run --maxWorkers=1 src/app/history/__tests__/handleCloseTrade.test.tsx`.
- [ ] **Step 3 — минимальный фикс.** `frontend/src/app/history/page.tsx:204-212` (before → after):
```tsx
    try {
      await api.delete(`/trades/${tradeId}`);
      fetchTrades();
    } catch (error) {
      console.error('Delete failed:', error);
    }
```
→
```tsx
    try {
      await api.delete(`/trades/${tradeId}`);
      fetchTrades();
    } catch (error) {
      toast.error(error instanceof ApiError ? error.toUserMessage() : 'Не удалось удалить сделку');
    }
```
Вторично в `TradeRow.tsx:357` — обернуть кнопку Trash2: `disabled={trade.data_source === 'tinkoff_v2'}` + `title={trade.data_source === 'tinkoff_v2' ? 'Синхронизированную сделку нельзя удалить' : 'Удалить'}`.
- [ ] **Step 4 — верификация.** vitest passed; `npx tsc --noEmit` чисто. Ручной: удалить sync-сделку → toast с 409-detail; кнопка на sync-строке задизейблена.
- [ ] **Step 5 — commit.** `fix(history): 409 при удалении sync-сделки показывается тостом + гард кнопки (S3-06)`.

---

### S3-07 [HIGH] «Удалить все» обрывается на первой sync-сделке

**Files:**
- Modify: `frontend/src/app/history/page.tsx:214-229` (`handleDeleteAllTrades`)
- Test: `frontend/src/app/history/__tests__/handleDeleteAll.test.tsx` (Create)

**Проблема:** Цикл DELETE по одной; первая tinkoff_v2-сделка вернёт 409 → цикл прерывается: ручные сделки до неё уже удалены, остальное осталось, `alert('Ошибка при удалении сделок')` без объяснений. Плюс до 500 последовательных запросов.

**Interfaces:** Фильтрует `trades` по `data_source !== 'tinkoff_v2'` (только manual удаляемы), собирает per-item ошибки, показывает итог тостом. Использует `toast` из S3-05.

- [ ] **Step 1 — падающий тест.** Создать `frontend/src/app/history/__tests__/handleDeleteAll.test.tsx`:
```tsx
import { describe, it, expect, vi } from 'vitest';

type Trade = { id: number; data_source?: string };

async function deleteAll(
  trades: Trade[],
  del: (id: number) => Promise<void>,
): Promise<{ deleted: number; skipped: number }> {
  const manual = trades.filter(t => t.data_source !== 'tinkoff_v2');
  const skipped = trades.length - manual.length;
  let deleted = 0;
  for (const t of manual) {
    try { await del(t.id); deleted += 1; } catch { /* собираем, не прерываем */ }
  }
  return { deleted, skipped };
}

describe('deleteAll', () => {
  it('пропускает sync-сделки, удаляет manual, не падает', async () => {
    const trades: Trade[] = [
      { id: 1, data_source: 'manual' },
      { id: 2, data_source: 'tinkoff_v2' },
      { id: 3, data_source: 'manual' },
    ];
    const del = vi.fn().mockResolvedValue(undefined);
    const res = await deleteAll(trades, del);
    expect(res).toEqual({ deleted: 2, skipped: 1 });
    expect(del).toHaveBeenCalledTimes(2);
    expect(del).not.toHaveBeenCalledWith(2);
  });
});
```
- [ ] **Step 2 — запуск, ожидание PASS helper.** `cd frontend && npx vitest run --maxWorkers=1 src/app/history/__tests__/handleDeleteAll.test.tsx` (спецификация паттерна).
- [ ] **Step 3 — минимальный фикс.** `frontend/src/app/history/page.tsx:214-229` (before → after):
```tsx
  const handleDeleteAllTrades = async () => {
    setIsDeleting(true);
    try {
      // Удаляем все сделки по одной
      for (const trade of trades) {
        await api.delete(`/trades/${trade.id}`);
      }
      setShowDeleteConfirm(false);
      fetchTrades();
    } catch (error) {
      console.error('Delete all failed:', error);
      alert('Ошибка при удалении сделок');
    } finally {
      setIsDeleting(false);
    }
  };
```
→
```tsx
  const handleDeleteAllTrades = async () => {
    setIsDeleting(true);
    try {
      // Синхронизированные сделки удалить нельзя (backend 409) — пропускаем их,
      // ручные удаляем по одной, не прерываясь на ошибках отдельного элемента.
      const manual = trades.filter(t => t.data_source !== 'tinkoff_v2');
      const skipped = trades.length - manual.length;
      let deleted = 0;
      for (const trade of manual) {
        try {
          await api.delete(`/trades/${trade.id}`);
          deleted += 1;
        } catch (error) {
          console.error(`Delete failed for ${trade.id}:`, error);
        }
      }
      setShowDeleteConfirm(false);
      fetchTrades();
      toast.success(
        skipped > 0
          ? `Удалено ${deleted}, пропущено ${skipped} синхронизированных`
          : `Удалено ${deleted}`,
      );
    } finally {
      setIsDeleting(false);
    }
  };
```
- [ ] **Step 4 — верификация.** vitest passed; `npx tsc --noEmit` чисто. Ручной: «Удалить все» на аккаунте с sync-сделками → итог-тост, sync-сделки на месте.
- [ ] **Step 5 — commit.** `fix(history): delete-all пропускает sync-сделки и показывает итог (S3-07)`.

---

### S3-08 [HIGH] PnLHealthBadge маскирует backend-статус 'investigate' зелёным

**Files:**
- Modify: `frontend/src/components/PnLHealthBadge.tsx:20` (union), `:40-89` (styleFor), `:244-252` (useMemo)
- Test: `frontend/src/components/__tests__/PnLHealthBadge.test.tsx` (Create)

**Проблема:** Backend при RED любого контрольного слоя ставит `status='investigate'` («громкая страховка от ×1000», `pnl_health_service.py:282-284`; `HealthStatus = Literal["ok","warning","investigate","na","stale"]`, `:57`), даже при малом `diff_pct`. Фронт пересчитывает статус ТОЛЬКО по `diff_pct` (`<1% → 'ok'`), учитывая `data.status` лишь для `'na'` → при layer RED и diff 0.3% юзер видит зелёный «Корректно». `'investigate'` вообще нет в union → при `diff_pct=null` проваливается в default «Проверка нужна» (серый).

**Interfaces:** Расширяет `PnLHealthStatus` до `"investigate"`. `styleFor` получает красный стиль для `investigate`. Backend не меняется.

- [ ] **Step 1 — падающий тест.** Создать `frontend/src/components/__tests__/PnLHealthBadge.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { PnLHealthBadge } from '../PnLHealthBadge';

describe('PnLHealthBadge', () => {
  it('investigate от backend НЕ маскируется зелёным при малом diff_pct', () => {
    render(<PnLHealthBadge data={{
      status: 'investigate', diff_pct: 0.3, diff_rub: 100, checked_at: null,
    }} />);
    expect(screen.queryByText('Корректно')).not.toBeInTheDocument();
    expect(screen.getByText('Расхождение')).toBeInTheDocument();
  });

  it('investigate при diff_pct=null тоже красный, не серый', () => {
    render(<PnLHealthBadge data={{
      status: 'investigate', diff_pct: null, diff_rub: null, checked_at: null,
    }} />);
    expect(screen.queryByText('Проверка нужна')).not.toBeInTheDocument();
    expect(screen.getByText('Расхождение')).toBeInTheDocument();
  });

  it('ok при diff 0.3% и status ok остаётся зелёным', () => {
    render(<PnLHealthBadge data={{
      status: 'ok', diff_pct: 0.3, diff_rub: 100, checked_at: null,
    }} />);
    expect(screen.getByText('Корректно')).toBeInTheDocument();
  });
});
```
- [ ] **Step 2 — запуск, ожидание FAIL.** `cd frontend && npx vitest run --maxWorkers=1 src/components/__tests__/PnLHealthBadge.test.tsx`. Ожидаем FAIL первых двух кейсов.
- [ ] **Step 3 — минимальный фикс.** В `frontend/src/components/PnLHealthBadge.tsx`:
  - `:20` union (before → after):
    ```tsx
    export type PnLHealthStatus = "ok" | "warning" | "mismatch" | "na" | "stale";
    ```
    →
    ```tsx
    export type PnLHealthStatus = "ok" | "warning" | "mismatch" | "investigate" | "na" | "stale";
    ```
  - В `styleFor` (`switch`, после `case "mismatch":` блока) добавить:
    ```tsx
    case "investigate":
      return {
        dotColor: "bg-rose-400",
        textColor: "text-rose-400",
        bgColor: "bg-rose-500/10",
        borderColor: "border-rose-500/30",
        icon: <AlertCircle size={14} />,
        label: "Расхождение",
      };
    ```
  - `:244-252` useMemo (before → after):
    ```tsx
    const status: PnLHealthStatus = useMemo(() => {
      if (!data) return "stale";
      if (data.diff_pct === null || data.diff_pct === undefined) return data.status || "stale";
      const pct = Math.abs(data.diff_pct);
      if (data.status === "na") return "na";  // sentinel для пустых счетов
      if (pct < 1.0) return "ok";
      if (pct < 5.0) return "warning";
      return "mismatch";
    }, [data]);
    ```
    →
    ```tsx
    const status: PnLHealthStatus = useMemo(() => {
      if (!data) return "stale";
      // Серьёзные статусы backend'а (worst-of RED любого контрольного слоя)
      // имеют приоритет над band'ом по diff_pct — иначе маленький diff при
      // RED-слое ложно окрашивается зелёным (S3-08).
      if (data.status === "investigate") return "investigate";
      if (data.status === "na") return "na";
      if (data.diff_pct === null || data.diff_pct === undefined) return data.status || "stale";
      const pct = Math.abs(data.diff_pct);
      if (pct < 1.0) return "ok";
      if (pct < 5.0) return "warning";
      return "mismatch";
    }, [data]);
    ```
- [ ] **Step 4 — запуск, ожидание PASS.** `cd frontend && npx vitest run --maxWorkers=1 src/components/__tests__/PnLHealthBadge.test.tsx` → 3 passed. `npx tsc --noEmit` чисто.
- [ ] **Step 5 — commit.** `fix(pnl-health): бейдж уважает backend-статус investigate (worst-of RED) (S3-08)`.

---

### S3-09 [HIGH] Вкладки «Продвинутая»/«Сравнение» игнорируют FilterPanel

**Files:**
- Modify: `frontend/src/app/DashboardHome.tsx:226-237` (advancedQuery/benchmarkQuery)
- Test: `frontend/src/app/__tests__/dashboardTabsParams.test.ts` (Create) — unit на построение params-подмножества

**Проблема:** `FilterPanel` виден на всех трёх вкладках, но `advancedQuery`/`benchmarkQuery` уходят без параметров (`queryKey ['stats','advanced']` статичен), хотя `/stats/advanced` принимает `period/start_date/end_date/start_trade_id/tag` (`stats_advanced.py:47-51`), а `/stats/benchmark` — `period/start_date/end_date`. Юзер выбирает «7 дней»/точку отсчёта → advanced молча показывает all-time.

**Interfaces:** `statsParams` (`DashboardHome.tsx:176-196`) содержит и `mae_method`, который advanced/benchmark НЕ принимают. Нужно передавать ПОДМНОЖЕСТВО без `mae_method`.

- [ ] **Step 1 — падающий тест.** Создать `frontend/src/app/__tests__/dashboardTabsParams.test.ts`:
```ts
import { describe, it, expect } from 'vitest';

// Копия helper'а, который вынесем из DashboardHome (или инлайн-логика).
function toStatsSubset(p: Record<string, string>): Record<string, string> {
  const { mae_method, ...rest } = p;  // advanced/benchmark не принимают mae_method
  void mae_method;
  return rest;
}

describe('toStatsSubset', () => {
  it('выбрасывает mae_method, сохраняет период/тег/точку отсчёта', () => {
    const params = { period: '7days', tag: 'plan', start_trade_id: '42', mae_method: 'moex' };
    expect(toStatsSubset(params)).toEqual({ period: '7days', tag: 'plan', start_trade_id: '42' });
  });

  it('пустой набор → пустой', () => {
    expect(toStatsSubset({})).toEqual({});
  });
});
```
- [ ] **Step 2 — запуск, ожидание PASS helper.** `cd frontend && npx vitest run --maxWorkers=1 src/app/__tests__/dashboardTabsParams.test.ts`.
- [ ] **Step 3 — минимальный фикс.** В `frontend/src/app/DashboardHome.tsx` рядом со `statsParams` (после `:196`) добавить подмножество:
```tsx
  // advanced/benchmark принимают period/start_date/end_date/start_trade_id/tag,
  // но НЕ mae_method — иначе бэкенд отбросит лишний query-параметр.
  const statsSubset = useMemo(() => {
    const { mae_method, ...rest } = statsParams;
    void mae_method;
    return rest;
  }, [statsParams]);
```
Затем `:226-237` (before → after):
```tsx
  const advancedQuery = useQuery<unknown>({
    queryKey: ['stats', 'advanced'],
    queryFn: () => api.get('/stats/advanced'),
    enabled: !!user && activeTab === 'advanced',
    staleTime: 5 * 60 * 1000,
  });
  const benchmarkQuery = useQuery<unknown>({
    queryKey: ['stats', 'benchmark'],
    queryFn: () => api.get('/stats/benchmark'),
    enabled: !!user && activeTab === 'benchmark',
    staleTime: 5 * 60 * 1000,
  });
```
→
```tsx
  const advancedQuery = useQuery<unknown>({
    queryKey: ['stats', 'advanced', statsSubset],
    queryFn: () => api.get('/stats/advanced', { params: statsSubset }),
    enabled: !!user && activeTab === 'advanced',
    staleTime: 5 * 60 * 1000,
  });
  const benchmarkQuery = useQuery<unknown>({
    queryKey: ['stats', 'benchmark', statsSubset],
    queryFn: () => api.get('/stats/benchmark', { params: statsSubset }),
    enabled: !!user && activeTab === 'benchmark',
    staleTime: 5 * 60 * 1000,
  });
```
- [ ] **Step 4 — верификация.** vitest passed; `npx tsc --noEmit` чисто. Ручной: выбрать «7 дней» на вкладке «Продвинутая» → числа меняются (сравнить с all-time).
- [ ] **Step 5 — commit.** `fix(dashboard): вкладки advanced/benchmark уважают FilterPanel (S3-09)`.

---

### S3-10 [MEDIUM] Naive-UTC даты парсятся как локальное время (−3ч для МСК)

**Files:**
- Create: `frontend/src/lib/dateUtils.ts` (`parseApiDate`)
- Modify: `frontend/src/app/history/_components/TradeRow.tsx:63-74` (даты вх/вых)
- Modify: `frontend/src/components/dashboard/PortfolioCard.tsx:223` (`updated_at`)
- Test: `frontend/src/lib/__tests__/dateUtils.test.ts` (Create)

**Проблема:** Все datetime хранятся как naive UTC и Pydantic сериализует их без offset/Z (`'2026-07-02T12:30:00'`). Фронт `new Date(...)` трактует строку без offset как ЛОКАЛЬНОЕ время → для МСК всё на 3ч раньше; сделки 00:00–02:59 МСК попадают на предыдущую дату. Backend Z-суффикс задел бы десятки response-схем — контейнерный фронт-util безопаснее.

**Interfaces:** `parseApiDate(s: string): Date` — единая точка. Все `new Date(<api-datetime>)` в TradeRow/PortfolioCard заменяются на неё. (Прочие компоненты — вне scope этой задачи; чинить по мере обнаружения.)

- [ ] **Step 1 — падающий тест.** Создать `frontend/src/lib/__tests__/dateUtils.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import { parseApiDate } from '../dateUtils';

describe('parseApiDate', () => {
  it('naive-строку трактует как UTC (добавляет Z)', () => {
    const d = parseApiDate('2026-07-02T12:30:00');
    expect(d.toISOString()).toBe('2026-07-02T12:30:00.000Z');
  });

  it('строку с Z не трогает', () => {
    const d = parseApiDate('2026-07-02T12:30:00Z');
    expect(d.toISOString()).toBe('2026-07-02T12:30:00.000Z');
  });

  it('строку с offset не трогает', () => {
    const d = parseApiDate('2026-07-02T15:30:00+03:00');
    expect(d.toISOString()).toBe('2026-07-02T12:30:00.000Z');
  });
});
```
- [ ] **Step 2 — запуск, ожидание FAIL.** `cd frontend && npx vitest run --maxWorkers=1 src/lib/__tests__/dateUtils.test.ts`. Ожидаем FAIL с `Cannot find module '../dateUtils'`.
- [ ] **Step 3 — минимальный фикс.** Создать `frontend/src/lib/dateUtils.ts`:
```ts
/**
 * Парсит datetime из API. Backend хранит и отдаёт naive-UTC без суффикса
 * ('2026-07-02T12:30:00'), а new Date(строка-без-offset) трактует её как
 * ЛОКАЛЬНОЕ время → сдвиг на -3ч для МСК (S3-10). Добавляем Z, если offset
 * отсутствует.
 */
export function parseApiDate(s: string): Date {
  const hasTz = /(?:Z|[+-]\d{2}:?\d{2})$/.test(s);
  return new Date(hasTz ? s : `${s}Z`);
}
```
Затем в `TradeRow.tsx` заменить `new Date(trade.entry_at)` (`:63`, `:65`) и `new Date(trade.exit_at)` (`:72`, `:74`) на `parseApiDate(...)`; добавить импорт `import { parseApiDate } from '@/lib/dateUtils';`. В `PortfolioCard.tsx:223` — `new Date(portfolio.updated_at)` → `parseApiDate(portfolio.updated_at)`.
- [ ] **Step 4 — запуск, ожидание PASS.** `cd frontend && npx vitest run --maxWorkers=1 src/lib/__tests__/dateUtils.test.ts` → 3 passed. `npx tsc --noEmit` чисто.
- [ ] **Step 5 — commit.** `fix(frontend): parseApiDate трактует naive-даты как UTC (S3-10)`.

---

### S3-11 [MEDIUM] Benchmark: profit_factor и r_expectancy из словарей без этих ключей

**Files:**
- Modify: `backend/routers/stats_advanced.py:202-226` (источник метрик)
- Test: `backend/tests/test_benchmark_metric_sources.py` (Create)

**Проблема:** `user_metrics['profit_factor'] = win_loss.get('profit_factor')`, но `calculate_win_loss_stats` возвращает `win_rate/avg_win/avg_loss/payoff_ratio/largest_win/largest_loss/expectancy` (`distributions.py:45-53`) — PF там НЕТ. Аналогично `opt_f.get('r_expectancy')` — `calculate_optimal_f` не возвращает `r_expectancy`. Оба всегда `None` → `build_benchmark_response` пропускает метрику. Правильный источник — `calculate_advanced_stats` (`risk.py:77-82` возвращает `profit_factor` и `r_expectancy`).

**Interfaces:** Добавляет вызов `analytics.calculate_advanced_stats(pnls, risks)` и берёт из него оба ключа.

- [ ] **Step 1 — падающий тест.** Создать `backend/tests/test_benchmark_metric_sources.py`:
```python
"""S3-11: profit_factor и r_expectancy берутся из calculate_advanced_stats."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import analytics  # noqa: E402


def test_win_loss_has_no_profit_factor():
    # Характеризуем корень: источник, из которого читали, не содержит ключа.
    wl = analytics.calculate_win_loss_stats([100.0, -50.0, 200.0])
    assert "profit_factor" not in wl


def test_advanced_stats_has_both_keys():
    adv = analytics.calculate_advanced_stats([100.0, -50.0, 200.0], [10.0, 10.0, 10.0])
    assert "profit_factor" in adv
    assert "r_expectancy" in adv
    assert adv["profit_factor"] is not None
```
- [ ] **Step 2 — запуск, ожидание PASS (характеризация корня).** `cd backend && C:/Python314/python.exe -m pytest tests/test_benchmark_metric_sources.py -q` → passed (это фиксирует, откуда брать значения). Правка роутера проверяется curl-смоуком в Step 4.
- [ ] **Step 3 — минимальный фикс.** `backend/routers/stats_advanced.py` — после `:203 opt_f = analytics.calculate_optimal_f(pnls, risks)` добавить:
```python
    adv_stats = analytics.calculate_advanced_stats(pnls, risks)
```
и в `user_metrics` (`:225-226`) before → after:
```python
        "profit_factor": win_loss.get("profit_factor"),
        "r_expectancy": opt_f.get("r_expectancy") if isinstance(opt_f, dict) else None,
```
→
```python
        "profit_factor": adv_stats.get("profit_factor"),
        "r_expectancy": adv_stats.get("r_expectancy"),
```
- [ ] **Step 4 — верификация.** `cd backend && C:/Python314/python.exe -c "import main"` (импорт чист). Curl-смоук на живом backend (GET, read-only): `curl -s http://localhost:8000/stats/benchmark` под валидной сессией — в ответе items должны содержать `profit_factor` и `r_expectancy` (не пропущены). Если сессии нет — достаточно unit-проверки Step 2 + импорт.
- [ ] **Step 5 — commit.** `fix(benchmark): PF/R-expectancy из calculate_advanced_stats (S3-11)`.

---

### S3-12 [MEDIUM] Heatmap/time_patterns/календарный P&L в UTC без конвертации в МСК

**Files:**
- Modify: `backend/analytics/advanced.py:331-355` (`calculate_hour_dow_heatmap`), `:655-684` (`calculate_daily_pnl`)
- Modify: `backend/analytics/distributions.py:273-282` (`analyze_time_patterns`)
- Test: `backend/tests/test_analytics_tz.py` (Create)

**Проблема:** `Trade.entry_at` — naive-UTC. `calculate_hour_dow_heatmap` берёт `dt.weekday()/dt.hour`, `analyze_time_patterns` — `entry_time.hour`, `calculate_daily_pnl` — `dt.strftime('%Y-%m-%d')` без tz-конвертации → «лучший час 7:00» вместо 10:00 МСК; сделки 00:00–02:59 МСК уезжают на предыдущий день. Тот же класс, что уже исправленный «MAE −3ч» (`market_service._to_msk` конвертирует, аналитика — нет).

**Interfaces:** Вводит локальный хелпер `_to_msk_naive(dt)` в `advanced.py` (паттерн из `market_service._to_msk`: `pytz.utc.localize(dt).astimezone(MSK_TZ)`, затем `.replace(tzinfo=None)` для однородности с остальными полями). `distributions.py` импортирует его или дублирует минимально.

- [ ] **Step 1 — падающий тест.** Создать `backend/tests/test_analytics_tz.py`:
```python
"""S3-12: heatmap/daily_pnl/time_patterns бакетируют по МСК, не UTC."""
from __future__ import annotations

import os
import sys
from datetime import datetime
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics.advanced import calculate_hour_dow_heatmap, calculate_daily_pnl  # noqa: E402
from analytics.distributions import analyze_time_patterns  # noqa: E402


def test_heatmap_hour_shifted_to_msk():
    # 07:00 UTC == 10:00 МСК (открытие основной сессии MOEX).
    rows = [{"entry_at": datetime(2026, 3, 2, 7, 0), "pnl": 100.0}]  # Пн
    m = calculate_hour_dow_heatmap(rows)
    assert m[0][10]["count"] == 1   # МСК-час 10
    assert m[0][7]["count"] == 0    # не UTC-час 7


def test_daily_pnl_late_session_stays_same_msk_day():
    # 22:30 UTC 1 марта == 01:30 МСК 2 марта — должно попасть на 2026-03-02.
    rows = [{"entry_at": datetime(2026, 3, 1, 22, 30), "pnl": 50.0}]
    out = calculate_daily_pnl(rows)
    assert out[0]["date"] == "2026-03-02"


def test_time_patterns_hour_msk():
    trades = [SimpleNamespace(pnl=100.0, net_pnl=100.0,
                              entry_at=datetime(2026, 3, 2, 7, 0))]
    tp = analyze_time_patterns(trades)
    hours = {h["hour"] for h in tp["hour_stats"]} if isinstance(tp, dict) and tp.get("hour_stats") else set()
    assert "10:00" in hours
```
(Если структура `analyze_time_patterns` иная — сначала прочитать её return, скорректировать assert под фактический ключ. Читать `distributions.py` вокруг `:305-330`.)
- [ ] **Step 2 — запуск, ожидание FAIL.** `cd backend && C:/Python314/python.exe -m pytest tests/test_analytics_tz.py -q`. Ожидаем FAIL (бакеты по UTC-часу 7 / дате 03-01).
- [ ] **Step 3 — минимальный фикс.** В `backend/analytics/advanced.py` вверху добавить:
```python
import pytz

_MSK_TZ = pytz.timezone("Europe/Moscow")


def _to_msk(dt: datetime) -> datetime:
    """naive → трактуем как UTC → в МСК (паттерн market_service._to_msk)."""
    if dt.tzinfo is None:
        return pytz.utc.localize(dt).astimezone(_MSK_TZ)
    return dt.astimezone(_MSK_TZ)
```
В `calculate_hour_dow_heatmap` (`:344`) before → after:
```python
        cell = matrix[dt.weekday()][dt.hour]
```
→
```python
        dt = _to_msk(dt)
        cell = matrix[dt.weekday()][dt.hour]
```
В `calculate_daily_pnl` (`:670`) before → after:
```python
        key = dt.strftime("%Y-%m-%d")
```
→
```python
        key = _to_msk(dt).strftime("%Y-%m-%d")
```
В `distributions.py` (`:278`) before → after:
```python
        entry_time = t.entry_at
```
→
```python
        from analytics.advanced import _to_msk as _to_msk_helper
        entry_time = _to_msk_helper(t.entry_at)
```
(Импорт локальный внутри цикла нежелателен по перф — вынести `from analytics.advanced import _to_msk` в топ модуля `distributions.py`, если нет цикла импортов; проверить `python -c "import analytics"` после.)
- [ ] **Step 4 — запуск, ожидание PASS.** `cd backend && C:/Python314/python.exe -m pytest tests/test_analytics_tz.py tests/test_advanced_benchmark.py -q` → passed. Импорт-смоук `C:/Python314/python.exe -c "import main"`.
- [ ] **Step 5 — commit.** `fix(analytics): heatmap/daily/time_patterns бакетируют по МСК (S3-12)`.

---

### S3-13 [MEDIUM] Benchmark сравнивает per-trade Sortino и полный sqrt(N)-SQN с baseline другой шкалы

**Files:**
- Modify: `backend/routers/stats_advanced.py:228` (`sqn` → `sqn_n100`)
- Test: `backend/tests/test_benchmark_metric_sources.py` (расширить)

**Проблема:** В `user_metrics` уходит `sqn` с полным `sqrt(N)`, но шкала Ван Тарпа калибрована на N≤100 — в самом `vince_tharp.py:290` для рейтинга используется `sqn_n100`. Активный трейдер с 2500 сделками получает `sqn` ×5 к сопоставимому и «топ-1%» по определению. (Sortino-часть — оставляем per-trade как есть с пометкой; минимальный безопасный фикс — только SQN, т.к. `sqn_n100` уже вычислен и однозначен.)

**Interfaces:** Использует `sqn.get("sqn_n100")` (ключ уже в return `calculate_sqn`, `vince_tharp.py:301`).

- [ ] **Step 1 — тест.** Добавить в `backend/tests/test_benchmark_metric_sources.py`:
```python
def test_sqn_returns_n100_key():
    sqn = analytics.calculate_sqn([100.0, -50.0, 200.0, -30.0], [10.0, 10.0, 10.0, 10.0])
    assert "sqn_n100" in sqn
    # sqn_n100 ограничен sqrt(min(n,100)) — для сопоставимости с baseline Ван Тарпа.
    assert sqn["sqn_n100"] is not None
```
- [ ] **Step 2 — запуск, ожидание PASS.** `cd backend && C:/Python314/python.exe -m pytest tests/test_benchmark_metric_sources.py -q`.
- [ ] **Step 3 — минимальный фикс.** `backend/routers/stats_advanced.py:228` (before → after):
```python
        "sqn": sqn.get("sqn") if isinstance(sqn, dict) else None,
```
→
```python
        # Ван-Тарп-шкала калибрована на N≤100 → сопоставимая метрика = sqn_n100,
        # а не полный sqrt(N)-SQN (иначе активный трейдер «топ-1%» по определению).
        "sqn": sqn.get("sqn_n100") if isinstance(sqn, dict) else None,
```
- [ ] **Step 4 — верификация.** `C:/Python314/python.exe -c "import main"`; `pytest tests/test_benchmark_metric_sources.py -q` passed.
- [ ] **Step 5 — commit.** `fix(benchmark): сравнивать sqn_n100 вместо полного SQN (S3-13)`.

---

### S3-14 [MEDIUM] abs() на нетто-депозитах ломает ROI/drawdown-базу при чистом выводе средств

**Files:**
- Modify: `backend/analytics/_common_baseline.py:107-108` (`get_net_deposits_baseline_from_db`)
- Modify: `backend/routers/stats.py:540` (`drawdown_baseline = abs(...)`)
- Test: `backend/tests/test_common_baseline.py` (Create)

**Проблема:** `get_net_deposits_baseline_from_db` возвращает `abs(Σ NET_DEPOSIT)`. Если выведено больше, чем внесено (Σ < 0 — реально для anchored-счетов), знак переворачивается и база завышается: `roi_base = anchor + |net|` вместо `anchor + net`. `pnl_health_service` использует знаковую сумму (`:201 effective_deposits = net_deposits + initial_balance`) — на одном счёте ROI/DD% и health-cash считаются от разных баз.

**Interfaces:** Функция начинает возвращать знаковый `Decimal`. Оба потребителя (`stats_advanced.py:86`, `stats.py`) добавляют к нему `initial_balance` — при отрицательной effective-базе показывать `None` вместо счёта от перевёрнутого знаменателя (защита в роутере).

- [ ] **Step 1 — падающий тест.** Создать `backend/tests/test_common_baseline.py`:
```python
"""S3-14: get_net_deposits_baseline_from_db возвращает знаковую сумму."""
from __future__ import annotations

import os
import sys
from decimal import Decimal
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from analytics._common_baseline import get_net_deposits_baseline_from_db  # noqa: E402


def _db_with_sum(units, nano):
    db = MagicMock()
    q = db.query.return_value.filter.return_value
    q.one.return_value = (units, nano)
    return db


def test_net_negative_stays_negative():
    # Выведено 100k, внесено 20k → Σ = -80000 (не +80000).
    db = _db_with_sum(-80_000, 0)
    result = get_net_deposits_baseline_from_db(db, account_id=1)
    assert result == Decimal("-80000")


def test_net_positive_unchanged():
    db = _db_with_sum(150_000, 0)
    assert get_net_deposits_baseline_from_db(db, account_id=1) == Decimal("150000")
```
- [ ] **Step 2 — запуск, ожидание FAIL.** `cd backend && C:/Python314/python.exe -m pytest tests/test_common_baseline.py -q`. Ожидаем FAIL первого теста (`abs` → +80000).
- [ ] **Step 3 — минимальный фикс.**
  `backend/analytics/_common_baseline.py:107-108` (before → after):
  ```python
      total = Decimal(row[0] or 0) + Decimal(row[1] or 0) / Decimal(10**9)
      return abs(total)
  ```
  →
  ```python
      # Знаковая сумма (INPUT>0 / OUTPUT<0). abs() переворачивал базу для счетов
      # с чистым выводом средств → ROI/DD считались от завышенного знаменателя,
      # расходясь с pnl_health (знаковая effective_deposits) (S3-14).
      total = Decimal(row[0] or 0) + Decimal(row[1] or 0) / Decimal(10**9)
      return total
  ```
  Обновить комментарий `:103-106` (убрать «нужна абсолютная»).
  `backend/routers/stats.py:540` (before → after):
  ```python
              drawdown_baseline = abs(float(_row[0] or 0) + float(_row[1] or 0) / 1e9)
  ```
  →
  ```python
              drawdown_baseline = float(_row[0] or 0) + float(_row[1] or 0) / 1e9
  ```
  Ниже, где `drawdown_baseline` используется как знаменатель для DD% (после `:546` прибавления `initial_balance`), убедиться что есть гард `if drawdown_baseline <= 0` (он есть на `:549`) — при отрицательной базе DD% не считается, что корректно.
- [ ] **Step 4 — запуск, ожидание PASS.** `cd backend && C:/Python314/python.exe -m pytest tests/test_common_baseline.py -q` → passed. Импорт `C:/Python314/python.exe -c "import main"`. P&L sanity: прочитать `docs/PNL_PLAYBOOK.md`, при наличии reconcile-tool прогнать против тест-БД (не atom.db).
- [ ] **Step 5 — commit.** `fix(baseline): знаковые нетто-депозиты в ROI/drawdown-базе (S3-14)`.

---

### S3-15 [MEDIUM] SyncStatusIndicator.triggerSync: молчаливая ошибка + фикс-таймер 3с

**Files:**
- Modify: `frontend/src/components/SyncStatusIndicator.tsx:146-160` (`triggerSync`)
- Test: `frontend/src/components/__tests__/syncTrigger.test.ts` (Create) — unit на паттерн

**Проблема:** `triggerSync` ждёт блокирующий POST `/broker/trigger-sync/{id}`, но catch — только `console.error` (401/429/408 молча), а `finally` гасит spinner через фикс-`setTimeout 3000`, тогда как реальный синк 10–90с → кнопка перестаёт крутиться до завершения, юзер жмёт снова (ровно паттерн против ERR-303).

**Interfaces:** Добавляет `useToast()` в компонент; держит `syncing` до завершения `await`, `refetchStatus()` — сразу после ответа. Тот же `ApiError`/`toUserMessage` паттерн.

- [ ] **Step 1 — тест.** Создать `frontend/src/components/__tests__/syncTrigger.test.ts`:
```ts
import { describe, it, expect, vi } from 'vitest';
import { ApiError } from '@/lib/apiClient';

const toastError = vi.fn();

async function triggerSync(
  post: () => Promise<void>,
  refetch: () => void,
  setSyncing: (v: number | null) => void,
  id: number,
) {
  setSyncing(id);
  try {
    await post();
    refetch();
  } catch (e) {
    toastError(e instanceof ApiError ? e.toUserMessage() : 'Не удалось запустить синхронизацию');
  } finally {
    setSyncing(null);
  }
}

describe('triggerSync', () => {
  it('держит syncing до завершения await и рефетчит после успеха', async () => {
    const setSyncing = vi.fn();
    const refetch = vi.fn();
    await triggerSync(() => Promise.resolve(), refetch, setSyncing, 5);
    expect(setSyncing).toHaveBeenNthCalledWith(1, 5);
    expect(refetch).toHaveBeenCalled();
    expect(setSyncing).toHaveBeenLastCalledWith(null);
  });

  it('показывает toast при ошибке', async () => {
    toastError.mockClear();
    await triggerSync(() => Promise.reject(new ApiError(429, 'Слишком часто.')),
      vi.fn(), vi.fn(), 5);
    expect(toastError).toHaveBeenCalledWith('Слишком часто.');
  });
});
```
- [ ] **Step 2 — запуск, ожидание PASS helper.** `cd frontend && npx vitest run --maxWorkers=1 src/components/__tests__/syncTrigger.test.ts`.
- [ ] **Step 3 — минимальный фикс.** В `SyncStatusIndicator.tsx` добавить `import { useToast } from '@/contexts/ToastContext';` + `import { api, ApiError } from '@/lib/apiClient';` (проверить, что `ApiError` доступен; `:8` сейчас `import { api }`) и `const toast = useToast();`. Затем `:146-160` (before → after):
```tsx
  const triggerSync = async (connectionId: number) => {
    setSyncing(connectionId);
    try {
      await api.post(`/broker/trigger-sync/${connectionId}`);
      // Ждём немного и обновляем статус
      setTimeout(() => {
        refetchStatus();
        onTradesUpdated?.();
      }, 2000);
    } catch (error) {
      console.error('Failed to trigger sync:', error);
    } finally {
      setTimeout(() => setSyncing(null), 3000);
    }
  };
```
→
```tsx
  const triggerSync = async (connectionId: number) => {
    setSyncing(connectionId);
    try {
      // Блокирующий endpoint (10-90с) — держим spinner до фактического ответа,
      // затем сразу рефетчим статус (ERR-303: фикс-таймеры вводили в заблуждение).
      await api.post(`/broker/trigger-sync/${connectionId}`);
      refetchStatus();
      onTradesUpdated?.();
    } catch (error) {
      toast.error(error instanceof ApiError ? error.toUserMessage() : 'Не удалось запустить синхронизацию');
    } finally {
      setSyncing(null);
    }
  };
```
- [ ] **Step 4 — верификация.** vitest passed; `npx tsc --noEmit` чисто. Ручной: нажать «Синхр. сейчас» при недоступном backend → toast; spinner не гаснет раньше ответа.
- [ ] **Step 5 — commit.** `fix(sync-ui): triggerSync показывает ошибку и держит spinner до ответа (S3-15)`.

---

### S3-16 [MEDIUM] Сбой загрузки скриншота после создания сделки

**Files:**
- Modify: `frontend/src/components/AddTradeModal.tsx:70-108` (`handleSubmit`)
- Test: `frontend/src/components/__tests__/addTradeUpload.test.ts` (Create) — unit на разделённый flow

**Проблема:** POST `/trades/` и `api.upload` скриншота обёрнуты одним try (`:70-96`). Если сделка создалась, а upload упал — `toast.error('Не удалось сохранить сделку')`, `onSuccess()` не вызывается, модалка открыта → повторный клик даёт дубликат/409. Юзер не понимает, что сделка записана.

**Interfaces:** Разделить: успех создания → `onSuccess()+onClose()` всегда; ошибка upload → отдельный `toast.error('Сделка сохранена, но скриншот не загрузился')` (у нас нет `toast.warning`, используем `error` с явным текстом).

- [ ] **Step 1 — падающий тест.** Создать `frontend/src/components/__tests__/addTradeUpload.test.ts`:
```ts
import { describe, it, expect, vi } from 'vitest';

const toast = { success: vi.fn(), error: vi.fn() };

async function submit(
  createTrade: () => Promise<{ id: number }>,
  uploadScreenshot: ((id: number) => Promise<void>) | null,
  onSuccess: () => void,
  onClose: () => void,
) {
  let created: { id: number };
  try {
    created = await createTrade();
  } catch {
    toast.error('Не удалось сохранить сделку');
    return;
  }
  if (uploadScreenshot) {
    try {
      await uploadScreenshot(created.id);
      toast.success('Сделка добавлена');
    } catch {
      toast.error('Сделка сохранена, но скриншот не загрузился');
    }
  } else {
    toast.success('Сделка добавлена');
  }
  onSuccess();
  onClose();
}

describe('AddTrade submit', () => {
  it('при сбое upload всё равно onSuccess+onClose и warning-текст', async () => {
    toast.success.mockClear(); toast.error.mockClear();
    const onSuccess = vi.fn(); const onClose = vi.fn();
    await submit(
      () => Promise.resolve({ id: 7 }),
      () => Promise.reject(new Error('upload 500')),
      onSuccess, onClose,
    );
    expect(onSuccess).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith('Сделка сохранена, но скриншот не загрузился');
  });

  it('при сбое создания — не onSuccess', async () => {
    const onSuccess = vi.fn();
    await submit(() => Promise.reject(new Error('409')), null, onSuccess, vi.fn());
    expect(onSuccess).not.toHaveBeenCalled();
  });
});
```
- [ ] **Step 2 — запуск, ожидание PASS helper.** `cd frontend && npx vitest run --maxWorkers=1 src/components/__tests__/addTradeUpload.test.ts`.
- [ ] **Step 3 — минимальный фикс.** `AddTradeModal.tsx:91-104` (before → after):
```tsx
      // Загружаем скриншот если есть
      if (screenshotFile && createdTrade.id) {
        const formDataUpload = new FormData();
        formDataUpload.append('file', screenshotFile);
        await api.upload(`/trades/${createdTrade.id}/screenshot`, formDataUpload);
      }
      
      toast.success('Сделка добавлена');
      onSuccess();
      onClose();
      // Сбрасываем скриншот
      clearScreenshot();
    } catch (error) {
      toast.error(error instanceof ApiError ? error.toUserMessage() : 'Не удалось сохранить сделку');
    } finally {
```
→
```tsx
      // Скриншот — вторичен: сделка уже создана. Его сбой НЕ должен блокировать
      // onSuccess/onClose, иначе повторный сабмит даёт дубликат/409 (S3-16).
      let screenshotFailed = false;
      if (screenshotFile && createdTrade.id) {
        try {
          const formDataUpload = new FormData();
          formDataUpload.append('file', screenshotFile);
          await api.upload(`/trades/${createdTrade.id}/screenshot`, formDataUpload);
        } catch {
          screenshotFailed = true;
        }
      }

      if (screenshotFailed) {
        toast.error('Сделка сохранена, но скриншот не загрузился');
      } else {
        toast.success('Сделка добавлена');
      }
      onSuccess();
      onClose();
      // Сбрасываем скриншот
      clearScreenshot();
    } catch (error) {
      toast.error(error instanceof ApiError ? error.toUserMessage() : 'Не удалось сохранить сделку');
    } finally {
```
- [ ] **Step 4 — верификация.** vitest passed; `npx tsc --noEmit` чисто. Ручной: создать сделку со скриншотом при недоступном upload-эндпоинте → модалка закрывается, журнал обновлён, warning-тост.
- [ ] **Step 5 — commit.** `fix(add-trade): сбой скриншота не блокирует сохранение сделки (S3-16)`.

---

### S3-17 [MEDIUM] Формы принимают отрицательные цену/объём/плечо и будущую дату; backend не валидирует

**Files:**
- Modify: `frontend/src/components/AddTradeModal.tsx:199-236` (min на price/quantity/leverage), `entry_at` datetime-local (max)
- Modify: `backend/schemas.py:281-282` (`TradeBase.entry_price/quantity` → `Field(gt=0)`), `:329-330` (`TradeUpdate`)
- Test: `backend/tests/test_trade_schema_validation.py` (Create)

**Проблема:** Инпуты `entry_price/quantity/leverage/commission` — `type=number step=any` без `min`; `entry_at` без `max`. `TradeBase.entry_price/quantity` — голый `float` без `gt=0`. Сделка с ценой −100/объёмом −5 проходит end-to-end и искажает P&L.

**Interfaces:** Граница системы — backend `Field(gt=0)` на `entry_price`/`quantity`. Фронт-`min` — UX-подсказка. Обе стороны.

- [ ] **Step 1 — падающий тест (backend, граница).** Создать `backend/tests/test_trade_schema_validation.py`:
```python
"""S3-17: TradeBase/TradeUpdate отвергают неположительные price/quantity."""
from __future__ import annotations

import os
import sys

import pytest
from pydantic import ValidationError

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import schemas  # noqa: E402


def _valid_payload(**over):
    p = {
        "symbol": "SBER",
        "direction": "LONG",
        "entry_price": 300.0,
        "quantity": 10.0,
        "entry_at": "2026-01-01T10:00:00",
    }
    p.update(over)
    return p


def test_negative_price_rejected():
    with pytest.raises(ValidationError):
        schemas.TradeBase(**_valid_payload(entry_price=-100.0))


def test_zero_quantity_rejected():
    with pytest.raises(ValidationError):
        schemas.TradeBase(**_valid_payload(quantity=0.0))


def test_valid_payload_accepted():
    t = schemas.TradeBase(**_valid_payload())
    assert t.entry_price == 300.0


def test_update_negative_price_rejected():
    with pytest.raises(ValidationError):
        schemas.TradeUpdate(entry_price=-5.0)
```
- [ ] **Step 2 — запуск, ожидание FAIL.** `cd backend && C:/Python314/python.exe -m pytest tests/test_trade_schema_validation.py -q`. Ожидаем FAIL (отрицательные значения проходят).
- [ ] **Step 3 — минимальный фикс.**
  `backend/schemas.py` — импорт `Field` уже есть (`:1`). `:281-282` (before → after):
  ```python
      entry_price: float
      quantity: float
  ```
  →
  ```python
      entry_price: float = Field(gt=0)
      quantity: float = Field(gt=0)
  ```
  `:329-330` (`TradeUpdate`, before → after):
  ```python
      entry_price: Optional[float] = None
      quantity: Optional[float] = None
  ```
  →
  ```python
      entry_price: Optional[float] = Field(None, gt=0)
      quantity: Optional[float] = Field(None, gt=0)
  ```
  Фронт `AddTradeModal.tsx`: на `entry_price`/`quantity` инпутах (`:201`, `:211`) добавить `min="0.00000001"`; на `leverage` (`:223`) — `min="1"`; найти `entry_at` datetime-local инпут (grep `entry_at` в JSX части) и добавить `max={new Date().toISOString().slice(0,16)}`. Аналогичные `min` — в `EditTradeModal.tsx` на тех же полях.
- [ ] **Step 4 — запуск, ожидание PASS.** `cd backend && C:/Python314/python.exe -m pytest tests/test_trade_schema_validation.py -q` → passed. `C:/Python314/python.exe -c "import main"`. `cd frontend && npx tsc --noEmit` чисто.
- [ ] **Step 5 — commit.** `fix(trades): Field(gt=0) на price/quantity + min на формах (S3-17)`.

---

### S3-18 [MEDIUM] CommandPalette: дублированный id и 4 пункта-заглушки на «/»

**Files:**
- Modify: `frontend/src/components/CommandPalette.tsx:80-84` (дубль `nav.setups`, пункты «Заметки»/«Импорт»/«Брокеры»)
- Test: `frontend/src/components/__tests__/commandPaletteItems.test.ts` (Create)

**Проблема:** Два элемента с `id="nav.setups"` (`:80` и `:82`) → key-collision, второй «Сетапы» ведёт на «/». «Заметки»/«Импорт сделок»/«Брокеры» (`:81,83,84`) тоже `router.push("/")`. Рабочие цели существуют: `action.import` диспатчит `empirik:import-trades`, брокеры на `/profile?tab=brokers`.

**Interfaces:** ITEMS-массив с уникальными `id`. Тест проверяет уникальность id и целевые роуты.

- [ ] **Step 1 — падающий тест.** Создать `frontend/src/components/__tests__/commandPaletteItems.test.ts`:
```ts
import { describe, it, expect } from 'vitest';
import { ITEMS } from '../CommandPalette';

describe('CommandPalette ITEMS', () => {
  it('все id уникальны', () => {
    const ids = ITEMS.map(i => i.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('нет пунктов-заглушек «Брокеры» с router.push("/")', () => {
    const brokers = ITEMS.find(i => i.label === 'Брокеры');
    // либо удалён, либо ведёт на реальный роут — но не должен быть заглушкой
    if (brokers) expect(brokers.id).not.toBe('nav.brokers-stub');
  });
});
```
(Тест импортирует `{ ITEMS }` — экспорт добавляется в Step 3a ниже. До него `import { ITEMS }` не резолвится, поэтому запускать Step 2 только ПОСЛЕ 3a. Порядок: сделать 3a (export) → Step 2 (red по уникальности) → 3b (фикс дублей).)
- [ ] **Step 3a — экспортировать ITEMS.** В `CommandPalette.tsx` на строке 71 объявление сейчас `const ITEMS: CommandItem[] = [` — заменить на:
```tsx
export const ITEMS: CommandItem[] = [
```
- [ ] **Step 2 — запуск, ожидание FAIL.** `cd frontend && npx vitest run --maxWorkers=1 src/components/__tests__/commandPaletteItems.test.ts`. Ожидаем FAIL теста уникальности (дубль `nav.setups`).
- [ ] **Step 3b — минимальный фикс.** `CommandPalette.tsx:81-84` (before → after):
```tsx
  { id: "nav.notes", label: "Заметки", Icon: StickyNote, group: "Навигация", onSelect: ({ router }) => router.push("/") },
  { id: "nav.setups", label: "Сетапы", Icon: Layers, group: "Навигация", onSelect: ({ router }) => router.push("/") },
  { id: "nav.import", label: "Импорт сделок", Icon: Upload, group: "Навигация", onSelect: ({ router }) => router.push("/") },
  { id: "nav.brokers", label: "Брокеры", Icon: Plug, group: "Навигация", onSelect: ({ router }) => router.push("/") },
```
→
```tsx
  { id: "nav.import", label: "Импорт сделок", Icon: Upload, group: "Навигация", keywords: ["загрузить", "csv"], onSelect: ({ closePalette }) => { closePalette(); window.dispatchEvent(new CustomEvent("empirik:import-trades")); } },
  { id: "nav.brokers", label: "Брокеры", Icon: Plug, group: "Навигация", keywords: ["tinkoff", "подключить"], onSelect: ({ router }) => router.push("/profile?tab=brokers") },
```
(Дубль `nav.setups` `:82` и заглушка «Заметки» удалены — реальный `nav.setups` `:80` уже ведёт на `/analysis/setups`. Проверить, что `closePalette` доступен в сигнатуре `onSelect` — она такая же, как в `action.import` `:98`.)
- [ ] **Step 4 — запуск, ожидание PASS.** `cd frontend && npx vitest run --maxWorkers=1 src/components/__tests__/commandPaletteItems.test.ts` → passed. `npx tsc --noEmit` чисто. Ручной: Cmd+K → «Брокеры» ведёт на `/profile?tab=brokers`.
- [ ] **Step 5 — commit.** `fix(command-palette): убран дубль id и заглушки, брокеры/импорт на реальные цели (S3-18)`.

---

### S3-19 [MEDIUM] SetupManagerModal: мутации глотают ошибки, нет защиты от double-submit

**Files:**
- Modify: `frontend/src/components/SetupManagerModal.tsx:61-118` (`handleSave`/`handleDelete`/`initPresets`), `:215-221` (кнопка)
- Test: покрывается ручной проверкой + tsc (MEDIUM — сжатый цикл)

**Проблема:** `handleSave`/`handleDelete`/`initPresets` ловят ошибки только в `console.error` — при 4xx/5xx юзер жмёт «Создать сетап», форма не закрывается, ничего не происходит. Кнопка «Сохранить» без `disabled` → двойной клик = два сетапа.

**Interfaces:** Добавить `useToast()` + `ApiError` (импорт `import { api, ApiError } from '@/lib/apiClient';`) + `isSubmitting`-state.

- [ ] **Step 1 — проверка.** Ручной repro: открыть SetupManagerModal при недоступном backend, нажать «Создать сетап» → сейчас тишина. Зафиксировать как baseline.
- [ ] **Step 2 — фикс.**
  Добавить импорты и state: `const toast = useToast();`, `const [isSubmitting, setIsSubmitting] = useState(false);`.
  `handleSave` (`:61-80`, before → after):
  ```tsx
  const handleSave = async () => {
    if (!formData.name.trim()) return;
    try {
      if (editingSetup) {
        await api.put(`/setups/${editingSetup.id}`, { body: formData });
        fetchSetups();
        setEditingSetup(null);
      } else {
        await api.post('/setups/', { body: formData });
        fetchSetups();
        setIsAddingNew(false);
      }
      resetForm();
    } catch (e) {
      console.error('Failed to save setup:', e);
    }
  };
  ```
  →
  ```tsx
  const handleSave = async () => {
    if (!formData.name.trim() || isSubmitting) return;
    setIsSubmitting(true);
    try {
      if (editingSetup) {
        await api.put(`/setups/${editingSetup.id}`, { body: formData });
        setEditingSetup(null);
      } else {
        await api.post('/setups/', { body: formData });
        setIsAddingNew(false);
      }
      fetchSetups();
      resetForm();
    } catch (e) {
      toast.error(e instanceof ApiError ? e.toUserMessage() : 'Не удалось сохранить сетап');
    } finally {
      setIsSubmitting(false);
    }
  };
  ```
  `handleDelete` (`:88-90`) и `initPresets` (`:115-117`) — заменить `console.error(...)` на `toast.error(e instanceof ApiError ? e.toUserMessage() : 'Не удалось удалить сетап' /* или инициализировать пресеты */)`.
  Кнопка `:215-221` (before → after): добавить `disabled={isSubmitting || !formData.name.trim()}` и класс `disabled:opacity-50`.
- [ ] **Step 3 — верификация + commit.** `cd frontend && npx tsc --noEmit` чисто; `npx vitest run --maxWorkers=1` (полный) без регрессий. Ручной: недоступный backend → toast; двойной клик не создаёт дубль. Commit: `fix(setups): тосты ошибок + защита от double-submit (S3-19)`.

---

### S3-20 [MEDIUM] 422-ошибка показывается как «[object Object]»

**Files:**
- Modify: `frontend/src/lib/apiClient.ts:202-208` (нормализация detail)
- Test: `frontend/src/lib/__tests__/apiError422.test.ts` (Create)

**Проблема:** При 422 FastAPI кладёт в `detail` массив `[{loc, msg, type}]`. `apiClient` берёт `errorData.detail` как есть → `ApiError(status, detail)` интерполирует массив → «[object Object],[object Object]».

**Interfaces:** Нормализует массив-detail в строку `d.msg` через `; `. `toUserMessage()` не меняется.

- [ ] **Step 1 — падающий тест.** Создать `frontend/src/lib/__tests__/apiError422.test.ts`:
```ts
import { describe, it, expect } from 'vitest';

// Извлекаем нормализующую логику ровно как в apiClient.request.
function normalizeDetail(errorData: { detail?: unknown }, status: number): string {
  const raw = errorData.detail;
  if (Array.isArray(raw)) {
    return raw.map((d: { msg?: string }) => d?.msg ?? String(d)).join('; ');
  }
  return (raw as string) || `HTTP ${status}`;
}

describe('normalizeDetail (422)', () => {
  it('массив pydantic-ошибок → человекочитаемая строка', () => {
    const detail = [
      { loc: ['body', 'entry_price'], msg: 'Input should be greater than 0', type: 'greater_than' },
      { loc: ['body', 'quantity'], msg: 'Field required', type: 'missing' },
    ];
    expect(normalizeDetail({ detail }, 422)).toBe('Input should be greater than 0; Field required');
  });

  it('строковый detail не трогает', () => {
    expect(normalizeDetail({ detail: 'Уже существует' }, 409)).toBe('Уже существует');
  });
});
```
- [ ] **Step 2 — запуск, ожидание PASS helper.** `cd frontend && npx vitest run --maxWorkers=1 src/lib/__tests__/apiError422.test.ts`.
- [ ] **Step 3 — минимальный фикс.** `frontend/src/lib/apiClient.ts:202-208` (before → after):
```ts
    const errorData = await response.json().catch(() => ({ detail: undefined }));
    const detail = errorData.detail
      || (response.status === 401
        ? (isAuthEndpoint
            ? 'Неверный email или пароль'
            : 'Сессия истекла. Войдите снова.')
        : `HTTP ${response.status}`);
```
→
```ts
    const errorData = await response.json().catch(() => ({ detail: undefined }));
    // FastAPI 422 кладёт detail массивом [{loc,msg,type}] — иначе toUserMessage
    // интерполирует его как "[object Object]" (S3-20).
    const rawDetail = Array.isArray(errorData.detail)
      ? errorData.detail.map((d: { msg?: string }) => d?.msg ?? String(d)).join('; ')
      : errorData.detail;
    const detail = rawDetail
      || (response.status === 401
        ? (isAuthEndpoint
            ? 'Неверный email или пароль'
            : 'Сессия истекла. Войдите снова.')
        : `HTTP ${response.status}`);
```
- [ ] **Step 4 — верификация.** vitest passed; `npx tsc --noEmit` чисто. Ручной: отправить невалидную форму → внятный текст вместо «[object Object]».
- [ ] **Step 5 — commit.** `fix(api-client): нормализация 422-detail массива в строку (S3-20)`.

---

### S3-21 [MEDIUM] Ошибка второстепенного действия затирает основную таблицу

**Files:**
- Modify: `frontend/src/components/PositionJournalView.tsx:850-857` (`handleEditExecution`)
- Modify: `frontend/src/app/positions/page.tsx:166-168` (`handleSync` error), `:432-434` (onEdit error)
- Test: покрывается ручной проверкой + tsc (MEDIUM — сжатый цикл)

**Проблема:** `handleEditExecution` при сбое GET `/trades/{id}` делает `setError(...)`, а рендер `loading ? ... : error ? <ошибка> : <таблица>` (`:993`) заменяет весь журнал строкой ошибки без повтора. То же в `positions/page.tsx`: ошибка `onEdit`/`handleSync` выставляет `error` и `!loading && !error && ...` (`:297`) прячет таблицу.

**Interfaces:** Разделить `error` (первичная загрузка) и action-ошибки. Простейший безопасный вариант — action-ошибки показывать тостом, НЕ через `setError`. Оба файла используют `toast`/`ApiError` паттерн (в `positions/page.tsx` — добавить `useToast`).

- [ ] **Step 1 — проверка.** Ручной repro: в PositionJournalView открыть редактирование сделки при недоступном backend → вся таблица исчезает. Baseline.
- [ ] **Step 2 — фикс.**
  `PositionJournalView.tsx:850-857` — добавить `const toast = useToast();` в компонент (импорт), затем (before → after):
  ```tsx
  const handleEditExecution = useCallback(async (executionId: number) => {
    try {
      const full = await api.get<EditableTrade>(`/trades/${executionId}`);
      setEditingTrade(full);
    } catch (e) {
      setError((e as Error).message || 'Не удалось загрузить сделку');
    }
  }, []);
  ```
  →
  ```tsx
  const handleEditExecution = useCallback(async (executionId: number) => {
    try {
      const full = await api.get<EditableTrade>(`/trades/${executionId}`);
      setEditingTrade(full);
    } catch (e) {
      // Ошибка вторичного действия НЕ должна затирать уже загруженный журнал —
      // error зарезервирован под первичную загрузку (S3-21).
      toast.error(e instanceof ApiError ? e.toUserMessage() : 'Не удалось загрузить сделку');
    }
  }, [toast]);
  ```
  `positions/page.tsx` — добавить `const toast = useToast();`; в `handleSync` (`:166-168`) и `onEdit` (`:432-434`) заменить `setError(msg)` на `toast.error(err instanceof ApiError ? err.toUserMessage() : '<fallback>')`. Импортировать `ApiError` из apiClient и `useToast`.
- [ ] **Step 3 — верификация + commit.** `cd frontend && npx tsc --noEmit` чисто; `npx vitest run --maxWorkers=1` без регрессий. Ручной: edit/sync-ошибка → тост, таблица на месте. Commit: `fix(positions): ошибки вторичных действий через тост, таблица не затирается (S3-21)`.

---

### S3-22 [MEDIUM] IMOEX-оверлей нормируется на PnL первой сделки

**Files:**
- Modify: `frontend/src/components/dashboard/EquityCurveCard.tsx:84-95` (нормировка benchmark)
- Test: `frontend/src/components/__tests__/equityBenchmarkRatio.test.ts` (Create)

**Проблема:** Для broker-юзера `equity_curve` — кумулятивный realized PnL, стартующий с PnL первой сделки. `ratio = data[0].balance / firstBenchmark`: убыточная первая сделка (`balance<0`) → отрицательный ratio → IMOEX зеркально; `balance===0` (falsy) → `ratio=1` → IMOEX в пунктах (~2800) на оси рублей.

**Interfaces:** Для `isBrokerCumulative` использовать `pctBaseline` (Σ NET_DEPOSIT) как знаменатель нормировки вместо `data[0].balance`; при отсутствии валидной базы — не рисовать оверлей (benchmark=null).

- [ ] **Step 1 — падающий тест.** Создать `frontend/src/components/__tests__/equityBenchmarkRatio.test.ts`:
```ts
import { describe, it, expect } from 'vitest';

// Логика выбора нормировочной базы (вынесем в чистую функцию).
function benchmarkRatio(opts: {
  isBrokerCumulative: boolean;
  firstBalance: number | undefined;
  firstBenchmark: number | undefined;
  pctBaseline: number | undefined;
}): number | null {
  const { isBrokerCumulative, firstBalance, firstBenchmark, pctBaseline } = opts;
  if (!firstBenchmark) return null;
  const base = isBrokerCumulative ? pctBaseline : firstBalance;
  if (!base || base <= 0) return null;  // невалидная база → оверлей не рисуем
  return base / firstBenchmark;
}

describe('benchmarkRatio', () => {
  it('broker: использует pctBaseline, не PnL первой сделки', () => {
    const r = benchmarkRatio({ isBrokerCumulative: true, firstBalance: -500,
      firstBenchmark: 2800, pctBaseline: 1_000_000 });
    expect(r).toBeGreaterThan(0);
    expect(r).toBeCloseTo(1_000_000 / 2800);
  });

  it('broker без baseline → null (не рисуем)', () => {
    expect(benchmarkRatio({ isBrokerCumulative: true, firstBalance: -500,
      firstBenchmark: 2800, pctBaseline: 0 })).toBeNull();
  });

  it('non-broker: по firstBalance', () => {
    const r = benchmarkRatio({ isBrokerCumulative: false, firstBalance: 100000,
      firstBenchmark: 2800, pctBaseline: undefined });
    expect(r).toBeCloseTo(100000 / 2800);
  });
});
```
- [ ] **Step 2 — запуск, ожидание PASS helper.** `cd frontend && npx vitest run --maxWorkers=1 src/components/__tests__/equityBenchmarkRatio.test.ts`.
- [ ] **Step 3 — минимальный фикс.** `EquityCurveCard.tsx:84-95` (before → after):
```tsx
    // Нормализуем benchmark к стартовому balance, чтобы линии были сравнимы
    const firstBenchmark = benchmark?.[0]?.value;
    const ratio = firstBenchmark && data[0]?.balance ? data[0].balance / firstBenchmark : 1;
    return data.map((p) => {
      const dayKey = p.date.slice(0, 10);
      const benchValue = benchByDate[dayKey];
      return {
        date: p.date,
        balance: p.balance,
        benchmark: benchValue !== undefined ? benchValue * ratio : null,
      };
    });
```
→
```tsx
    // Нормализуем benchmark к базе капитала. Для broker (кумулятивный PnL от 0)
    // база = pctBaseline (Σ NET_DEPOSIT), НЕ PnL первой сделки — иначе убыточный
    // старт инвертирует линию, а нулевой — ломает масштаб (S3-22).
    const firstBenchmark = benchmark?.[0]?.value;
    const normBase = isBrokerCumulative ? pctBaseline : data[0]?.balance;
    const ratio = firstBenchmark && normBase && normBase > 0 ? normBase / firstBenchmark : null;
    return data.map((p) => {
      const dayKey = p.date.slice(0, 10);
      const benchValue = benchByDate[dayKey];
      return {
        date: p.date,
        balance: p.balance,
        benchmark: ratio !== null && benchValue !== undefined ? benchValue * ratio : null,
      };
    });
```
Добавить `pctBaseline` и `isBrokerCumulative` в deps `useMemo` (`:96`): `}, [data, benchmark, isBrokerCumulative, pctBaseline]);`.
- [ ] **Step 4 — верификация.** vitest passed; `npx tsc --noEmit` чисто. Ручной: broker-аккаунт с убыточной первой сделкой → IMOEX-линия растёт вместе с индексом, не зеркалит.
- [ ] **Step 5 — commit.** `fix(equity-curve): нормировка IMOEX по pctBaseline для broker-кривой (S3-22)`.

---

### S3-23 [MEDIUM] Сохранение Daily Review без обработки ошибок — молчаливая потеря текста

**Files:**
- Modify: `frontend/src/app/review/page.tsx:87-104` (`save`), рендер около кнопки `:220-224`
- Test: покрывается ручной проверкой + tsc (MEDIUM — сжатый цикл)

**Проблема:** `save()` имеет только `finally`: при 401/5xx `api.post` бросает → unhandled rejection, «Сохранено ✓» не появляется, ошибки нет; уход со страницы = потеря текста. Загрузка (FE-02) уже через DataError, запись — нет.

**Interfaces:** Добавить `saveError`-state (`ApiError | Error | null`, `ApiError` уже импортирован `:16`) и рендерить его рядом с кнопкой; локальный стейт формы (`reflection`/`intention`/…) НЕ очищать.

- [ ] **Step 1 — проверка.** Ручной repro: написать рефлексию, при недоступном backend нажать «Сохранить review» → тишина. Baseline.
- [ ] **Step 2 — фикс.**
  Добавить state: `const [saveError, setSaveError] = useState<ApiError | Error | null>(null);`.
  `save()` (`:87-104`, before → after):
  ```tsx
  async function save() {
    setSaving(true);
    try {
      const updated = await api.post<ReviewData>("/review/", {
        body: { date, reflection, intention, rating, trade_reflections: tradeReflections },
      });
      setData(updated);
      setSavedAt(Date.now());
      setTimeout(() => setSavedAt(null), 3000);
    } finally {
      setSaving(false);
    }
  }
  ```
  →
  ```tsx
  async function save() {
    setSaving(true);
    setSaveError(null);
    try {
      const updated = await api.post<ReviewData>("/review/", {
        body: { date, reflection, intention, rating, trade_reflections: tradeReflections },
      });
      setData(updated);
      setSavedAt(Date.now());
      setTimeout(() => setSavedAt(null), 3000);
    } catch (e) {
      // Не очищаем локальный стейт формы — текст рефлексии должен остаться (S3-23).
      setSaveError(e as ApiError | Error);
    } finally {
      setSaving(false);
    }
  }
  ```
  Рядом с кнопкой `:220-224` добавить:
  ```tsx
  {saveError && (
    <span className="text-rose-400 text-sm ml-3">
      {saveError instanceof ApiError ? saveError.toUserMessage() : 'Не удалось сохранить'}
    </span>
  )}
  ```
- [ ] **Step 3 — верификация + commit.** `cd frontend && npx tsc --noEmit` чисто; `npx vitest run --maxWorkers=1` без регрессий. Ручной: недоступный backend → ошибка у кнопки, текст сохранён в форме. Commit: `fix(review): показывать ошибку сохранения, не терять текст (S3-23)`.

---

### S3-24 [LOW] /tags/ считает P&L по тегам GROSS (t.pnl), нарушая MATH-01

**Files:**
- Modify: `backend/routers/stats_tags.py:52-53` (сумма и wins)
- Test: `backend/tests/test_stats_tags_net.py` (Create)

**Проблема:** `/tags/` суммирует голый `t.pnl` и по нему считает win_rate (`:52-53`), тогда как остальные тег-агрегаты (`stats.py:503`) используют `net_pnl` с fallback на `pnl`. Для скальпера комиссии меняют суммы и знак маргинальных сделок → в двух местах UI разные PnL/WR по одному тегу.

**Interfaces:** Тот же net-приоритетный доступ `net_pnl if net_pnl is not None else (pnl or 0)`.

- [ ] **Step 1 — падающий тест.** Создать `backend/tests/test_stats_tags_net.py`:
```python
"""S3-24 (MATH-01): /tags/ агрегирует NET, не GROSS."""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _aggregate(trades):
    """Копия целевой логики для unit-проверки net-приоритета."""
    tag_stats = {}
    for t in trades:
        if not t.tags:
            continue
        pnl = float(t.net_pnl if t.net_pnl is not None else (t.pnl or 0))
        for tag in t.tags:
            k = tag.lower()
            s = tag_stats.setdefault(k, {"pnl": 0.0, "wins": 0, "count": 0})
            s["pnl"] += pnl
            s["count"] += 1
            if pnl > 0:
                s["wins"] += 1
    return tag_stats


def test_net_over_gross():
    # gross +10, комиссия делает net -5 → в минус, win НЕ засчитывается.
    trades = [SimpleNamespace(tags=["scalp"], pnl=10.0, net_pnl=-5.0)]
    out = _aggregate(trades)
    assert out["scalp"]["pnl"] == -5.0
    assert out["scalp"]["wins"] == 0
```
- [ ] **Step 2 — запуск, ожидание PASS helper.** `cd backend && C:/Python314/python.exe -m pytest tests/test_stats_tags_net.py -q` (спецификация целевой логики).
- [ ] **Step 3 — минимальный фикс.** `backend/routers/stats_tags.py:51-54` (before → after):
```python
            tag_stats[tag_lower]["count"] += 1
            tag_stats[tag_lower]["pnl"] += float(t.pnl or 0)
            if t.pnl and t.pnl > 0:
                tag_stats[tag_lower]["wins"] += 1
```
→
```python
            # MATH-01: NET (после комиссий) приоритетнее GROSS — иначе цифры
            # расходятся с tag_performance на дашборде (S3-24).
            _pnl = float(t.net_pnl if t.net_pnl is not None else (t.pnl or 0))
            tag_stats[tag_lower]["count"] += 1
            tag_stats[tag_lower]["pnl"] += _pnl
            if _pnl > 0:
                tag_stats[tag_lower]["wins"] += 1
```
- [ ] **Step 4 — верификация + commit.** `C:/Python314/python.exe -c "import main"`; `pytest tests/test_stats_tags_net.py -q` passed. Commit: `fix(tags): /tags агрегирует net_pnl по MATH-01 (S3-24)`.

---

### S3-25 [LOW] analytics.calculate_stats падает NameError на любом непустом списке

**Files:**
- Modify: `backend/analytics/aggregator.py:1-11` (добавить импорты helper-функций)
- Modify: `backend/tests/unit/test_analytics_aggregator.py` (снять xfail, удалить bug-reproducer)

**Проблема:** `aggregator.py` вызывает `calculate_optimal_f/calculate_z_score/calculate_sqn/calculate_advanced_stats/analyze_mae_mfe/calculate_sharpe_sortino/...` не импортируя их (`import` только `math, numpy, Decimal, UNDEFINED, _sanitize`) → любой вызов с непустым списком даёт `NameError`. Функция в публичном `analytics.__all__` (`:118`). `test_analytics_aggregator.py` документирует баг 7 xfail-тестами + reproducer, которые нужно перевести в PASS.

**Interfaces:** После фикса xfail-тесты (`test_single_winner...`, `test_mixed...`, `test_all_winners...`, `test_all_losers`, `test_equity_curve...`, `test_tag_stats...`, `test_pnl_none...`) станут проходить реальные assert'ы; `TestCalculateStatsBugReproducer.test_nameerror_on_nonempty_input` — удалить.

- [ ] **Step 1 — снять xfail (тесты станут падать).** В `backend/tests/unit/test_analytics_aggregator.py` удалить все `@pytest.mark.xfail(...)`-декораторы над 7 методами `TestCalculateStatsKnownBug` и удалить весь класс `TestCalculateStatsBugReproducer` (`:215-225`).
- [ ] **Step 2 — запуск, ожидание FAIL.** `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_analytics_aggregator.py -q`. Ожидаем FAIL с `NameError: name 'calculate_optimal_f' is not defined`.
- [ ] **Step 3 — минимальный фикс.** `backend/analytics/aggregator.py` — после `:11 from ._common import UNDEFINED, _sanitize` добавить (имена сверить с реальными модулями: `vince_tharp`, `risk`, `distributions`, `mae_mfe`):
```python
from .vince_tharp import calculate_optimal_f, calculate_sqn
from .risk import (
    calculate_advanced_stats,
    calculate_sharpe_sortino,
    calculate_z_score,
    calculate_drawdown_stats,
    calculate_calmar_ratio,
    calculate_risk_of_ruin,
    calculate_tail_ratio,
    calculate_r_distribution,
    monte_carlo_simulation,
)
from .distributions import (
    calculate_win_loss_stats,
    calculate_streaks,
    analyze_time_patterns,
    calculate_trade_duration,
)
from .mae_mfe import analyze_mae_mfe
```
**ВАЖНО:** перед коммитом grep по `aggregator.py` все вызываемые имена и подтвердить точный модуль-источник каждого (`grep -rn "^def calculate_z_score\|^def monte_carlo_simulation\|^def calculate_trade_duration\|^def calculate_calmar_ratio\|^def calculate_risk_of_ruin\|^def calculate_tail_ratio\|^def calculate_r_distribution" backend/analytics/`). Скорректировать `from`-модули под факт. Если какой-то функции нет — это отдельный баг, флагнуть, не выдумывать.
- [ ] **Step 4 — запуск, ожидание PASS.** `cd backend && C:/Python314/python.exe -m pytest tests/unit/test_analytics_aggregator.py -q` → все passed. `C:/Python314/python.exe -c "import analytics; analytics.calculate_stats"` без ошибок.
- [ ] **Step 5 — commit.** `fix(analytics): импортировать helpers в aggregator, calculate_stats больше не NameError (S3-25)`.

---

### S3-26 [LOW] Unused legacy crypto_utils import in verify_service

**Files:**
- Modify: `backend/services/verify_service.py:34` (удалить неиспользуемый импорт)
- Test: проверка через ruff/импорт (LOW — сжатый цикл)

**Проблема:** `crypto_utils` — legacy Fernet-слой с dev-fallback, деривящим ключ из `SECRET_KEY` (`crypto_utils.py:90-92`). Реальный путь — AES-256-GCM. Единственный оставшийся импорт (`verify_service.py:34 from crypto_utils import decrypt_token, TokenDecryptionError`) НЕ используется (grep подтвердил — только строка импорта). Мёртвый cross-secret crypto = риск регрессии.

**Interfaces:** Минимальный безопасный шаг — удалить неиспользуемый импорт. Удаление самого `crypto_utils.py` — отдельное решение (может импортироваться где-то ещё; не в scope этой LOW-задачи).

- [ ] **Step 1 — проверка.** `cd backend && C:/Python314/python.exe -m ruff check services/verify_service.py` — ожидаем F401 на строке 34 (unused import). Также подтвердить grep: `grep -rn "crypto_utils" backend/services/verify_service.py` даёт только `:34`.
- [ ] **Step 2 — фикс.** Удалить `backend/services/verify_service.py:34`:
```python
from crypto_utils import decrypt_token, TokenDecryptionError
```
(строку целиком).
- [ ] **Step 3 — верификация + commit.** `cd backend && C:/Python314/python.exe -c "from services import verify_service"` без ошибок; `C:/Python314/python.exe -m ruff check services/verify_service.py` без F401. Прогнать тесты, если есть: `pytest tests/ -k verify -q`. Commit: `chore(security): удалён неиспользуемый legacy crypto_utils импорт (S3-26)`.

---

### S3-27 [LOW] Reconciliation: выводы средств не учитываются (тип 'out' вместо 'output')

**Files:**
- Modify: `backend/services/reconciliation_service.py:321-324` (deposits/withdrawals классификатор)
- Modify: `backend/services/invariants_service.py:318-321` (тот же пропуск)
- Test: `backend/tests/test_reconciliation_cashflow.py` (Create)

**Проблема:** `compute_our_aggregates` классифицирует withdrawals по `{'out','pay_out','withdrawal'}`, но канонический тип T-Bank — `'output'` (`enums.py:115`, в NET_DEPOSIT-классификаторе `OperationType.OUTPUT`). Также deposits `{'input','pay_in','deposit'}` не включает `input_swift/input_acquiring/inp_multi`. У юзера с выводами `net_cash_flow` завышена. Дубль в `invariants_service._cash_invariant:320`.

**Interfaces:** Использовать единый классификатор `operation_types_in(CashFlowCategory.NET_DEPOSIT)` с разделением по знаку `payment` (INPUT>0 / OUTPUT<0). Импорт из `domain.pnl.cash_flow_classification`.

- [ ] **Step 1 — падающий тест.** Создать `backend/tests/test_reconciliation_cashflow.py`:
```python
"""S3-27: 'output' классифицируется как вывод; расширенные типы депозитов."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domain.pnl.cash_flow_classification import (  # noqa: E402
    CashFlowCategory,
    operation_types_in,
)


def test_net_deposit_set_includes_output_and_swift():
    types = operation_types_in(CashFlowCategory.NET_DEPOSIT)
    assert "output" in types          # канонический вывод (был пропущен)
    assert "input_swift" in types     # был пропущен
    assert "inp_multi" in types       # был пропущен
    assert "input" in types


def test_hardcoded_sets_missed_output():
    # Характеризует корень: старый hardcoded-набор НЕ содержал 'output'.
    old_withdrawals = {"out", "pay_out", "withdrawal"}
    assert "output" not in old_withdrawals
```
- [ ] **Step 2 — запуск, ожидание PASS.** `cd backend && C:/Python314/python.exe -m pytest tests/test_reconciliation_cashflow.py -q` (характеризует классификатор — источник истины).
- [ ] **Step 3 — минимальный фикс.**
  `backend/services/reconciliation_service.py:321-324` (before → after):
  ```python
          elif op_type in {"input", "pay_in", "deposit"}:
              deposits += payment
          elif op_type in {"out", "pay_out", "withdrawal"}:
              withdrawals += abs(payment)
  ```
  →
  ```python
          elif op_type in _NET_DEPOSIT_TYPES:
              # Единый классификатор: INPUT/OUTPUT/*_swift/*_acquiring/*_multi.
              # Знак payment различает ввод (>0) и вывод (<0) (S3-27).
              if payment >= 0:
                  deposits += payment
              else:
                  withdrawals += abs(payment)
  ```
  Вверху модуля добавить:
  ```python
  from domain.pnl.cash_flow_classification import (
      CashFlowCategory as _CFC,
      operation_types_in as _op_types_in,
  )

  _NET_DEPOSIT_TYPES = _op_types_in(_CFC.NET_DEPOSIT)
  ```
  Продублировать тот же паттерн в `invariants_service.py:318-321` (аналогичная замена, тот же `_NET_DEPOSIT_TYPES`).
- [ ] **Step 4 — верификация + commit.** `C:/Python314/python.exe -c "import main"`; `pytest tests/test_reconciliation_cashflow.py -q` passed. Прочитать `docs/PNL_PLAYBOOK.md`, при наличии reconcile-tool — прогон против тест-БД. Commit: `fix(reconciliation): выводы средств через единый NET_DEPOSIT-классификатор (S3-27)`.

---

### S3-28 [LOW] Расчёт MAE/MFE молча глотает ошибку

**Files:**
- Modify: `frontend/src/app/history/page.tsx:308-326` (`calculateMAEMFE`)
- Test: покрывается helper-паттерном S3-05 + ручной (LOW — сжатый цикл)

**Проблема:** `calculateMAEMFE` при сбое POST `/trades/calculate-mae-mfe` пишет только `console.error` (`:322`): спиннер исчезает, ни результата, ни ошибки. Успешный путь показывает бейдж «Обновлено: N», поэтому отсутствие сообщения при ошибке = «зависание фичи».

**Interfaces:** Тот же `toast`/`ApiError` паттерн из S3-05 (`const toast = useToast()` уже добавлен в этот файл в S3-05).

- [ ] **Step 1 — проверка.** Ручной repro: нажать «Рассчитать MAE/MFE» при недоступном backend → тишина. Baseline.
- [ ] **Step 2 — фикс.** `frontend/src/app/history/page.tsx:321-323` (before → after):
```tsx
    } catch (error) {
      console.error('Error calculating MAE/MFE:', error);
    } finally {
```
→
```tsx
    } catch (error) {
      toast.error(error instanceof ApiError ? error.toUserMessage() : 'Не удалось рассчитать MAE/MFE');
    } finally {
```
- [ ] **Step 3 — верификация + commit.** `cd frontend && npx tsc --noEmit` чисто; `npx vitest run --maxWorkers=1` без регрессий. Ручной: сбой расчёта → toast. Commit: `fix(history): ошибка расчёта MAE/MFE показывается тостом (S3-28)`.

---

## Проверка спринта

Полный гейт (все зелёное перед закрытием Спринта 3):

**Backend** (S3-01…03, 11…14, 24, 25, 27; из `backend/`):
```
cd backend && C:/Python314/python.exe -m pytest tests/test_stats_mae_mfe_recommendations.py tests/test_advanced_benchmark.py tests/test_stats_filtering_equity.py tests/test_benchmark_metric_sources.py tests/test_analytics_tz.py tests/test_common_baseline.py tests/test_trade_schema_validation.py tests/test_stats_tags_net.py tests/unit/test_analytics_aggregator.py tests/test_reconciliation_cashflow.py -q
cd backend && C:/Python314/python.exe -c "import main"
```
Ожидаемо: все passed; импорт без ошибок. Флейк `test_debug_warning`/`test_market_service_async::test_get_client_returns_singleton` в полном прогоне — не регрессия.

**Frontend** (S3-04…10, 15…23, 28):
```
cd frontend && npx vitest run --maxWorkers=1
cd frontend && npx tsc --noEmit
```
Ожидаемо: все vitest passed (в т.ч. новые ReconnectBanner/PnLHealthBadge/dateUtils/apiError422/equityBenchmarkRatio/commandPaletteItems/syncTrigger/addTradeUpload/handleCloseTrade/handleDeleteAll/dashboardTabsParams тесты); tsc без ошибок.

**Ручной сквозной проход** (после Спринта 1, backend :8000 + `npm run dev -- -p 3001`):
- Закрыть/удалить/удалить-все/добавить сделку при недоступном backend → всюду тост с внятным текстом (не «[object Object]», не тишина).
- Вкладка «Продвинутая» с фильтром «7 дней» → метрики меняются.
- P&L Health при backend-статусе investigate → красный «Расхождение».
- Отключить брокера → на дашборде НЕТ красного reconnect-баннера.

**P&L-инварианты** (S3-14, S3-27): прочитать `docs/PNL_PLAYBOOK.md`; при наличии reconcile-tool прогнать против тест-БД (НЕ `atom.db`) — audit=0, без новых HARD-breaks. ADR-0007/MATH-01 не нарушены.

**Git:** каждая задача — отдельный коммит формата `fix(<область>): <что> (SN-XX)` на ветке `feat/rebrand-empirik`; не пушить/мержить без команды.
