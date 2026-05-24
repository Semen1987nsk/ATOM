# ADR-0006: Editorial Financial rebrand (supersedes implicit «Linear-style»)

**Статус:** Принято (2026-05-17). Реализация в текущей сессии (Phase 0–5, см. план `C:\Users\Administrator\.claude\plans\noble-herding-book.md`).
**Supersedes:** неявное решение в [`design-system.md` v2](../../product/design-system.md) о «Linear/Vercel/Stripe-стиле, отказ от Bloomberg-meets-cyberpunk» (зафиксировано в [`history/2026-05-07-audit-and-stack-up.md`](../../history/2026-05-07-audit-and-stack-up.md) как достижение аудит-сессии). Раздел «Цвета», «Типографика», «Радиусы», «Лендинг-классы» переписываются полностью.
**Связанное:** [`product/CLAUDE.md`](../../product/CLAUDE.md) (правило «никаких новых цветов и шрифтов» — обновляется), [`feature-canon/01-dashboard.md`](../../product/feature-canon/01-dashboard.md) (раздел «Семантика цвета» — патчится), [`marketing/messaging.md`](../../marketing/messaging.md) (tone-of-voice «спокойный профи» — сохраняется и усиливается).

## Контекст

В мае 2026 пользователь констатировал: текущий UI Eqio (лендинг + залогиненная часть) визуально неотличим от типового AI-vibecoded SaaS-аутпута. Аудит UI подтвердил наличие классических «AI-tells», описанных Anthropic в материалах по skill `frontend-design` (ноябрь 2025):

- **Indigo `#6366F1`** как brand-accent — это статистический центр LLM-генерации UI (~80% всех AI-сгенерированных лендингов).
- **Фиолетово-индиго градиенты 135°** на 6 Bento-плитках лендинга (`tile-indigo`, `tile-violet`, `tile-emerald`, `tile-rose`, `tile-amber`, `tile-sky`).
- **Hardcoded `from-cyan-500 to-teal-500`** в `MAEMFECard.tsx` и **`from-purple-500 to-pink-500`** в `PostExitCard.tsx` — прямое нарушение действующего канона («Discord-стиль accent» уже запрещён в `design-system.md` v2:151, но осталось в коде).
- **3-колоночные feature-grid** с иконкой-в-цветном-круге сверху — каноничный SaaS-template.
- **`--radius-xl: 20px`** на всех карточках, pill-buttons как primary CTA, `Sparkles` lucide-иконка в hero, `backdrop-blur` translucent панели — каждый из этих признаков по отдельности безобиден, в комбинации даёт «явно AI».

Канон `design-system.md` v2 от 07.05.2026 сознательно отказался от изначального видения «Bloomberg-meets-cyberpunk» (neon, glow, монопространный) в пользу «Linear/Vercel/Stripe-стиля». Это решение принималось до того, как стало понятно, что **именно Linear/Vercel-стиль и есть LLM-default** — поэтому он перестал нести сигнал «премиум-инструмент» и стал нести сигнал «vibe-coded SaaS».

Целевая персона P1 ([`personas.md`](../../product/personas.md)) — «серьёзный РФ-трейдер 28–45, технический/финансовый бэкграунд, скептичен ко всему западному и шаблонному, цена в рублях работает». Для него «выглядит как Linear» — это не плюс, а отталкивающий маркер «ещё один SaaS-сервис, который завтра закроют».

**Освобождная категория:** ни один прямой конкурент в trading-журналах не использует editorial-financial эстетику. TradeZella — Linear-копия, Tradervue — устаревший дашборд-стиль, Edgewonk — корпоративный SaaS, TraderMake/Tradary — generic-крипто-стиль. Финансовая пресса (FT.com, Bloomberg.com/markets, Stripe Press, WSJ.com) — оккупирована издателями, не продуктами. Заняв эту визуальную нишу для трейдинг-журнала, Eqio получает уникальную визуальную подпись, читаемую как «настоящий профессиональный инструмент».

