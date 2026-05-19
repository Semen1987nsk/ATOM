# Landing Champions Rebuild — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Перестроить лендинг МААТТ: новый Hero, два новых блока (Сам факт записи + Дисциплина чемпионов с 6 портретами), переписанные тексты всех 14 существующих секций, обновлённый дизайн и SEO.

**Architecture:** 4 фазы с контрольными точками. Каждая задача → отдельный коммит. Маркетинг-агенты дают артефакты в `docs/`, потом implementer переносит их в код. Worktree: `C:\Users\Administrator\Eqio\ATOM-landing`, ветка `feat/landing-handcrafted`.

**Tech Stack:** Next.js 16 App Router, React 19, Tailwind v4, TypeScript, Playwright e2e+visual, Fraunces+Cormorant+Inter+JetBrains Mono variable fonts, FastAPI backend (только Phase 4 для OG-image).

**Spec:** `docs/superpowers/specs/2026-05-18-landing-champions-rebuild-design.md`

---

## File Structure

### Создаются

| Путь | Ответственность |
|---|---|
| `.agents/product-marketing.md` | Продуктовый контекст для всех маркетинг-агентов |
| `docs/brand/voice.md` | Голос бренда (архетипы, do/don't) |
| `docs/brand/messaging.md` | Иерархия сообщений (big idea → pillars → proofs) |
| `docs/landing/champions-research.md` | 6 чемпионов: биография + verbatim-цитаты |
| `docs/landing/cro-audit.md` | CRO-аудит текущего лендинга |
| `docs/landing/seo-checklist.md` | Manual SEO шаги (Yandex Webmaster, GSC) |
| `frontend/src/components/landing/data/champions.ts` | Type-safe данные 6 персон |
| `frontend/src/components/landing/data/simple-fact.ts` | Type-safe 3 утверждения |
| `frontend/src/components/landing/parts/SimpleFactSection.tsx` | Секция «Сам факт записи» |
| `frontend/src/components/landing/parts/ChampionsSection.tsx` | Секция «Дисциплина чемпионов» |
| `frontend/src/components/landing/parts/ChampionCard.tsx` | Презентационная карточка |
| `frontend/src/app/structured-data.ts` | 4 JSON-LD блока |
| `frontend/public/landing/champions/{livermore,darvas,minervini,tudor-jones,elder,raschke}.svg` | 6 SVG-гравюр |
| `frontend/e2e/landing-ia.spec.ts` | Smoke + visual regression для новых блоков |

### Модифицируются

| Путь | Что меняем |
|---|---|
| `frontend/src/components/landing/Landing.tsx` | IA реструктура (16 секций), все тексты |
| `frontend/src/components/landing/parts/MaattOrigin.tsx` → `AudienceQualifier.tsx` | Rename + обновление копи |
| `frontend/src/components/landing/parts/LiveTicker.tsx` | Pulse 1.5s → 2.0s, фон paper-tint |
| `frontend/src/components/landing/parts/HeroEquityCurve.tsx` | Eyebrow «-1.2R» снизу, убрать grid |
| `frontend/src/components/landing/parts/TradeReplayWidget.tsx` | Бордюр rule-strong → ink-3 |
| `frontend/src/components/landing/parts/InteractiveCandleChart.tsx` | Tooltip paper-tint фон, mono цифры |
| `frontend/src/app/globals.css` | Новые палитра-токены + типографика |
| `frontend/src/app/layout.tsx` | Обновлённая metadata + JSON-LD inject |
| `frontend/src/app/sitemap.ts` | Anchor-URL для новых секций |
| `frontend/src/app/robots.ts` | Disallow `/api/landing/ticker` |
| `frontend/e2e/landing-visual.spec.ts` | Расширить baseline-снимки |

### НЕ трогаем

- `backend/*` (кроме случая если OG-картинка regenerate сломается)
- `frontend/src/app/page.tsx` — Landing уже подключен в v1
- ATOM main worktree

---

## Phase 1 — Foundation & Research

### Task 1: Product Marketing Context

**Files:**
- Create: `.agents/product-marketing.md`

- [ ] **Step 1: Invoke product-marketing skill**

```
Skill tool: mkt-product-marketing
```

В режиме «auto-draft from codebase» дать прочитать:
- `README.md`, `BUSINESS_PLAN.md`, `BRAND.md` если есть
- `frontend/src/components/landing/Landing.tsx`
- `.business/marketing/positioning.md`, `.business/strategy/roadmap.md`, `.business/product/personas.md`

Результат — V1 черновика всех 12 секций (Product Overview, Target Audience, Personas, Problems, Competitive, Differentiation, Objections, Switching Dynamics, Customer Language, Brand Voice, Proof Points, Goals).

- [ ] **Step 2: Manual review and tighten**

Подтвердить/исправить:
- One-liner соответствует spec § 2 (big idea «запись = edge»)
- Direct competitors указаны (TradeZella, Edgewonk — direct foreign; Excel — indirect)
- Anti-persona описана (крипто/forex/западные биржи)
- Goals — primary conversion action указан

- [ ] **Step 3: Commit**

```bash
git add .agents/product-marketing.md
git commit -m "docs(marketing): foundation product context for landing rebuild"
```

---

### Task 2: Brand Voice Document

**Files:**
- Create: `docs/brand/voice.md`

- [ ] **Step 1: Dispatch brand-voice-designer**

```
Agent tool (brand-voice-designer):
  description: "Brand voice for МААТТ landing rebuild"
  prompt: |
    Develop the МААТТ brand voice for the new landing page.

    ## Context
    МААТТ — Russian trading journal SaaS for MOEX traders.
    Spec: docs/superpowers/specs/2026-05-18-landing-champions-rebuild-design.md
    Foundation: .agents/product-marketing.md
    Current landing: frontend/src/components/landing/Landing.tsx (14 sections)

    ## Required voice characteristics (from spec § 4)
    - Архетипы: Sage + Craftsman + Mentor
    - Утверждение, не призыв
    - Цифры обнажены
    - Метафоры из книг и спорта, не из ИТ
    - Короткие предложения
    - Безличный или 2-й pl («вы»)
    - Anti-vocabulary: «революционно», «прорыв», «инновация», «no-brainer»,
      «game-changer», «уникальный», «революция», «meta», «vibes», «нейросеть»,
      «AI-powered», «next-gen»
    - Favorite: «измерить», «запись», «факт», «фиксация», «свидетельство»,
      «ремесло», «партитура», «учёт», «дисциплина», «edge»

    ## Deliverable
    Write to docs/brand/voice.md:
    - Voice archetype rationale (why Sage + Craftsman + Mentor)
    - 8 voice rules with do/don't pairs (2 examples each)
    - Anti-vocabulary full list with rationale
    - Favorite vocabulary full list
    - 4 tone calibration examples (Hero / error / educational / footer)
    - Voice consistency checklist for content-editor

    Russian throughout. No emojis. Calm-editorial tone.
```

- [ ] **Step 2: Review and commit**

```bash
git add docs/brand/voice.md
git commit -m "docs(brand): voice guide — Sage+Craftsman+Mentor archetype, 8 rules"
```

---

### Task 3: Messaging Hierarchy

**Files:**
- Create: `docs/brand/messaging.md`

- [ ] **Step 1: Dispatch messaging-architect**

```
Agent tool (messaging-architect):
  description: "Messaging hierarchy for МААТТ landing"
  prompt: |
    Build strategic messaging framework for МААТТ landing rebuild.

    ## Context
    Foundation: .agents/product-marketing.md
    Voice: docs/brand/voice.md
    Spec: docs/superpowers/specs/2026-05-18-landing-champions-rebuild-design.md

    ## Required hierarchy
    1. ONE big idea matching spec § 2:
       «запись делает трейдера / что записано — то измерено»
    2. THREE message pillars (e.g., «дневник как привычка чемпионов» /
       «автоматизация ремесла» / «российский контекст MOEX»)
    3. 3-4 proof points per pillar
    4. Per persona variations (Active MOEX trader / Crossing-over investor /
       Newcomer testing waters) — see personas in .agents/product-marketing.md
    5. Channel adaptations: Hero / mid-funnel / Pricing / Final CTA / OG meta

    ## Deliverable
    Write to docs/brand/messaging.md:
    - Hierarchy diagram
    - Pillar definitions with rationale
    - Proof points table per pillar
    - Persona-message matrix
    - Channel adaptation guide

    Russian. Follow voice.md anti-vocabulary.
```

- [ ] **Step 2: Review and commit**

```bash
git add docs/brand/messaging.md
git commit -m "docs(brand): messaging hierarchy — 1 big idea, 3 pillars"
```

---

### Task 4: Champions Research

**Files:**
- Create: `docs/landing/champions-research.md`

- [ ] **Step 1: Dispatch general-purpose research subagent**

```
Agent tool (general-purpose):
  description: "Research 6 trader champions"
  prompt: |
    Research 6 famous traders/investors for МААТТ landing's "Дисциплина чемпионов"
    section. For each: verify journal-keeping habit with VERIFIABLE quotes.

    ## Casting (locked unless verifiable quote missing)
    1. Джесси Ливермор (1877–1940) — «Воспоминания биржевого спекулянта», Лефевр (1923)
    2. Николас Дарвас (1920–1977) — «Как я заработал $2,000,000 на бирже»
    3. Марк Минервини (р. 1965) — «Думай как чемпион биржи»
    4. Стэнли Дракенмиллер (р. 1953) — «The New Market Wizards», Schwager
    5. Александр Элдер (р. 1932) — «Как играть и выигрывать на бирже»
    6. Эрик Найман (р. 1969) — «Малая энциклопедия трейдера»

    ## For each person, deliver
    - Full name (RU + EN/original) + years of birth/death
    - Biography 60 words max (trading career + records-keeping)
    - 2-3 VERBATIM quote candidates about journaling/record-keeping/discipline
      with direct citation: book/page or interview/timestamp
    - One fact HOW they kept their journal (telegrams, legal pads, index cards)
    - Wikipedia URL (for sameAs JSON-LD)
    - License-cleared photo source if available

    ## CRITICAL
    - Do NOT invent quotes. If verifiable journal-quote missing → FLAG and
      suggest replacement candidate.
    - Verify Wikipedia URLs.
    - Use Russian and English sources.
    - WebSearch and WebFetch are your tools.

    ## Deliverable
    Write to docs/landing/champions-research.md:
    - Section per person (## Имя)
    - bio, journal-fact, 2-3 quote candidates with citations, Wikipedia URL
    - Summary table at top: name | years | recommended quote | source
    - "REPLACE" recommendations if verifiable quote missing
```

- [ ] **Step 2: Review replacement suggestions**

Если research-агент рекомендует REPLACE — обсудить с user (контрольная точка 1).

- [ ] **Step 3: Commit**

```bash
git add docs/landing/champions-research.md
git commit -m "docs(landing): champions research — 6 verified quotes with sources"
```

---

### Task 5: CRO Audit

**Files:**
- Create: `docs/landing/cro-audit.md`

- [ ] **Step 1: Dispatch conversion-optimizer**

```
Agent tool (conversion-optimizer):
  description: "CRO audit of current МААТТ landing"
  prompt: |
    Audit current МААТТ landing for conversion issues.

    ## Context
    Foundation: .agents/product-marketing.md
    Current landing: frontend/src/components/landing/Landing.tsx (14 sections)
    Spec: docs/superpowers/specs/2026-05-18-landing-champions-rebuild-design.md
    Your audit informs Phase 2 (copy) and AudienceQualifier rewrite.

    ## Audit areas
    - Hero: CTA clarity, value-prop alignment, friction
    - Numbers band: trust-signal effectiveness
    - Product sections (01-04): "what's in it for me?" clarity
    - Pricing: anchor effectiveness, objection coverage
    - Final CTA: motivation gap
    - AudienceQualifier (Раздел 05): right 3 objections? What else worries persona?

    ## Deliverable
    Write to docs/landing/cro-audit.md:
    - Top 10 conversion issues ranked H/M/L
    - For each: location, problem, hypothesis, suggested fix
    - 5-7 objections that target persona has (for AudienceQualifier rewrite)
    - 2 A/B test ideas for Hero H1
    - 2 A/B test ideas for Final CTA
    - Trust signals audit: what's missing
    - Anchor pricing analysis: 399 ₽ vs 0 ₽

    Russian. Reference section numbers from spec § 3.
```

- [ ] **Step 2: Review and commit**

```bash
git add docs/landing/cro-audit.md
git commit -m "docs(landing): CRO audit — top 10 issues + objections + A/B ideas"
```

---

### Checkpoint 1 (Phase 1 done)

Ручное ревью 5 артефактов. Approval — переход в Phase 2.

---

## Phase 2 — Copy + IA

### Task 6: IA Restructure

**Files:**
- Modify: `frontend/src/components/landing/Landing.tsx`
- Create: `frontend/e2e/landing-ia.spec.ts`

- [ ] **Step 1: Write failing e2e test**

```typescript
// frontend/e2e/landing-ia.spec.ts
import { test, expect } from '@playwright/test';

test('landing has 16 sections in correct order', async ({ page }) => {
  await page.goto('/');

  const sectionHeadings = [
    'Журнал сделок · MOEX',
    'Сам факт записи',
    'Дисциплина чемпионов',
    'Раздел 01 — Trade Replay',
    'Раздел 02 — MAE / MFE',
    'Раздел 03 — Аналитический центр',
    'Раздел 04 — Эвристический разбор',
    'Раздел 05 — Для серьёзного трейдера',
    'Раздел 06 — Тарифы',
  ];

  for (const h of sectionHeadings) {
    await expect(page.getByText(h, { exact: false }).first()).toBeVisible();
  }
});
```

- [ ] **Step 2: Run test, verify it fails**

```bash
cd frontend
npx playwright test landing-ia.spec.ts --project=chromium-desktop
```

Expected: FAIL — секции «Сам факт записи» и «Дисциплина чемпионов» отсутствуют.

- [ ] **Step 3: Edit Landing.tsx — reorder + add 2 stubs**

После Hero `</section>` вставить:

```tsx
{/* 4. SIMPLE FACT — NEW STUB */}
<section
  id="simple-fact"
  className="px-6 lg:px-12 py-24 lg:py-32 border-b border-[var(--rule)] bg-[var(--paper-tint,#f4ecdc)]"
>
  <div className="max-w-[1200px] mx-auto">
    <p className="editorial-eyebrow mb-6">Раздел 00 — Сам факт записи</p>
    <h2 className="editorial-h2 mb-6 text-[var(--ink)]">Сам факт записи.</h2>
    <p className="text-[16px] leading-[1.65] text-[var(--ink-2)] max-w-[60ch]">
      [Stub — copy в Task 8]
    </p>
  </div>
</section>

{/* 5. CHAMPIONS — NEW STUB */}
<section
  id="champions"
  className="px-6 lg:px-12 py-24 lg:py-32 border-b border-[var(--rule)]"
>
  <div className="max-w-[1200px] mx-auto">
    <p className="editorial-eyebrow mb-6">Раздел 00 — Дисциплина чемпионов</p>
    <h2 className="editorial-h2 mb-6 text-[var(--ink)]">Дисциплина чемпионов.</h2>
    <p className="text-[16px] leading-[1.65] text-[var(--ink-2)] max-w-[60ch]">
      [Stub — компонент в Task 9]
    </p>
  </div>
</section>
```

Переместить `<MaattOrigin />` (он будет переименован в Task 13) так чтобы шёл как Раздел 05 — между Section 04 Heuristics и Pricing. Унифицировать eyebrow'ы: «Раздел NN · …» → «Раздел NN — …». Проверить нумерацию 01-06 в порядке.

- [ ] **Step 4: Run test, verify pass**

```bash
npx playwright test landing-ia.spec.ts --project=chromium-desktop
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/landing/Landing.tsx frontend/e2e/landing-ia.spec.ts
git commit -m "feat(landing): restructure IA to 16 sections with SimpleFact + Champions stubs"
```

---

### Task 7: Hero + Numbers + Manifest + Pull-quote Copy

**Files:**
- Modify: `frontend/src/components/landing/Landing.tsx`
- Modify: `frontend/src/components/landing/parts/ManifestCutIn.tsx`
- Create: `docs/landing/copy-phase2-hero.md`

- [ ] **Step 1: Dispatch copywriter-specialist**

```
Agent tool (copywriter-specialist):
  description: "Rewrite Hero+Numbers+Manifest+Pull-quote"
  prompt: |
    Rewrite copy for 4 sections of МААТТ landing.

    ## Sources
    Foundation: .agents/product-marketing.md
    Voice: docs/brand/voice.md
    Messaging: docs/brand/messaging.md
    Spec: docs/superpowers/specs/2026-05-18-landing-champions-rebuild-design.md (§§ 2, 3, 4)
    CRO: docs/landing/cro-audit.md
    Current: frontend/src/components/landing/Landing.tsx

    ## Rewrites

    ### Section 3: Hero
    - Eyebrow (keep or 1 variant)
    - H1: 2 variants for A/B (calm assertion, spec § 4 rule 1)
    - Lede: 2 sentences max, 30-40 знаков в строке
    - Primary CTA: «Начать бесплатно» (proven)
    - Secondary CTA: refine
    - Trust line: «Бесплатно до 50 сделок. Без карты. 21 день Pro.»

    ### Section 6: Numbers band
    4 числа + 1-line note под каждым: 30+ метрик, 6 бордов MOEX,
    60 сек синхронизация, 399 ₽ / мес Pro. Strip пафос.

    ### Section 7: Manifest cut-in
    Афоризм 6-12 слов под big idea. Сохранить структуру component.

    ### Section 11: Customer pull-quote
    Под big idea, 2 варианта (placeholder до реальной бета-цитаты).

    ## Voice constraints MUST
    Полный anti-vocabulary см. voice.md. Без emoji, «!», «AI-powered».

    ## Deliverable
    docs/landing/copy-phase2-hero.md — 1-2 варианта copy per section + rationale.
```

- [ ] **Step 2: Content-editor pass**

```
Agent tool (content-editor):
  description: "Edit hero+numbers copy"
  prompt: |
    Edit docs/landing/copy-phase2-hero.md per voice.md.
    Check anti-vocabulary, consistency, length, punctuation
    (тире «—», кавычки «», цифры цифрами).
    Output corrected version inline.
```

- [ ] **Step 3: Apply copy to .tsx files**

Открыть `docs/landing/copy-phase2-hero.md`, для каждой секции выбрать вариант A (рекомендованный). Применить в `Landing.tsx` (Hero `<h1>`, lede `<p>`, NUMBERS_BAND array, customer pull-quote) и `ManifestCutIn.tsx`.

- [ ] **Step 4: Visual check**

`http://localhost:3001/`:
- H1 не выходит за 88px
- Lede ≤ 36ch
- Numbers band читабельный mobile

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/landing/Landing.tsx \
        frontend/src/components/landing/parts/ManifestCutIn.tsx \
        docs/landing/copy-phase2-hero.md
git commit -m "feat(landing): copy rewrite — Hero+Numbers+Manifest+Pull-quote in new voice"
```

---

### Task 8: SimpleFactSection

**Files:**
- Create: `frontend/src/components/landing/data/simple-fact.ts`
- Create: `frontend/src/components/landing/parts/SimpleFactSection.tsx`
- Create: `docs/landing/copy-simple-fact.md`
- Modify: `frontend/src/components/landing/Landing.tsx`
- Modify: `frontend/e2e/landing-ia.spec.ts`

- [ ] **Step 1: Dispatch copywriter for content**

```
Agent tool (copywriter-specialist):
  description: "Copy for SimpleFact section"
  prompt: |
    Write copy for МААТТ landing Section 4 "Сам факт записи".

    ## Sources
    Spec § 3.1, Voice docs/brand/voice.md, Messaging docs/brand/messaging.md

    ## Structure
    - Section eyebrow + H2 (6-10 words)
    - 3 columns each: caption «01/02/03», sub-heading (2-4 слова),
      body (2 sentences max, ≤80 знаков каждое)
    - Bridge phrase tying to Champions section

    ## Draft (rewrite for voice)
      01 — Ты видишь сделки: Не помнишь — видишь. Память врёт. Запись — нет.
      02 — Ты признаёшь ошибки: Не оправдываешь — признаёшь. Цифра не спорит.
      03 — Ты сравниваешь себя с собой: Не с рынком — с собой. Квартал к кварталу.
      Bridge: «Это всё, что нужно. Метрики и алгоритмы — уже сверху.»

    ## Voice
    Anti-vocabulary strict. «Ты» допустим (личный регистр). Короткие фразы.

    ## Deliverable
    docs/landing/copy-simple-fact.md:
    - eyebrow, H2, 3 columns × (caption, sub-heading, body), bridge
    - 1 альтернативный H2
```

- [ ] **Step 2: Write failing e2e test**

В `landing-ia.spec.ts` добавить:

```typescript
test('SimpleFact section has 3 columns', async ({ page }) => {
  await page.goto('/');
  const section = page.locator('#simple-fact');
  await expect(section).toBeVisible();
  await expect(section.locator('[data-testid="simple-fact-column"]')).toHaveCount(3);
  await expect(section.getByText('01').first()).toBeVisible();
  await expect(section.getByText('02').first()).toBeVisible();
  await expect(section.getByText('03').first()).toBeVisible();
});
```

```bash
npx playwright test landing-ia.spec.ts -g "SimpleFact"
```

Expected: FAIL.

- [ ] **Step 3: Create data file**

```typescript
// frontend/src/components/landing/data/simple-fact.ts
export type SimpleFactItem = {
  caption: string;
  heading: string;
  body: string;
};

export const SIMPLE_FACT_HEADING: string = ""; // из copy-simple-fact.md
export const SIMPLE_FACT_EYEBROW: string = ""; // из copy-simple-fact.md

export const SIMPLE_FACT_ITEMS: SimpleFactItem[] = [
  { caption: "01", heading: "", body: "" },
  { caption: "02", heading: "", body: "" },
  { caption: "03", heading: "", body: "" },
];

export const SIMPLE_FACT_BRIDGE: string = "";
```

Заполнить из `docs/landing/copy-simple-fact.md`.

- [ ] **Step 4: Create component**

```tsx
// frontend/src/components/landing/parts/SimpleFactSection.tsx
import {
  SIMPLE_FACT_EYEBROW,
  SIMPLE_FACT_HEADING,
  SIMPLE_FACT_ITEMS,
  SIMPLE_FACT_BRIDGE,
} from "../data/simple-fact";

export function SimpleFactSection() {
  return (
    <section
      id="simple-fact"
      className="px-6 lg:px-12 py-24 lg:py-32 border-b border-[var(--rule)] bg-[var(--paper-tint,#f4ecdc)]"
    >
      <div className="max-w-[1200px] mx-auto">
        <p className="editorial-eyebrow mb-8">{SIMPLE_FACT_EYEBROW}</p>
        <h2 className="editorial-h2 mb-16 text-[var(--ink)] max-w-[24ch]">
          {SIMPLE_FACT_HEADING}
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-10 lg:gap-16 mb-16">
          {SIMPLE_FACT_ITEMS.map((item) => (
            <div key={item.caption} data-testid="simple-fact-column">
              <div className="num text-[56px] text-[var(--ink-3)] leading-none mb-6">
                {item.caption}
              </div>
              <h3
                className="text-[22px] mb-4 text-[var(--ink)]"
                style={{ fontFamily: "var(--font-serif), var(--font-serif-cyr), Georgia, serif" }}
              >
                {item.heading}
              </h3>
              <p className="text-[15px] leading-[1.65] text-[var(--ink-2)]">
                {item.body}
              </p>
            </div>
          ))}
        </div>
        <p
          className="text-[16px] italic text-[var(--ink-2)] max-w-[60ch]"
          style={{ fontFamily: "var(--font-serif), var(--font-serif-cyr), Georgia, serif" }}
        >
          {SIMPLE_FACT_BRIDGE}
        </p>
      </div>
    </section>
  );
}
```

- [ ] **Step 5: Wire into Landing.tsx**

Импорт `SimpleFactSection`. Заменить stub Section 4 на `<SimpleFactSection />`.

- [ ] **Step 6: Run test**

```bash
npx playwright test landing-ia.spec.ts -g "SimpleFact"
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/landing/data/simple-fact.ts \
        frontend/src/components/landing/parts/SimpleFactSection.tsx \
        frontend/src/components/landing/Landing.tsx \
        frontend/e2e/landing-ia.spec.ts \
        docs/landing/copy-simple-fact.md
git commit -m "feat(landing): SimpleFactSection — 3-column editorial with numbered headings"
```

---

### Task 9: ChampionsSection + ChampionCard (skeleton)

**Files:**
- Create: `frontend/src/components/landing/data/champions.ts`
- Create: `frontend/src/components/landing/parts/ChampionCard.tsx`
- Create: `frontend/src/components/landing/parts/ChampionsSection.tsx`
- Create: `frontend/public/landing/champions/{slug}.svg` × 6 (placeholders)
- Modify: `frontend/src/components/landing/Landing.tsx`
- Modify: `frontend/e2e/landing-ia.spec.ts`

- [ ] **Step 1: Write failing e2e test**

В `landing-ia.spec.ts` добавить:

```typescript
test('Champions section has 6 cards', async ({ page }) => {
  await page.goto('/');
  const section = page.locator('#champions');
  await expect(section).toBeVisible();
  await expect(section.locator('[data-testid="champion-card"]')).toHaveCount(6);
  for (const name of ['Ливермор','Дарвас','Минервини','Тюдор Джонс','Элдер','Рашке']) {
    await expect(section.getByText(name).first()).toBeVisible();
  }
});
```

```bash
npx playwright test landing-ia.spec.ts -g "Champions"
```

Expected: FAIL.

- [ ] **Step 2: Create data type and 6 entries**

```typescript
// frontend/src/components/landing/data/champions.ts
export type Champion = {
  slug: string;
  firstName: string;
  lastName: string;
  originalName?: string;
  birthYear: number;
  deathYear?: number;
  bio: string;        // ≤60 words — Task 10 заполнит
  quote: string;      // verbatim — Task 10 заполнит
  source: string;     // Task 10 заполнит
  wikipediaUrl: string;
  portraitSrc: string;
};

export const CHAMPIONS_LEDE: string = ""; // 1-2 sentences — Task 10

export const CHAMPIONS: Champion[] = [
  {
    slug: "livermore",
    firstName: "Джесси",
    lastName: "Ливермор",
    originalName: "Jesse Livermore",
    birthYear: 1877,
    deathYear: 1940,
    bio: "",
    quote: "",
    source: "",
    wikipediaUrl: "https://ru.wikipedia.org/wiki/Ливермор,_Джесси",
    portraitSrc: "/landing/champions/livermore.svg",
  },
  {
    slug: "darvas",
    firstName: "Николас",
    lastName: "Дарвас",
    originalName: "Nicolas Darvas",
    birthYear: 1920,
    deathYear: 1977,
    bio: "", quote: "", source: "",
    wikipediaUrl: "https://en.wikipedia.org/wiki/Nicolas_Darvas",
    portraitSrc: "/landing/champions/darvas.svg",
  },
  {
    slug: "minervini",
    firstName: "Марк",
    lastName: "Минервини",
    originalName: "Mark Minervini",
    birthYear: 1965,
    bio: "", quote: "", source: "",
    wikipediaUrl: "https://en.wikipedia.org/wiki/Mark_Minervini",
    portraitSrc: "/landing/champions/minervini.svg",
  },
  {
    slug: "tudor-jones",
    firstName: "Пол",
    lastName: "Тюдор Джонс",
    originalName: "Paul Tudor Jones",
    birthYear: 1954,
    bio: "", quote: "", source: "",
    wikipediaUrl: "https://en.wikipedia.org/wiki/Paul_Tudor_Jones",
    portraitSrc: "/landing/champions/tudor-jones.svg",
  },
  {
    slug: "elder",
    firstName: "Александр",
    lastName: "Элдер",
    originalName: "Alexander Elder",
    birthYear: 1950,
    bio: "", quote: "", source: "",
    wikipediaUrl: "https://ru.wikipedia.org/wiki/Элдер,_Александр",
    portraitSrc: "/landing/champions/elder.svg",
  },
  {
    slug: "raschke",
    firstName: "Линда",
    lastName: "Брэдфорд Рашке",
    originalName: "Linda Bradford Raschke",
    birthYear: 1959,
    bio: "", quote: "", source: "",
    wikipediaUrl: "https://en.wikipedia.org/wiki/Linda_Bradford_Raschke",
    portraitSrc: "/landing/champions/raschke.svg",
  },
];
```

- [ ] **Step 3: Create ChampionCard component**

```tsx
// frontend/src/components/landing/parts/ChampionCard.tsx
import Image from "next/image";
import type { Champion } from "../data/champions";

export function ChampionCard({ champion }: { champion: Champion }) {
  const yearsLabel = champion.deathYear
    ? `${champion.birthYear} — ${champion.deathYear}`
    : `р. ${champion.birthYear}`;

  return (
    <article
      data-testid="champion-card"
      className="border border-[var(--rule)] p-8 bg-[var(--paper)] flex flex-col"
    >
      <div className="mb-6 mx-auto" style={{ width: 220, height: 220 }}>
        <Image
          src={champion.portraitSrc}
          alt={`Гравюрный портрет — ${champion.firstName} ${champion.lastName}`}
          width={220}
          height={220}
          loading="lazy"
          unoptimized
        />
      </div>
      <h3
        className="text-[26px] italic mb-2 text-[var(--ink)] leading-tight"
        style={{ fontFamily: "var(--font-serif), var(--font-serif-cyr), Georgia, serif" }}
      >
        {champion.firstName}<br />{champion.lastName}
      </h3>
      <div className="num text-[12px] text-[var(--ink-3)] mb-6">{yearsLabel}</div>
      {champion.bio && (
        <p className="text-[14px] leading-[1.55] text-[var(--ink-2)] mb-6">
          {champion.bio}
        </p>
      )}
      {champion.quote && (
        <blockquote
          className="text-[15px] italic text-[var(--ink)] leading-[1.55] border-l-2 border-[var(--accent)] pl-4 mb-4 flex-grow"
          style={{ fontFamily: "var(--font-serif), var(--font-serif-cyr), Georgia, serif" }}
        >
          «{champion.quote}»
        </blockquote>
      )}
      {champion.source && (
        <cite
          className="block text-[11px] not-italic text-[var(--ink-3)] uppercase tracking-[0.08em]"
          style={{ fontFamily: "var(--font-mono), monospace" }}
        >
          — {champion.source}
        </cite>
      )}
    </article>
  );
}
```

- [ ] **Step 4: Create ChampionsSection**

```tsx
// frontend/src/components/landing/parts/ChampionsSection.tsx
import { CHAMPIONS, CHAMPIONS_LEDE } from "../data/champions";
import { ChampionCard } from "./ChampionCard";

export function ChampionsSection() {
  return (
    <section
      id="champions"
      className="px-6 lg:px-12 py-24 lg:py-32 border-b border-[var(--rule)]"
    >
      <div className="max-w-[1200px] mx-auto">
        <p className="editorial-eyebrow mb-8">Раздел 00 — Дисциплина чемпионов</p>
        <h2 className="editorial-h2 mb-6 text-[var(--ink)] max-w-[20ch]">
          Дисциплина чемпионов.
        </h2>
        {CHAMPIONS_LEDE && (
          <p className="text-[16px] leading-[1.65] text-[var(--ink-2)] max-w-[60ch] mb-16">
            {CHAMPIONS_LEDE}
          </p>
        )}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 lg:gap-10">
          {CHAMPIONS.map((c) => (
            <ChampionCard key={c.slug} champion={c} />
          ))}
        </div>
      </div>
    </section>
  );
}
```

- [ ] **Step 5: Create 6 placeholder SVG portraits**

Создать `frontend/public/landing/champions/{slug}.svg` для каждого slug. Placeholder с инициалами:

```svg
<svg width="220" height="220" viewBox="0 0 220 220" xmlns="http://www.w3.org/2000/svg">
  <rect width="220" height="220" fill="#f4ecdc" />
  <text x="110" y="120" text-anchor="middle"
        font-family="Georgia, serif" font-size="64" font-style="italic"
        fill="#26221c">ДЛ</text>
</svg>
```

Инициалы: livermore=ДЛ, darvas=НД, minervini=ММ, tudor-jones=ПТ, elder=АЭ, raschke=ЛР.

- [ ] **Step 6: Wire into Landing.tsx**

Импорт `ChampionsSection`, заменить stub Section 5.

- [ ] **Step 7: Run test**

```bash
npx playwright test landing-ia.spec.ts -g "Champions"
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/landing/data/champions.ts \
        frontend/src/components/landing/parts/ChampionCard.tsx \
        frontend/src/components/landing/parts/ChampionsSection.tsx \
        frontend/src/components/landing/Landing.tsx \
        frontend/public/landing/champions/*.svg \
        frontend/e2e/landing-ia.spec.ts
git commit -m "feat(landing): ChampionsSection — 3x2 grid + 6 placeholder SVGs"
```

---

### Task 10: Champions content (bio + quotes)

**Files:**
- Modify: `frontend/src/components/landing/data/champions.ts`
- Create: `docs/landing/copy-champions.md`

- [ ] **Step 1: Dispatch copywriter for 6 bios + quote selection**

```
Agent tool (copywriter-specialist):
  description: "Polish 6 champion bios + select final quotes"
  prompt: |
    Polish copy for 6 trader champions on МААТТ landing.

    ## Sources
    Research: docs/landing/champions-research.md (raw facts + quote candidates)
    Voice: docs/brand/voice.md
    Spec § 3.2

    ## For each of 6 champions
    - Polish biography to EXACTLY ≤60 words, focused on records/journal habit
    - Select ONE quote from research candidates (shortest + voice-resonant)
    - Translate quote to Russian if English source. Show both inline.

    ## Constraint
    No invented quotes. If best candidate needs trimming, mark [...] with context.

    ## Voice
    - Past tense for historical, present for living
    - Favorite verbs: "записывал" / "ведёт"
    - Avoid: "достиг успеха", "стал легендой"
    - Prefer: "записывал телеграммой", "вёл legal pad"

    ## Deliverable
    docs/landing/copy-champions.md:
    - Section per champion: slug, bio (60w), final quote + translation, source
    - Lede 1-2 sentences explaining WHY these 6
```

- [ ] **Step 2: Content-editor pass**

```
Agent tool (content-editor):
  description: "Edit champions copy"
  prompt: |
    Edit docs/landing/copy-champions.md. Check:
    - Every bio ≤60 words (count exactly)
    - Voice consistency (docs/brand/voice.md)
    - Punctuation (тире —, кавычки «»)
    - Anti-vocabulary
    Output corrected file in place.
```

- [ ] **Step 3: Apply final content to champions.ts**

Заполнить `bio`, `quote`, `source` для всех 6 в array. Заполнить `CHAMPIONS_LEDE` экспорт.

- [ ] **Step 4: Visual check + commit**

`http://localhost:3001/#champions`:
- 6 карточек видны
- Био не выпирают за равную высоту grid
- Цитаты читаются

```bash
git add frontend/src/components/landing/data/champions.ts \
        docs/landing/copy-champions.md
git commit -m "feat(landing): champions final bios + quotes from research"
```

---

### Task 11: Sections 01-04 copy rewrite

**Files:**
- Modify: `frontend/src/components/landing/Landing.tsx`
- Create: `docs/landing/copy-sections-01-04.md`

- [ ] **Step 1: Dispatch copywriter**

```
Agent tool (copywriter-specialist):
  description: "Rewrite product sections 01-04"
  prompt: |
    Rewrite copy for Раздел 01-04 of МААТТ landing.

    ## Sources
    Voice: docs/brand/voice.md
    Messaging: docs/brand/messaging.md
    Spec § 3 (per-section direction)
    Current: frontend/src/components/landing/Landing.tsx

    ## Per section

    ### Раздел 01 · Trade Replay (lines ~138-167)
    Direction (spec):
    "Меньше «у других нет», больше «вот что вы видите».
     Описание шкал, маркеров, точки выхода — что трейдер получает."
    Deliverable: eyebrow + H2 + 2-3 paragraph body + link text

    ### Раздел 02 · MAE / MFE (lines ~169-197)
    Direction:
    "Сначала что это (3 строки inline glossary). Потом — что говорит о ваших стопах.
     Конкуренты — одной строкой в конце."
    Deliverable: eyebrow + H2 + glossary + body + competitor line + link text

    ### Раздел 03 · Метрики (lines ~199-258)
    Direction: усилить вводный параграф. Explainer'ы — Task 12 отдельно.
    Deliverable: eyebrow + H2 + лиде 2-3 предложения

    ### Раздел 04 · Эвристики (lines ~278-310)
    Direction:
    "Перефреймить: сейчас — детерминированные правила.
     «AI-разбор · скоро» — мелкий бейдж снизу."
    Deliverable: eyebrow + H2 + body + badge text + link text

    ## Deliverable
    docs/landing/copy-sections-01-04.md.
```

- [ ] **Step 2: Content-editor pass**

```
Agent tool (content-editor):
  description: "Edit sections 01-04 copy"
  prompt: |
    Edit docs/landing/copy-sections-01-04.md per voice.md.
    Anti-vocabulary, length, punctuation. Output in place.
```

- [ ] **Step 3: Apply to Landing.tsx**

Обновить тексты в Sections 01-04. Не трогать виджеты, table, image.

- [ ] **Step 4: Visual check + commit**

```bash
git add frontend/src/components/landing/Landing.tsx \
        docs/landing/copy-sections-01-04.md
git commit -m "feat(landing): rewrite Sections 01-04 — less competitor-bash, more product-truth"
```

---

### Task 12: Metric explainers expand to 13

**Files:**
- Modify: `frontend/src/components/landing/Landing.tsx`
- Create: `docs/landing/copy-metrics-explainers.md`

- [ ] **Step 1: Dispatch copywriter**

```
Agent tool (copywriter-specialist):
  description: "Explainers for 13 metrics"
  prompt: |
    Expand metrics table on МААТТ landing.

    ## Current state
    Landing.tsx METRICS_TABLE has 13 metrics, 4 have explainer field
    (Optimal f, SQN, Risk of Ruin, MAE/MFE). Need explainers for remaining 9:
    R-Expectancy, Profit Factor, Z-Score, Sortino Ratio, Calmar Ratio,
    Recovery Factor, Monte Carlo 10 000, Post-Exit, Tail Ratio, GHPR.

    ## Format per explainer
    30-60 words, 3 beats:
    1. Что считаем (формула в естественном языке)
    2. Что показывает (интерпретация)
    3. Когда пора менять параметры стратегии

    ## Voice
    Spec § 4 rule 6 (explain unobvious things).
    Краткое, точное. Формулы в скобках если простые.

    ## Deliverable
    docs/landing/copy-metrics-explainers.md — 10 новых explainer'ов в формате
    METRICS_TABLE entries.
```

- [ ] **Step 2: Content-editor pass + math accuracy spot check**

```
Agent tool (content-editor):
  description: "Edit metric explainers"
  prompt: |
    Edit docs/landing/copy-metrics-explainers.md.
    Voice/length check + math accuracy spot check on
    R-Expectancy, Sortino, Calmar formulas.
    Output corrected in place.
```

- [ ] **Step 3: Update METRICS_TABLE**

В `Landing.tsx` обновить `METRICS_TABLE` array: добавить `explainer` поле для 9 строк где сейчас его нет (плюс по необходимости отредактировать существующие 4 если copywriter улучшил).

- [ ] **Step 4: Visual check**

Все 13 explainer'ов помещаются в editorial-table. Mobile — таблица скроллит горизонтально (existing behavior).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/landing/Landing.tsx \
        docs/landing/copy-metrics-explainers.md
git commit -m "feat(landing): expand metric explainers to all 13 — 30-60 words each"
```

---

### Task 13: AudienceQualifier rename + Pricing + Final CTA + Footer

**Files:**
- Rename: `frontend/src/components/landing/parts/MaattOrigin.tsx` → `AudienceQualifier.tsx`
- Modify: `frontend/src/components/landing/Landing.tsx`
- Create: `docs/landing/copy-sections-05-tail.md`

- [ ] **Step 1: Rename file**

```bash
cd frontend/src/components/landing/parts
git mv MaattOrigin.tsx AudienceQualifier.tsx
```

В `AudienceQualifier.tsx`: переименовать `export function MaattOrigin` → `export function AudienceQualifier`.
В `Landing.tsx`: обновить импорт и использование.

- [ ] **Step 2: Dispatch copywriter**

```
Agent tool (copywriter-specialist):
  description: "Rewrite AudienceQualifier + Pricing + Final CTA + Footer"
  prompt: |
    Rewrite remaining sections of МААТТ landing.

    ## Sources
    Voice: docs/brand/voice.md
    CRO audit: docs/landing/cro-audit.md (top objections для AudienceQualifier)
    Spec § 3 + § 4
    Current: Landing.tsx + AudienceQualifier.tsx

    ## Sections

    ### Раздел 05 · Для серьёзного трейдера (AudienceQualifier.tsx)
    Сейчас 5 ✓ + 3 × items.
    Use CRO audit top 5-7 objections для refining ✓ и × items.
    Каждая ✓ — конкретный jobs-to-be-done.
    Каждая × — конкретная объекция/anti-persona.

    ### Раздел 06 · Тарифы (Landing.tsx lines ~316-362)
    Free items — что можно ПОНЯТЬ.
    Pro items — что можно ИЗМЕНИТЬ.
    Anchor copy: уточнить под CRO audit anchor analysis.

    ### Final CTA (Landing.tsx lines ~364-379)
    2 варианта под new big idea. Lede 1 sentence.

    ### Footer (Landing.tsx lines ~381-426)
    Tagline «Точно. Чисто. Честно.» — пересмотреть.
    Подзаголовок — обновить под new positioning.

    ## Deliverable
    docs/landing/copy-sections-05-tail.md.
```

- [ ] **Step 3: Content-editor pass**

```
Agent tool (content-editor):
  description: "Edit AudienceQualifier + Pricing + Final CTA + Footer copy"
  prompt: |
    Edit docs/landing/copy-sections-05-tail.md per voice.md.
    Output in place.
```

- [ ] **Step 4: Apply changes**

- AudienceQualifier.tsx: обновить ✓/× checklist
- Landing.tsx: Pricing features, Final CTA H2 + lede, Footer tagline

- [ ] **Step 5: Visual check + commit**

```bash
git add frontend/src/components/landing/parts/AudienceQualifier.tsx \
        frontend/src/components/landing/Landing.tsx \
        docs/landing/copy-sections-05-tail.md
git commit -m "feat(landing): rewrite AudienceQualifier + Pricing + Final CTA + Footer copy"
```

---

### Checkpoint 2 (Phase 2 done)

Manual browser walk-through `http://localhost:3001/` от начала до конца.

---

## Phase 3 — Design + visuals

### Task 14: 6 engraved portrait SVGs

**Files:**
- Replace: `frontend/public/landing/champions/{livermore,darvas,minervini,tudor-jones,elder,raschke}.svg`

- [ ] **Step 1: Generate stipple portraits (Strategy A)**

Использовать AI image generator (Midjourney/DALL-E) для каждого из 6:

```
Prompt template:
stipple engraving portrait of <NAME> (<YEARS, brief profession descriptor>),
black ink dots on cream paper, WSJ-style hedcut illustration, monochrome,
transparent background, 1:1 square, minimal background, high contrast
```

Конкретные подсказки для description:
- Livermore (1877-1940 American stock trader, 1920s formal suit, side-parted hair)
- Darvas (1920-1977 Hungarian-American dancer/trader, 1950s vintage formal)
- Minervini (born 1965, modern US business casual)
- Paul Tudor Jones (born 1954, contemporary US business attire, often photographed with legal pad)
- Elder (born 1950, Russian-American psychiatrist-trader, thoughtful expression)
- Linda Bradford Raschke (born 1959, only woman in cast, contemporary US business)

- [ ] **Step 2: Vectorize**

Конвертировать bitmap → SVG:
- Inkscape: `inkscape input.png --export-plain-svg=output.svg --export-area-page`
- Альтернатива: vectorizer.io
- Цвет линий: `#26221c`. Прозрачный background.

- [ ] **Step 3: Optimize SVGs**

```bash
cd frontend/public/landing/champions
npx svgo --multipass *.svg
```

Каждый файл ≤ 25 KB.

- [ ] **Step 4: Visual review**

`http://localhost:3001/#champions`:
- 6 портретов видны
- Стиль консистентен
- Цвет совпадает с `--ink`
- Mobile не размытые

Если Strategy A несогласованный → переключиться на Strategy B (spec § 6.1) с public-domain фото + CSS filter.

- [ ] **Step 5: Commit**

```bash
git add frontend/public/landing/champions/*.svg
git commit -m "feat(landing): 6 engraved portrait SVGs for Champions section"
```

---

### Task 15: Typography + palette tweaks

**Files:**
- Modify: `frontend/src/app/globals.css`
- Modify: `frontend/src/components/landing/Landing.tsx`

- [ ] **Step 1: Add new palette tokens**

В `globals.css` блок `[data-theme="maatt-cream"]` добавить:

```css
[data-theme="maatt-cream"] {
  /* ... existing tokens ... */
  --ochre-deep: #5d2a14;
  --paper-tint: #f4ecdc;
  --quote-mark: rgba(38, 34, 28, 0.08);
}
```

- [ ] **Step 2: Adjust H1 max size**

Найти `.editorial-display`, заменить max size в clamp с 96px на 88px (например `clamp(48px, 6vw, 88px)`).

- [ ] **Step 3: Unify H2**

В `.editorial-h2` зафиксировать font-size `clamp(32px, 4vw, 42px)`.

- [ ] **Step 4: Update eyebrow separator**

В `Landing.tsx` заменить «· » на «— » в eyebrow строках секций (Hero, Sections 01-06). НЕ менять разделитель в `Live Ticker` и в карточках чемпионов источник цитат (другой контекст).

- [ ] **Step 5: Numbers band spacing**

В `Landing.tsx` Numbers band секции: `gap-x-10 gap-y-10` → `gap-x-14 gap-y-14`.

- [ ] **Step 6: Visual check**

`http://localhost:3001/`:
- H1 ≤ 88px
- H2 равномерно ~42px
- Eyebrow с em-dash «— »

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/globals.css frontend/src/components/landing/Landing.tsx
git commit -m "feat(design): palette tokens + typography refinements"
```

---

### Task 16: Widget polish

**Files:**
- Modify: `frontend/src/components/landing/parts/LiveTicker.tsx`
- Modify: `frontend/src/components/landing/parts/HeroEquityCurve.tsx`
- Modify: `frontend/src/components/landing/parts/TradeReplayWidget.tsx`
- Modify: `frontend/src/components/landing/parts/InteractiveCandleChart.tsx`
- Modify: `frontend/src/components/landing/Landing.tsx` (widget wrapper borders)

- [ ] **Step 1: LiveTicker — pulse 1.5s → 2.0s + paper-tint фон**

В `LiveTicker.tsx`:
- Animation duration `1.5s` или `1500ms` → `2s` / `2000ms`
- Background container класс → `bg-[var(--paper-tint)]/60` (или style)

- [ ] **Step 2: HeroEquityCurve — eyebrow + убрать grid**

В `HeroEquityCurve.tsx`:
- Удалить grid `<line>`/`<g>` элементы если есть
- Добавить под SVG:

```tsx
<p className="text-[11px] mt-3 text-[var(--ink-3)] uppercase tracking-[0.08em]"
   style={{ fontFamily: "var(--font-mono), monospace" }}>
  Открытая позиция · −1.2R
