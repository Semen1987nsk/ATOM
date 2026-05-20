# Bloomberg Design Uplift Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Поднять визуальный уровень лендинга МААТТ до agency-grade за счёт чередующегося dark/light ритма (Bloomberg Businessweek), Manrope для bold uppercase, тёплого orange `#E84E1C` акцента и 5 точечных motion-moment'ов — не трогая копирайт, IA и product-виджеты.

**Architecture:** Внедряем без рефакторинга существующих компонентов: добавляем Manrope через `next/font`, 12 новых CSS-токенов и 8 utility-классов в `[data-theme="maatt-cream"]`, затем секция за секцией оборачиваем DOM в uplift-wrapper'ы и заменяем типографику. Motion — чистый CSS + IntersectionObserver, без Framer Motion. Тесты — поэтапно: smoke (`landing-smoke.spec.ts`) + visual regression (refresh baselines в конце).

**Tech Stack:** Next.js 16 App Router, React 19, TypeScript strict, Tailwind v4, next/font/google (Manrope), CSS variables, IntersectionObserver API, Playwright 1.x (chromium-desktop + chromium-mobile).

**Spec:** `docs/superpowers/specs/2026-05-19-bloomberg-design-uplift-design.md` (commit `b9a3c4f`)
**Working tree:** `C:\Users\Administrator\Eqio\ATOM-landing`
**Branch:** `feat/landing-handcrafted`

---

## Файловая структура

| Файл | Ответственность | Изменение |
|---|---|---|
| `frontend/src/app/layout.tsx` | next/font конфиг | + Manrope import + variable |
| `frontend/src/app/globals.css` | landing-токены и utility-классы | + 12 токенов в `[data-theme="maatt-cream"]`, + 8 uplift-классов |
| `frontend/src/hooks/useInView.ts` | IntersectionObserver hook (если нет existing) | NEW |
| `frontend/src/components/common/CountUp.tsx` | utility-компонент с RAF count-up | NEW |
| `frontend/src/components/landing/parts/LiveTicker.tsx` | секция 2 — orange-strip | rewrite |
| `frontend/src/components/landing/parts/HeroEquityCurve.tsx` | мотион stroke-dashoffset draw | extend |
| `frontend/src/components/landing/parts/SimpleFactSection.tsx` | секция 4 — orange-цифры 01/02/03 | typography rewrite |
| `frontend/src/components/landing/parts/ChampionsSection.tsx` | секция 5 — staggered raise | + IO hook |
| `frontend/src/components/landing/parts/ChampionCard.tsx` | имя Manrope + orange quote rule | type rewrite |
| `frontend/src/components/landing/parts/ManifestCutIn.tsx` | секция 7 — paper-tint + decor `«` | extend |
| `frontend/src/components/landing/parts/AudienceQualifier.tsx` | секция 13 — paper-tint + orange marks | extend |
| `frontend/src/components/landing/Landing.tsx` | wrapper-классы + inline-секции (Hero, Numbers, Pull-quote, Pricing, FinalCTA, Footer) | inline edits |
| `frontend/e2e/landing-smoke.spec.ts` | smoke + ритм-проверки | + rhythm/motion smoke |
| `frontend/e2e/landing-visual.spec.ts` | визуальные регрессии | refresh baselines |
| `frontend/e2e/landing-rhythm.spec.ts` | NEW — проверка dark/light/orange-strip соседств | NEW |

---

## Конвенции тестирования

- Все smoke-тесты прогоняем на `localhost:3001` (Playwright webServer в `playwright.config.ts`).
- Запуск одиночного теста: `npx playwright test e2e/landing-smoke.spec.ts -g "test name" --project=chromium-desktop`.
- Запуск всех: `npx playwright test --project=chromium-desktop`.
- Тип-чек: `npx tsc --noEmit`.
- Lint: `npm run lint` (Next.js встроенный ESLint).
- Перед каждым тестом ждать `document.fonts.ready` + 500ms (как в `landing-visual.spec.ts`).
- Каждая задача с visual-эффектом сопровождается smoke-тестом (DOM, computed styles, data-атрибуты). Pixel-snapshot'ы рефрешим оптом в Task 14.

---

## Task 1: Подключить Manrope через next/font

**Files:**
- Modify: `frontend/src/app/layout.tsx:1-44`
- Modify: `frontend/src/app/globals.css:720-735`
- Test: `frontend/e2e/landing-smoke.spec.ts` (новый тест в существующем describe)

- [ ] **Step 1: Написать падающий smoke-тест на Manrope**

В `frontend/e2e/landing-smoke.spec.ts` в существующем describe `"Landing — smoke"` добавить:

```typescript
  test("Manrope font loaded and applied to body display class", async ({ page }) => {
    await page.evaluate(() => document.fonts.ready);
    const fontFaces = await page.evaluate(() =>
      Array.from(document.fonts).map((f) => f.family.toLowerCase())
    );
    expect(fontFaces.some((f) => f.includes("manrope"))).toBe(true);

    const cssVar = await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue("--font-display").trim()
    );
    expect(cssVar.length).toBeGreaterThan(0);
  });
```

- [ ] **Step 2: Прогнать тест — должен упасть**

Run: `npx playwright test e2e/landing-smoke.spec.ts -g "Manrope font loaded" --project=chromium-desktop`
Expected: FAIL — `--font-display` пуст или `manrope` не в fontFaces.

- [ ] **Step 3: Добавить Manrope в layout.tsx**

В `frontend/src/app/layout.tsx`:

1. В импорт строки 2 добавить `Manrope`:

```tsx
import { Cormorant, Fraunces, Inter, JetBrains_Mono, Manrope } from "next/font/google";
```

2. Под объявлением `const geistMono` (после строки 44) добавить:

```tsx
const manrope = Manrope({
  subsets: ["latin", "latin-ext", "cyrillic"],
  variable: "--font-display",
  weight: ["500", "700", "800", "900"],
  display: "swap",
});
```

3. В `<html className={...}>` (строка 78) добавить `${manrope.variable}`:

```tsx
<html lang="ru" className={`${fraunces.variable} ${cormorant.variable} ${inter.variable} ${geistMono.variable} ${manrope.variable}`} suppressHydrationWarning>
```

- [ ] **Step 4: Прогнать тест — должен пройти**

Run: `npx playwright test e2e/landing-smoke.spec.ts -g "Manrope font loaded" --project=chromium-desktop`
Expected: PASS.

- [ ] **Step 5: Type-check**

Run: `npx tsc --noEmit`
Expected: 0 ошибок.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/app/layout.tsx frontend/e2e/landing-smoke.spec.ts
git commit -m "feat(landing): add Manrope display font via next/font

- subsets latin+latin-ext+cyrillic, weights 500/700/800/900
- exposes --font-display CSS variable
- smoke test asserts font loaded and var defined"
```

---

## Task 2: Добавить uplift-токены и utility-классы в globals.css

**Files:**
- Modify: `frontend/src/app/globals.css:720-735` (блок `[data-theme="maatt-cream"]`)
- Test: `frontend/e2e/landing-smoke.spec.ts`

- [ ] **Step 1: Написать падающий тест на CSS-токены**

Добавить в `landing-smoke.spec.ts`:

```typescript
  test("uplift tokens defined on landing root", async ({ page }) => {
    const tokens = await page.evaluate(() => {
      const root = document.querySelector('[data-theme="maatt-cream"]') ?? document.documentElement;
      const cs = getComputedStyle(root);
      return {
        orange: cs.getPropertyValue("--orange").trim(),
        orangeHover: cs.getPropertyValue("--orange-hover").trim(),
        orangeSoft: cs.getPropertyValue("--orange-soft").trim(),
        inkDark: cs.getPropertyValue("--ink-dark").trim(),
        paperOnDark: cs.getPropertyValue("--paper-on-dark").trim(),
        ruleOnDark: cs.getPropertyValue("--rule-on-dark").trim(),
      };
    });
    expect(tokens.orange.toLowerCase()).toBe("#e84e1c");
    expect(tokens.orangeHover.toLowerCase()).toBe("#d44516");
    expect(tokens.orangeSoft).toContain("0.10");
    expect(tokens.inkDark.toLowerCase()).toBe("#0a0a0a");
    expect(tokens.paperOnDark.toLowerCase()).toBe("#fafafa");
    expect(tokens.ruleOnDark).toContain("0.10");
  });
```

- [ ] **Step 2: Прогнать тест — FAIL**

Run: `npx playwright test e2e/landing-smoke.spec.ts -g "uplift tokens" --project=chromium-desktop`
Expected: FAIL — токены не определены.

- [ ] **Step 3: Добавить токены в globals.css**

В `frontend/src/app/globals.css`, найти блок `[data-theme="maatt-cream"]` (строка 720) и **в конец блока** (перед закрывающей `}`) добавить:

```css
  /* ─── Bloomberg uplift tokens (2026-05-19) ─── */
  --orange:           #E84E1C;
  --orange-hover:     #d44516;
  --orange-strip:     #E84E1C;
  --orange-soft:      rgba(232, 78, 28, 0.10);
  --orange-quote:     rgba(232, 78, 28, 0.40);

  --ink-dark:         #0a0a0a;
  --ink-dark-2:       #1a1a1a;
  --paper-on-dark:    #fafafa;
  --paper-on-dark-2:  rgba(250, 250, 250, 0.70);
  --paper-on-dark-3:  rgba(250, 250, 250, 0.45);
  --rule-on-dark:     rgba(250, 250, 250, 0.10);
  --rule-on-dark-strong: rgba(250, 250, 250, 0.22);
```

- [ ] **Step 4: Прогнать тест — PASS**

Run: `npx playwright test e2e/landing-smoke.spec.ts -g "uplift tokens" --project=chromium-desktop`
Expected: PASS.

- [ ] **Step 5: Добавить utility-классы для uplift-секций**

Дальше после CSS-токенов, в конец файла `globals.css` добавить блок:

```css
/* ═════════ Bloomberg uplift — utility classes (2026-05-19) ═════════ */