## Решение

Принят стиль **Editorial Financial**, со следующими аксиомами:

### Типографика — три семьи

- **Headlines/display:** Fraunces (вариативный serif, full cyrillic, italic-пара, optical-size axis). Близкий free-аналог Tiempos Headline / Söhne Serif. Используется в H1/H2/display и в editorial-lede.
- **Body/UI:** Geist Sans (без изменений). Сохраняется как утилитарный sans с cyrillic-subset.
- **Digits:** Geist Mono (без изменений) с принудительным `font-variant-numeric: tabular-nums lining-nums` на всех числах, таблицах, StatTile-значениях.

Snowballing: одна serif-семья + одна sans + одна mono = классическая editorial-палитра шрифтов (FT, Bloomberg, Stripe Press строятся на этой же базе).

### Палитра — warm paper + ink + single acid

**Dark theme (default — трейдеры работают в темноте):**

- Paper-base `#14110d` (warm near-black, тёплый коричневатый, не cold cyberpunk-чёрный `#0a0a0b`).
- Ink `#f5f1e8` (warm off-white).
- Hairline rules — `rgba(245,241,232,0.10)` и `0.22` для усиленных.
- Acid accent **`#d4a13a` ochre** (FT/Bloomberg territory). Не конфликтует с P&L-семантикой (не красный, не зелёный, не индиго).
- P&L semantic: profit `#2c8c5c` (forest green, не neon `#10b981`), loss `#b94731` (brick red, не neon `#f43f5e`). Desaturated editorial-print.

**Light theme — FT pink-paper:** `#faf7f0` cream paper, accent тоном темнее (`#b5871f`) для контраста.

### Геометрия — почти flat

- `--radius-xl` редуцируется с 20px до 8px (все 20px-карточки автоматически становятся 8px через `var()` ребиндинг).
- Радиусы 2–6px на inputs/buttons. Pill-buttons (9999px) остаются ТОЛЬКО для filter chips, НЕ как primary CTA.
- Тени удаляются по умолчанию. Карточка = hairline border, не shadow. Единственная разрешённая тень — модалки.

### Композиция — asymmetric editorial

- 12-col grid с asymmetric распределением (5/7, 7/5, 9/3 — не симметричные 4/4/4).
- Hairline rules (`border-top: 1px solid var(--rule)`) разделяют секции вместо боксов-карточек.
- Pull-quotes (крупный serif italic) центрированы между rule-strong, без карточек.
- Numbers band — 4 hairline-separated columns с mono-числами и serif-labels.
- Метрики (вместо 6 цветных tiles) — dense editorial-table со sticky header.

### Семантика цвета (для дашборда)

- Profit `var(--profit)` (forest green), Loss `var(--loss)` (brick red) — на equity-curve, в StatTile значениях, в badges.
- IMOEX benchmark overlay — приглушённый ochre `var(--accent)`, dashed line.
- Все остальные числа — `var(--ink)` (warm white). Никаких «пёстрых цветов для разных метрик».

### Композиция CTA

Primary CTA — rectangle button с `--radius-md` (4px), не pill. Цвет — ochre accent, надпись `var(--paper-base)` (warm dark). Outline CTA — прозрачный с border `currentColor` и тем же 4px radius.

## Технические следствия

### Frontend (`frontend/`)