</p>
```

- [ ] **Step 3: TradeReplayWidget wrapper border**

В `Landing.tsx` секция Раздел 01 wrapper div:
- `border-[var(--rule-strong)]` → `border-[var(--ink-3)]`

В `TradeReplayWidget.tsx`: если есть `shadow-md` → `shadow-sm` или убрать.

- [ ] **Step 4: InteractiveCandleChart tooltip refinement**

В `InteractiveCandleChart.tsx` найти tooltip div:
- Добавить `style={{ background: "var(--paper-tint)" }}` или эквивалент классом
- Цифры в tooltip обернуть `className="num"` (использует JetBrains Mono из .num)

- [ ] **Step 5: Visual check**

```bash
cd frontend
# regenerate baselines будет на Task 17, тут просто визуально
```

Открыть dev, scroll по виджетам — проверить hover-tooltips, pulse, equity-eyebrow.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/landing/parts/*.tsx \
        frontend/src/components/landing/Landing.tsx
git commit -m "feat(design): widget polish — pulse, equity-eyebrow, tooltip, borders"
```

---

### Task 17: Playwright visual regression — full baseline regenerate

**Files:**
- Modify: `frontend/e2e/landing-visual.spec.ts`
- Create: `frontend/e2e/landing-visual.spec.ts-snapshots/*.png` (через --update-snapshots)