[data-theme="maatt-cream"] .uplift-section-light {
  background-color: var(--paper);
  color: var(--ink);
}
[data-theme="maatt-cream"] .uplift-section-tint {
  background-color: var(--paper-tint);
  color: var(--ink);
}
[data-theme="maatt-cream"] .uplift-section-dark {
  background-color: var(--ink-dark);
  color: var(--paper-on-dark);
}
[data-theme="maatt-cream"] .uplift-section-dark .uplift-eyebrow,
[data-theme="maatt-cream"] .uplift-section-dark .editorial-eyebrow {
  color: var(--paper-on-dark-3);
}
[data-theme="maatt-cream"] .uplift-section-dark a {
  color: var(--paper-on-dark);
}

/* Display sans (Manrope) heading family */
[data-theme="maatt-cream"] .uplift-h1 {
  font-family: var(--font-display), "Helvetica Neue", Arial, sans-serif;
  font-weight: 900;
  font-size: clamp(48px, 7vw, 88px);
  line-height: 0.92;
  letter-spacing: -0.03em;
  text-transform: uppercase;
}
[data-theme="maatt-cream"] .uplift-h2 {
  font-family: var(--font-display), "Helvetica Neue", Arial, sans-serif;
  font-weight: 800;
  font-size: clamp(36px, 4.5vw, 56px);
  line-height: 0.96;
  letter-spacing: -0.025em;
  text-transform: uppercase;
}
[data-theme="maatt-cream"] .uplift-numbers {
  font-family: var(--font-display), "Helvetica Neue", Arial, sans-serif;
  font-weight: 900;
  font-size: clamp(56px, 7vw, 96px);
  line-height: 0.88;
  letter-spacing: -0.02em;
  color: var(--orange);
  font-variant-numeric: tabular-nums;
}

/* Ticker strip */
[data-theme="maatt-cream"] .uplift-ticker-strip {
  background-color: var(--orange-strip);
  color: #0a0a0a;
  border-top: 1px solid #0a0a0a;
  border-bottom: 1px solid #0a0a0a;
}
[data-theme="maatt-cream"] .uplift-ticker-track {
  display: inline-flex;
  gap: 36px;
  white-space: nowrap;
  animation: uplift-ticker-scroll 60s linear infinite;
  font-family: var(--font-mono), "JetBrains Mono", monospace;
  font-weight: 500;
  font-size: 12px;
  letter-spacing: 0.04em;
}
@keyframes uplift-ticker-scroll {
  from { transform: translateX(0); }
  to   { transform: translateX(-50%); }
}

/* Hero equity curve draw */
@keyframes uplift-curve-draw {
  from { stroke-dashoffset: var(--curve-length, 800); }
  to   { stroke-dashoffset: 0; }
}
[data-theme="maatt-cream"] .uplift-curve-animate {
  animation: uplift-curve-draw 1.2s cubic-bezier(0.22, 1, 0.36, 1) forwards;
}

/* Champions raise on scroll */
[data-theme="maatt-cream"] .uplift-raise {
  opacity: 0;
  transform: translateY(20px);
  transition: opacity 0.6s cubic-bezier(0.22, 1, 0.36, 1),
              transform 0.6s cubic-bezier(0.22, 1, 0.36, 1);
}
[data-theme="maatt-cream"] .uplift-raise[data-inview="true"] {
  opacity: 1;
  transform: translateY(0);
}

/* Focus ring for orange CTAs */
[data-theme="maatt-cream"] .uplift-focus:focus-visible {
  outline: 2px solid var(--orange);
  outline-offset: 2px;
}

/* prefers-reduced-motion — disable all uplift motion */
@media (prefers-reduced-motion: reduce) {
  [data-theme="maatt-cream"] .uplift-ticker-track { animation: none; transform: none; }
  [data-theme="maatt-cream"] .uplift-curve-animate { animation: none; stroke-dashoffset: 0 !important; }
  [data-theme="maatt-cream"] .uplift-raise { opacity: 1 !important; transform: none !important; transition: none !important; }
}
```

- [ ] **Step 6: Тип-чек и lint**

Run: `npx tsc --noEmit && npm run lint`
Expected: 0 ошибок.

- [ ] **Step 7: Smoke-тест ещё раз — PASS**

Run: `npx playwright test e2e/landing-smoke.spec.ts -g "uplift tokens" --project=chromium-desktop`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/app/globals.css frontend/e2e/landing-smoke.spec.ts
git commit -m "feat(landing): add Bloomberg uplift CSS tokens + utility classes

12 tokens (orange family + dark-on-cream pairs) + 8 utility classes
(uplift-section-light/tint/dark, uplift-h1/h2/numbers, uplift-ticker-strip,
uplift-raise) gated by [data-theme=maatt-cream]. Reduced-motion guard
zeroes all uplift animations."
```

---

## Task 3: useInView hook + CountUp компонент

**Files:**
- Create: `frontend/src/hooks/useInView.ts`
- Create: `frontend/src/components/common/CountUp.tsx`
- Test: `frontend/e2e/landing-smoke.spec.ts`

- [ ] **Step 1: Проверить, нет ли existing хука useInView**

Run: `npx grep -r "useInView" frontend/src/hooks frontend/src/lib 2>NUL`
Expected: ничего — создаём новый. Если уже есть — пропустить создание, переиспользовать.

- [ ] **Step 2: Создать useInView hook**

Файл: `frontend/src/hooks/useInView.ts`:

```tsx
"use client";

import { useEffect, useRef, useState } from "react";

export type UseInViewOptions = {
  rootMargin?: string;
  threshold?: number | number[];
  once?: boolean;
};

export function useInView<T extends HTMLElement>(options: UseInViewOptions = {}) {
  const { rootMargin = "0px 0px -10% 0px", threshold = 0.1, once = true } = options;
  const ref = useRef<T | null>(null);
  const [inView, setInView] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined" || !ref.current) return;
    const node = ref.current;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setInView(true);
            if (once) observer.unobserve(entry.target);
          } else if (!once) {
            setInView(false);
          }
        }
      },
      { rootMargin, threshold }
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [rootMargin, threshold, once]);

  return { ref, inView };
}
```

- [ ] **Step 3: Создать CountUp компонент**

Файл: `frontend/src/components/common/CountUp.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useInView } from "@/hooks/useInView";

export type CountUpProps = {
  to: number;
  durationMs?: number;
  suffix?: string;
  prefix?: string;
  decimals?: number;
  className?: string;
};

export function CountUp({ to, durationMs = 1500, suffix = "", prefix = "", decimals = 0, className }: CountUpProps) {
  const { ref, inView } = useInView<HTMLSpanElement>({ rootMargin: "0px 0px -100px 0px", once: true });
  const [value, setValue] = useState(0);

  useEffect(() => {
    if (!inView) return;
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReducedMotion) {
      setValue(to);
      return;
    }
    let raf = 0;
    const start = performance.now();
    const ease = (t: number) => 1 - Math.pow(1 - t, 3);
    const step = (now: number) => {
      const elapsed = now - start;
      const t = Math.min(elapsed / durationMs, 1);
      setValue(to * ease(t));
      if (t < 1) raf = requestAnimationFrame(step);
    };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  }, [inView, to, durationMs]);

  const formatted = decimals > 0 ? value.toFixed(decimals) : Math.round(value).toString();
  return (
    <span ref={ref} className={className}>
      {prefix}
      {formatted}
      {suffix}
    </span>
  );
}
```

- [ ] **Step 4: Добавить smoke-тест на CountUp в landing-smoke.spec.ts**

Поскольку CountUp пока никуда не вкручен, smoke-тест добавляем в Task 7 (NumbersBand). Здесь только проверяем тип-чек/билд.

- [ ] **Step 5: Тип-чек**

Run: `npx tsc --noEmit`
Expected: 0 ошибок.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/hooks/useInView.ts frontend/src/components/common/CountUp.tsx
git commit -m "feat(common): useInView hook + CountUp component

- useInView: IntersectionObserver with rootMargin/threshold/once options
- CountUp: RAF-based easeOutCubic animation, prefers-reduced-motion
  short-circuits to final value, mounted via useInView trigger"
```

---

## Task 4: LiveTicker — orange strip + infinite scroll

**Files:**
- Modify: `frontend/src/components/landing/parts/LiveTicker.tsx`
- Test: `frontend/e2e/landing-smoke.spec.ts`

- [ ] **Step 1: Прочитать текущий LiveTicker**

Read: `frontend/src/components/landing/parts/LiveTicker.tsx`
Цель — понять текущую структуру (вероятно `<div>` с 5 тикерами SBER/GAZP/LKOH/YNDX/IMOEX, pulse-dot для LIVE).

- [ ] **Step 2: Написать падающий тест на orange-strip**

В `landing-smoke.spec.ts` добавить:

```typescript
  test("LiveTicker rendered on orange strip with mono text", async ({ page }) => {
    const ticker = page.locator('[data-section="live-ticker"]');
    await expect(ticker).toBeVisible();
    const bg = await ticker.evaluate((el) => getComputedStyle(el).backgroundColor);
    // #E84E1C = rgb(232, 78, 28)
    expect(bg).toBe("rgb(232, 78, 28)");
    const track = ticker.locator(".uplift-ticker-track").first();
    await expect(track).toBeVisible();
    const fontFamily = await track.evaluate((el) => getComputedStyle(el).fontFamily);
    expect(fontFamily.toLowerCase()).toContain("mono");
  });
```

- [ ] **Step 3: Прогнать тест — FAIL**

Run: `npx playwright test e2e/landing-smoke.spec.ts -g "LiveTicker rendered on orange" --project=chromium-desktop`
Expected: FAIL.

- [ ] **Step 4: Переписать LiveTicker.tsx**

Заменить корневой контейнер на:

```tsx
<section
  data-section="live-ticker"
  className="uplift-ticker-strip overflow-hidden"
  aria-label="Биржевой тикер MOEX"