1. **`globals.css`** — полная замена `:root` и `:root[data-theme="light"]` (см. план §2.1). Удаление `.tile-{indigo,violet,emerald,rose,amber,sky}`, `.text-gradient`, `.text-neon`, `.bg-mesh-*`, `.pulse-glow`, `.float`, `.glow-*`. Замена `.btn-primary` radius с pill на md.
2. **`layout.tsx`** — добавление Fraunces через `next/font/google` как `--font-serif`, cyrillic subset для Geist Sans.
3. **`app/page.tsx`** — guest-landing-ветвь (lines 332–825) извлекается в новый компонент `components/landing/Landing.tsx` и переписывается с нуля в editorial-композиции (10 секций, см. план §3.2). Authenticated-ветвь (lines 826+) не меняется.
4. **`components/landing/KonturCurve.tsx`** — удаляется полностью.
5. **`components/ui/Tile.tsx`** — TypeScript-тип `TileColor` редуцируется до `"neutral" | "inverse"`. Все вызовы `<Tile color="indigo|violet|emerald|rose|amber|sky" />` начнут падать TS-ошибкой — это намеренно, для compiler-driven discovery call-sites.
6. **`components/dashboard/MAEMFECard.tsx`, `PostExitCard.tsx`, `MAEMFEAnalysisPanel.tsx`, `PortfolioCard.tsx`** — точечная зачистка hardcoded `from-*/to-*` Tailwind-классов.
7. **`app/pricing/page.tsx`, `app/manual/page.tsx`, `app/profile/page.tsx`, `app/admin/page.tsx`, `components/TrialEndedDialog.tsx`, `TrialCountdownBanner.tsx`, `ImportPreviewModal.tsx`** — grep-replace gradient utility-классов, инспекция featured-plan на gradient-фоны.

### Канон (`.business/product/`)

1. **`design-system.md` → v3** — полное переписывание разделов «Цвета», «Типографика», «Радиусы», «Лендинг-классы», «Анти-паттерны». Версия указана в начале файла.
2. **`feature-canon/01-dashboard.md`** — точечный патч раздела «Семантика цвета» (indigo accent → ochre).
3. **`product/CLAUDE.md`** — обновление жёстких правил: «Geist + Fraunces» вместо «Geist only», «никаких новых цветов после v3» вместо «после v2».

### Инструменты (Phase 0)