- [ ] **Step 1: Extend visual spec**

Добавить в `landing-visual.spec.ts`:

```typescript
test('simple-fact section desktop', async ({ page }) => {
  await page.goto('/');
  await page.locator('#simple-fact').scrollIntoViewIfNeeded();
  await expect(page.locator('#simple-fact')).toHaveScreenshot('simple-fact-desktop.png');
});

test('champions section desktop', async ({ page }) => {
  await page.goto('/');
  await page.locator('#champions').scrollIntoViewIfNeeded();
  await expect(page.locator('#champions')).toHaveScreenshot('champions-desktop.png');
});

test('metric explainers expanded', async ({ page }) => {
  await page.goto('/');
  const sel = 'section:has(h2:has-text("метрик"))';
  await page.locator(sel).scrollIntoViewIfNeeded();
  await expect(page.locator(sel)).toHaveScreenshot('metrics-table.png');
});

test('audience qualifier', async ({ page }) => {
  await page.goto('/');
  const sel = 'section:has(h2:has-text("Для серьёзного"))';
  await page.locator(sel).scrollIntoViewIfNeeded();
  await expect(page.locator(sel)).toHaveScreenshot('audience-qualifier.png');
});
```

Плюс mobile варианты тех же тестов через `test.use({ viewport: { width: 375, height: 812 } })`.

