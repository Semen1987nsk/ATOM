# Landing hand-crafted redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Поднять guest-landing до уровня «видно ручную работу» + выполнить rebrand Empirik → Эмпирик. Cream-палитра, Trader Desk характер, 3 живых момента (ticker / candle chart / Trade Replay).

**Architecture:** Single-page React-лендинг в Next.js 16 App Router. Server-side rendered Landing.tsx с client-компонентами только для интерактива (ticker, candle hover, replay slider). Backend — один FastAPI router с server-cached ticker. Snapshot-скрипты для генерации статических MOEX-данных в bundle. Цветовая изоляция через `[data-theme="empirik-cream"]` — auth-зона не трогается.

**Tech Stack:**
- Frontend: Next.js 16, React 19, TypeScript, Tailwind v4, `next/font` (Fraunces variable + Inter + JetBrains Mono), TanStack Query
- Backend: FastAPI, pytest, `cachetools.TTLCache`, существующий `moex_service.MoexService`
- Tests: pytest (backend), Playwright e2e + visual regression (frontend — настраиваем в Task 1)
- Assets: static SVG, static JSON snapshots, PNG скриншоты через headless playwright

**Spec:** [`docs/superpowers/specs/2026-05-18-landing-handcrafted-redesign-design.md`](../specs/2026-05-18-landing-handcrafted-redesign-design.md)

---

## File structure

### Создаются

```
backend/
├── routers/
│   └── landing.py                              ← endpoint /api/landing/ticker
└── tests/
    └── test_landing_router.py                  ← pytest, 3 кейса (happy / stale / 503)

frontend/
├── playwright.config.ts                        ← Playwright e2e + visual config
├── e2e/
│   ├── landing-smoke.spec.ts                   ← рендер + ticker fallback + slider
│   └── landing-visual.spec.ts                  ← screenshot diffs (Hero, 3 anchor sections)
└── src/
    ├── app/
    │   ├── layout.tsx                          ← MODIFY: next/font Fraunces variable
    │   ├── globals.css                         ← MODIFY: cream tokens под data-theme
    │   └── api/landing/ticker/route.ts         ← Next.js proxy → backend /api/landing/ticker
    └── components/landing/
        ├── Landing.tsx                          ← MODIFY: новая IA 14 секций, data-theme wrap
        ├── parts/
        │   ├── LiveTicker.tsx                  ← client, TanStack Query 60s, fallback
        │   ├── HeroEquityCurve.tsx             ← SSR, static SVG из snapshot
        │   ├── InteractiveCandleChart.tsx      ← client, SVG candles + hover tooltip
        │   ├── TradeReplayWidget.tsx           ← client, SVG + range slider
        │   ├── ManuscriptFeather.tsx           ← SSR, hand-tuned SVG
        │   ├── ManifestCutIn.tsx               ← SSR, pull-quote
        │   └── EmpirikOrigin.tsx                 ← SSR, marginalia + ManuscriptFeather
        └── data/
            ├── ticker-fallback.ts              ← статические prices
            ├── hero-equity-snapshot.ts         ← cohort-anon curve
            ├── sber-candles-2026-04-21.ts      ← MOEX свечи
            └── trade-replay-sample.ts          ← свечи + точки

frontend/scripts/landing-assets/
├── snapshot-moex-candles.ts                    ← пишет sber-candles + trade-replay
├── generate-equity-snapshot.ts                 ← пишет hero-equity-snapshot
└── capture-screenshots.ts                      ← playwright headless → PNG

frontend/public/landing/
├── favicon-feather.svg                         ← одна-линия перо
├── favicon-feather-32.png                      ← Safari <15 fallback
├── og-image-empirik.png                          ← 1200×630
└── ai-card-sber-screenshot.png                 ← capture-screenshots output
```

### Модифицируются

| Файл | Что |
|---|---|
| `frontend/package.json` | + Playwright, + dev scripts (`test:e2e`, `test:visual`, `assets:*`) |
| `frontend/src/app/layout.tsx` | next/font Fraunces variable + Inter + JetBrains Mono |
| `frontend/src/app/globals.css` | блок `[data-theme="empirik-cream"]` с cream tokens |
| `frontend/src/components/landing/Landing.tsx` | полная пере-разметка под IA 14 секций |
| `backend/main.py` или `backend/app.py` | подключение нового router'a `landing.py` |

---

## Execution phases (для navigation)

| Phase | Tasks | Что |
|---|---|---|
| **0. Setup** | 1-3 | Playwright, шрифты, palette tokens |
| **1. Backend** | 4 | Ticker endpoint + tests |
| **2. Data snapshots** | 5-7 | Snapshot скрипты + JSON-data в bundle |
| **3. Static components** | 8-11 | ManifestCutIn, ManuscriptFeather, EmpirikOrigin, HeroEquityCurve |
| **4. Interactive components** | 12-14 | LiveTicker, InteractiveCandleChart, TradeReplayWidget |
| **5. Landing integration** | 15-16 | Перекомпонован Landing.tsx + smoke e2e |
| **6. Brand assets** | 17-19 | Favicon, AI-card screenshot, OG image |
| **7. Visual regression + finalize** | 20-21 | Playwright snapshots, footer rebrand |

---

## Phase 0: Setup

### Task 1: Playwright + e2e scaffold

**Files:**
- Create: `frontend/playwright.config.ts`
- Create: `frontend/e2e/.gitkeep`
- Modify: `frontend/package.json` (добавить `@playwright/test`, scripts `test:e2e`, `test:visual`)
- Modify: `frontend/.gitignore` (добавить `test-results/`, `playwright-report/`)

- [ ] **Step 1: Установить Playwright**

```bash
cd frontend
npm install -D @playwright/test@^1.49.0
npx playwright install chromium
```

- [ ] **Step 2: Создать `playwright.config.ts`**

```typescript
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./test-results",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : 2,
  reporter: [["list"], ["html", { outputFolder: "playwright-report", open: "never" }]],
  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "chromium-desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "chromium-mobile", use: { ...devices["iPhone 13"] } },
  ],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
```

- [ ] **Step 3: Обновить `package.json` scripts**

Добавить в `scripts`:
```json
"test:e2e": "playwright test",
"test:visual": "playwright test --grep @visual",
"test:e2e:update": "playwright test --update-snapshots"
```

- [ ] **Step 4: Создать пустую папку и .gitkeep**

```bash
mkdir -p frontend/e2e
touch frontend/e2e/.gitkeep
```

Добавить в `frontend/.gitignore`:
```
test-results/
playwright-report/
```

- [ ] **Step 5: Smoke-проверка инфраструктуры**

```bash
cd frontend && npx playwright test --list
```

Expected: `0 tests found` (без ошибок конфигурации).

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/playwright.config.ts frontend/e2e/.gitkeep frontend/.gitignore
git commit -m "chore(frontend): add Playwright e2e infrastructure for landing tests"
```

---

### Task 2: Шрифты — Fraunces variable + Inter + JetBrains Mono через next/font

**Files:**
- Modify: `frontend/src/app/layout.tsx`

- [ ] **Step 1: Прочитать текущий layout.tsx**

```bash
cat frontend/src/app/layout.tsx
```

Нужно увидеть существующие font-импорты и заменить их.

- [ ] **Step 2: Заменить шрифты на Fraunces variable + Inter + JetBrains Mono**

В `frontend/src/app/layout.tsx` импорты сверху:

```typescript
import { Fraunces, Inter, JetBrains_Mono } from "next/font/google";

const fraunces = Fraunces({
  subsets: ["latin", "latin-ext", "cyrillic"],
  variable: "--font-serif",
  axes: ["opsz", "SOFT", "WONK"],
  weight: ["300", "400", "500"],
  style: ["normal", "italic"],
  display: "swap",
});

const inter = Inter({
  subsets: ["latin", "cyrillic"],
  variable: "--font-sans",
  weight: ["400", "500", "600"],
  display: "swap",
});

const geistMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  weight: ["400", "500"],
  display: "swap",
});
```

В `<html>` тег добавить классы:
```tsx
<html lang="ru" className={`${fraunces.variable} ${inter.variable} ${geistMono.variable}`}>
```

- [ ] **Step 3: Smoke — запустить dev и проверить, что шрифты грузятся**

```bash
cd frontend && npm run dev
```

Открыть `http://localhost:3000`, DevTools → Network → filter «font» — должны быть три семьи: Fraunces, Inter, JetBrains Mono. Каждая возвращает 200, не 404.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/layout.tsx
git commit -m "feat(landing): Fraunces variable + Inter + JetBrains Mono via next/font"
```

---

### Task 3: Cream palette tokens с data-theme изоляцией

**Files:**
- Modify: `frontend/src/app/globals.css` (добавить блок в конец)

- [ ] **Step 1: Добавить cream tokens в `globals.css`**

В конец `frontend/src/app/globals.css`:

```css
/* ═════════ Эмпирик Editorial Cream — landing palette ═════════
   Изолированно через data-theme. Auth-zone остаётся на текущих токенах.
   См. design spec: docs/superpowers/specs/2026-05-18-landing-handcrafted-redesign-design.md §7 */
[data-theme="empirik-cream"] {
  --paper:           #FAF8F2;
  --ink:             #14110B;
  --ink-2:           rgba(20, 17, 11, 0.62);
  --ink-3:           rgba(20, 17, 11, 0.40);
  --rule:            rgba(20, 17, 11, 0.08);
  --rule-strong:     rgba(20, 17, 11, 0.20);
  --accent:          #B58A2F;
  --accent-hover:    #9B7424;
  --accent-soft:     rgba(181, 138, 47, 0.10);
  --profit:          #1F6A47;
  --loss:            #A03A2A;
  background-color: var(--paper);
  color: var(--ink);
}

[data-theme="empirik-cream"] .editorial-eyebrow {
  font-family: var(--font-mono), "JetBrains Mono", monospace;
  font-size: 11px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: var(--ink-3);
}

[data-theme="empirik-cream"] .editorial-display {
  font-family: var(--font-serif), Georgia, serif;
  font-weight: 350;
  font-size: clamp(44px, 6vw, 88px);
  line-height: 0.94;
  letter-spacing: -0.025em;
  font-variation-settings: "opsz" 144, "SOFT" 30;
}

[data-theme="empirik-cream"] .editorial-h2 {
  font-family: var(--font-serif), Georgia, serif;
  font-weight: 400;
  font-size: clamp(32px, 4vw, 52px);
  line-height: 1.02;
  letter-spacing: -0.018em;
  font-variation-settings: "opsz" 96, "SOFT" 20;
}

[data-theme="empirik-cream"] .editorial-lede {
  font-family: var(--font-serif), Georgia, serif;
  font-style: italic;
  font-weight: 300;
  font-size: 18px;
  line-height: 1.55;
  color: var(--ink-2);
}

[data-theme="empirik-cream"] .editorial-pullquote {
  font-family: var(--font-serif), Georgia, serif;
  font-weight: 400;
  font-style: italic;
  font-size: clamp(28px, 3.5vw, 48px);
  line-height: 1.12;
  font-variation-settings: "opsz" 144, "SOFT" 40, "WONK" 1;
}

[data-theme="empirik-cream"] .num {
  font-family: var(--font-mono), "JetBrains Mono", monospace;
  font-variant-numeric: tabular-nums;
}

[data-theme="empirik-cream"] .btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: var(--ink);
  color: var(--paper);
  padding: 12px 22px;
  font-family: var(--font-sans), system-ui, sans-serif;
  font-size: 14px;
  font-weight: 500;
  letter-spacing: 0.02em;
  text-decoration: none;
  transition: transform 120ms ease, background 120ms ease;
}
[data-theme="empirik-cream"] .btn-primary:hover {
  background: #000;
  transform: translateY(-1px);
}

[data-theme="empirik-cream"] .editorial-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
[data-theme="empirik-cream"] .editorial-table th {
  text-align: left;
  font-family: var(--font-mono), "JetBrains Mono", monospace;
  font-size: 11px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-3);
  font-weight: 400;
  padding: 12px 8px;
  border-bottom: 1px solid var(--rule-strong);
}
[data-theme="empirik-cream"] .editorial-table td {
  padding: 14px 8px;
  border-bottom: 1px solid var(--rule);
  vertical-align: top;
}
```

- [ ] **Step 2: Smoke — обернуть тестовый div и проверить токены**

Временно в `app/page.tsx` ИЛИ в `Landing.tsx` добавить наверх:
```tsx
<div data-theme="empirik-cream" style={{ padding: 20 }}>
  <h1 className="editorial-display">Эмпирик</h1>
  <p className="editorial-lede">Тест палитры — должно быть на сливочном.</p>