Подключаются 3 MCP-сервера в `ATOM/.claude/settings.json`:
- `chrome-devtools` (npx `chrome-devtools-mcp@latest`) — для screenshot-итерации.
- `shadcn-ui` (npx `@jpisnice/shadcn-ui-mcp-server`) — reference-чтение editorial-компонентов (НЕ миграция на shadcn).
- `21st-dev-magic` (npx `@21st-dev/magic@latest`) — генерация editorial-блоков (требует API-key с https://21st.dev, регистрирует пользователь).

## Последствия

### Плюсы

- **Уникальная визуальная подпись.** Eqio не пересекается визуально ни с одним AI-vibecoded SaaS и ни с одним прямым конкурентом в trading-журналах. Это работает как brand-recognition даже без бюджета на performance-маркетинг.
- **Усиление позиционирования.** «MOEX-нативный AI-журнал» + editorial-financial эстетика = consistent message «настоящий финансовый продукт», не «крипта/forex/SaaS-template».
- **Tone-of-voice resonance.** «Спокойный профи» из `messaging.md` визуально подкрепляется serif-headlines и hairline-композициями. Tone и visual теперь говорят одно и то же.
- **Premium perception без премиум-бюджета.** Editorial-эстетика читается как «hand-crafted», даже когда генерируется LLM — потому что LLM по умолчанию её не выбирает.
- **Future-proof.** AI-tells выявленные в 2026 (Indigo + Inter + gradient-tiles) — следствие тренировочной выборки 2023–2025. Editorial-financial — стиль 100-летних финансовых газет. Он не устареет в следующей волне distributional convergence.

### Минусы / риски

1. **Полный rewrite guest-landing** (page.tsx, 1252 строки). Iterative patching исключён — оставит fossils. Ожидаемая стоимость: ~6 часов одного сеанса.
2. **9+ файлов app-UI** с hardcoded gradient-классами требуют ручной grep-replace. Большинство — точечно по 1–3 строк, manual/page.tsx — крупный (~12 occurrences).
3. **Fraunces на русском.** Variable serif с cyrillic-subset существует, но русский italic читается необычно. Mitigation — открыть demo с русским hero и спросить пользователя «читается?». Fallback — Source Serif 4 (более utilitarian, но полностью кириллический).
4. **Light theme drastically different** (FT pink-paper). Юзеры с light-preference увидят кардинально изменённый UI. Mitigation — `personas.md` явно говорит «трейдеры работают в темноте», dark остаётся primary.
5. **`ux-laws.md` напряжение.** Закон «плотность важнее воздуха» для дашборда — Editorial для лендинга использует больше whitespace. Решение: законы применяются по контексту — landing допускает editorial-air, dashboard сохраняет density. `ux-laws.md` не меняется.
6. **Связь с историей.** `history/2026-05-07-audit-and-stack-up.md` ссылается на «отказ от Bloomberg-cyberpunk → Linear» как достижение. Этот ADR явно supersede это решение, audit-сессия остаётся как historical record.
7. **Breaking change для скриншотов.** `feature-canon/01-dashboard.md` ссылается на `eqio-final-dashboard.png` — после рефакторинга скриншоты устаревают. Митигация: Phase 5 — пересохранить скриншоты, обновить ссылки.
8. **Light theme рефакторинг откладывается.** Все 16 hardcoded overrides в `globals.css:551–569` (`text-gray-400`, `bg-white/5` etc.) — legacy для старого Tailwind-кода. После Phase 4 будут визуально странные на новом cream-paper фоне. Не блокер для Phase 0–5, но требует отдельного захода (см. план §«What follows after this plan»).

## Поведенческие правила

1. **Никаких новых цветов после v3.** Если возникает потребность в дополнительном цвете — сначала обновление `design-system.md` v4 + новый ADR.
2. **Никаких новых шрифтов.** Geist + Fraunces — закрытое множество.
3. **Никаких gradient backgrounds на UI-элементах.** Gradient — это AI-tell. Если кажется, что нужен — используется solid `var(--accent-soft)` или hairline border.
4. **Никаких pill-buttons как primary CTA.** Pill — только для filter chips.
5. **Никаких pulse-glow / animate-pulse на индикаторах.** Анимации точечные, не вечные.
6. **Все числа — Geist Mono с tabular-nums.** Прыгающие proportional-цифры в таблице — анти-паттерн.
7. **P&L-цвета — только `var(--profit)` / `var(--loss)`.** Никаких Tailwind `text-green-500` / `text-red-500` хардкодом — иначе light-theme сломается.

## Связанное

- [`product/design-system.md`](../../product/design-system.md) — будет переписан в v3 в Phase 1.2 текущего плана
- [`product/feature-canon/01-dashboard.md`](../../product/feature-canon/01-dashboard.md) — будет точечно патчен в Phase 1.3
- [`product/CLAUDE.md`](../../product/CLAUDE.md) — жёсткие правила обновляются
- [`marketing/messaging.md`](../../marketing/messaging.md) — tone «спокойный профи» теперь подкреплён визуально
- [`personas.md`](../../product/personas.md) — P1 «скептичен ко всему западному» — driving constraint
- [`ux-laws.md`](../../product/ux-laws.md) — «плотность важнее воздуха» остаётся для app, не для landing
- План реализации: `C:\Users\Administrator\.claude\plans\noble-herding-book.md`

## Источники

- [Anthropic — Improving frontend design through Skills (ноябрь 2025)](https://www.anthropic.com/) — основа концепции distributional convergence и negative constraints
- [Anthropic skill `frontend-design` SKILL.md](https://github.com/anthropics/skills) — список «AI-tells» (Inter, gradient-purple, stacked-cards)
- [FT.com](https://www.ft.com/) — reference editorial-financial composition
- [Stripe Press](https://press.stripe.com/) — reference type-pairing (serif + sans)
- [Bloomberg Markets](https://www.bloomberg.com/markets) — reference dense data-tables + warm ochre accent
- [Fraunces specimen](https://fonts.google.com/specimen/Fraunces) — cyrillic subset, variable axes