- [ ] **Step 2: Generate baselines**

```bash
cd frontend
npx playwright test landing-visual.spec.ts --update-snapshots
```

- [ ] **Step 3: Re-run to verify all pass**

```bash
npx playwright test landing-visual.spec.ts
```

Expected: PASS все тесты.

- [ ] **Step 4: Commit**

```bash
git add frontend/e2e/landing-visual.spec.ts frontend/e2e/landing-visual.spec.ts-snapshots/
git commit -m "test(landing): visual regression baselines for new sections"
```

---

### Checkpoint 3 (Phase 3 done)

Browser walk-through + Playwright suite green.

---

## Phase 4 — SEO

### Task 18: Metadata + 4 JSON-LD blocks

**Files:**
- Modify: `frontend/src/app/layout.tsx`
- Create: `frontend/src/app/structured-data.ts`

- [ ] **Step 1: Update metadata in layout.tsx**

Заменить existing `metadata` export:

```typescript
export const metadata: Metadata = {
  title: "МААТТ · Журнал сделок MOEX — дневник трейдера с автостатистикой",
  description:
    "Автоматический журнал сделок для трейдера MOEX: 30+ метрик " +
    "(Optimal f, SQN, MAE/MFE), синхронизация с Тинькофф API, " +
    "разбор каждой сделки. Бесплатно до 50 сделок в месяц.",
  alternates: {
    canonical: "https://maatt.ru/",
    languages: { "x-default": "https://maatt.ru/", "ru-RU": "https://maatt.ru/" },
  },
  openGraph: {
    title: "МААТТ — журнал сделок MOEX",
    description:
      "Автостатистика по 30+ метрикам. MAE/MFE из биржевых свечей. " +
      "Дневник, который ведут чемпионы.",
    url: "https://maatt.ru/",
    siteName: "МААТТ",
    locale: "ru_RU",
    type: "website",
    images: [{ url: "/landing/og-image.png", width: 1200, height: 630 }],
  },
  twitter: {
    card: "summary_large_image",
    title: "МААТТ — журнал сделок MOEX",
    description: "Автостатистика. Дневник чемпионов.",
    images: ["/landing/og-image.png"],
  },
  icons: { /* keep existing icons block */ },
};
```