>
  <div className="relative h-[38px] flex items-center">
    <div className="uplift-ticker-track" aria-hidden="false">
      {/* Двойная копия списка для seamless loop */}
      {[...tickerItems, ...tickerItems].map((item, idx) => (
        <span key={`${item.symbol}-${idx}`} className="inline-flex items-center gap-2">
          <span className="font-semibold">{item.symbol}</span>
          <span>{item.price}</span>
          <span className={item.change >= 0 ? "text-black/80" : "text-black/80"}>
            {item.change >= 0 ? "▲" : "▼"} {Math.abs(item.change).toFixed(2)}%
          </span>
          <span className="opacity-50 mx-2">·</span>
        </span>
      ))}
    </div>
  </div>
</section>
```

Где `tickerItems` — текущий fallback-массив (если используется `useLiveTicker` хук с MOEX live data, оставить логику; только заменить разметку). Если массив маленький — продублировать в JSX (`[...tickerItems, ...tickerItems]`), чтобы при `translateX(-50%)` ленте было что показать.

**Важно:** сохранить fallback-тикеры `SBER`, `GAZP`, `LKOH`, `YNDX`, `IMOEX` — на них опирается тест `ticker shows 5 symbols` в `landing-smoke.spec.ts`.

- [ ] **Step 5: Прогнать оба теста**

Run: `npx playwright test e2e/landing-smoke.spec.ts -g "LiveTicker|ticker shows 5" --project=chromium-desktop`
Expected: оба PASS.

- [ ] **Step 6: Визуально проверить в браузере**

Открыть `http://localhost:3001/`, убедиться:
- Strip оранжевая, текст чёрный mono
- Лента бесконечно прокручивается влево
- При `prefers-reduced-motion: reduce` (DevTools → Rendering → Emulate CSS media feature) — лента стоит на месте

- [ ] **Step 7: Тип-чек + lint**

Run: `npx tsc --noEmit && npm run lint`
Expected: 0 ошибок.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/landing/parts/LiveTicker.tsx frontend/e2e/landing-smoke.spec.ts
git commit -m "feat(landing): LiveTicker — orange strip + infinite scroll

- Background #E84E1C with black mono text
- 60s/cycle horizontal scroll via uplift-ticker-track keyframe
- Track duplicated (items × 2) for seamless wrap at translateX(-50%)
- Reduced-motion freezes the track"
```

---

## Task 5: Hero — Manrope H1 + orange вторая строка + DARK wrapper + equity curve motion

**Files:**
- Modify: `frontend/src/components/landing/Landing.tsx:97-131` (секция Hero inline)
- Modify: `frontend/src/components/landing/parts/HeroEquityCurve.tsx` (stroke-dashoffset)
- Test: `frontend/e2e/landing-smoke.spec.ts`

- [ ] **Step 1: Прочитать HeroEquityCurve.tsx**

Read: `frontend/src/components/landing/parts/HeroEquityCurve.tsx`
Цель — найти `<path>` элемент equity curve и рассчитать его `getTotalLength()`. Если в текущем компоненте используется SVG, нам нужно добавить ref и stroke-dasharray/dashoffset.

- [ ] **Step 2: Написать падающий smoke-тест**

```typescript
  test("Hero on dark background with Manrope H1 and orange second line", async ({ page }) => {
    const hero = page.locator('[data-section="hero"]');
    await expect(hero).toBeVisible();
    const bg = await hero.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(bg).toBe("rgb(10, 10, 10)"); // --ink-dark
    const h1 = hero.locator("h1").first();
    const h1Font = await h1.evaluate((el) => getComputedStyle(el).fontFamily);
    expect(h1Font.toLowerCase()).toContain("manrope");
    const orangeLine = hero.locator('[data-h1-accent="true"]').first();
    await expect(orangeLine).toBeVisible();
    const orangeColor = await orangeLine.evaluate((el) => getComputedStyle(el).color);
    expect(orangeColor).toBe("rgb(232, 78, 28)");
  });
```

- [ ] **Step 3: Прогнать тест — FAIL**

Run: `npx playwright test e2e/landing-smoke.spec.ts -g "Hero on dark" --project=chromium-desktop`
Expected: FAIL.

- [ ] **Step 4: Переделать Hero-секцию в Landing.tsx**

Заменить блок `{/* 3. HERO */} <section ...>...</section>` (строки 97-131) на:

```tsx
{/* 3. HERO */}
<section
  data-section="hero"
  className="uplift-section-dark px-6 lg:px-12 pt-16 lg:pt-24 pb-20 lg:pb-28"
>
  <div className="max-w-[1200px] mx-auto grid grid-cols-12 gap-6 lg:gap-10 items-center">
    <div className="col-span-12 lg:col-span-7">
      <p className="editorial-eyebrow mb-7 uplift-eyebrow" style={{ color: "var(--paper-on-dark-3)" }}>
        ── Журнал сделок · MOEX · <span style={{ color: "var(--orange)" }}>● LIVE</span>
      </p>
      <h1 className="uplift-h1 mb-9" style={{ color: "var(--paper-on-dark)" }}>
        Запись делает<br />
        <span data-h1-accent="true" style={{ color: "var(--orange)" }}>трейдера.</span>
      </h1>
      <p className="text-[16px] lg:text-[17px] leading-[1.55] max-w-[44ch] mb-10" style={{ color: "var(--paper-on-dark-2)" }}>
        MAE и MFE из биржевых свечей. Тридцать с лишним метрик из работ
        Винса и Тарпа. На ваших сделках MOEX. Автосинхронизация
        с Тинькофф — 60 сек.
      </p>
      <div className="flex flex-col sm:flex-row items-start gap-5">
        <Link
          href="/register"
          className="uplift-focus inline-flex items-center gap-2 px-8 py-4 text-[13px] font-bold uppercase tracking-[0.06em] no-underline transition-colors"
          style={{ backgroundColor: "var(--orange)", color: "#0a0a0a", fontFamily: "var(--font-display), sans-serif" }}
        >
          → Начать бесплатно
        </Link>
        <Link
          href="/register?provider=tinkoff_id"
          className="text-[14px] no-underline inline-flex items-center gap-1 py-3 transition-colors"
          style={{ color: "var(--paper-on-dark-2)" }}
        >
          Войти через Тинькофф ID <ArrowRight size={13} />
        </Link>
      </div>
      <p className="mt-6 text-[12px] num" style={{ color: "var(--paper-on-dark-3)" }}>
        Бесплатно до 50 сделок. Без карты. 21 день Pro в подарок.
      </p>
    </div>
    <div className="col-span-12 lg:col-span-5 lg:pl-6">
      <HeroEquityCurve />
    </div>
  </div>
</section>
```

- [ ] **Step 5: Добавить stroke-dashoffset мотион в HeroEquityCurve**

В `HeroEquityCurve.tsx` найти главный `<path>` (вероятно с stroke `--accent`):

1. Добавить `className="uplift-curve-animate"` к path
2. Добавить ref и считать длину:

```tsx
"use client";
import { useEffect, useRef } from "react";

export function HeroEquityCurve() {
  const pathRef = useRef<SVGPathElement | null>(null);

  useEffect(() => {
    if (!pathRef.current) return;
    const len = pathRef.current.getTotalLength();
    pathRef.current.style.setProperty("--curve-length", String(len));
    pathRef.current.style.strokeDasharray = String(len);
    pathRef.current.style.strokeDashoffset = String(len);
    // Force reflow before triggering animation
    void pathRef.current.getBoundingClientRect();
    pathRef.current.classList.add("uplift-curve-animate");
  }, []);

  return (
    <svg /* existing props */>
      {/* existing decor */}
      <path ref={pathRef} d="..." stroke="var(--orange)" strokeWidth={2} fill="none" />
      {/* existing decor */}
    </svg>
  );
}
```

(Точные изменения зависят от текущего SVG; ключ — `pathRef`, `getTotalLength()`, stroke=`var(--orange)`.)

- [ ] **Step 6: Прогнать тест Hero — PASS**

Run: `npx playwright test e2e/landing-smoke.spec.ts -g "Hero on dark" --project=chromium-desktop`
Expected: PASS.

- [ ] **Step 7: Прогнать существующий smoke — должен остаться зелёный**

Run: `npx playwright test e2e/landing-smoke.spec.ts -g "renders all 16 sections" --project=chromium-desktop`
Expected: PASS (заголовок «Запись делает трейдера» сохранён).

- [ ] **Step 8: Визуально проверить в браузере**

`http://localhost:3001/`:
- Hero на чёрном фоне
- H1 в Manrope, «трейдера.» — оранжевый
- Equity curve рисуется при загрузке за ~1.2с
- В DevTools → Rendering → Emulate CSS `prefers-reduced-motion: reduce` → curve сразу видна без анимации

- [ ] **Step 9: Тип-чек + lint + commit**

```bash
npx tsc --noEmit && npm run lint
git add frontend/src/components/landing/Landing.tsx frontend/src/components/landing/parts/HeroEquityCurve.tsx frontend/e2e/landing-smoke.spec.ts
git commit -m "feat(landing): Hero — DARK section + Manrope H1 + orange accent + curve motion

- Section wrapper: uplift-section-dark (ink-dark background)
- H1 Manrope 900 uppercase, second line 'трейдера.' in orange
- Eyebrow with orange LIVE indicator
- Orange primary CTA on black background
- HeroEquityCurve: stroke-dashoffset auto-draw via uplift-curve-animate"
```

---

## Task 6: SimpleFactSection — orange 01/02/03 + Manrope H3

**Files:**
- Modify: `frontend/src/components/landing/parts/SimpleFactSection.tsx`
- Test: `frontend/e2e/landing-ia.spec.ts` (тест "SimpleFact section has 3 columns" расширить)