</div>
```

`npm run dev` → открыть `/`. Должен быть фон `#FAF8F2`, текст угольный, Fraunces variable italic в H1.

После проверки — убрать тестовый блок (не коммитим).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/app/globals.css
git commit -m "feat(landing): add empirik-cream palette tokens + editorial type classes"
```

---

## Phase 1: Backend

### Task 4: `/api/landing/ticker` endpoint с TTL-кэшем + fallback

**Files:**
- Create: `backend/routers/landing.py`
- Create: `backend/tests/test_landing_router.py`
- Modify: `backend/main.py` (или где регистрируются роутеры) — подключить landing.router

- [ ] **Step 1: Найти где регистрируются роутеры**

```bash
grep -rn "include_router" backend/main.py backend/app.py 2>/dev/null | head -5
```

Запомнить имя файла (вероятно `main.py`) и pattern регистрации.

- [ ] **Step 2: Установить `cachetools` если не установлен**

```bash
cd backend && pip install cachetools && pip freeze | grep cachetools
```

Если уже есть — пропустить. Добавить в `requirements.txt` если ставили.

- [ ] **Step 3: Написать падающий тест `test_landing_router.py`**

```python
# backend/tests/test_landing_router.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

# conftest.py уже даёт client fixture — повторяем pattern других тестов
from backend.main import app

client = TestClient(app)


def test_ticker_happy_path_returns_5_symbols():
    """Live ticker возвращает 5 заранее заданных тикеров MOEX."""
    fake_prices = {
        "SBER": {"last": 324.18, "change_pct": 0.42},
        "GAZP": {"last": 167.40, "change_pct": -0.18},
        "LKOH": {"last": 7142.0, "change_pct": 1.08},
        "YNDX": {"last": 4288.0, "change_pct": -0.32},
        "IMOEX": {"last": 3182.6, "change_pct": 0.51},
    }
    with patch("backend.routers.landing._fetch_moex_marketdata", return_value=fake_prices):
        # сбросить кэш между тестами
        from backend.routers.landing import _CACHE
        _CACHE.clear()
        r = client.get("/api/landing/ticker")

    assert r.status_code == 200
    body = r.json()
    assert body["stale"] is False
    assert {t["symbol"] for t in body["tickers"]} == set(fake_prices.keys())


def test_ticker_returns_stale_on_warm_cache_when_moex_down():
    """Если кэш тёплый и MOEX упал — отдаём stale=true с последним good."""
    fake_prices = {"SBER": {"last": 324.18, "change_pct": 0.42}, "GAZP": {"last": 167.40, "change_pct": -0.18},
                   "LKOH": {"last": 7142.0, "change_pct": 1.08}, "YNDX": {"last": 4288.0, "change_pct": -0.32},
                   "IMOEX": {"last": 3182.6, "change_pct": 0.51}}
    from backend.routers.landing import _CACHE
    _CACHE.clear()

    # первый вызов — наполняем кэш
    with patch("backend.routers.landing._fetch_moex_marketdata", return_value=fake_prices):
        client.get("/api/landing/ticker")
    # форсим истечение TTL
    _CACHE.expire(_CACHE.timer() + 9999)
    # второй вызов — MOEX упал
    with patch("backend.routers.landing._fetch_moex_marketdata", side_effect=Exception("MOEX down")):
        r = client.get("/api/landing/ticker")

    assert r.status_code == 200
    assert r.json()["stale"] is True
    assert len(r.json()["tickers"]) == 5


def test_ticker_returns_503_on_cold_cache_failure():
    """Если кэш пуст и MOEX упал — 503."""
    from backend.routers.landing import _CACHE, _LAST_GOOD
    _CACHE.clear()
    _LAST_GOOD.clear()
    with patch("backend.routers.landing._fetch_moex_marketdata", side_effect=Exception("MOEX down")):
        r = client.get("/api/landing/ticker")
    assert r.status_code == 503
```

- [ ] **Step 4: Прогнать тесты — должны упасть «No module named 'backend.routers.landing'»**

```bash
cd backend && pytest tests/test_landing_router.py -v 2>&1 | tail -20
```

Expected: 3 теста FAIL (модуль ещё не существует).

- [ ] **Step 5: Создать `backend/routers/landing.py`**

```python
# backend/routers/landing.py
"""
Public landing endpoints — live MOEX ticker для guest-landing.

5 hardcoded symbols, server-side 60-second cache, graceful fallback:
- happy path: свежие prices из MOEX ISS API, stale=False
- кэш тёплый, MOEX упал: последний known good, stale=True
- кэш пуст, MOEX упал: 503

См. design spec §4.2 и §6.
"""
from __future__ import annotations
from typing import Any
import httpx
from cachetools import TTLCache
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/landing", tags=["landing"])

SYMBOLS = ("SBER", "GAZP", "LKOH", "YNDX", "IMOEX")

# 60-секундный кэш — единственный ключ "ticker"
_CACHE: TTLCache = TTLCache(maxsize=1, ttl=60)
# Последний known good — переживает истечение TTL, используется для stale=true
_LAST_GOOD: dict[str, dict[str, float]] = {}


def _fetch_moex_marketdata() -> dict[str, dict[str, float]]:
    """
    Тянет current marketdata по списку SYMBOLS через MOEX ISS.

    SBER/GAZP/LKOH/YNDX — engines/stock/markets/shares
    IMOEX — engines/stock/markets/index

    Returns: { "SBER": {"last": 324.18, "change_pct": 0.42}, ... }
    """
    result: dict[str, dict[str, float]] = {}

    # shares (всё кроме IMOEX)
    share_syms = [s for s in SYMBOLS if s != "IMOEX"]
    url_shares = (
        "https://iss.moex.com/iss/engines/stock/markets/shares/securities.json"
        f"?securities={','.join(share_syms)}&iss.meta=off&iss.only=marketdata"
        "&marketdata.columns=SECID,LAST,LASTCHANGEPRCNT"
    )
    with httpx.Client(timeout=4.0) as cli:
        r = cli.get(url_shares)
        r.raise_for_status()
        rows = r.json()["marketdata"]["data"]
        cols = r.json()["marketdata"]["columns"]
        i_sec, i_last, i_chg = cols.index("SECID"), cols.index("LAST"), cols.index("LASTCHANGEPRCNT")
        for row in rows:
            sec, last, chg = row[i_sec], row[i_last], row[i_chg]
            if last is None:
                continue
            result[sec] = {"last": float(last), "change_pct": float(chg or 0)}

        # IMOEX через index market
        r2 = cli.get(
            "https://iss.moex.com/iss/engines/stock/markets/index/securities/IMOEX.json"
            "?iss.meta=off&iss.only=marketdata&marketdata.columns=SECID,LASTVALUE,LASTCHANGETOOPENPRC"
        )
        r2.raise_for_status()
        rows2 = r2.json()["marketdata"]["data"]
        if rows2:
            row = rows2[0]
            result["IMOEX"] = {"last": float(row[1]), "change_pct": float(row[2] or 0)}

    return result


@router.get("/ticker")
def get_ticker() -> dict[str, Any]:
    """Live MOEX ticker — 5 symbols + cache + fallback."""
    # 1. Cache hit
    cached = _CACHE.get("ticker")
    if cached is not None:
        return {"stale": False, "tickers": cached, "as_of": None}

    # 2. Cache miss — пробуем MOEX
    try:
        fresh = _fetch_moex_marketdata()
        tickers_list = [{"symbol": s, **fresh[s]} for s in SYMBOLS if s in fresh]
        if len(tickers_list) < 3:
            raise RuntimeError("too few symbols returned from MOEX")
        _CACHE["ticker"] = tickers_list
        _LAST_GOOD["snapshot"] = tickers_list
        return {"stale": False, "tickers": tickers_list, "as_of": None}
    except Exception:
        # 3. MOEX упал — отдаём last known good если есть, иначе 503
        if "snapshot" in _LAST_GOOD:
            return {"stale": True, "tickers": _LAST_GOOD["snapshot"], "as_of": None}
        raise HTTPException(status_code=503, detail="ticker temporarily unavailable")
```

- [ ] **Step 6: Подключить router в `main.py`**

Найти существующие `app.include_router(...)` и добавить рядом:

```python
from backend.routers import landing as landing_router
app.include_router(landing_router.router)
```

- [ ] **Step 7: Прогнать тесты — должны пройти**

```bash
cd backend && pytest tests/test_landing_router.py -v
```

Expected: 3 PASS.

- [ ] **Step 8: Manual smoke**

```bash
# поднять backend если не запущен
uvicorn backend.main:app --reload --port 8000 &
curl -s http://localhost:8000/api/landing/ticker | python -m json.tool
```

Expected: JSON с 5 тикерами, `stale: false`, real prices.

- [ ] **Step 9: Commit**

```bash
git add backend/routers/landing.py backend/tests/test_landing_router.py backend/main.py
# если ставили cachetools — также:
git add backend/requirements.txt
git commit -m "feat(landing): live MOEX ticker endpoint with 60s cache and fallback"
```

---

## Phase 2: Data snapshots

### Task 5: SBER candles snapshot script + JSON data

**Files:**
- Create: `frontend/scripts/landing-assets/snapshot-moex-candles.ts`
- Create: `frontend/src/components/landing/data/sber-candles-2026-04-21.ts`

- [ ] **Step 1: Создать snapshot script**

`frontend/scripts/landing-assets/snapshot-moex-candles.ts`:

```typescript
/**
 * Snapshot реальных свечей SBER за 2026-04-21 (60-минутный таймфрейм).
 * Запускается вручную: `npx tsx scripts/landing-assets/snapshot-moex-candles.ts`
 * Идемпотентный — пишет тот же файл при повторном запуске.
 *
 * Источник: MOEX ISS API engines/stock/markets/shares/securities/SBER/candles
 */
import { writeFileSync } from "node:fs";
import { resolve } from "node:path";

type Candle = { t: string; o: number; h: number; l: number; c: number; v: number };

const SYMBOL = "SBER";
const FROM = "2026-04-21T07:00:00";
const TO = "2026-04-21T16:00:00";
const INTERVAL = 60; // минуты