- [ ] **Step 2: Create structured-data.ts**

```typescript
// frontend/src/app/structured-data.ts
import { CHAMPIONS } from "@/components/landing/data/champions";

const SITE_URL = "https://maatt.ru";

export const organizationSchema = {
  "@context": "https://schema.org",
  "@type": "Organization",
  name: "МААТТ",
  url: SITE_URL,
  logo: `${SITE_URL}/favicon.svg`,
  description: "Автоматический журнал сделок для трейдеров MOEX",
};

export const softwareApplicationSchema = {
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  name: "МААТТ",
  applicationCategory: "FinanceApplication",
  operatingSystem: "Web",
  offers: [
    { "@type": "Offer", name: "Free", price: "0",   priceCurrency: "RUB" },
    { "@type": "Offer", name: "Pro",  price: "399", priceCurrency: "RUB" },
  ],
  description: "Журнал сделок MOEX с автостатистикой по 30+ метрикам",
};

export const faqSchema = {
  "@context": "https://schema.org",
  "@type": "FAQPage",
  mainEntity: [
    {
      "@type": "Question",
      name: "Зачем вести журнал сделок?",
      acceptedAnswer: {
        "@type": "Answer",
        text:
          "Запись отделяет трейдера от игрока. Память врёт, цифра не врёт. " +
          "Журнал даёт edge до всяких метрик и алгоритмов.",
      },
    },
    {
      "@type": "Question",
      name: "Какие метрики считает МААТТ?",
      acceptedAnswer: {
        "@type": "Answer",
        text:
          "30+ метрик: Optimal f, SQN, R-Expectancy, Sortino, Calmar, " +
          "Monte Carlo, MAE/MFE из свечей MOEX.",
      },
    },
    {
      "@type": "Question",
      name: "Бесплатно?",
      acceptedAnswer: {
        "@type": "Answer",
        text:
          "Free до 50 сделок в месяц с базовыми метриками. Pro 399 ₽/мес " +
          "со всеми метриками и AI-разбором.",
      },
    },
  ],
};

export const championsSchemas = CHAMPIONS.map((c) => ({
  "@context": "https://schema.org",
  "@type": "Person",
  name: `${c.firstName} ${c.lastName}`,
  alternateName: c.originalName,
  birthDate: c.birthYear.toString(),
  ...(c.deathYear && { deathDate: c.deathYear.toString() }),
  sameAs: c.wikipediaUrl,
  subjectOf: {
    "@type": "Quotation",
    text: c.quote,
    citation: c.source,
  },
}));

export function allSchemasJson(): string {
  return JSON.stringify([
    organizationSchema,
    softwareApplicationSchema,
    faqSchema,
    ...championsSchemas,
  ]);
}
```