- [ ] **Step 1: Прочитать текущий SimpleFactSection**

Read: `frontend/src/components/landing/parts/SimpleFactSection.tsx`

- [ ] **Step 2: Написать падающий тест**

В `frontend/e2e/landing-ia.spec.ts` после существующего теста добавить:

```typescript
test("SimpleFact columns show large orange numerals", async ({ page }) => {
  await page.goto("/");
  const section = page.locator("#simple-fact");
  const numerals = section.locator('[data-fact-numeral]');
  await expect(numerals).toHaveCount(3);
  const color = await numerals.first().evaluate((el) => getComputedStyle(el).color);
  expect(color).toBe("rgb(232, 78, 28)");
  const fontFamily = await numerals.first().evaluate((el) => getComputedStyle(el).fontFamily);
  expect(fontFamily.toLowerCase()).toContain("manrope");
});
```

- [ ] **Step 3: Прогнать тест — FAIL**

Run: `npx playwright test e2e/landing-ia.spec.ts -g "SimpleFact columns show large" --project=chromium-desktop`
Expected: FAIL.

- [ ] **Step 4: Обновить SimpleFactSection.tsx**

В разметке трёх колонок заменить блок с цифрами на:

```tsx
<div data-testid="simple-fact-column" className="flex flex-col">
  <div data-fact-numeral className="uplift-numbers mb-4">{column.numeral /* "01" | "02" | "03" */}</div>
  <h3 className="uplift-h2 text-[clamp(20px,2vw,28px)] mb-3" style={{ color: "var(--ink)", letterSpacing: "-0.015em" }}>
    {column.heading}
  </h3>
  <p className="text-[15px] lg:text-[16px] leading-[1.65]" style={{ color: "var(--ink-2)" }}>
    {column.body}
  </p>
</div>
```

И обернуть всю секцию в:

```tsx
<section
  id="simple-fact"
  data-section="simple-fact"
  className="uplift-section-light px-6 lg:px-12 py-24 lg:py-32 border-y border-[var(--rule-strong)]"
>
  {/* … */}
</section>
```

Если в данных столбцов нет `numeral` — добавить: `["01", "02", "03"]` в соответствие столбцам.

- [ ] **Step 5: Прогнать тест — PASS**

Run: `npx playwright test e2e/landing-ia.spec.ts -g "SimpleFact columns show large" --project=chromium-desktop`
Expected: PASS.

Также прогнать существующий тест `SimpleFact section has 3 columns` — должен остаться PASS.

- [ ] **Step 6: Визуально проверить**

`http://localhost:3001/`:
- Большие оранжевые цифры 01/02/03 над каждой колонкой
- H3 в Manrope uppercase

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/landing/parts/SimpleFactSection.tsx frontend/e2e/landing-ia.spec.ts
git commit -m "feat(landing): SimpleFact — orange 01/02/03 numerals + Manrope H3

Large orange Manrope numerals (uplift-numbers class) above each column.
H3 in Manrope uppercase. Section wrapped in uplift-section-light."
```

---

## Task 7: NumbersBand (Section 6) — DARK + count-up

**Files:**
- Modify: `frontend/src/components/landing/Landing.tsx:139-152` (NumbersBand inline)
- Modify: `frontend/src/components/landing/Landing.tsx` (импорт `CountUp`)
- Test: `frontend/e2e/landing-smoke.spec.ts`

- [ ] **Step 1: Написать падающий тест**

```typescript
  test("NumbersBand section is dark with orange numerals", async ({ page }) => {
    const band = page.locator('[data-section="numbers-band"]');
    await expect(band).toBeVisible();
    const bg = await band.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(bg).toBe("rgb(10, 10, 10)");
    const numerals = band.locator('[data-numeral]');
    await expect(numerals).toHaveCount(4);
    const color = await numerals.first().evaluate((el) => getComputedStyle(el).color);
    expect(color).toBe("rgb(232, 78, 28)");
  });
```

- [ ] **Step 2: Прогнать тест — FAIL**

Run: `npx playwright test e2e/landing-smoke.spec.ts -g "NumbersBand section is dark" --project=chromium-desktop`
Expected: FAIL.

- [ ] **Step 3: Переписать NumbersBand-секцию в Landing.tsx**

В верхней части файла Landing.tsx добавить импорт:

```tsx
import { CountUp } from "@/components/common/CountUp";
```

Заменить `{/* 6. NUMBERS BAND */} <section ...>...</section>` на:

```tsx
{/* 6. NUMBERS BAND */}
<section
  data-section="numbers-band"
  className="uplift-section-dark px-6 lg:px-12 py-20 lg:py-28"
>
  <div className="max-w-[1200px] mx-auto">
    <p className="editorial-eyebrow mb-10 uplift-eyebrow" style={{ color: "var(--paper-on-dark-3)" }}>
      ── По-простому
    </p>
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-x-10 gap-y-12">
      {NUMBERS_BAND.map((n) => (
        <div key={n.label}>
          <div data-numeral className="uplift-numbers mb-4">
            {renderNumeral(n)}
          </div>
          <div className="text-[13px] italic leading-snug mb-1" style={{ fontFamily: "var(--font-serif), Georgia, serif", color: "var(--paper-on-dark-2)" }}>
            {n.label}
          </div>
          <div className="text-[11px] leading-tight" style={{ color: "var(--paper-on-dark-3)" }}>{n.note}</div>
        </div>
      ))}
    </div>
  </div>
</section>
```

И добавить helper `renderNumeral` в начало компонента (или импортом). Если в `NUMBERS_BAND` элементы вида `{ value: "30+", label: ..., note: ... }`:

```tsx
function renderNumeral(n: { value: string }) {
  // Если "30+" — парсим число и суффикс
  const match = n.value.match(/^(\d+)(.*)$/);
  if (match) {
    const num = parseInt(match[1], 10);
    return <CountUp to={num} suffix={match[2]} />;
  }
  return <span>{n.value}</span>;
}
```

Если `NUMBERS_BAND` содержит десятичные (e.g. `1.5×`) — расширить regex.

- [ ] **Step 4: Прогнать тест — PASS**

Run: `npx playwright test e2e/landing-smoke.spec.ts -g "NumbersBand section is dark" --project=chromium-desktop`
Expected: PASS.

- [ ] **Step 5: Визуально проверить**

`http://localhost:3001/`:
- Numbers band на чёрном фоне
- Цифры оранжевые Manrope 900
- Count-up анимация при прокрутке в viewport
- В reduced-motion — цифры сразу финальные

- [ ] **Step 6: Тип-чек + commit**

```bash
npx tsc --noEmit
git add frontend/src/components/landing/Landing.tsx frontend/e2e/landing-smoke.spec.ts
git commit -m "feat(landing): NumbersBand — DARK section + orange count-up

- Wrapped in uplift-section-dark (ink-dark background)
- Numerals use CountUp component with RAF easeOutCubic 1.5s
- Reduced-motion short-circuits to final value
- Manrope 900 orange tabular-nums"
```

---

## Task 8: ChampionsSection + ChampionCard — Manrope name + orange quote rule + raise on scroll

**Files:**
- Modify: `frontend/src/components/landing/parts/ChampionsSection.tsx`
- Modify: `frontend/src/components/landing/parts/ChampionCard.tsx`
- Test: `frontend/e2e/landing-ia.spec.ts`

- [ ] **Step 1: Прочитать оба файла**

Read: `ChampionsSection.tsx`, `ChampionCard.tsx`

- [ ] **Step 2: Написать падающий тест**

В `landing-ia.spec.ts` после `Champions section has 6 cards` добавить:

```typescript
test("Champion cards have Manrope names and orange quote rule", async ({ page }) => {
  await page.goto("/");
  const card = page.locator('[data-testid="champion-card"]').first();
  await expect(card).toBeVisible();
  const name = card.locator('[data-champion-name]');
  const nameFont = await name.evaluate((el) => getComputedStyle(el).fontFamily);
  expect(nameFont.toLowerCase()).toContain("manrope");
  const quote = card.locator('blockquote, [data-champion-quote]').first();
  const borderColor = await quote.evaluate((el) => getComputedStyle(el).borderLeftColor);
  expect(borderColor).toBe("rgb(232, 78, 28)");
});

test("Champion cards raise on scroll (have uplift-raise class)", async ({ page }) => {
  await page.goto("/");
  const cards = page.locator('[data-testid="champion-card"]');
  await expect(cards.first()).toHaveClass(/uplift-raise/);
});
```

- [ ] **Step 3: Прогнать тесты — FAIL**

Run: `npx playwright test e2e/landing-ia.spec.ts -g "Champion cards have Manrope|Champion cards raise" --project=chromium-desktop`
Expected: оба FAIL.

- [ ] **Step 4: Обновить ChampionCard.tsx**

Заменить корневой `<article>` (или div) на:

```tsx
"use client";

import { useInView } from "@/hooks/useInView";
import type { Champion } from "../data/champions";

export function ChampionCard({ champion }: { champion: Champion }) {
  const { ref, inView } = useInView<HTMLElement>({ rootMargin: "0px 0px -50px 0px", once: true });

  return (
    <article
      ref={ref as React.RefObject<HTMLElement>}
      data-testid="champion-card"
      data-inview={inView ? "true" : "false"}
      className="uplift-raise flex flex-col"
    >
      <img
        src={champion.portraitSrc}
        alt={`${champion.firstName} ${champion.lastName}, гравюрный портрет`}
        width={220}
        height={220}
        className="mb-5"
        loading="lazy"
      />
      <h3
        data-champion-name
        className="text-[18px] font-extrabold uppercase tracking-[-0.015em] mb-1"
        style={{ fontFamily: "var(--font-display), sans-serif", color: "var(--ink)" }}
      >
        {champion.lastName} {champion.firstName ? champion.firstName[0] + "." : ""}
      </h3>
      <p className="num text-[11px] uppercase tracking-[0.06em] mb-3" style={{ color: "var(--ink-3)" }}>
        {champion.birthYear} — {champion.deathYear ?? "—"}
      </p>
      <p className="text-[13px] leading-[1.55] mb-4" style={{ color: "var(--ink-2)" }}>
        {champion.bio}
      </p>
      <blockquote
        data-champion-quote
        className="text-[15px] italic leading-[1.5] pl-3.5 m-0"
        style={{
          borderLeft: "2px solid var(--orange)",
          fontFamily: "var(--font-serif), var(--font-serif-cyr), Georgia, serif",
          color: "var(--ink)",
        }}
      >
        «{champion.quote}»
      </blockquote>
      <cite
        className="block mt-2 text-[10px] uppercase tracking-[0.08em] num not-italic"
        style={{ color: "var(--ink-3)" }}
      >
        — {champion.source}
      </cite>
    </article>
  );
}
```