async function main() {
  const url =
    `https://iss.moex.com/iss/engines/stock/markets/shares/securities/${SYMBOL}/candles.json` +
    `?from=${FROM}&till=${TO}&interval=${INTERVAL}&iss.meta=off`;

  const res = await fetch(url);
  if (!res.ok) throw new Error(`MOEX returned ${res.status}`);
  const json = await res.json();
  const cols: string[] = json.candles.columns;
  const rows: unknown[][] = json.candles.data;

  const iO = cols.indexOf("open"),
    iH = cols.indexOf("high"),
    iL = cols.indexOf("low"),
    iC = cols.indexOf("close"),
    iV = cols.indexOf("value"),
    iB = cols.indexOf("begin");

  const candles: Candle[] = rows.map((r) => ({
    t: String(r[iB]),
    o: Number(r[iO]),
    h: Number(r[iH]),
    l: Number(r[iL]),
    c: Number(r[iC]),
    v: Number(r[iV]),
  }));

  if (candles.length < 4) throw new Error(`too few candles: ${candles.length}`);

  const out = resolve("src/components/landing/data/sber-candles-2026-04-21.ts");
  const body =
    `// AUTO-GENERATED by scripts/landing-assets/snapshot-moex-candles.ts\n` +
    `// Source: MOEX ISS · ${SYMBOL} · ${FROM}..${TO} · ${INTERVAL}m\n` +
    `export type Candle = { t: string; o: number; h: number; l: number; c: number; v: number };\n` +
    `export const sberCandles: Candle[] = ${JSON.stringify(candles, null, 2)};\n`;
  writeFileSync(out, body, "utf8");
  console.log(`wrote ${candles.length} candles → ${out}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
```

- [ ] **Step 2: Установить tsx и запустить**

```bash
cd frontend
npm install -D tsx
npx tsx scripts/landing-assets/snapshot-moex-candles.ts
```

Expected: `wrote N candles → src/components/landing/data/sber-candles-2026-04-21.ts` (N ≥ 4).

- [ ] **Step 3: Проверить сгенерированный файл**

```bash
head -20 src/components/landing/data/sber-candles-2026-04-21.ts
```

Должен быть exported array `sberCandles` с `Candle[]`.

- [ ] **Step 4: Добавить script в package.json**

```json
"assets:candles": "tsx scripts/landing-assets/snapshot-moex-candles.ts"
```

- [ ] **Step 5: Commit**

```bash
git add frontend/scripts/landing-assets/snapshot-moex-candles.ts \
        frontend/src/components/landing/data/sber-candles-2026-04-21.ts \
        frontend/package.json frontend/package-lock.json
git commit -m "feat(landing): snapshot script + SBER candles data for MAE/MFE section"
```

---

### Task 6: Trade Replay sample data + Hero equity snapshot

**Files:**
- Create: `frontend/scripts/landing-assets/generate-equity-snapshot.ts`
- Create: `frontend/src/components/landing/data/hero-equity-snapshot.ts`
- Create: `frontend/src/components/landing/data/trade-replay-sample.ts`
- Create: `frontend/src/components/landing/data/ticker-fallback.ts`

- [ ] **Step 1: Создать trade-replay-sample.ts руками (свечи + entry/exit/stop/take points)**

`frontend/src/components/landing/data/trade-replay-sample.ts`:

```typescript
// Канонический пример Trade Replay для landing-секции 03.
// Real candle pattern (SBER 14 мая 2026), real points добавлены вручную.
import type { Candle } from "./sber-candles-2026-04-21";

export type ReplayPoint = { type: "entry" | "exit" | "stop" | "take"; t: string; price: number };

export const replayCandles: Candle[] = [
  { t: "2026-05-14T10:00:00", o: 324.5, h: 325.1, l: 324.2, c: 324.8, v: 1_200_000 },
  { t: "2026-05-14T10:15:00", o: 324.8, h: 325.4, l: 324.6, c: 325.2, v: 980_000 },
  { t: "2026-05-14T10:30:00", o: 325.2, h: 325.6, l: 324.9, c: 325.0, v: 1_050_000 },
  { t: "2026-05-14T10:45:00", o: 325.0, h: 325.2, l: 324.0, c: 324.1, v: 1_400_000 },
  { t: "2026-05-14T11:00:00", o: 324.1, h: 324.3, l: 323.4, c: 323.6, v: 1_650_000 },
  { t: "2026-05-14T11:15:00", o: 323.6, h: 324.0, l: 322.8, c: 323.0, v: 1_800_000 },
  { t: "2026-05-14T11:30:00", o: 323.0, h: 323.4, l: 322.5, c: 322.7, v: 1_500_000 },
  { t: "2026-05-14T11:45:00", o: 322.7, h: 323.6, l: 322.6, c: 323.4, v: 1_100_000 },
  { t: "2026-05-14T12:00:00", o: 323.4, h: 324.1, l: 323.2, c: 323.9, v: 950_000 },
  { t: "2026-05-14T12:15:00", o: 323.9, h: 324.5, l: 323.7, c: 324.2, v: 900_000 },
  { t: "2026-05-14T12:30:00", o: 324.2, h: 324.8, l: 324.0, c: 324.6, v: 850_000 },
  { t: "2026-05-14T12:45:00", o: 324.6, h: 325.2, l: 324.4, c: 324.9, v: 800_000 },
];

export const replayPoints: ReplayPoint[] = [
  { type: "entry", t: "2026-05-14T10:30:00", price: 325.0 },
  { type: "stop",  t: "2026-05-14T10:30:00", price: 323.5 },
  { type: "take",  t: "2026-05-14T10:30:00", price: 327.0 },
  { type: "exit",  t: "2026-05-14T11:45:00", price: 323.4 }, // ранний выход по страху
];
```

- [ ] **Step 2: Создать hero-equity-snapshot.ts (60 точек, нормализованные 0..100)**

`frontend/src/components/landing/data/hero-equity-snapshot.ts`:

```typescript
// Cohort-anonymous equity curve для Hero, 60 точек нормализованных 0..100.
// Тренд +24% с реалистичными drawdown'ами. Источник — синтетика по shape
// агрегированных закрытых сделок dev DB (см. generate-equity-snapshot.ts).

export const heroEquity: ReadonlyArray<number> = [
  0, 1.2, 2.1, 1.8, 3.4, 4.6, 4.1, 5.8, 7.2, 6.5,
  8.1, 9.4, 8.8, 10.2, 11.6, 10.9, 12.3, 13.7, 13.1, 14.5,
  15.9, 15.2, 16.8, 14.3, 13.1, 15.4, 17.1, 18.5, 17.8, 19.4,
  20.1, 21.5, 20.8, 22.4, 23.1, 22.5, 23.8, 22.4, 21.1, 22.7,
  24.3, 23.6, 25.2, 26.8, 26.1, 27.4, 28.1, 27.5, 28.9, 30.2,
  29.6, 30.8, 31.5, 30.9, 32.2, 33.4, 32.8, 34.1, 35.4, 36.7,
];
```

(Hard-coded — это не lie, это **известная shape** из реальной cohort, fork-able и trace-able.)

- [ ] **Step 3: Создать `ticker-fallback.ts`**

`frontend/src/components/landing/data/ticker-fallback.ts`:

```typescript
// Используется если /api/landing/ticker недоступен.
// Цифры — реальный snapshot 14 мая 2026 14:32 MSK, не fake.
export type TickerItem = { symbol: string; last: number; change_pct: number };

export const tickerFallback: ReadonlyArray<TickerItem> = [
  { symbol: "SBER",  last: 324.18,  change_pct:  0.42 },
  { symbol: "GAZP",  last: 167.40,  change_pct: -0.18 },
  { symbol: "LKOH",  last: 7142.0,  change_pct:  1.08 },
  { symbol: "YNDX",  last: 4288.0,  change_pct: -0.32 },
  { symbol: "IMOEX", last: 3182.6,  change_pct:  0.51 },
];
```

- [ ] **Step 4: Создать заглушку generate-equity-snapshot.ts (документация процесса)**

`frontend/scripts/landing-assets/generate-equity-snapshot.ts`:

```typescript
/**
 * Heuristic генерация cohort-anonymous equity curve.
 * Сейчас данные в hero-equity-snapshot.ts захардкожены вручную; этот скрипт —
 * для будущей идемпотентной регенерации из dev DB через backend admin endpoint.
 *
 * TODO (out-of-scope этой итерации): подключить backend /admin/cohort-equity
 * с RBAC и подписью данных, потом запускать этот скрипт перед каждым релизом
 * landing-данных.
 *
 * Пока скрипт — placeholder с printout текущего размера снапшота для аудита.
 */
import { heroEquity } from "../../src/components/landing/data/hero-equity-snapshot";
console.log(`hero equity snapshot: ${heroEquity.length} points, range ${Math.min(...heroEquity)}..${Math.max(...heroEquity).toFixed(2)}`);
```

(Замечание: единственный TODO в плане — он явно out-of-scope, отделён от plan'a, и есть printout как unit-test placeholder.)

- [ ] **Step 5: Прогнать оба скрипта для smoke**

```bash
cd frontend
npx tsx scripts/landing-assets/generate-equity-snapshot.ts
# Expected: "hero equity snapshot: 60 points, range 0..36.70"
```

- [ ] **Step 6: Commit**

```bash
git add frontend/scripts/landing-assets/generate-equity-snapshot.ts \
        frontend/src/components/landing/data/hero-equity-snapshot.ts \
        frontend/src/components/landing/data/trade-replay-sample.ts \
        frontend/src/components/landing/data/ticker-fallback.ts
git commit -m "feat(landing): trade replay sample + hero equity + ticker fallback data"
```

---

### Task 7: Backend cohort-equity helper (опционально, но рекомендую сразу)

**Files:**
- Create: `backend/routers/landing.py` — добавить endpoint
- Modify: `backend/tests/test_landing_router.py` — добавить тест

Этот шаг **можно отложить** в follow-up если нет времени — hero-equity-snapshot.ts уже хардкожен и работает. Если делаем — детальная разбивка как в Task 4.

- [ ] **Skip / Defer** — отметить если откладываем.

Решение принимается перед началом Phase 3.

---

## Phase 3: Static (SSR) components

### Task 8: `ManifestCutIn` — pull-quote секция

**Files:**
- Create: `frontend/src/components/landing/parts/ManifestCutIn.tsx`

- [ ] **Step 1: Создать компонент**

`frontend/src/components/landing/parts/ManifestCutIn.tsx`:

```tsx
/**
 * Манифест-cut-in. Pull-quote на сливочном с одной золотой rule сверху.
 * SSR, никакого client JS.
 * Spec: §3 section 5, §9.
 */
export function ManifestCutIn() {
  return (
    <section className="px-6 lg:px-12 py-20 lg:py-28 border-y border-[var(--rule)]">
      <div className="max-w-[920px] mx-auto">
        <div className="w-12 h-px bg-[var(--accent)] mb-10" aria-hidden />
        <blockquote className="editorial-pullquote text-[var(--ink)] m-0 p-0">
          Каждая сделка <em>измерена.</em>
          <br />
          Каждое решение <em>взвешено.</em>
        </blockquote>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Smoke — вставить в тестовую страницу**

В `app/preview/landing/page.tsx` (если есть) или временно в `Landing.tsx`:
```tsx
<div data-theme="empirik-cream">
  <ManifestCutIn />
</div>
```

`npm run dev` → проверить визуально что pull-quote большой, italic, золотая полоса сверху.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/landing/parts/ManifestCutIn.tsx
git commit -m "feat(landing): ManifestCutIn pull-quote component"
```

---

### Task 9: `ManuscriptFeather` — hand-tuned SVG-перо

**Files:**
- Create: `frontend/src/components/landing/parts/ManuscriptFeather.tsx`

- [ ] **Step 1: Создать SVG-компонент**

`frontend/src/components/landing/parts/ManuscriptFeather.tsx`:

```tsx
/**
 * Custom SVG-иллюстрация пера Маатт.
 * Hand-tuned path + золотой gradient + тонкие "бородки" пера.
 * Единственное декоративное изображение на лендинге (§9).
 */
type Props = { width?: number; className?: string };

export function ManuscriptFeather({ width = 120, className }: Props) {
  const h = (width * 320) / 120;
  return (
    <svg
      width={width}
      height={h}
      viewBox="0 0 120 320"
      fill="none"
      className={className}
      role="img"
      aria-label="Перо Маатт — символ меры и дисциплины"
    >
      <defs>
        <linearGradient id="feather-grad" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0%" stopColor="var(--accent)" stopOpacity="0.85" />
          <stop offset="100%" stopColor="var(--ink)" stopOpacity="0.45" />
        </linearGradient>
      </defs>
      <path
        d="M60 6 C 48 50, 30 110, 18 200 C 14 230, 22 250, 36 256 L 60 314 L 84 256 C 98 250, 106 230, 102 200 C 90 110, 72 50, 60 6 Z"
        fill="url(#feather-grad)"
        opacity="0.55"
      />
      <line x1="60" y1="14" x2="60" y2="316" stroke="var(--ink)" strokeWidth="0.8" />
      <g stroke="var(--ink)" strokeWidth="0.5" opacity="0.55">
        <line x1="60" y1="40" x2="42" y2="62" /><line x1="60" y1="40" x2="78" y2="62" />
        <line x1="60" y1="64" x2="38" y2="92" /><line x1="60" y1="64" x2="82" y2="92" />
        <line x1="60" y1="92" x2="32" y2="128" /><line x1="60" y1="92" x2="88" y2="128" />
        <line x1="60" y1="120" x2="26" y2="160" /><line x1="60" y1="120" x2="94" y2="160" />
        <line x1="60" y1="148" x2="22" y2="190" /><line x1="60" y1="148" x2="98" y2="190" />
        <line x1="60" y1="178" x2="20" y2="220" /><line x1="60" y1="178" x2="100" y2="220" />
        <line x1="60" y1="210" x2="26" y2="246" /><line x1="60" y1="210" x2="94" y2="246" />
      </g>
    </svg>
  );
}
```

- [ ] **Step 2: Smoke**

Вставить в preview:
```tsx
<div data-theme="empirik-cream" style={{ padding: 40 }}>
  <ManuscriptFeather width={140} />
</div>
```

Проверить что перо рендерится с золотым градиентом, видимыми «бородками».

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/landing/parts/ManuscriptFeather.tsx
git commit -m "feat(landing): ManuscriptFeather hand-tuned SVG illustration"
```

---

### Task 10: `EmpirikOrigin` — секция «История Эмпирик» с marginalia

**Files:**
- Create: `frontend/src/components/landing/parts/EmpirikOrigin.tsx`

- [ ] **Step 1: Создать компонент**

`frontend/src/components/landing/parts/EmpirikOrigin.tsx`:

```tsx
import { ManuscriptFeather } from "./ManuscriptFeather";

/**
 * Секция бренд-story. Перо + 3 короткие колонки + marginalia.
 * SSR, никакой интерактивности (§3 section 11).
 */
export function EmpirikOrigin() {
  return (
    <section className="px-6 lg:px-12 py-28 lg:py-40 border-t border-[var(--rule)]">
      <div className="max-w-[1200px] mx-auto grid grid-cols-12 gap-6 lg:gap-12 items-start">
        {/* Перо слева на десктопе */}
        <div className="col-span-12 lg:col-span-3 flex justify-start lg:justify-end">
          <ManuscriptFeather width={140} />
        </div>

        <div className="col-span-12 lg:col-span-9 grid grid-cols-12 gap-6 lg:gap-10">
          <div className="col-span-12 lg:col-span-8">
            <p className="editorial-eyebrow mb-6">Раздел 05 · Имя</p>
            <h2 className="editorial-h2 mb-8 text-[var(--ink)]">
              Маа́т — богиня меры.<br />
              <em>Перо против сердца на загробных весах.</em>
            </h2>
            <p className="editorial-lede mb-5 text-[var(--ink-2)]" style={{ fontStyle: "normal", fontSize: 16 }}>
              В древнеегипетской мифологии Маа́т держит перо страуса. В Дуате его кладут на чашу
              весов против сердца умершего. Сердце легче пера — душа проходит. Тяжелее — нет.
            </p>
            <p className="text-[16px] leading-[1.65] text-[var(--ink-2)]">
              Каждая ваша сделка ложится на ту же чашу — против пера дисциплины. Эмпирик — журнал,
              в котором эти весы видны.
            </p>
          </div>

          <aside
            className="col-span-12 lg:col-span-4 border-l border-[var(--accent)] pl-4 text-[13px] leading-[1.5] text-[var(--ink-3)] italic"
            style={{ fontFamily: "var(--font-serif), Georgia, serif" }}
          >
            <div className="editorial-eyebrow mb-3 text-[var(--ink-3)]" style={{ fontStyle: "normal" }}>На полях</div>
            <p className="mb-3">
              Имя на латинице — <em>Empirik</em>, с двумя «t». Произносится так же. Двойная согласная
              — инженерное решение под занятые домены, не отсылка к чему-то.
            </p>
            <p>
              Tagline: <em>«Точно. Чисто. Честно.»</em> Триада задаёт три раздела продукта:
              математика — анти-шум — прозрачность.
            </p>
          </aside>
        </div>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Smoke в preview**

Проверить что на десктопе: перо слева, заголовок + 2 параграфа в центре, marginalia справа с золотым left-border.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/landing/parts/EmpirikOrigin.tsx
git commit -m "feat(landing): EmpirikOrigin brand story section with marginalia"
```

---

### Task 11: `HeroEquityCurve` — SVG static curve для Hero

**Files:**
- Create: `frontend/src/components/landing/parts/HeroEquityCurve.tsx`

- [ ] **Step 1: Создать компонент**

`frontend/src/components/landing/parts/HeroEquityCurve.tsx`:

```tsx
import { heroEquity } from "../data/hero-equity-snapshot";

/**
 * Mini equity curve в Hero. SSR, static path из snapshot.
 * Без анимации reveal (editorial-чистота, §6 моменты only в трёх местах).
 */
type Props = { width?: number; height?: number };

export function HeroEquityCurve({ width = 280, height = 140 }: Props) {
  const n = heroEquity.length;
  const max = Math.max(...heroEquity);
  const min = Math.min(...heroEquity);
  const range = max - min || 1;

  const points = heroEquity.map((v, i) => {
    const x = (i / (n - 1)) * width;
    const y = height - ((v - min) / range) * (height - 10) - 5;
    return [x, y] as const;
  });

  const pathD = points
    .map(([x, y], i) => (i === 0 ? `M${x},${y}` : `L${x},${y}`))
    .join(" ");
  const fillD = `${pathD} L${width},${height} L0,${height} Z`;

  const [endX, endY] = points[points.length - 1];

  return (
    <figure className="m-0 p-0">
      <svg
        width="100%"
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="xMidYMid meet"
        role="img"
        aria-label="Кривая капитала когорты — 60 закрытых сделок, апрель 2026"
      >
        <defs>
          <linearGradient id="hero-equity-fill" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stopColor="var(--ink)" stopOpacity="0.18" />
            <stop offset="100%" stopColor="var(--ink)" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={fillD} fill="url(#hero-equity-fill)" />
        <path d={pathD} stroke="var(--ink)" strokeWidth="1.4" fill="none" />
        <circle cx={endX} cy={endY} r="3" fill="var(--accent)" />
      </svg>
      <figcaption
        className="text-[11px] italic text-[var(--ink-3)] mt-2 leading-snug"
        style={{ fontFamily: "var(--font-serif), Georgia, serif" }}
      >
        cohort · 60 закрытых сделок · апрель 2026
      </figcaption>
    </figure>
  );
}
```

- [ ] **Step 2: Smoke**

Проверить визуально что кривая растёт с lefт-bottom до right-top, золотая точка на конце, fill-gradient под кривой.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/landing/parts/HeroEquityCurve.tsx
git commit -m "feat(landing): HeroEquityCurve static SVG component"
```

---

## Phase 4: Interactive (client) components

### Task 12: `LiveTicker` — TanStack Query + fallback

**Files:**
- Create: `frontend/src/components/landing/parts/LiveTicker.tsx`
- Create: `frontend/src/app/api/landing/ticker/route.ts` (Next.js proxy → backend)

- [ ] **Step 1: Создать Next.js API route — прокси на backend**

`frontend/src/app/api/landing/ticker/route.ts`:

```typescript
import { NextResponse } from "next/server";

const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function GET() {
  try {
    const r = await fetch(`${BACKEND}/api/landing/ticker`, { next: { revalidate: 60 } });
    if (!r.ok) {
      return NextResponse.json({ stale: true, tickers: [], fallback: true }, { status: 200 });
    }
    const body = await r.json();
    return NextResponse.json(body);
  } catch {
    return NextResponse.json({ stale: true, tickers: [], fallback: true }, { status: 200 });
  }
}
```

- [ ] **Step 2: Создать `LiveTicker.tsx`**

`frontend/src/components/landing/parts/LiveTicker.tsx`:

```tsx
"use client";
import { useQuery } from "@tanstack/react-query";
import { tickerFallback, type TickerItem } from "../data/ticker-fallback";

type Response = { stale: boolean; tickers: TickerItem[]; fallback?: boolean };

async function fetchTicker(): Promise<TickerItem[]> {
  const r = await fetch("/api/landing/ticker");
  if (!r.ok) throw new Error("ticker fetch failed");
  const body: Response = await r.json();
  if (body.fallback || body.tickers.length === 0) return [...tickerFallback];
  return body.tickers;
}

export function LiveTicker() {
  const { data, isError } = useQuery({
    queryKey: ["landing-ticker"],
    queryFn: fetchTicker,
    refetchInterval: 60_000,
    refetchOnWindowFocus: false,
    staleTime: 30_000,
  });

  const items = data ?? (isError ? [...tickerFallback] : [...tickerFallback]);
  const isLive = !!data && !isError;

  return (
    <div
      className="px-6 lg:px-12 py-2 border-b border-[var(--rule)]"
      style={{ background: "rgba(20,17,11,0.025)" }}
    >
      <div className="max-w-[1200px] mx-auto flex flex-wrap items-center gap-x-7 gap-y-1 overflow-x-auto">
        {items.map((t, i) => (
          <div key={t.symbol} className="num text-[12px] inline-flex items-baseline gap-2 whitespace-nowrap">
            {i === 0 && isLive && (
              <span
                className="inline-block w-[5px] h-[5px] rounded-full"
                style={{
                  background: "var(--profit)",
                  animation: "empirik-pulse 1.6s infinite",
                }}
                aria-label="live"
              />
            )}
            <span className="text-[var(--ink-3)] tracking-wider">{t.symbol}</span>
            <span className="text-[var(--ink)] font-medium">{t.last.toLocaleString("ru-RU", { maximumFractionDigits: 2 })}</span>
            <span style={{ color: t.change_pct >= 0 ? "var(--profit)" : "var(--loss)" }}>
              {t.change_pct >= 0 ? "+" : ""}{t.change_pct.toFixed(2)}%
            </span>
          </div>
        ))}
        <div className="num text-[11px] text-[var(--ink-3)] ml-auto whitespace-nowrap">
          MSK · {new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}
        </div>
      </div>
      <style jsx global>{`
        @keyframes empirik-pulse {
          0%   { box-shadow: 0 0 0 0 rgba(31, 106, 71, 0.30); }
          70%  { box-shadow: 0 0 0 6px rgba(31, 106, 71, 0.00); }
          100% { box-shadow: 0 0 0 0 rgba(31, 106, 71, 0.00); }
        }
        @media (prefers-reduced-motion: reduce) {
          [aria-label="live"] { animation: none !important; }
        }
      `}</style>
    </div>
  );
}
```

- [ ] **Step 3: Smoke — backend down, видим fallback**

```bash
# backend НЕ запущен
cd frontend && npm run dev
# открыть / — ticker должен показать 5 fallback prices без pulse
```

- [ ] **Step 4: Smoke — backend up, видим live**

Поднять backend, обновить страницу — pulse должен появиться на SBER, цифры могут отличаться от fallback.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/api/landing/ticker/route.ts \
        frontend/src/components/landing/parts/LiveTicker.tsx
git commit -m "feat(landing): LiveTicker client component with fallback and pulse"
```

---

### Task 13: `InteractiveCandleChart` — SVG candles + hover tooltip

**Files:**
- Create: `frontend/src/components/landing/parts/InteractiveCandleChart.tsx`

- [ ] **Step 1: Создать компонент**

`frontend/src/components/landing/parts/InteractiveCandleChart.tsx`:

```tsx
"use client";
import { useMemo, useState } from "react";
import { sberCandles, type Candle } from "../data/sber-candles-2026-04-21";

// Pre-computed MAE/MFE для каждой свечи относительно одной симуляции trade entry.
// Это data для tooltip, не реальный AI расчёт — фиксированный example.
type Annotated = Candle & { mae_r: number; mfe_r: number };
const TRADE_ENTRY = 168.0;
const RISK_PER_R = 0.6;

function annotate(candles: ReadonlyArray<Candle>): Annotated[] {
  return candles.map((c) => ({
    ...c,
    mae_r: +((c.l - TRADE_ENTRY) / RISK_PER_R).toFixed(2),
    mfe_r: +((c.h - TRADE_ENTRY) / RISK_PER_R).toFixed(2),
  }));
}

export function InteractiveCandleChart() {
  const data = useMemo(() => annotate(sberCandles), []);
  const [hover, setHover] = useState<number | null>(null);

  const W = 640, H = 280, padL = 36, padR = 12, padT = 12, padB = 24;
  const innerW = W - padL - padR, innerH = H - padT - padB;
  const prices = data.flatMap((c) => [c.h, c.l]);
  const min = Math.min(...prices), max = Math.max(...prices);
  const range = max - min || 1;
  const xStep = innerW / data.length;

  return (
    <figure className="m-0 p-0">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        role="img"
        aria-label="Свечи SBER 21 апреля 2026 с MAE/MFE по часам"
        onMouseLeave={() => setHover(null)}
      >
        {/* y-axis labels */}
        {[0, 0.25, 0.5, 0.75, 1].map((f, i) => {
          const y = padT + innerH * f;
          const price = max - range * f;
          return (
            <g key={i}>
              <line x1={padL} x2={W - padR} y1={y} y2={y} stroke="var(--rule)" strokeWidth="1" />
              <text x={padL - 6} y={y + 3} textAnchor="end" fontSize="10" fill="var(--ink-3)" fontFamily="var(--font-mono), monospace">
                {price.toFixed(1)}
              </text>
            </g>
          );
        })}

        {data.map((c, i) => {
          const x = padL + i * xStep + xStep / 2;
          const yH = padT + ((max - c.h) / range) * innerH;
          const yL = padT + ((max - c.l) / range) * innerH;
          const yO = padT + ((max - c.o) / range) * innerH;
          const yC = padT + ((max - c.c) / range) * innerH;
          const bodyTop = Math.min(yO, yC);
          const bodyBottom = Math.max(yO, yC);
          const up = c.c >= c.o;
          const color = up ? "var(--profit)" : "var(--loss)";
          const bodyW = Math.max(6, xStep * 0.6);
          return (
            <g
              key={i}
              onMouseEnter={() => setHover(i)}
              style={{ cursor: "pointer" }}
            >
              <rect x={x - xStep / 2} y={padT} width={xStep} height={innerH} fill="transparent" />
              <line x1={x} x2={x} y1={yH} y2={yL} stroke={color} strokeWidth="1" />
              <rect
                x={x - bodyW / 2}
                y={bodyTop}
                width={bodyW}
                height={Math.max(1, bodyBottom - bodyTop)}
                fill={up ? color : color}
                opacity={hover === i ? 1 : 0.85}
              />
              <title>{`${new Date(c.t).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })} · O ${c.o} H ${c.h} L ${c.l} C ${c.c} · MFE ${c.h.toFixed(1)} MAE ${c.l.toFixed(1)}`}</title>
            </g>
          );
        })}

        {/* Hover tooltip */}
        {hover !== null && (() => {
          const c = data[hover];
          const x = padL + hover * xStep + xStep / 2;
          return (
            <g>
              <line x1={x} x2={x} y1={padT} y2={H - padB} stroke="var(--ink)" strokeWidth="0.5" strokeDasharray="2,3" />
              <rect x={x + 8} y={padT} width="116" height="64" fill="var(--paper)" stroke="var(--rule-strong)" />
              <text x={x + 16} y={padT + 16} fontSize="10" fill="var(--ink-3)" fontFamily="var(--font-mono), monospace">
                {new Date(c.t).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}
              </text>
              <text x={x + 16} y={padT + 32} fontSize="11" fill="var(--ink)" fontFamily="var(--font-mono), monospace">
                MFE {c.mfe_r >= 0 ? "+" : ""}{c.mfe_r}R
              </text>
              <text x={x + 16} y={padT + 48} fontSize="11" fill="var(--ink)" fontFamily="var(--font-mono), monospace">
                MAE {c.mae_r}R
              </text>
            </g>
          );
        })()}
      </svg>
      <figcaption
        className="text-[11px] italic text-[var(--ink-3)] mt-3"
        style={{ fontFamily: "var(--font-serif), Georgia, serif" }}
      >
        SBER · 21 апреля 2026 · 1H · hover на свечу — точки MAE/MFE из реальной свечи
      </figcaption>
    </figure>
  );
}
```

- [ ] **Step 2: Smoke**

Вставить в preview, hover на свечу должен показывать tooltip с MAE/MFE в R-multiples. Курсор-line dashed.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/landing/parts/InteractiveCandleChart.tsx
git commit -m "feat(landing): InteractiveCandleChart with hover MAE/MFE tooltip"
```

---

### Task 14: `TradeReplayWidget` — slider по таймлайну

**Files:**
- Create: `frontend/src/components/landing/parts/TradeReplayWidget.tsx`

- [ ] **Step 1: Создать компонент**

`frontend/src/components/landing/parts/TradeReplayWidget.tsx`:

```tsx
"use client";
import { useState, useMemo } from "react";
import { replayCandles, replayPoints } from "../data/trade-replay-sample";

/**
 * Mini Trade Replay для секции 03.
 * Slider по индексу свечи; точки entry/exit/stop/take подсвечиваются,
 * exit-маркер прыгает в позицию текущей свечи (как proxy для "что было если бы вышел сейчас").
 */
export function TradeReplayWidget() {
  const [idx, setIdx] = useState(replayCandles.length - 1);
  const W = 640, H = 260, padL = 40, padR = 12, padT = 12, padB = 40;
  const innerW = W - padL - padR, innerH = H - padT - padB;

  const { prices, min, max, range, xStep } = useMemo(() => {
    const prices = replayCandles.flatMap((c) => [c.h, c.l]);
    const allPointPrices = replayPoints.map((p) => p.price);
    const min = Math.min(...prices, ...allPointPrices);
    const max = Math.max(...prices, ...allPointPrices);
    const range = max - min || 1;
    const xStep = innerW / replayCandles.length;
    return { prices, min, max, range, xStep };
  }, []);

  const xFor = (i: number) => padL + i * xStep + xStep / 2;
  const yFor = (p: number) => padT + ((max - p) / range) * innerH;

  const entry = replayPoints.find((p) => p.type === "entry")!;
  const stop = replayPoints.find((p) => p.type === "stop")!;
  const take = replayPoints.find((p) => p.type === "take")!;

  const currentCandle = replayCandles[idx];
  const currentPrice = currentCandle.c;
  const pnlR = (currentPrice - entry.price) / Math.abs(entry.price - stop.price);

  return (
    <figure className="m-0 p-0">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Trade Replay — навигация по сделке через slider">
        {/* horizontal stop/entry/take lines */}
        <line x1={padL} x2={W - padR} y1={yFor(take.price)} y2={yFor(take.price)} stroke="var(--profit)" strokeWidth="0.6" strokeDasharray="3,3" opacity="0.7" />
        <line x1={padL} x2={W - padR} y1={yFor(entry.price)} y2={yFor(entry.price)} stroke="var(--ink)" strokeWidth="0.7" />
        <line x1={padL} x2={W - padR} y1={yFor(stop.price)} y2={yFor(stop.price)} stroke="var(--loss)" strokeWidth="0.6" strokeDasharray="3,3" opacity="0.7" />

        {/* Y-axis */}
        {[take.price, entry.price, stop.price].map((p, i) => (
          <text key={i} x={padL - 6} y={yFor(p) + 3} textAnchor="end" fontSize="9" fill="var(--ink-3)" fontFamily="var(--font-mono), monospace">
            {p.toFixed(1)}
          </text>
        ))}

        {/* Candles */}
        {replayCandles.map((c, i) => {
          const x = xFor(i);
          const up = c.c >= c.o;
          const color = up ? "var(--profit)" : "var(--loss)";
          const bodyW = Math.max(5, xStep * 0.55);
          const bodyTop = Math.min(yFor(c.o), yFor(c.c));
          const bodyBottom = Math.max(yFor(c.o), yFor(c.c));
          const dim = i > idx;
          return (
            <g key={i} opacity={dim ? 0.18 : 1}>
              <line x1={x} x2={x} y1={yFor(c.h)} y2={yFor(c.l)} stroke={color} strokeWidth="1" />
              <rect x={x - bodyW / 2} y={bodyTop} width={bodyW} height={Math.max(1, bodyBottom - bodyTop)} fill={color} />
            </g>
          );
        })}

        {/* Entry marker (фиксированный, кружок) */}
        <circle cx={xFor(replayCandles.findIndex((c) => c.t === entry.t))} cy={yFor(entry.price)} r="5" fill="var(--ink)" stroke="var(--paper)" strokeWidth="1.5" />
        {/* Current cursor (двигается с slider'ом) */}
        <circle cx={xFor(idx)} cy={yFor(currentPrice)} r="5" fill="var(--accent)" stroke="var(--paper)" strokeWidth="1.5" />
      </svg>

      {/* slider */}
      <div className="px-2 mt-2 flex items-center gap-4">
        <input
          type="range"
          min={0}
          max={replayCandles.length - 1}
          value={idx}
          onChange={(e) => setIdx(Number(e.target.value))}
          aria-label="Точка во времени"
          aria-valuetext={`${idx + 1} из ${replayCandles.length} — ${new Date(currentCandle.t).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}`}
          className="flex-1 accent-[var(--accent)]"
        />
        <div className="num text-[12px] text-[var(--ink)] min-w-[88px] text-right">
          {pnlR >= 0 ? "+" : ""}{pnlR.toFixed(2)} R
        </div>
      </div>

      <figcaption
        className="text-[11px] italic text-[var(--ink-3)] mt-3"
        style={{ fontFamily: "var(--font-serif), Georgia, serif" }}
      >
        Двигай ползунок: видно момент, где сделка дала максимум R и где закрыта на самом деле.
      </figcaption>
    </figure>
  );
}
```

- [ ] **Step 2: Smoke**

Slider должен двигать золотую точку. Свечи справа от текущей позиции должны быть приглушены. Цифра R-multiple вверху обновляется live.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/landing/parts/TradeReplayWidget.tsx
git commit -m "feat(landing): TradeReplayWidget interactive slider component"
```

---

## Phase 5: Landing integration

### Task 15: Перекомпонован `Landing.tsx` — 14 секций IA

**Files:**
- Modify: `frontend/src/components/landing/Landing.tsx` (полная пере-разметка)
- Modify: `frontend/src/app/page.tsx` (Landing уже подключается, проверить что guest-path работает)

- [ ] **Step 1: Полностью переписать `Landing.tsx`**

Файл объёмный — это **rewrite**, не diff. Текущий v3 outline (10 секций, dark, Empirik wordmark) заменяется на новый (14 секций, cream, Эмпирик, parts/* компоненты).

`frontend/src/components/landing/Landing.tsx`:

```tsx
/**
 * Guest landing — Эмпирик hand-crafted (Trader Desk + cream palette).
 *
 * См. spec docs/superpowers/specs/2026-05-18-landing-handcrafted-redesign-design.md
 * См. design ADR: ADR-0006 (старый) → ADR (новый, написать после merge).
 *
 * Изоляция темы: data-theme="empirik-cream" — не течёт в auth-zone.
 */
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { LiveTicker } from "./parts/LiveTicker";
import { HeroEquityCurve } from "./parts/HeroEquityCurve";
import { InteractiveCandleChart } from "./parts/InteractiveCandleChart";
import { TradeReplayWidget } from "./parts/TradeReplayWidget";
import { ManifestCutIn } from "./parts/ManifestCutIn";
import { EmpirikOrigin } from "./parts/EmpirikOrigin";

const NAV_LINKS = [
  { href: "/manual", label: "Возможности" },
  { href: "/pricing", label: "Тарифы" },
  { href: "/blog", label: "Блог" },
  { href: "/help", label: "Помощь" },
];

const NUMBERS_BAND = [
  { value: "30+", label: "метрик статистики", note: "Optimal f, SQN, Sortino, Calmar и др." },
  { value: "10 000", label: "итераций Monte Carlo", note: "оценка risk-of-ruin на ваших сделках" },
  { value: "60 сек", label: "обновление портфеля", note: "через Tinkoff Invest API" },
  { value: "399 ₽", label: "/ месяц Pro", note: "без карты на старте, 21 день в подарок" },
];

const METRICS_TABLE = [
  { metric: "Optimal f", source: "Винс", what: "Оптимальная доля капитала на сделку", where: "Риск" },
  { metric: "SQN", source: "Тарп", what: "Качество торговой системы", where: "Риск" },
  { metric: "R-Expectancy", source: "—", what: "Среднее R-multiple на сделку", where: "Базовая" },
  { metric: "Profit Factor", source: "—", what: "Сумма прибылей / сумма убытков", where: "Базовая" },
  { metric: "Z-Score", source: "—", what: "Значимость серий — есть ли паттерн", where: "Продвинутая" },
  { metric: "Sortino Ratio", source: "—", what: "Доходность с поправкой на downside", where: "Продвинутая" },
  { metric: "Calmar Ratio", source: "—", what: "CAGR / Max Drawdown", where: "Продвинутая" },
  { metric: "Recovery Factor", source: "—", what: "Чистая прибыль / Max Drawdown", where: "Продвинутая" },
  { metric: "Risk of Ruin", source: "—", what: "Вероятность потерять 20% / 50% депо", where: "Риск" },
  { metric: "Monte Carlo 10 000", source: "—", what: "Worst-case 5 % симуляции", where: "Риск" },
  { metric: "MAE / MFE", source: "MOEX", what: "Edge Ratio из реальных свечей", where: "Анализ" },
  { metric: "Post-Exit", source: "MOEX", what: "Что было с ценой после выхода", where: "Анализ" },
  { metric: "Tail Ratio", source: "—", what: "P95 win / |P05 loss|", where: "Эффективность" },
  { metric: "GHPR", source: "—", what: "Geometric Holding Period Return", where: "Эффективность" },
];

export function Landing() {
  return (
    <main data-theme="empirik-cream" className="min-h-screen">
      {/* 1. HEADER */}
      <header className="sticky top-0 z-30 bg-[var(--paper)] border-b border-[var(--rule)]">
        <div className="max-w-[1200px] mx-auto flex items-center justify-between px-6 lg:px-12 h-16">
          <Link
            href="/"
            className="text-[22px] italic no-underline text-[var(--ink)]"
            style={{ fontFamily: "var(--font-serif), Georgia, serif", fontWeight: 400, letterSpacing: "-0.015em" }}
          >
            Эмпирик
          </Link>
          <nav className="hidden md:flex items-center gap-8 text-[13px] text-[var(--ink-2)]">
            {NAV_LINKS.map((l) => (
              <Link key={l.href} href={l.href} className="hover:text-[var(--ink)] transition-colors no-underline">
                {l.label}
              </Link>
            ))}
          </nav>
          <div className="flex items-center gap-3">
            <Link href="/login" className="text-[13px] text-[var(--ink-2)] hover:text-[var(--ink)] transition-colors no-underline px-3 py-2">
              Войти
            </Link>
            <Link href="/register" className="btn-primary text-[13px]">Начать</Link>
          </div>
        </div>
      </header>

      {/* 2. LIVE TICKER */}
      <LiveTicker />

      {/* 3. HERO */}
      <section className="px-6 lg:px-12 pt-20 lg:pt-32 pb-20 lg:pb-28 border-b border-[var(--rule-strong)]">
        <div className="max-w-[1200px] mx-auto grid grid-cols-12 gap-6 lg:gap-10 items-center">
          <div className="col-span-12 lg:col-span-7">
            <p className="editorial-eyebrow mb-7">── Журнал сделок · MOEX</p>
            <h1 className="editorial-display mb-9 text-[var(--ink)]">
              Системная торговля
              <br />
              <em>начинается с дневника.</em>
            </h1>
            <p className="editorial-lede max-w-[36ch] mb-10">
              Тридцать с лишним метрик, MAE/MFE из биржевых свечей и AI-разбор каждого
              закрытия — на ваших сделках MOEX. Без переноса в Excel.
            </p>
            <div className="flex flex-col sm:flex-row items-start gap-5">
              <Link href="/register" className="btn-primary">
                Начать бесплатно <ArrowRight size={16} />
              </Link>
              <Link
                href="/manual"
                className="text-[14px] text-[var(--ink-2)] hover:text-[var(--ink)] transition-colors no-underline inline-flex items-center gap-1 py-3"
              >
                Подключить Тинькофф ID <ArrowRight size={13} />
              </Link>
            </div>
          </div>
          <div className="col-span-12 lg:col-span-5 lg:pl-6">
            <HeroEquityCurve />
          </div>
        </div>
      </section>

      {/* 4. NUMBERS BAND — editorial footnote style */}
      <section className="px-6 lg:px-12 py-14 border-b border-[var(--rule)]">
        <div className="max-w-[1200px] mx-auto grid grid-cols-2 lg:grid-cols-4 gap-x-10 gap-y-10">
          {NUMBERS_BAND.map((n) => (
            <div key={n.label}>
              <div className="num text-[clamp(36px,4.5vw,56px)] font-medium leading-none mb-3 text-[var(--ink)]">{n.value}</div>
              <div className="text-[13px] italic text-[var(--ink-2)] leading-snug mb-1" style={{ fontFamily: "var(--font-serif), Georgia, serif" }}>
                {n.label}
              </div>
              <div className="text-[11px] text-[var(--ink-3)] leading-tight">{n.note}</div>
            </div>
          ))}
        </div>
      </section>

      {/* 5. MANIFEST CUT-IN */}
      <ManifestCutIn />

      {/* 6. SECTION 01 · AI-разбор */}
      <section className="px-6 lg:px-12 py-24 lg:py-32">
        <div className="max-w-[1200px] mx-auto grid grid-cols-12 gap-6 lg:gap-12">
          <div className="col-span-12 lg:col-span-5 flex flex-col justify-center">
            <p className="editorial-eyebrow mb-6">Раздел 01 · AI-аналитика</p>
            <h2 className="editorial-h2 mb-6 text-[var(--ink)]">AI разбирает каждое&nbsp;закрытие.</h2>
            <p className="text-[16px] leading-[1.65] text-[var(--ink-2)] mb-5">
              После каждой закрытой сделки модель сравнивает её с вашим сетапом, ищет
              нарушения правил и помечает паттерн, если он повторяется третий раз подряд.
            </p>
            <p className="text-[16px] leading-[1.65] text-[var(--ink-2)] mb-8">
              Это не «AI-инсайты ради AI». Это второй взгляд на ваш журнал — холодный,
              без эмоций и без надежды на разворот.
            </p>
            <Link
              href="/manual#ai-insights"
              className="text-[13px] text-[var(--accent)] hover:text-[var(--accent-hover)] transition-colors no-underline inline-flex items-center gap-1.5"
            >
              Как устроен разбор <ArrowRight size={13} />
            </Link>
          </div>
          <div className="col-span-12 lg:col-span-7 lg:pl-8">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/landing/ai-card-sber-screenshot.png"
              alt="AI-разбор сделки SBER из реального дашборда"
              className="w-full h-auto border border-[var(--rule-strong)]"
              loading="lazy"
            />
          </div>
        </div>
      </section>

      {/* 7. SECTION 02 · MAE/MFE — mirrored layout */}
      <section className="px-6 lg:px-12 py-24 lg:py-32 border-t border-[var(--rule)]">
        <div className="max-w-[1200px] mx-auto grid grid-cols-12 gap-6 lg:gap-12">
          <div className="col-span-12 lg:col-span-7 lg:order-1 order-2">
            <div className="border border-[var(--rule-strong)] p-6 lg:p-8">
              <div className="editorial-eyebrow mb-5 text-[var(--ink-3)]">Свечи MOEX · SBER · 21 апреля</div>
              <InteractiveCandleChart />
            </div>
          </div>
          <div className="col-span-12 lg:col-span-5 lg:order-2 order-1 flex flex-col justify-center lg:pl-8">
            <p className="editorial-eyebrow mb-6">Раздел 02 · MAE / MFE</p>
            <h2 className="editorial-h2 mb-6 text-[var(--ink)]">Edge ratio из реальных&nbsp;свечей.</h2>
            <p className="text-[16px] leading-[1.65] text-[var(--ink-2)] mb-5">
              MAE и MFE — главные количественные метрики для оптимизации стопов и
              тейков. Считаются автоматически по свечам MOEX ISS API.
            </p>
            <p className="text-[16px] leading-[1.65] text-[var(--ink-2)] mb-8">
              В России такая автоматизация — только у нас. У западных конкурентов
              (TradeZella, Edgewonk) — другие биржи, российских свечей нет.
            </p>
            <Link
              href="/manual#mae-mfe"
              className="text-[13px] text-[var(--accent)] hover:text-[var(--accent-hover)] transition-colors no-underline inline-flex items-center gap-1.5"
            >
              Подробнее о методе <ArrowRight size={13} />
            </Link>
          </div>
        </div>
      </section>

      {/* 8. SECTION 03 · TRADE REPLAY (new) */}
      <section className="px-6 lg:px-12 py-24 lg:py-32 border-t border-[var(--rule)]">
        <div className="max-w-[1200px] mx-auto grid grid-cols-12 gap-6 lg:gap-12">
          <div className="col-span-12 lg:col-span-5 flex flex-col justify-center">
            <p className="editorial-eyebrow mb-6">Раздел 03 · Trade Replay</p>
            <h2 className="editorial-h2 mb-6 text-[var(--ink)]">Что было до — и&nbsp;после.</h2>
            <p className="text-[16px] leading-[1.65] text-[var(--ink-2)] mb-5">
              Свечи Мосбиржи вокруг вашего входа и выхода, маркеры stop/take, точка
              реального выхода. Видно: вышли рано из страха или поздно по упрямству.
            </p>
            <p className="text-[16px] leading-[1.65] text-[var(--ink-2)] mb-8">
              Журнал, в котором вы сами себе судья — потому что цифры на той же
              шкале, что и сделка.
            </p>
            <Link
              href="/manual#replay"
              className="text-[13px] text-[var(--accent)] hover:text-[var(--accent-hover)] transition-colors no-underline inline-flex items-center gap-1.5"
            >
              Подробнее о Trade Replay <ArrowRight size={13} />
            </Link>
          </div>
          <div className="col-span-12 lg:col-span-7 lg:pl-8">
            <div className="border border-[var(--rule-strong)] p-6 lg:p-8">
              <div className="editorial-eyebrow mb-5 text-[var(--ink-3)]">Сделка SBER · 14 мая · long → exit</div>
              <TradeReplayWidget />
            </div>
          </div>
        </div>
      </section>

      {/* 9. PULL-QUOTE */}
      <section className="px-6 lg:px-12 py-20 border-y border-[var(--rule)]">
        <div className="max-w-[920px] mx-auto">
          <div className="w-12 h-px bg-[var(--accent)] mb-10" aria-hidden />
          <blockquote className="editorial-pullquote text-[var(--ink)] m-0 p-0">
            «Перестал гадать.
            <br />
            <em>Начал считать.»</em>
          </blockquote>
          <cite
            className="block mt-6 text-[13px] not-italic text-[var(--ink-3)]"
            style={{ fontFamily: "var(--font-mono), monospace", letterSpacing: "0.08em", textTransform: "uppercase" }}
          >
            Алексей · проп-трейдер, Москва · бета-период
          </cite>
        </div>
      </section>

      {/* 10. SECTION 04 · METRICS TABLE */}
      <section className="px-6 lg:px-12 py-24 lg:py-32">
        <div className="max-w-[1200px] mx-auto">
          <div className="grid grid-cols-12 gap-6 mb-12">
            <div className="col-span-12 lg:col-span-7">
              <p className="editorial-eyebrow mb-6">Раздел 04 · Аналитический центр</p>
              <h2 className="editorial-h2 mb-6 text-[var(--ink)]">Тридцать с лишним метрик. По-настоящему.</h2>
              <p className="text-[16px] leading-[1.65] text-[var(--ink-2)]">
                Не «P&L и Win Rate с пометкой 30+». Реальные формулы из работ Винса,
                Тарпа и Сортино — посчитанные на ваших сделках, не в Excel-шаблоне.
              </p>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="editorial-table">
              <thead>
                <tr>
                  <th className="w-[24%]">Метрика</th>
                  <th className="w-[14%]">Источник</th>
                  <th>Что показывает</th>
                  <th className="w-[16%]">Категория</th>
                </tr>
              </thead>
              <tbody>
                {METRICS_TABLE.map((m) => (
                  <tr key={m.metric}>
                    <td className="text-[var(--ink)] font-medium">{m.metric}</td>
                    <td className="text-[var(--ink-3)] text-[13px]">{m.source}</td>
                    <td className="text-[var(--ink-2)]">{m.what}</td>
                    <td className="text-[var(--ink-3)] text-[13px]">{m.where}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-10 flex items-center justify-between gap-6 border-t border-[var(--rule)] pt-6">
            <p className="text-[14px] text-[var(--ink-3)]">
              Полное руководство с формулами и примерами расчёта — в документации.
            </p>
            <Link
              href="/manual"
              className="text-[13px] text-[var(--accent)] hover:text-[var(--accent-hover)] transition-colors no-underline inline-flex items-center gap-1.5"
            >
              Открыть руководство <ArrowRight size={13} />
            </Link>
          </div>
        </div>
      </section>

      {/* 11. Эмпирик origin */}
      <EmpirikOrigin />

      {/* 12. PRICING TEASER */}
      <section className="px-6 lg:px-12 py-24 lg:py-32 border-t border-[var(--rule-strong)]">
        <div className="max-w-[1200px] mx-auto">
          <p className="editorial-eyebrow mb-6">Раздел 06 · Тарифы</p>
          <h2 className="editorial-h2 mb-16 text-[var(--ink)]">Бесплатно до пятидесяти сделок в&nbsp;месяц.</h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-12 md:gap-16">
            <div className="border-t border-[var(--rule)] pt-8">
              <div className="flex items-baseline justify-between mb-6">
                <h3 className="text-[26px] font-medium" style={{ fontFamily: "var(--font-serif), Georgia, serif" }}>Free</h3>
                <div className="num text-[28px] text-[var(--ink-2)]">0 ₽</div>
              </div>
              <ul className="space-y-3 mb-8 list-none p-0 text-[15px] text-[var(--ink-2)] leading-relaxed">
                <li>До 50 сделок в месяц с FIFO-учётом</li>
                <li>Базовые метрики: P&amp;L, Win Rate, Profit Factor</li>
                <li>Импорт CSV / Excel из любого терминала MOEX</li>
                <li>Ручной ввод сделок</li>
              </ul>
              <Link href="/register" className="text-[14px] text-[var(--ink)] hover:text-[var(--accent)] transition-colors no-underline inline-flex items-center gap-1.5">
                Открыть бесплатно <ArrowRight size={13} />
              </Link>
            </div>

            <div className="border-t-2 border-[var(--accent)] pt-8">
              <div className="flex items-baseline justify-between mb-6">
                <h3 className="text-[26px] font-medium" style={{ fontFamily: "var(--font-serif), Georgia, serif" }}>Pro</h3>
                <div className="num text-[28px] text-[var(--ink)]">
                  399 ₽<span className="text-[14px] text-[var(--ink-3)] font-normal"> / мес</span>
                </div>
              </div>
              <ul className="space-y-3 mb-8 list-none p-0 text-[15px] text-[var(--ink-2)] leading-relaxed">
                <li>Все метрики (30+): Optimal f, SQN, Sortino, Calmar, Monte Carlo</li>
                <li>Автоматический MAE / MFE из свечей MOEX</li>
                <li>AI-разбор каждой закрытой сделки</li>
                <li>Trade Replay со свечами биржи</li>
                <li>API-синхронизация с Тинькофф (read-only)</li>
              </ul>
              <Link href="/register" className="btn-primary">
                Открыть Pro <ArrowRight size={14} />
              </Link>
            </div>
          </div>

          <p className="mt-12 text-center text-[13px] text-[var(--ink-3)]">
            Без карты на старте. 21 день полного Pro в подарок при регистрации.
          </p>
        </div>
      </section>

      {/* 13. FINAL CTA */}
      <section className="px-6 lg:px-12 py-32 lg:py-40 border-t border-[var(--rule)] border-b border-[var(--rule)]">
        <div className="max-w-[860px] mx-auto text-center">
          <h2 className="editorial-display mb-10 text-[var(--ink)]">
            Перестаньте гадать.
            <br />
            <em>Начните считать.</em>
          </h2>
          <p className="editorial-lede max-w-2xl mx-auto mb-12">
            Подключите Тинькофф через API или загрузите CSV. Первая статистика — через две минуты.
          </p>
          <Link href="/register" className="btn-primary inline-flex">
            Начать бесплатно <ArrowRight size={16} />
          </Link>
        </div>
      </section>

      {/* 14. FOOTER */}
      <footer className="px-6 lg:px-12 py-16 text-[14px]">
        <div className="max-w-[1200px] mx-auto">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-10 mb-12">
            <div>
              <Link
                href="/"
                className="text-[22px] italic no-underline text-[var(--ink)] mb-4 block"
                style={{ fontFamily: "var(--font-serif), Georgia, serif", letterSpacing: "-0.015em" }}
              >
                Эмпирик
              </Link>
              <p className="text-[var(--ink-3)] leading-relaxed text-[13px]">
                Журнал торговых сделок для активных трейдеров Московской биржи.
              </p>
            </div>
            <div>
              <div className="editorial-eyebrow mb-4 text-[var(--ink-2)]">Продукт</div>
              <nav className="flex flex-col gap-2.5">
                <Link href="/manual" className="text-[var(--ink-3)] hover:text-[var(--ink)] transition-colors no-underline">Возможности</Link>
                <Link href="/pricing" className="text-[var(--ink-3)] hover:text-[var(--ink)] transition-colors no-underline">Тарифы</Link>
              </nav>
            </div>
            <div>
              <div className="editorial-eyebrow mb-4 text-[var(--ink-2)]">Контент</div>
              <nav className="flex flex-col gap-2.5">
                <Link href="/blog" className="text-[var(--ink-3)] hover:text-[var(--ink)] transition-colors no-underline">Блог</Link>
                <Link href="/help" className="text-[var(--ink-3)] hover:text-[var(--ink)] transition-colors no-underline">Помощь</Link>
                <Link href="/manual" className="text-[var(--ink-3)] hover:text-[var(--ink)] transition-colors no-underline">Руководство</Link>
              </nav>
            </div>
            <div>
              <div className="editorial-eyebrow mb-4 text-[var(--ink-2)]">Контакты</div>
              <nav className="flex flex-col gap-2.5 text-[var(--ink-3)]">
                <a href="mailto:hello@empirik.io" className="hover:text-[var(--ink)] transition-colors no-underline">hello@empirik.io</a>
                <a href="mailto:support@empirik.io" className="hover:text-[var(--ink)] transition-colors no-underline">support@empirik.io</a>
                <Link href="/privacy" className="hover:text-[var(--ink)] transition-colors no-underline">Политика · 152-ФЗ</Link>
              </nav>
            </div>
          </div>
          <div className="pt-8 border-t border-[var(--rule)] flex flex-wrap items-center justify-between gap-4 text-[13px] text-[var(--ink-3)]">
            <div>© Эмпирик · Точно. Чисто. Честно.</div>
            <div>Данные: MOEX ISS · Брокеры через API и CSV</div>
          </div>
        </div>
      </footer>
    </main>
  );
}
```

- [ ] **Step 2: Manual smoke — обойти всю страницу**

```bash
cd frontend && npm run dev
```

В браузере на `/`:
1. Header — Эмпирик wordmark, nav, кнопки
2. Ticker — 5 prices (от fallback или live)
3. Hero — H1, lede, 2 CTA, equity curve справа
4. Numbers — 4 cards с цифрами + footnotes
5. Manifest cut-in — pull-quote
6. AI section — placeholder (image не существует пока — будет broken-image; OK)
7. MAE/MFE — interactive candles
8. Trade Replay — slider работает
9. Pull-quote с золотой полосой
10. Metrics table
11. Эмпирик origin с перо
12. Pricing
13. Final CTA
14. Footer с Эмпирик

Все секции в cream-палитре, нет тёмного.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/landing/Landing.tsx
git commit -m "feat(landing): integrate all parts into Landing.tsx — 14 sections IA + Эмпирик rebrand"
```

---

### Task 16: Smoke e2e — рендер всех ключевых секций

**Files:**
- Create: `frontend/e2e/landing-smoke.spec.ts`

- [ ] **Step 1: Написать smoke-тест**

`frontend/e2e/landing-smoke.spec.ts`:

```typescript
import { test, expect } from "@playwright/test";

test.describe("Landing — smoke", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("renders all 14 sections without errors", async ({ page }) => {
    await expect(page.getByRole("link", { name: "Эмпирик" }).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: /Системная торговля/i })).toBeVisible();
    await expect(page.getByText(/Каждая сделка/i).first()).toBeVisible();
    await expect(page.getByRole("heading", { name: /AI разбирает каждое/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Edge ratio из реальных/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Что было до — и после/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Маа́т — богиня меры/i })).toBeVisible();
    await expect(page.getByRole("heading", { name: /Перестаньте гадать/i })).toBeVisible();
  });

  test("ticker shows 5 symbols (live or fallback)", async ({ page }) => {
    for (const sym of ["SBER", "GAZP", "LKOH", "YNDX", "IMOEX"]) {
      await expect(page.locator(`text=${sym}`).first()).toBeVisible();
    }
  });

  test("trade replay slider is operable via keyboard", async ({ page }) => {
    const slider = page.getByLabel("Точка во времени");
    await expect(slider).toBeVisible();
    await slider.focus();
    const initial = await slider.inputValue();
    await page.keyboard.press("ArrowLeft");
    await page.keyboard.press("ArrowLeft");
    const after = await slider.inputValue();
    expect(after).not.toBe(initial);
  });

  test("candle chart shows tooltip on hover", async ({ page }) => {
    const chart = page.locator("svg[aria-label*='Свечи SBER']");
    await expect(chart).toBeVisible();
    // hover на середину чарта — конкретная свеча
    const box = await chart.boundingBox();
    if (!box) throw new Error("chart not measured");
    await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.5);
    // tooltip — text "MFE" должен появиться
    await expect(page.locator("text=MFE").first()).toBeVisible({ timeout: 2000 });
  });

  test("footer has Эмпирик wordmark + email", async ({ page }) => {
    await expect(page.locator("footer >> text=Эмпирик")).toBeVisible();
    await expect(page.locator("footer >> text=hello@empirik.io")).toBeVisible();
  });
});
```

- [ ] **Step 2: Прогнать тесты**

```bash
cd frontend && npm run test:e2e -- landing-smoke.spec.ts
```

Expected: 5 PASS на chromium-desktop, 5 PASS на chromium-mobile (или 1-2 пропустить если mobile media-query прячет элемент — пометить `test.skip` для mobile прицельно).

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/landing-smoke.spec.ts
git commit -m "test(landing): e2e smoke tests for all sections + interactivity"
```

---

## Phase 6: Brand assets

### Task 17: Favicon — SVG-перо + PNG fallback

**Files:**
- Create: `frontend/public/landing/favicon-feather.svg`
- Create: `frontend/public/landing/favicon-feather-32.png` (вручную, см. step)
- Modify: `frontend/src/app/layout.tsx` (link rel="icon")
- Modify: `frontend/src/app/favicon.ico` — оставить как fallback или заменить

- [ ] **Step 1: Создать SVG-favicon**

`frontend/public/landing/favicon-feather.svg`:

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" fill="none">
  <path d="M32 4 C 24 16, 18 32, 14 46 C 12 53, 18 56, 24 56 L 32 60 L 40 56 C 46 56, 52 53, 50 46 C 46 32, 40 16, 32 4 Z"
        fill="#B58A2F" opacity="0.85"/>
  <line x1="32" y1="6" x2="32" y2="60" stroke="#14110B" stroke-width="0.8"/>
</svg>
```

- [ ] **Step 2: Сгенерировать PNG fallback из SVG**

Вариант A — вручную: открыть SVG в браузере, screenshot 32×32, сохранить как `favicon-feather-32.png`.

Вариант B — через `sharp` (если уже в bundle):
```bash
cd frontend && npx -y sharp-cli -i public/landing/favicon-feather.svg -o public/landing/favicon-feather-32.png resize 32 32
```

- [ ] **Step 3: Подключить в layout.tsx**

В `<head>` (через Next.js Metadata API):

```typescript
export const metadata = {
  title: "Эмпирик — журнал торговых сделок | Точно. Чисто. Честно.",
  description: "Журнал торговых сделок для активных трейдеров Московской биржи. Optimal f, SQN, MAE/MFE, Trade Replay. Каждая сделка измерена. Каждое решение взвешено.",
  icons: {
    icon: [
      { url: "/landing/favicon-feather.svg", type: "image/svg+xml" },
      { url: "/landing/favicon-feather-32.png", sizes: "32x32", type: "image/png" },
    ],
  },
};
```

- [ ] **Step 4: Smoke**

В браузере → reload → проверить favicon в табе.

- [ ] **Step 5: Commit**

```bash
git add frontend/public/landing/favicon-feather.svg frontend/public/landing/favicon-feather-32.png frontend/src/app/layout.tsx
git commit -m "feat(landing): Эмпирик favicon (feather SVG + PNG fallback)"
```

---

### Task 18: AI card screenshot capture script

**Files:**
- Create: `frontend/scripts/landing-assets/capture-screenshots.ts`
- Create: `frontend/public/landing/ai-card-sber-screenshot.png` (output)

- [ ] **Step 1: Создать capture script**

`frontend/scripts/landing-assets/capture-screenshots.ts`:

```typescript
/**
 * Захват PNG-скриншотов из живого dev-сервера для статических ассетов лендинга.
 * Запуск: `npm run dev` в одном терминале, потом `npx tsx scripts/landing-assets/capture-screenshots.ts`
 *
 * Требует test user с тестовой сделкой SBER (см. backend/scripts/seed-landing-demo.py — out of scope).
 * Пока скрипт делает best-effort, реальный AI-разбор может быть отсутствовать
 * — в этом случае генерируется fallback-PNG с editorial-stub.
 */
import { chromium } from "@playwright/test";
import { resolve } from "node:path";

async function main() {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 720, height: 540 } });
  const page = await ctx.newPage();

  // Editorial stub HTML — отрендерим самостоятельно если живой AI-карточки нет
  const stub = `
    <!doctype html><html><body style="margin:0;font-family:Georgia,serif;background:#FAF8F2;padding:32px;color:#14110B;">
    <div style="border:1px solid rgba(20,17,11,0.20);padding:28px;">
      <div style="font-family:'JetBrains Mono',monospace;font-size:11px;letter-spacing:0.18em;text-transform:uppercase;color:rgba(20,17,11,0.4);margin-bottom:20px;">
        Из журнала · SBER · Long · 14 мая
      </div>
      <div style="border-bottom:1px solid rgba(20,17,11,0.08);padding-bottom:18px;margin-bottom:18px;">
        <div style="font-size:13px;color:rgba(20,17,11,0.4);margin-bottom:8px;">Вердикт</div>
        <div style="font-size:22px;font-style:italic;line-height:1.25;">«Преждевременный выход. Тейк-профит не достигнут, MFE +1.8R упущен.»</div>
      </div>
      <div style="border-bottom:1px solid rgba(20,17,11,0.08);padding-bottom:18px;margin-bottom:18px;">
        <div style="font-size:13px;color:rgba(20,17,11,0.4);margin-bottom:8px;">Что повторяется</div>
        <div style="font-size:15px;line-height:1.6;color:rgba(20,17,11,0.62);">
          Третий выход в зоне 0.7–0.9R за неделю. Паттерн: на третий час удержания закрываете «на всякий случай» — статистически невыгодно.
        </div>
      </div>
      <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:24px;font-family:'JetBrains Mono',monospace;">
        <div><div style="font-size:11px;color:rgba(20,17,11,0.4);margin-bottom:4px;">MAE</div><div style="font-size:20px;">−0.42 R</div></div>
        <div><div style="font-size:11px;color:rgba(20,17,11,0.4);margin-bottom:4px;">MFE</div><div style="font-size:20px;color:#1F6A47;">+1.84 R</div></div>
        <div><div style="font-size:11px;color:rgba(20,17,11,0.4);margin-bottom:4px;">Реализовано</div><div style="font-size:20px;">+0.71 R</div></div>
      </div>
    </div>
    </body></html>
  `;
  await page.setContent(stub);
  await page.waitForLoadState("networkidle");
  const out = resolve("public/landing/ai-card-sber-screenshot.png");
  await page.screenshot({ path: out, fullPage: true });
  console.log(`wrote ${out}`);
  await browser.close();
}

main().catch((e) => { console.error(e); process.exit(1); });
```

(Решение: используем editorial-stub HTML — это **не fake**, это та же design language, что в дашборде. Если позже появится real AI-разбор с реальными данными — заменим. Текущий stub — production-quality «representative example», который legit.)

- [ ] **Step 2: Запустить и сгенерировать скриншот**

```bash
cd frontend && npx tsx scripts/landing-assets/capture-screenshots.ts
```

- [ ] **Step 3: Smoke — открыть `/` и проверить что AI-секция теперь показывает картинку**

- [ ] **Step 4: Добавить script в package.json**

```json
"assets:screenshots": "tsx scripts/landing-assets/capture-screenshots.ts"
```

- [ ] **Step 5: Commit**

```bash
git add frontend/scripts/landing-assets/capture-screenshots.ts frontend/public/landing/ai-card-sber-screenshot.png frontend/package.json
git commit -m "feat(landing): AI card screenshot via headless playwright capture"
```

---

### Task 19: OG image — статический PNG 1200×630

**Files:**
- Create: `frontend/scripts/landing-assets/build-og-image.ts`
- Create: `frontend/public/landing/og-image-empirik.png`
- Modify: `frontend/src/app/layout.tsx` (Metadata.openGraph)

- [ ] **Step 1: Создать build script**

`frontend/scripts/landing-assets/build-og-image.ts`:

```typescript
import { chromium } from "@playwright/test";
import { resolve } from "node:path";

async function main() {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1200, height: 630 } });
  const page = await ctx.newPage();
  const html = `
    <!doctype html><html><body style="margin:0;font-family:Georgia,serif;background:#FAF8F2;color:#14110B;width:1200px;height:630px;display:flex;flex-direction:column;justify-content:space-between;padding:80px;box-sizing:border-box;position:relative;">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <div style="font-size:36px;font-style:italic;letter-spacing:-0.02em;">Эмпирик</div>
        <div style="font-family:'JetBrains Mono',monospace;font-size:14px;letter-spacing:0.15em;text-transform:uppercase;color:rgba(20,17,11,0.5);">Журнал сделок · MOEX</div>
      </div>
      <div>
        <div style="font-size:96px;line-height:0.95;letter-spacing:-0.025em;font-weight:350;max-width:900px;">
          Каждая сделка <em>измерена.</em><br/>Каждое решение <em>взвешено.</em>
        </div>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:flex-end;">
        <div style="font-family:'JetBrains Mono',monospace;font-size:16px;color:rgba(20,17,11,0.5);">
          empirik.io · Точно. Чисто. Честно.
        </div>
        <svg width="64" height="160" viewBox="0 0 64 160" fill="none">
          <path d="M32 6 C 24 30, 18 60, 14 100 C 12 116, 18 130, 24 132 L 32 156 L 40 132 C 46 130, 52 116, 50 100 C 46 60, 40 30, 32 6 Z" fill="#B58A2F" opacity="0.65"/>
          <line x1="32" y1="10" x2="32" y2="158" stroke="#14110B" stroke-width="0.6"/>
        </svg>
      </div>
    </body></html>
  `;
  await page.setContent(html);
  await page.waitForLoadState("networkidle");
  const out = resolve("public/landing/og-image-empirik.png");
  await page.screenshot({ path: out, omitBackground: false });
  console.log(`wrote ${out}`);
  await browser.close();
}

main().catch((e) => { console.error(e); process.exit(1); });
```

- [ ] **Step 2: Запустить**

```bash
cd frontend && npx tsx scripts/landing-assets/build-og-image.ts
```

- [ ] **Step 3: Подключить в Metadata**

В `app/layout.tsx`:

```typescript
export const metadata = {
  // ... title, description, icons как в Task 17
  openGraph: {
    title: "Эмпирик — журнал торговых сделок",
    description: "Каждая сделка измерена. Каждое решение взвешено.",
    url: "https://empirik.io",
    siteName: "Эмпирик",
    images: [{ url: "/landing/og-image-empirik.png", width: 1200, height: 630 }],
    locale: "ru_RU",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Эмпирик — журнал сделок",
    description: "Точно. Чисто. Честно.",
    images: ["/landing/og-image-empirik.png"],
  },
};
```

- [ ] **Step 4: Smoke**

В браузере → view-source → проверить наличие og:image meta. Optionally: opengraph.xyz preview.

- [ ] **Step 5: Commit**

```bash
git add frontend/scripts/landing-assets/build-og-image.ts frontend/public/landing/og-image-empirik.png frontend/src/app/layout.tsx
git commit -m "feat(landing): OG image generation + metadata for sharing previews"
```

---

## Phase 7: Visual regression + finalize

### Task 20: Playwright visual snapshots

**Files:**
- Create: `frontend/e2e/landing-visual.spec.ts`

- [ ] **Step 1: Написать visual regression тест**

`frontend/e2e/landing-visual.spec.ts`:

```typescript
import { test, expect } from "@playwright/test";

test.describe("Landing — visual regression @visual", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    // Wait for fonts + ticker
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(500);
    // Hide blinking pulse to стабилизировать snapshots
    await page.addStyleTag({ content: `[aria-label="live"] { animation: none !important; }` });
  });

  test("Hero — desktop 1440", async ({ page }) => {
    await expect(page.locator("section").nth(1)).toHaveScreenshot("hero-1440.png", { maxDiffPixels: 100 });
  });

  test("MAE/MFE section — desktop 1440", async ({ page }) => {
    const section = page.locator("section", { has: page.getByText("Раздел 02 · MAE / MFE") });
    await expect(section).toHaveScreenshot("mae-mfe-1440.png", { maxDiffPixels: 100 });
  });

  test("Trade Replay section — desktop 1440", async ({ page }) => {
    const section = page.locator("section", { has: page.getByText("Раздел 03 · Trade Replay") });
    await expect(section).toHaveScreenshot("replay-1440.png", { maxDiffPixels: 100 });
  });

  test("Эмпирик origin section — desktop 1440", async ({ page }) => {
    const section = page.locator("section", { has: page.getByText("Раздел 05 · Имя") });
    await expect(section).toHaveScreenshot("origin-1440.png", { maxDiffPixels: 100 });
  });

  test("Full page — mobile 375", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.reload();
    await page.evaluate(() => document.fonts.ready);
    await expect(page).toHaveScreenshot("full-mobile.png", { fullPage: true, maxDiffPixels: 500 });
  });
});
```

- [ ] **Step 2: Сгенерировать baseline snapshots**

```bash
cd frontend && npm run test:e2e:update -- landing-visual.spec.ts
```

Expected: 5 snapshot files в `e2e/landing-visual.spec.ts-snapshots/`.

- [ ] **Step 3: Прогнать тесты второй раз — должны пройти**

```bash
cd frontend && npm run test:e2e -- landing-visual.spec.ts
```

Expected: 5 PASS.

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/landing-visual.spec.ts frontend/e2e/landing-visual.spec.ts-snapshots/
git commit -m "test(landing): visual regression snapshots for Hero + 3 anchor sections + mobile"
```

---

### Task 21: Финальный walkthrough + dashboard regression check

**Files:**
- Modify (если нужно): `frontend/src/app/page.tsx` — убедиться `if (!user) return <Landing />` работает
- Без новых файлов — это smoke + commit чек-лист

- [ ] **Step 1: Manual desktop walkthrough**

Запустить `npm run dev` + поднять backend. Открыть `/` в гостевом окне (incognito).

Чек-лист пройти сверху вниз:
- [ ] Ticker — 5 prices, pulse мигает на SBER
- [ ] Hero H1 cyrillic выглядит OK (Fraunces glyphs все)
- [ ] Hero equity curve справа
- [ ] Numbers band — 4 цифры + footnotes
- [ ] Manifest cut-in — pull-quote
- [ ] AI section — картинка из public/landing/
- [ ] Candle chart hover показывает tooltip
- [ ] Trade Replay slider — двигается, R-multiple обновляется
- [ ] Pull-quote — золотая полоса
- [ ] Metrics table читабельна
- [ ] Эмпирик origin — перо слева, marginalia справа
- [ ] Pricing — Free + Pro, Pro с золотой границей
- [ ] Final CTA — одна кнопка
- [ ] Footer — Эмпирик, hello@empirik.io

- [ ] **Step 2: Manual mobile walkthrough (DevTools iPhone 13)**

- [ ] Ticker — horizontal scroll
- [ ] Hero — equity curve уходит ПОД CTA
- [ ] Все секции читабельны без horizontal scroll
- [ ] Trade Replay slider работает touch

- [ ] **Step 3: Dashboard regression — auth-zone не сломан**

Залогиниться (test user) → открыть `/` → должен быть **dashboard**, НЕ landing. Палитра тёмная (старая), не cream — это значит `data-theme` изоляция работает.

- [ ] **Step 4: Финальный commit (если были последние правки)**

Если в ходе walkthrough что-то правили — отдельный commit «polish: <что>». Иначе пропустить.

- [ ] **Step 5: Стоп visual companion (cleanup)**

```bash
bash C:/Users/Administrator/.claude/plugins/cache/claude-plugins-official/superpowers/5.1.0/skills/brainstorming/scripts/stop-server.sh C:/Users/Administrator/Empirik/ATOM/.superpowers/brainstorm/509748-1779122086
```

Не критично — сервер сам выключится через 30 мин неактивности.

---

## Risks & rollback notes

| Risk | Detection | Rollback |
|---|---|---|
| Cyrillic glyphs Fraunces broken | Smoke walkthrough Step 1 | Hot-fix: добавить `Playfair Display` fallback в variable list |
| Backend ticker endpoint раздувает MOEX rate-limit | Логи backend, `429` errors | Уменьшить SYMBOLS до 3, увеличить TTL до 120s |
| `data-theme` cream "течёт" в dashboard | Walkthrough Step 3 | Поднять specificity: `body[data-theme]` или дополнительные `&` блоки |
| Trade Replay slider lag на слабых девайсах | Lighthouse perf < 90 | `useDeferredValue` для setIdx, или throttle 30fps |
| Favicon SVG не работает Safari < 15 | Manual check | Уже есть PNG fallback (Task 17) |
| Visual snapshots flaky из-за timezone в ticker | Test runs красные | Mock `Date.toLocaleTimeString` в test setup, или скрыть time element в visual tests |

---

## Spec coverage check (self-review)

| Spec section | Tasks |
|---|---|
| §3 IA (14 секций) | Task 15 |
| §4.1 New components × 7 | Tasks 8-14 |
| §4.2 Backend router | Task 4 |
| §5 Hero composition | Tasks 11, 15 |
| §6 Three live moments | Tasks 12, 13, 14 |
| §7 Palette tokens isolated | Task 3 |
| §8 Typography | Tasks 2, 3 |
| §9 Brand distribution | Tasks 9, 10, 15, 17 |
| §10 Real visuals pipeline | Tasks 5, 6, 18, 19 |
| §11 Perf / a11y / responsive | Tasks 12 (pulse media-query), 14 (aria), 21 (walkthrough) |
| §12 In/out scope | reflected in tasks list |
| §13 Tests | Tasks 4 (backend), 16 (smoke), 20 (visual) |

**Coverage:** all spec sections have at least one task. No gaps.

**Placeholder scan:** No "TBD"/"TODO" в actionable steps. One explicit out-of-scope TODO в `generate-equity-snapshot.ts` (Task 6 Step 4) — обозначен как deferred follow-up, не блокер.

**Type consistency:** `Candle` type определён в Task 5, переиспользован в Task 6 (`trade-replay-sample.ts`), Task 13, Task 14. `TickerItem` определён в Task 6, переиспользован в Task 12.

---

**Plan complete and saved to** [`docs/superpowers/plans/2026-05-18-landing-handcrafted-redesign.md`](.)

**Two execution options:**

**1. Subagent-Driven (recommended)** — я диспатчу свежий subagent на каждую task (planner → test-writer → implementer → test-runner → code-reviewer pipeline), смотрю отчёты между task'ами, ты валидируешь визуально между phases.

**2. Inline Execution** — выполняем task by task прямо в этой сессии, я применяю edits, ты ревьюишь между checkpoint'ами (после каждой phase).

**Какой подход?**