- [ ] **Step 3: Inject schemas in layout.tsx via next/script**

Использовать `next/script` (safe, не нужен `dangerouslySetInnerHTML`):

```tsx
// frontend/src/app/layout.tsx
import Script from "next/script";
import { allSchemasJson } from "./structured-data";

// внутри return body:
<Script id="structured-data" type="application/ld+json" strategy="beforeInteractive">
  {allSchemasJson()}
</Script>
```

Поместить `<Script>` после `{children}` или в `<head>` через App Router — следовать существующему паттерну в проекте.

- [ ] **Step 4: Verify JSON-LD with browser**

Запустить dev. `view-source:http://localhost:3001/`, найти `<script id="structured-data">`. Скопировать содержимое в [validator.schema.org](https://validator.schema.org/) — все блоки должны пройти валидацию.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/layout.tsx frontend/src/app/structured-data.ts
git commit -m "feat(seo): metadata + JSON-LD via next/script — Org, SoftwareApp, FAQ, Person×6"
```

---

### Task 19: Sitemap + robots + OG image regenerate

**Files:**
- Modify: `frontend/src/app/sitemap.ts`
- Modify: `frontend/src/app/robots.ts`
- Modify: `frontend/public/landing/og-image.png`

- [ ] **Step 1: Update sitemap.ts**

```typescript
// frontend/src/app/sitemap.ts
import type { MetadataRoute } from "next";

export default function sitemap(): MetadataRoute.Sitemap {
  const base = "https://maatt.ru";
  const lastModified = new Date();
  return [
    { url: `${base}/`,             lastModified, changeFrequency: "weekly",  priority: 1.0 },
    { url: `${base}/#simple-fact`, lastModified, changeFrequency: "monthly", priority: 0.8 },
    { url: `${base}/#champions`,   lastModified, changeFrequency: "monthly", priority: 0.8 },
    { url: `${base}/#metrics`,     lastModified, changeFrequency: "weekly",  priority: 0.7 },
    { url: `${base}/pricing`,      lastModified, changeFrequency: "monthly", priority: 0.9 },
    { url: `${base}/manual`,       lastModified, changeFrequency: "weekly",  priority: 0.6 },
  ];
}
```

- [ ] **Step 2: Update robots.ts**

```typescript
// frontend/src/app/robots.ts
import type { MetadataRoute } from "next";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/api/", "/admin/", "/_next/", "/dashboard/"],
      },
    ],
    sitemap: "https://maatt.ru/sitemap.xml",
    host: "https://maatt.ru",
  };
}
```

- [ ] **Step 3: Regenerate OG image**

Реюзать существующий pipeline:

```bash
cd frontend
npm run capture:og  # если скрипт есть
```

Иначе вручную: headless playwright, screenshot Hero area 1200×630 → `public/landing/og-image.png`.

- [ ] **Step 4: Verify**

- `http://localhost:3001/sitemap.xml` — 6 URL
- `http://localhost:3001/robots.txt` — Disallow для api/admin
- OG: [opengraph.xyz](https://www.opengraph.xyz/)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/sitemap.ts \
        frontend/src/app/robots.ts \
        frontend/public/landing/og-image.png
git commit -m "feat(seo): sitemap with anchor-URLs + robots + regenerated OG image"
```

---

### Task 20: SEO checklist + Lighthouse + final review

**Files:**
- Create: `docs/landing/seo-checklist.md`

- [ ] **Step 1: Run Lighthouse**

```bash
cd frontend
# dev server должен быть запущен на 3001
npx lighthouse http://localhost:3001/ \
  --only-categories=performance,accessibility,seo,best-practices \
  --form-factor=mobile \
  --output=html --output-path=./lighthouse-mobile.html
```

Target: ≥ 95 в каждой категории. Если ниже — определить причины (Network, JS bundle, CLS из-за гравюр без width/height).

- [ ] **Step 2: Create seo-checklist.md**

```markdown
# SEO Manual Steps Checklist

После деплоя в production:

- [ ] Yandex.Webmaster:
  1. https://webmaster.yandex.ru
  2. Property maatt.ru
  3. Submit sitemap.xml
  4. Проверка структурированных данных
- [ ] Google Search Console:
  1. https://search.google.com/search-console
  2. Property maatt.ru
  3. Submit sitemap.xml
- [ ] Yandex.Metrika:
  1. Counter ID в layout.tsx — production
  2. Цели: register-cta-click, telegram-cta-click, free-cta-click
- [ ] OG preview:
  1. https://www.opengraph.xyz/url/maatt.ru
  2. https://cards-dev.twitter.com/validator
  3. Telegram link preview
- [ ] Schema.org validation:
  1. https://validator.schema.org/ — paste maatt.ru
- [ ] Mobile-Friendly:
  1. https://search.google.com/test/mobile-friendly
- [ ] Core Web Vitals:
  1. https://pagespeed.web.dev/analysis?url=https://maatt.ru
```

- [ ] **Step 3: Dispatch code-reviewer**

```
Agent tool (code-reviewer):
  description: "Final review of landing rebuild diff"
  prompt: |
    Review diff feat/landing-handcrafted vs db17c93 (spec commit).

    Focus:
    - File create/modify count matches plan File Structure section
    - Landing.tsx imports correctly, no orphan stubs
    - Voice consistency in committed copy files
    - JSON-LD blocks validate (test with validator.schema.org content)
    - Visual regression baselines exist for new sections
    - No console errors when dev server runs
    - TypeScript compiles (npx tsc --noEmit) clean
    - ESLint clean (npm run lint)
    - Playwright tests pass (npx playwright test)

    Report: Strengths, Issues (Critical/Important/Minor), Assessment.
```

- [ ] **Step 4: Dispatch security-reviewer**

```
Agent tool (security-reviewer):
  description: "Security review of landing diff"
  prompt: |
    Security review of landing rebuild diff vs db17c93.

    Focus:
    - No PII/secrets in committed copy files
    - JSON-LD via next/script — content statically generated, no user input
    - External Wikipedia URLs — verify no XSS risk in href
    - SVG portraits — no embedded scripts (<script>, on* attrs)
    - OG image URL — same-origin
    - 152-ФЗ compliance unchanged (footer privacy link works)

    Report findings.
```

- [ ] **Step 5: Address critical/important issues**

Если reviewers выкатили critical/important — патчить, повторять Tasks 18-19 если нужно.

- [ ] **Step 6: Commit checklist**

```bash
git add docs/landing/seo-checklist.md
git commit -m "docs(seo): manual checklist for production deploy"
```

---

### Checkpoint 4 (Phase 4 done) — Ready to merge

Все тесты зелёные, Lighthouse ≥ 95, два reviewer'а зелёные. Готово к merge в main.

---

## Self-review

**Spec coverage check:**

| Spec section | Plan task | Status |
|---|---|---|
| § 2 Big idea | Task 7 (Hero copy) | OK |
| § 3 IA (16 секций) | Task 6 | OK |
| § 3.1 SimpleFact | Task 8 | OK |
| § 3.2 Champions × 6 | Tasks 4, 9, 10, 14 | OK |
| § 4 Voice + anti-vocab | Task 2 (voice.md) | OK |
| § 4.1-4.4 rules | Applied in Tasks 7, 10-13 copywriter prompts | OK |
| § 5 SEO keywords | Tasks 7, 18 | OK |
| § 5.2 Meta tags | Task 18 | OK |
| § 5.3 JSON-LD (4 schemas) | Task 18 | OK |
| § 5.4 Semantic HTML | Tasks 8, 9 | OK |
| § 5.5 Technical SEO | Tasks 18, 19, 20 | OK |
| § 6.1 Engravings | Task 14 | OK |
| § 6.2 Typography | Task 15 | OK |
| § 6.3 Palette | Task 15 | OK |
| § 6.4 Widget polish | Task 16 | OK |
| § 6.5 New components | Tasks 8, 9 | OK |
| § 6.6 Accessibility | Implicit Tasks 8, 9 + Task 20 review | OK |
| § 6.7 Visual regression | Task 17 | OK |
| § 7 Orchestration 4 phases | All tasks grouped under phase headings | OK |

**Placeholder scan:** All steps have concrete code blocks, no TBD/TODO. Subagent prompts contain full context. Champion bio/quote content is delegated to Task 4 research → Task 10 copywriter (correct — cannot pre-write what doesn't exist).

**Type consistency:** `Champion` type defined Task 9, used Tasks 14 (portraitSrc), 18 (championsSchemas reads same fields). `SimpleFactItem` defined Task 8, used same task. No drift.

---

## Plan complete

Saved to `docs/superpowers/plans/2026-05-18-landing-champions-rebuild.md`.

**Execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, two-stage review (spec compliance + code quality) between tasks. Best fit since most tasks dispatch domain-specific agents anyway.

2. **Inline Execution** — все 20 задач в текущей сессии, чекпойнты после фаз. Быстрее, но риск переполнения контекста.