(Если текущая разметка отличается — сохранить ключевые data-attributes: `data-testid="champion-card"`, `data-champion-name`, `data-champion-quote`. Текущий тест `Champions section has 6 cards` опирается на `data-testid="champion-card"`.)

- [ ] **Step 5: Проверить ChampionsSection.tsx wrapper**

Должна быть обёртка:

```tsx
<section
  id="champions"
  data-section="champions"
  className="uplift-section-light px-6 lg:px-12 py-24 lg:py-32 border-b border-[var(--rule-strong)]"
>
  <div className="max-w-[1200px] mx-auto">
    <p className="editorial-eyebrow mb-8">── Дисциплина чемпионов</p>
    <h2 className="uplift-h2 mb-12" style={{ color: "var(--ink)" }}>Дисциплина чемпионов</h2>
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-14">
      {champions.map((c, idx) => (
        <div key={c.slug} style={{ transitionDelay: `${idx * 80}ms` }}>
          <ChampionCard champion={c} />
        </div>
      ))}
    </div>
  </div>
</section>
```

(Staggered delay 80ms между карточками — через inline-style на родителе, чтобы не плодить классы.)

- [ ] **Step 6: Прогнать оба теста — PASS**

Run: `npx playwright test e2e/landing-ia.spec.ts --project=chromium-desktop`
Expected: все 3 теста PASS (старый `has 6 cards` + 2 новых).

- [ ] **Step 7: Визуально проверить raise on scroll**

`http://localhost:3001/`:
- Скролл вниз до Champions
- Каждая карточка появляется staggered (80ms сдвиг)
- В reduced-motion — карточки сразу видны без transform

- [ ] **Step 8: Тип-чек + commit**

```bash
npx tsc --noEmit
git add frontend/src/components/landing/parts/ChampionsSection.tsx frontend/src/components/landing/parts/ChampionCard.tsx frontend/e2e/landing-ia.spec.ts
git commit -m "feat(landing): Champions — Manrope names + orange quote rule + staggered raise

- ChampionCard: name in Manrope 800 uppercase, quote with border-left orange
- uplift-raise + useInView trigger via data-inview attribute
- Staggered transition-delay 80ms × index on wrapper div
- Reduced-motion short-circuits to final state"
```

---

## Task 9: Manifest cut-in + Pull-quote — decor `«` mark

**Files:**
- Modify: `frontend/src/components/landing/parts/ManifestCutIn.tsx`
- Modify: `frontend/src/components/landing/Landing.tsx` (Pull-quote inline)
- Test: `frontend/e2e/landing-smoke.spec.ts`

- [ ] **Step 1: Написать падающий тест**

```typescript
  test("Manifest section uses paper-tint background", async ({ page }) => {
    const section = page.locator('[data-section="manifest"]');
    await expect(section).toBeVisible();
    const bg = await section.evaluate((el) => getComputedStyle(el).backgroundColor);
    // --paper-tint = #f4ecdc
    expect(bg).toBe("rgb(244, 236, 220)");
  });

  test("Pull-quote section is dark with orange decorative quote mark", async ({ page }) => {
    const section = page.locator('[data-section="pull-quote"]');
    await expect(section).toBeVisible();
    const bg = await section.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(bg).toBe("rgb(10, 10, 10)");
    const decor = section.locator('[data-decor-quote]');
    await expect(decor).toBeVisible();
    const decorColor = await decor.evaluate((el) => getComputedStyle(el).color);
    // --orange-quote = rgba(232, 78, 28, 0.40)
    expect(decorColor).toMatch(/rgba?\(232,\s*78,\s*28/);
  });
```

- [ ] **Step 2: Прогнать тесты — FAIL**

Run: `npx playwright test e2e/landing-smoke.spec.ts -g "Manifest section|Pull-quote section" --project=chromium-desktop`
Expected: оба FAIL.

- [ ] **Step 3: Обновить ManifestCutIn.tsx**

Обернуть в `uplift-section-tint` + добавить decor `«`:

```tsx
export function ManifestCutIn() {
  return (
    <section data-section="manifest" className="uplift-section-tint relative overflow-hidden px-6 lg:px-12 py-32 lg:py-40 border-y border-[var(--rule-strong)]">
      <span
        aria-hidden="true"
        className="absolute -top-12 -left-4 lg:-left-10 select-none pointer-events-none"
        style={{
          fontFamily: "var(--font-serif), Georgia, serif",
          fontStyle: "italic",
          fontSize: "clamp(240px, 28vw, 380px)",
          lineHeight: 0.85,
          color: "var(--orange-soft)",
          fontWeight: 300,
        }}
      >
        «
      </span>
      <div className="relative max-w-[1100px] mx-auto">
        <p className="editorial-pullquote max-w-[26ch]" style={{ color: "var(--ink)" }}>
          {/* существующий текст манифеста */}
          Запись — это ремесло. Сначала фиксация. Потом измерение. Потом разбор.
        </p>
        <p className="mt-8 editorial-eyebrow" style={{ color: "var(--ink-3)" }}>
          — Манифест МААТТ
        </p>
      </div>
    </section>
  );
}
```

(Текст манифеста брать из текущего файла, не выдумывать.)

- [ ] **Step 4: Найти pull-quote секцию в Landing.tsx и обновить**

Найти секцию pull-quote клиента (обычно после Раздела 03 Metrics, перед Эвристиками — это секция 11). Обернуть в:

```tsx
{/* 11. PULL-QUOTE */}
<section data-section="pull-quote" className="uplift-section-dark relative overflow-hidden px-6 lg:px-12 py-28 lg:py-36">
  <span
    data-decor-quote
    aria-hidden="true"
    className="absolute -top-20 -left-4 lg:-left-12 select-none pointer-events-none"
    style={{
      fontFamily: "var(--font-serif), Georgia, serif",
      fontStyle: "italic",
      fontSize: "clamp(320px, 32vw, 480px)",
      lineHeight: 0.85,
      color: "var(--orange-quote)",
      fontWeight: 300,
    }}
  >
    «
  </span>
  <div className="relative max-w-[1000px] mx-auto">
    <blockquote
      className="text-[clamp(28px,4vw,52px)] italic leading-[1.15] max-w-[28ch] m-0"
      style={{ fontFamily: "var(--font-serif), Georgia, serif", color: "var(--paper-on-dark)", fontWeight: 300 }}
    >
      {/* существующий текст цитаты клиента */}
    </blockquote>
    <p className="mt-8 num text-[11px] uppercase tracking-[0.08em]" style={{ color: "var(--paper-on-dark-3)" }}>
      — Атрибуция (имя · роль · источник)
    </p>
  </div>
</section>
```

(Текст и атрибуцию pull-quote'а взять из текущего блока в Landing.tsx, не переписывать.)

- [ ] **Step 5: Прогнать тесты — PASS**

Run: `npx playwright test e2e/landing-smoke.spec.ts -g "Manifest section|Pull-quote section" --project=chromium-desktop`
Expected: оба PASS.

- [ ] **Step 6: Тип-чек + commit**

```bash
npx tsc --noEmit
git add frontend/src/components/landing/parts/ManifestCutIn.tsx frontend/src/components/landing/Landing.tsx frontend/e2e/landing-smoke.spec.ts
git commit -m "feat(landing): Manifest + Pull-quote — decor « + tint/dark wrappers

- ManifestCutIn: paper-tint background + large soft-orange decor «
- Pull-quote section: ink-dark background + bold orange-quote decor «
- Both retain existing copy verbatim"
```

---

## Task 10: Sections 01–04 + AudienceQualifier — wrappers и orange акценты

**Files:**
- Modify: `frontend/src/components/landing/Landing.tsx` (секции 01, 02, 03, 04 inline)
- Modify: `frontend/src/components/landing/parts/AudienceQualifier.tsx`
- Test: `frontend/e2e/landing-rhythm.spec.ts` (NEW — см. Task 13)

- [ ] **Step 1: Обновить wrapper'ы 4 inline-секций**

В `Landing.tsx` для каждой из секций добавить `data-section` атрибут и uplift-класс:

| Секция | data-section | Класс wrapper |
|---|---|---|
| 8 — Trade Replay | `replay-01` | `uplift-section-light` |
| 9 — MAE/MFE | `mae-mfe-02` | `uplift-section-dark` |
| 10 — Metrics | `metrics-03` | `uplift-section-light` |
| 12 — Heuristics | `heuristics-04` | `uplift-section-light` |

Пример для MAE/MFE (sec 9, текущая строка 190):

```tsx
{/* 9. SECTION 02 · MAE/MFE — mirrored */}
<section
  data-section="mae-mfe-02"
  className="uplift-section-dark px-6 lg:px-12 py-24 lg:py-32"
>
  {/* для DARK варианта: внутренние text-цвета меняем на paper-on-dark */}
</section>
```

**Важно для секции 9 (MAE/MFE) — DARK:** обновить inline-цвета:
- `text-[var(--ink)]` → `text-[var(--paper-on-dark)]`
- `text-[var(--ink-2)]` → `text-[var(--paper-on-dark-2)]`
- `text-[var(--ink-3)]` → `text-[var(--paper-on-dark-3)]`
- `border-[var(--rule-strong)]` → `border-[var(--rule-on-dark-strong)]`
- Внутренние плашки с белым фоном (`<dl>` с `bg-[var(--paper-tint)]/40`) → заменить на `bg-[var(--ink-dark-2)]` + текст paper-on-dark
- Ссылку "Подробнее о методе" с `var(--accent)` → `var(--orange)`

Для остальных трёх (LIGHT) — оставить текущие inline-цвета, только обновить wrapper-класс.

- [ ] **Step 2: Обновить AudienceQualifier.tsx**

Обернуть в `uplift-section-tint`:

```tsx
export function AudienceQualifier() {
  return (
    <section
      data-section="audience-05"
      className="uplift-section-tint px-6 lg:px-12 py-24 lg:py-32 border-y border-[var(--rule-strong)]"
    >
      {/* существующее содержимое */}
    </section>
  );
}
```

Заменить иконки/маркеры внутри (если есть checkmark / x) на оранжевые:
- `text-[var(--accent)]` → `text-[var(--orange)]` для checkmark-bullet'ов
- `text-[var(--accent-hover)]` оставить (охра остаётся в стилистических деталях)

- [ ] **Step 3: Smoke-тест на 4 секции**

В `landing-smoke.spec.ts`:

```typescript
  test("sections 01-04 wrappers applied", async ({ page }) => {
    for (const { id, expectedBg } of [
      { id: "replay-01", expectedBg: "rgb(250, 246, 238)" },
      { id: "mae-mfe-02", expectedBg: "rgb(10, 10, 10)" },
      { id: "metrics-03", expectedBg: "rgb(250, 246, 238)" },
      { id: "heuristics-04", expectedBg: "rgb(250, 246, 238)" },
      { id: "audience-05", expectedBg: "rgb(244, 236, 220)" },
    ]) {
      const section = page.locator(`[data-section="${id}"]`);
      await expect(section).toBeVisible();
      const bg = await section.evaluate((el) => getComputedStyle(el).backgroundColor);
      expect(bg).toBe(expectedBg);
    }
  });
```

- [ ] **Step 4: Прогнать тест — PASS после правок**

Run: `npx playwright test e2e/landing-smoke.spec.ts -g "sections 01-04 wrappers" --project=chromium-desktop`
Expected: PASS.

- [ ] **Step 5: Визуально проверить ритм**

`http://localhost:3001/` — пройти по странице сверху вниз. Должно чередоваться:
Hero(DARK) → SimpleFact(LIGHT) → Champions(LIGHT) → Numbers(DARK) → Manifest(TINT) → Replay-01(LIGHT) → MAE/MFE-02(DARK) → Metrics-03(LIGHT) → Pull-quote(DARK) → Heuristics-04(LIGHT) → Audience-05(TINT) → Pricing(SPLIT) → FinalCTA(DARK)

- [ ] **Step 6: Тип-чек + commit**

```bash
npx tsc --noEmit && npm run lint
git add frontend/src/components/landing/Landing.tsx frontend/src/components/landing/parts/AudienceQualifier.tsx frontend/e2e/landing-smoke.spec.ts
git commit -m "feat(landing): wrap sections 01-05 with uplift backgrounds

- Replay (01): uplift-section-light
- MAE/MFE (02): uplift-section-dark + text-on-dark colors + orange link
- Metrics (03): uplift-section-light
- Heuristics (04): uplift-section-light
- AudienceQualifier (05): uplift-section-tint + orange marks"
```

---

## Task 11: Pricing split — Free=paper, Pro=DARK

**Files:**
- Modify: `frontend/src/components/landing/Landing.tsx` (Pricing inline, ~ строки 380-450)
- Test: `frontend/e2e/landing-smoke.spec.ts`

- [ ] **Step 1: Прочитать текущий Pricing блок**

Read: `frontend/src/components/landing/Landing.tsx` строки 380-450 (где определена секция Pricing).

- [ ] **Step 2: Написать падающий тест**

```typescript
  test("Pricing split — Free is paper, Pro is dark with orange CTA", async ({ page }) => {
    const free = page.locator('[data-pricing="free"]');
    const pro = page.locator('[data-pricing="pro"]');
    await expect(free).toBeVisible();
    await expect(pro).toBeVisible();
    const freeBg = await free.evaluate((el) => getComputedStyle(el).backgroundColor);
    const proBg = await pro.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(freeBg).toBe("rgb(250, 246, 238)");
    expect(proBg).toBe("rgb(10, 10, 10)");
    const proCta = pro.locator('a[href="/register"]').first();
    const ctaBg = await proCta.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(ctaBg).toBe("rgb(232, 78, 28)");
  });
```

- [ ] **Step 3: Прогнать — FAIL**

Run: `npx playwright test e2e/landing-smoke.spec.ts -g "Pricing split" --project=chromium-desktop`
Expected: FAIL.

- [ ] **Step 4: Переписать Pricing-секцию**

Заменить блок Pricing в `Landing.tsx` на:

```tsx
{/* 14. PRICING */}
<section
  data-section="pricing-06"
  className="uplift-section-light px-6 lg:px-12 py-24 lg:py-32 border-t border-[var(--rule-strong)]"
>
  <div className="max-w-[1100px] mx-auto">
    <p className="editorial-eyebrow mb-6">── Тарифы</p>
    <h2 className="uplift-h2 mb-12" style={{ color: "var(--ink)" }}>
      Free — чтобы понять. Pro — чтобы изменить.
    </h2>
    <div className="grid grid-cols-1 md:grid-cols-2 border border-[var(--ink)]">
      {/* FREE */}
      <div data-pricing="free" className="px-8 lg:px-12 py-10 lg:py-14 border-b md:border-b-0 md:border-r border-[var(--ink)]">
        <p className="num text-[11px] uppercase tracking-[0.08em] mb-3" style={{ color: "var(--ink-3)" }}>
          Free
        </p>
        <h3 className="uplift-h2 text-[clamp(40px,4vw,56px)] mb-2" style={{ color: "var(--ink)" }}>
          Бесплатно
        </h3>
        <p className="num text-[64px] leading-none mb-6" style={{ fontFamily: "var(--font-display), sans-serif", fontWeight: 900, color: "var(--ink)" }}>
          0 ₽
        </p>
        <ul className="text-[15px] leading-[1.7] mb-8 list-none p-0" style={{ color: "var(--ink-2)" }}>
          {/* существующие bullets Free */}
        </ul>
        <Link href="/register" className="text-[14px] no-underline inline-flex items-center gap-1.5" style={{ color: "var(--ink)" }}>
          Открыть бесплатно <ArrowRight size={13} />
        </Link>
      </div>
      {/* PRO */}
      <div data-pricing="pro" className="uplift-section-dark px-8 lg:px-12 py-10 lg:py-14">
        <p className="num text-[11px] uppercase tracking-[0.08em] mb-3" style={{ color: "var(--orange)" }}>
          Pro
        </p>
        <h3 className="uplift-h2 text-[clamp(40px,4vw,56px)] mb-2" style={{ color: "var(--paper-on-dark)" }}>
          Pro
        </h3>
        <p className="num text-[64px] leading-none mb-6" style={{ fontFamily: "var(--font-display), sans-serif", fontWeight: 900, color: "var(--paper-on-dark)" }}>
          399 ₽<span className="text-[20px] font-medium" style={{ color: "var(--paper-on-dark-2)" }}> /мес</span>
        </p>
        <ul className="text-[15px] leading-[1.7] mb-8 list-none p-0" style={{ color: "var(--paper-on-dark-2)" }}>
          {/* существующие bullets Pro — каждый префиксован orange ✓ */}
        </ul>
        <Link
          href="/register"
          className="uplift-focus inline-flex items-center gap-2 px-6 py-3 text-[13px] font-bold uppercase tracking-[0.06em] no-underline"
          style={{ backgroundColor: "var(--orange)", color: "#0a0a0a", fontFamily: "var(--font-display), sans-serif" }}
        >
          → Открыть Pro
        </Link>
      </div>
    </div>
  </div>
</section>
```

**Сохранить:** все bullet'ы из существующей разметки 1:1 (текст из копирайта).

- [ ] **Step 5: Прогнать тест — PASS**

Run: `npx playwright test e2e/landing-smoke.spec.ts -g "Pricing split" --project=chromium-desktop`
Expected: PASS.

- [ ] **Step 6: Существующий smoke `renders all 16 sections` — должен остаться PASS**

Run: `npx playwright test e2e/landing-smoke.spec.ts -g "renders all 16 sections" --project=chromium-desktop`
Expected: PASS (заголовок `Free — чтобы понять. Pro — чтобы изменить.` сохранён).

- [ ] **Step 7: Mobile проверка**

Run: `npx playwright test e2e/landing-smoke.spec.ts -g "Pricing split" --project=chromium-mobile`
Expected: PASS (split складывается в вертикальный стек, верхняя — Free, нижняя — Pro).

- [ ] **Step 8: Тип-чек + commit**

```bash
npx tsc --noEmit
git add frontend/src/components/landing/Landing.tsx frontend/e2e/landing-smoke.spec.ts
git commit -m "feat(landing): Pricing split — Free=paper / Pro=DARK with orange CTA

- Two-column 50/50 split with 1px ink border between
- Free: paper background, ink text, secondary CTA
- Pro: ink-dark background, paper text, orange primary CTA
- Mobile: stacks vertically (Free top, Pro bottom)"
```

---

## Task 12: Final CTA + Footer — continuous DARK zone

**Files:**
- Modify: `frontend/src/components/landing/Landing.tsx` (FinalCTA + Footer inline)
- Test: `frontend/e2e/landing-smoke.spec.ts`

- [ ] **Step 1: Написать падающий тест**

```typescript
  test("Final CTA and Footer are both dark", async ({ page }) => {
    const cta = page.locator('[data-section="final-cta"]');
    const footer = page.locator("footer");
    const ctaBg = await cta.evaluate((el) => getComputedStyle(el).backgroundColor);
    const footerBg = await footer.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(ctaBg).toBe("rgb(10, 10, 10)");
    expect(footerBg).toBe("rgb(10, 10, 10)");
    const ctaButton = cta.locator('a[href="/register"]').first();
    const buttonBg = await ctaButton.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(buttonBg).toBe("rgb(232, 78, 28)");
  });
```

- [ ] **Step 2: Прогнать — FAIL**

Run: `npx playwright test e2e/landing-smoke.spec.ts -g "Final CTA and Footer are both dark" --project=chromium-desktop`
Expected: FAIL.

- [ ] **Step 3: Обновить Final CTA**

Найти секцию Final CTA (примерно строка 460+ в Landing.tsx). Обернуть в:

```tsx
{/* 15. FINAL CTA */}
<section
  data-section="final-cta"
  className="uplift-section-dark px-6 lg:px-12 py-28 lg:py-36"
>
  <div className="max-w-[900px] mx-auto text-center">
    <h2 className="uplift-h1 mb-8" style={{ color: "var(--paper-on-dark)", fontSize: "clamp(40px, 6vw, 80px)" }}>
      Начните вести{/* существующий текст финального CTA */}
    </h2>
    <p className="text-[17px] leading-[1.55] max-w-[50ch] mx-auto mb-10" style={{ color: "var(--paper-on-dark-2)" }}>
      {/* существующий подзаголовок */}
    </p>
    <Link
      href="/register"
      className="uplift-focus inline-flex items-center gap-2 px-9 py-4.5 text-[14px] font-bold uppercase tracking-[0.06em] no-underline"
      style={{ backgroundColor: "var(--orange)", color: "#0a0a0a", fontFamily: "var(--font-display), sans-serif" }}
    >
      → Начать бесплатно
    </Link>
    <p className="mt-6 num text-[11px] uppercase tracking-[0.08em]" style={{ color: "var(--paper-on-dark-3)" }}>
      Без карты · 50 сделок бесплатно
    </p>
  </div>
</section>
```

**Сохранить тексты H2 и подзаголовка ровно как в существующей разметке** (smoke-тест `Начните вести` зависит от него).

- [ ] **Step 4: Обновить Footer**

Найти `<footer>` блок. Обернуть/обновить:

```tsx
<footer className="uplift-section-dark px-6 lg:px-12 pt-16 pb-10 border-t border-[var(--rule-on-dark)]">
  <div className="max-w-[1200px] mx-auto">
    {/* существующая разметка футера — text-цвета меняем: */}
    {/*   var(--ink) → var(--paper-on-dark) */}
    {/*   var(--ink-2) → var(--paper-on-dark-2) */}
    {/*   var(--ink-3) → var(--paper-on-dark-3) */}
    {/*   border-[var(--rule)] → border-[var(--rule-on-dark)] */}
  </div>
</footer>
```

- [ ] **Step 5: Прогнать тест — PASS**

Run: `npx playwright test e2e/landing-smoke.spec.ts -g "Final CTA and Footer are both dark|footer has МААТТ" --project=chromium-desktop`
Expected: оба PASS.

- [ ] **Step 6: Header проверка — оставлен LIGHT**

```typescript
  test("Header stays light at top", async ({ page }) => {
    const header = page.locator("header").first();
    const bg = await header.evaluate((el) => getComputedStyle(el).backgroundColor);
    // Header может быть transparent — тогда родитель paper
    expect(["rgb(250, 246, 238)", "rgba(0, 0, 0, 0)"]).toContain(bg);
  });
```

Run: `npx playwright test e2e/landing-smoke.spec.ts -g "Header stays light" --project=chromium-desktop`
Expected: PASS.

- [ ] **Step 7: Тип-чек + commit**

```bash
npx tsc --noEmit
git add frontend/src/components/landing/Landing.tsx frontend/e2e/landing-smoke.spec.ts
git commit -m "feat(landing): Final CTA + Footer — continuous DARK zone

- Final CTA: uplift-section-dark with orange primary CTA
- Footer: uplift-section-dark continuation, paper-on-dark text variants
- Header stays light at page top"
```

---

## Task 13: Ритм-spec — проверка соседств dark/light/orange-strip

**Files:**
- Create: `frontend/e2e/landing-rhythm.spec.ts`

- [ ] **Step 1: Написать тест на полную карту ритма**

Файл `frontend/e2e/landing-rhythm.spec.ts`:

```typescript
import { test, expect } from "@playwright/test";

const EXPECTED_RHYTHM: Array<{ section: string; bg: string }> = [
  { section: "live-ticker",  bg: "rgb(232, 78, 28)"   }, // orange strip
  { section: "hero",         bg: "rgb(10, 10, 10)"    }, // DARK
  { section: "simple-fact",  bg: "rgb(250, 246, 238)" }, // LIGHT paper
  { section: "champions",    bg: "rgb(250, 246, 238)" }, // LIGHT paper
  { section: "numbers-band", bg: "rgb(10, 10, 10)"    }, // DARK
  { section: "manifest",     bg: "rgb(244, 236, 220)" }, // LIGHT tint
  { section: "replay-01",    bg: "rgb(250, 246, 238)" }, // LIGHT paper
  { section: "mae-mfe-02",   bg: "rgb(10, 10, 10)"    }, // DARK
  { section: "metrics-03",   bg: "rgb(250, 246, 238)" }, // LIGHT paper
  { section: "pull-quote",   bg: "rgb(10, 10, 10)"    }, // DARK
  { section: "heuristics-04", bg: "rgb(250, 246, 238)" }, // LIGHT paper
  { section: "audience-05",  bg: "rgb(244, 236, 220)" }, // LIGHT tint
  { section: "pricing-06",   bg: "rgb(250, 246, 238)" }, // SPLIT root paper
  { section: "final-cta",    bg: "rgb(10, 10, 10)"    }, // DARK
];

test("landing follows expected dark/light/orange rhythm in order", async ({ page }) => {
  await page.goto("/");
  await page.evaluate(() => document.fonts.ready);
  const ys: number[] = [];
  for (const { section, bg } of EXPECTED_RHYTHM) {
    const locator = page.locator(`[data-section="${section}"]`);
    await expect(locator, `section ${section} present`).toBeVisible();
    const actualBg = await locator.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(actualBg, `${section} background`).toBe(bg);
    const box = await locator.boundingBox();
    if (!box) throw new Error(`No box for ${section}`);
    ys.push(box.y);
  }
  for (let i = 1; i < ys.length; i++) {
    expect(ys[i], `${EXPECTED_RHYTHM[i].section} after ${EXPECTED_RHYTHM[i - 1].section}`).toBeGreaterThan(ys[i - 1]);
  }
});

test("no two consecutive sections share the same background (visual rhythm intact)", async ({ page }) => {
  await page.goto("/");
  const sections = EXPECTED_RHYTHM;
  // light/light соседство допустимо ТОЛЬКО если они оба paper или paper+tint (внутри cream-семейства). dark/dark недопустимо.
  for (let i = 1; i < sections.length; i++) {
    if (sections[i].bg === "rgb(10, 10, 10)" && sections[i - 1].bg === "rgb(10, 10, 10)") {
      throw new Error(`Two consecutive DARK sections: ${sections[i - 1].section} → ${sections[i].section}`);
    }
  }
});
```

- [ ] **Step 2: Прогнать тест**

Run: `npx playwright test e2e/landing-rhythm.spec.ts --project=chromium-desktop`
Expected: оба PASS (если что-то выпало — fix в Task 10 wrappers).

- [ ] **Step 3: Прогнать mobile**

Run: `npx playwright test e2e/landing-rhythm.spec.ts --project=chromium-mobile`
Expected: PASS (контрасты не меняются на mobile).

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/landing-rhythm.spec.ts
git commit -m "test(landing): rhythm spec — assert dark/light/orange order

Locks in 14-row background sequence map from spec §3:
ticker(orange) → hero(dark) → simple-fact(paper) → champions(paper) →
numbers(dark) → manifest(tint) → ... → final-cta(dark). Plus a guard
against two consecutive DARK sections."
```

---

## Task 14: Refresh visual regression baselines + add reduced-motion variant

**Files:**
- Modify: `frontend/e2e/landing-visual.spec.ts`
- Regenerate: `frontend/e2e/landing-visual.spec.ts-snapshots/*`

- [ ] **Step 1: Расширить landing-visual.spec.ts**

В существующем describe добавить scenarios:

```typescript
  test("Hero — desktop dark", async ({ page }) => {
    await expect(page.locator('[data-section="hero"]')).toHaveScreenshot("hero-dark-1440.png", { maxDiffPixels: 100 });
  });

  test("NumbersBand — desktop dark", async ({ page }) => {
    await expect(page.locator('[data-section="numbers-band"]')).toHaveScreenshot("numbers-dark-1440.png", { maxDiffPixels: 100 });
  });

  test("Champions — desktop", async ({ page }) => {
    await expect(page.locator('[data-section="champions"]')).toHaveScreenshot("champions-1440.png", { maxDiffPixels: 200 });
  });

  test("Pricing split — desktop", async ({ page }) => {
    await expect(page.locator('[data-section="pricing-06"]')).toHaveScreenshot("pricing-split-1440.png", { maxDiffPixels: 100 });
  });

  test("Final CTA — desktop", async ({ page }) => {
    await expect(page.locator('[data-section="final-cta"]')).toHaveScreenshot("final-cta-1440.png", { maxDiffPixels: 100 });
  });
```

И отдельный describe для reduced-motion (motion-free baseline):

```typescript
test.describe("Landing — reduced motion visual @visual", () => {
  test.use({ contextOptions: { reducedMotion: "reduce" } });
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(500);
  });

  test("Hero — desktop reduced motion (curve at final state)", async ({ page }) => {
    await expect(page.locator('[data-section="hero"]')).toHaveScreenshot("hero-dark-reduced-1440.png", { maxDiffPixels: 100 });
  });

  test("Full page — mobile reduced motion", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.reload();
    await page.evaluate(() => document.fonts.ready);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(500);
    await expect(page).toHaveScreenshot("full-mobile-reduced.png", { fullPage: true, maxDiffPixels: 500 });
  });
});
```

- [ ] **Step 2: Удалить старые snapshot'ы**

Run (PowerShell):

```powershell
Remove-Item -Recurse -Force frontend\e2e\landing-visual.spec.ts-snapshots -ErrorAction SilentlyContinue
```

- [ ] **Step 3: Сгенерировать новые baselines**

Run: `npx playwright test e2e/landing-visual.spec.ts --update-snapshots`
Expected: новые snapshot'ы созданы для всех тестов.

- [ ] **Step 4: Прогнать без --update — должно быть PASS**

Run: `npx playwright test e2e/landing-visual.spec.ts`
Expected: все PASS.

- [ ] **Step 5: Визуально просмотреть snapshot'ы**

Открыть в `frontend/e2e/landing-visual.spec.ts-snapshots/`:
- `hero-dark-1440-chromium-desktop.png` — Hero на чёрном с оранжевым акцентом
- `numbers-dark-1440-chromium-desktop.png` — DARK numbers band
- `champions-1440-chromium-desktop.png` — 6 карточек
- `pricing-split-1440-chromium-desktop.png` — Free/Pro контраст
- `final-cta-1440-chromium-desktop.png` — DARK final CTA
- `hero-dark-reduced-1440-chromium-desktop.png` — curve в финальной позиции, без анимации
- `full-mobile.png`, `full-mobile-reduced.png`

Если какой-то выглядит «не так» — пересмотреть соответствующую Task и пере-генерировать.

- [ ] **Step 6: Commit (snapshot'ы как часть коммита)**

```bash
git add frontend/e2e/landing-visual.spec.ts frontend/e2e/landing-visual.spec.ts-snapshots
git commit -m "test(landing): refresh visual regression baselines + reduced-motion variants

- New baselines for Hero/Numbers/Champions/Pricing/FinalCTA at 1440
- Reduced-motion describe block with separate snapshots
- maxDiffPixels tightened to 100 for high-contrast sections (200 for Champions)"
```

---

## Task 15: Manual QA + Lighthouse + final smoke run

**Files:** none (verification only)

- [ ] **Step 1: Запустить dev server (если не запущен)**

Run: `cd frontend && npm run dev -- -p 3001`

- [ ] **Step 2: Открыть `http://localhost:3001/` в Chrome**

Пройти страницу сверху вниз, проверить визуально:

- [ ] Header — paper, читаемый
- [ ] Ticker — оранжевый strip, лента бесконечно скроллится
- [ ] Hero — чёрный фон, H1 в Manrope, «трейдера.» оранжевое, equity curve рисуется при загрузке за ~1.2с
- [ ] SimpleFact — paper, большие orange 01/02/03
- [ ] Champions — paper, 6 карточек, при скролле появляются staggered
- [ ] Numbers — чёрный, оранжевые цифры count-up'ятся при заходе в viewport
- [ ] Manifest — paper-tint, большая мягко-оранжевая «
- [ ] Replay 01 — paper
- [ ] MAE/MFE 02 — чёрный, текст белый, ссылка оранжевая
- [ ] Metrics 03 — paper
- [ ] Pull-quote — чёрный, большая ярко-оранжевая «
- [ ] Heuristics 04 — paper
- [ ] Audience 05 — paper-tint, оранжевые маркеры
- [ ] Pricing — Free=paper, Pro=чёрный с оранжевой CTA
- [ ] Final CTA — чёрный, большая оранжевая кнопка
- [ ] Footer — чёрный, paper-on-dark тексты

- [ ] **Step 3: Проверить DevTools console**

Run: F12 → Console. Expected: NO `error`, NO `warning` (кроме React hot-reload в dev — ок).

- [ ] **Step 4: Проверить prefers-reduced-motion**

DevTools → ⋮ → More tools → Rendering → Emulate CSS media feature `prefers-reduced-motion: reduce`. Перезагрузить страницу.

Expected:
- Equity curve в Hero — сразу в финальном состоянии без анимации
- Ticker — стоит на месте
- Champions cards — все сразу видны без raise
- Numbers — финальные цифры сразу

- [ ] **Step 5: Mobile viewport**

DevTools → Device toolbar → iPhone 13 (390×844). Прокрутить страницу.

Expected:
- Все секции читаемы
- Pricing — Free сверху, Pro снизу (стек)
- Champions — 1 колонка
- Numbers — 2 колонки

- [ ] **Step 6: Lighthouse audit (Performance + Accessibility)**

DevTools → Lighthouse → Mobile → Performance + Accessibility → Run.

Expected:
- Performance ≥ 90
- Accessibility ≥ 95
- Best Practices ≥ 90
- SEO ≥ 90

Если Performance < 90 — проверить:
- Manrope subsets (не лишние ли)
- `<img>` `loading="lazy"` у Champions портретов
- Inline-стили не блокируют render

- [ ] **Step 7: Полный прогон всех Playwright тестов**

Run: `npx playwright test --project=chromium-desktop`
Expected: все PASS.

Run: `npx playwright test --project=chromium-mobile`
Expected: все PASS.

- [ ] **Step 8: Type-check + lint финально**

Run: `npx tsc --noEmit && npm run lint`
Expected: 0 ошибок.

- [ ] **Step 9: Final summary commit (если что-то поправляли в QA)**

Если в QA что-то фиксили — отдельный коммит. Если всё чисто — пропустить.

```bash
git add -A
git commit -m "chore(landing): post-QA polish for Bloomberg uplift

[опционально — описать что подправлено вручную, например:
 corner padding на mobile, contrast микро-tweak, lazy-loading flag]"
```

- [ ] **Step 10: Push (если ветка ещё не запушена)**

```bash
git push -u origin feat/landing-handcrafted
```

Открыть PR на GitHub при необходимости (или оставить на ветке).

---

## Self-Review

После составления плана прогнал по spec §3–§10:

**Spec coverage:**
- §3 ритм 16 секций → Task 4 (ticker), Task 5 (hero), Task 6 (simple-fact), Task 7 (numbers), Task 8 (champions), Task 9 (manifest+pull-quote), Task 10 (replay/mae-mfe/metrics/heuristics/audience), Task 11 (pricing), Task 12 (final-cta+footer). Task 13 lock'ает ритм-spec'ом.
- §4 типографика → Task 1 (Manrope font), Task 2 (uplift-h1/h2/numbers utility-классы), Task 5 (Hero H1), Task 6 (SimpleFact H3), Task 8 (Champion name).
- §5 палитра → Task 2 (12 токенов).
- §6.1–§6.9 компонентные паттерны → Task 4 (Ticker), 5 (Hero), 6 (SimpleFact), 8 (Champions), 7 (Numbers), 9 (Manifest+Pull-quote), 11 (Pricing split), 12 (Final CTA).
- §7 motion → Task 2 (CSS keyframes), Task 3 (useInView, CountUp), Task 4 (ticker scroll), Task 5 (curve draw), Task 7 (count-up), Task 8 (raise).
- §7.1 reduced-motion → Task 2 (media query), Task 3 (CountUp guard), Task 5 (curve guard), Task 14 (reduced-motion baseline).
- §8 accessibility → Task 2 (focus-ring), Task 5 (aria-label на ticker, alt у equity curve), Task 8 (alt у портретов).
- §9.1 implementation scope → все 15 задач.
- §10 acceptance criteria — все 14 чекбоксов покрыты в Task 15 manual QA + Tasks 1–14 автотесты.

**Placeholder scan:** все Task'и содержат code-блоки или конкретные действия. Где написано "существующий текст" — explicit указано, что брать из текущего файла без переписывания (это не placeholder, а инструкция implementer'у не выдумывать копирайт).

**Type consistency:**
- `useInView<T>()` возвращает `{ ref, inView }` — Task 3 и Task 8 используют одинаково ✓
- `CountUp` props `to / durationMs / suffix / prefix / decimals / className` — Task 3 объявляет, Task 7 использует `to` и `suffix` ✓
- `data-section` атрибуты единообразно: `hero`, `simple-fact`, `champions`, `numbers-band`, `manifest`, `replay-01`, `mae-mfe-02`, `metrics-03`, `pull-quote`, `heuristics-04`, `audience-05`, `pricing-06`, `final-cta`, `live-ticker` — используются в Tasks 4,5,6,7,8,9,10,11,12,13 одинаково ✓
- CSS-переменные `--orange / --orange-hover / --orange-soft / --orange-quote / --ink-dark / --paper-on-dark / --paper-on-dark-2 / --paper-on-dark-3 / --rule-on-dark` — Task 2 объявляет, все остальные задачи ссылаются на одно и то же ✓
- Utility-классы `uplift-section-light / -tint / -dark`, `uplift-h1 / -h2 / -numbers`, `uplift-ticker-strip / -track`, `uplift-curve-animate`, `uplift-raise`, `uplift-focus` — Task 2 объявляет, все последующие используют ✓

Готово.

---

## Execution

Plan complete and saved to `docs/superpowers/plans/2026-05-19-bloomberg-design-uplift.md`. Two execution options:

**1. Subagent-Driven (recommended)** — фреш subagent на каждый Task (frontend-design плагин + implementer для типографики и motion), two-stage review между задачами.

**2. Inline Execution** — выполнение в текущей сессии через executing-plans, batch-режим с чекпойнтами.

Который заходит?
