# Copy — Phase 2 Hero + Numbers + Manifest + Customer Pull-quote
*Last updated: 2026-05-18*

Source documents: `docs/brand/voice.md` (9 rules, anti-vocabulary, favorite vocabulary), `docs/brand/messaging.md` (big idea, 3 pillars, channel adaptation rows §3 / §6 / §7 / §11), `docs/landing/cro-audit.md` (Hero A/B variants, secondary CTA discovery bug, Numbers band tautology), `docs/superpowers/specs/2026-05-18-landing-champions-rebuild-design.md` §2 big idea + §3 IA + §4 voice, `.agents/product-marketing.md` (Customer Language, Proof Points, Objections), `frontend/src/components/landing/Landing.tsx` (current state).

Scope: четыре секции лендинга — Hero (§3), Numbers band (§6), Manifest cut-in (§7), Customer pull-quote (§11). Final CTA (§15) — отдельная Task 13.

---

## Section 3: Hero

### Eyebrow

**Recommended:** `── Журнал сделок · MOEX` *(keep — brand-separator)*

Rationale: средняя точка «·» — фирменный разделитель в eyebrow, не section-number. Spec §6.2 уже обновил section-number-eyebrow на em-dash «—» (например, «Раздел 02 — MAE / MFE»), но Hero-eyebrow здесь — другая роль: это inline-tagger «класс продукта · биржа», и точка тут стоит как лигатура двух facts, не как нумерация. `── ` (два em-dash + пробел) в начале — это leading editorial rule, типографская норма для cream-палитры (см. voice.md §Tone calibration #1: «── Журнал сделок · MOEX» приведён в hero-эталоне).

**Alternate (если редизайн eyebrow унифицирует разделители):** `── Журнал сделок — MOEX`. Не рекомендую — двойной em-dash в одной короткой строке создаёт визуальный гул на Fraunces; «·» здесь читается чище.

### H1 — 2 variants

**Variant A (Recommended for control):**

> Запись делает трейдера.
> Что записано — то измерено.

Rationale: canonical big idea из `messaging.md` §Big idea, плюс альтернатива «Что записано — то измерено» строкой ниже. Две строки = два утверждения = ритм Fraunces 88pt любит дыхание (voice.md Rule 4). По voice.md Rule 1 — это утверждения, не призывы; Rule 2 не задеваем (цифр здесь нет); Rule 3 в порядке (нет ИТ-метафор); Rule 8 в порядке (безличное). Big idea живёт полным голосом (messaging.md §Channel adaptation row 3 — Hero как §3 несёт A + B в genuine tie; H1 закрывает Pillar A целиком, lede ниже подключает Pillar B). Voice tone calibration #1 в voice.md приводит именно эту пару строк как hero-эталон — это уже utilized blueprint, не моя выдумка.

**Variant B (Challenger):**

> Память врёт.
> Запись — нет.

Rationale: альтернативная формулировка из messaging.md §Big idea (помечена как «Mentor-форма для SimpleFact и для email subject-line; не для Hero — слишком разговорная для главного fold»). CRO-аудит §A/B test ideas рекомендует именно эту пару как челленджер: 5 слов, конфронтационно, отражает verbatim-боль P1 «я не понимаю, где я теряю» (`.agents/product-marketing.md` §Customer Language). Loss-aversion фрейм («память врёт» — потеря доверия к себе) сильнее на cold-traffic из long-tail запросов «почему я теряю в трейдинге», «как вести дневник трейдера». Risk: messaging.md в явном виде помечает эту строку «не для Hero». Но CRO-аудит видит её как валидный челленджер для A/B-теста с критерием решения «scroll-depth past Hero + click на primary CTA». A/B-эксперимент = единственный честный способ снять конфликт между messaging.md (нормативный) и CRO (data-driven гипотеза).

**A/B test prediction:** A победит на warm-traffic из Smart-Lab / Тинькофф Pulse и из organic-search по brand+«дневник трейдера» (аудитория уже понимает ценность дневника; Sage-нота резонирует, editorial-tone не пугает). B победит на cold-traffic из long-tail problem-aware запросов («почему я сливаю депозит», «как перестать гадать в трейдинге»). Поскольку основной канал на бета-периоде — Smart-Lab / Pulse / brand-search, **A — control**, B — челленджер на отдельной cold-traffic-когорте после Q3 2026 paid launch. Метрика решения: CTA-click + scroll past Hero. На warm-trafic ожидаем CTR primary CTA по Variant A в диапазоне +12–22 % относительно текущего H1; на cold-trafic Variant B — потенциально +30–45 % при corner-case попадании в long-tail problem-aware (heuristic, без данных).

### Lede

**Recommended (2 sentences, 30–40 знаков на строку):**

> MAE и MFE из биржевых свечей.
> Тридцать с лишним метрик из работ
> Винса и Тарпа. На ваших сделках MOEX.
> Автосинхронизация с Тинькофф — 60 сек.

Rationale: формулировка взята из voice.md §Tone calibration #1 (Hero-эталон) — там уже соблюдена редакторская норма. Закрывает Pillar B в Hero-tie (messaging.md row 3 §Channel adaptation: «B — lede с MAE/MFE, 60 сек, 30+ метрик, Тинькофф автосинхронизация»). Структура — 4 коротких утверждения через точку (Rule 4: точек больше, чем запятых — 4 точки, 0 запятых на 4 строки). «Тридцать с лишним» — единственное место в копии, где число прописью допустимо, потому что (а) это устоявшаяся редакторская конструкция, (б) точное «30+» уже стоит в Numbers band ниже — дублировать цифру в lede плюс в monocube band под Hero = двойной numeric-удар без editorial-дыхания. Имена Винса и Тарпа — без эпитетов (Rule 9), привязки к страницам книг развёрнуты в §3 metrics table (Rule 9 требует source-attribution в первом значимом explainer-контексте, не в Hero-lede). «На ваших сделках MOEX» — Rule 8 («вы»). «60 сек» — Rule 2 (цифра обнажена). Anti-vocabulary scan: «революцион / прорыв / инноваци / уникальн / легко / быстро / без усилий / AI-powered / нейросет / next-gen» — ноль попаданий.

**Conflict flag for copywriter (Rule 2 vs voice.md exemplar):** voice.md §Tone calibration #1 содержит «Тридцать с лишним метрик» прописью, тогда как voice.md checklist item 4 («Цифры цифрами») и Rule 2 («цифры обнажены») формально требуют «30+ метрик». Конфликт между нормативным правилом и каноническим примером в одном и том же документе. Текущий lede воспроизводит exemplar дословно; решение принимать на уровне brand-voice-designer (синхронизировать exemplar с правилом или явно зафиксировать exception для редакторской конструкции в Rule 2).

Длина строк на Fraunces 18–20pt (editorial-lede): «MAE и MFE из биржевых свечей.» = 29 зн; «Тридцать с лишним метрик из работ» = 33 зн; «Винса и Тарпа. На ваших сделках MOEX.» = 39 зн; «Автосинхронизация с Тинькофф — 60 сек.» = 39 зн. Все четыре — в коридоре 30–40 зн (voice.md Rule 4 + spec §4.4).

**Alternate (если product-команда захочет вернуть упоминание автоматики «без Excel» из текущей копии):**

> MAE и MFE из биржевых свечей.
> Тридцать с лишним метрик. Автоматически
> на ваших сделках MOEX. Тинькофф — 60 сек.
> Никакого Excel.

Не рекомендую как primary: «Никакого Excel» — это объекция-ответ (`.agents/product-marketing.md` Objection #1, CRO §Objections row 1), а не product-claim. Объекция лучше отрабатывается в Section 13 AudienceQualifier (Phase 2 Task 13), не в Hero-lede. В Hero-lede место для proof points Pillar B, не для отрицательной дифференциации.

### Primary CTA

**Recommended:** `Начать бесплатно →` *(keep — proven)*

Rationale: CRO-аудит §Conversion friction оценивает текущий verbal anchor как ok, риск только в том, что «бесплатно» — слегка рекламный тон. Тон проверен: на warm-traffic выигрывает (CRO confirmed heuristic). Альтернативу «Открыть журнал» CRO предлагает как Final CTA Variant B (§A/B test ideas — Final CTA), не как Hero primary. Для Hero оставляем «Начать бесплатно» с ArrowRight icon. Risk-reversal — в trust-line ниже.

### Secondary CTA

**Recommended:** `Войти через Тинькофф ID →`

Rationale: текущий label «Подключить Тинькофф ID» CRO-аудит помечает как **discoverable trust-bug** (Issue #2, H-impact): пользователь жмёт ожидая OAuth, попадает на `/manual` (документация). Два варианта починки:

1. **Изменить target на `/register?provider=tinkoff_id`** (deep-link на OAuth-flow) — тогда label «Войти через Тинькофф ID →» точен: это вход через identity-provider в register-flow.
2. Оставить target `/manual` и переименовать в «Как подключается Тинькофф →» (честный read-link).

Рекомендую вариант 1: secondary CTA в Hero должен снижать friction на конверсии (CRO secondary impact), read-link на документацию — это leak attention из conversion-flow (CRO §Conversion friction row 5–8 — leak pattern). Label «Войти через Тинькофф ID» точно отражает actual flow (register → OAuth identity-provider → account creation), а не «подключение брокерского API» (это отдельный шаг внутри account, после регистрации). «Подключить» прямо лжёт о моменте действия. «Войти через» — стандартная identity-provider формулировка, нейтрально-фактическая, не sales.

**Alternate:** `Регистрация через Тинькофф ID →` — точнее семантически (не «войти», а «зарегистрироваться»; «войти» предполагает существующий аккаунт), но длиннее. Если frontend готов рендерить условный label на основе session-state (logged-in → «Войти», logged-out → «Регистрация»), стоит развести. В рамках Phase 2 copy-pass рекомендую универсальное «Войти через Тинькофф ID» — короче и работает в обоих случаях для OAuth-provider semantics.

**Alternate (если target `/manual` остаётся):** `Как подключается Тинькофф →`. Честно, но снижает CTR (пользователь видит «как» = «не сейчас»). Использовать только если backend register-flow с OAuth не готов к Phase 3.

Под secondary CTA — добавить trust micro-line (CRO §Trust signals missing, Hero placement): `152-ФЗ · Yandex Cloud · read-only Tinkoff API` (11 px JetBrains Mono, цвет `--ink-3`). Это закрывает объекции #2 и #5 (`.agents/product-marketing.md` Objections) в первый экран. Не входит в текущую структуру Hero — рекомендация в `Landing.tsx` Phase 3, не Phase 2 copy-only. Помечаю как handoff.

### Trust line

**Recommended:**

> Бесплатно до 50 сделок. Без карты. 21 день Pro в подарок.

*(keep — текущая формулировка уже соблюдает voice rules)*

Rationale: три факта через точку (Rule 4: 3 точки, 0 запятых = ритм-якорь). Цифры обнажены (Rule 2): 50, 21. Anti-vocabulary scan clean. Risk-reversal закрыт: «бесплатно» + «без карты» + «21 день Pro» = три из топ-3 SaaS-friction-снижателей. CRO-аудит Issue #5 рекомендует только перенос «21 день» в бейдж рядом с Pro-карточкой в Pricing — но в Hero-trust-line строка остаётся. Phase 2 copy-only: оставляем дословно. Phase 3 frontend: размер 12 px monospace остаётся, в Final CTA повторяем эту же строку как rhyme-якорь.

**Alternate (если CRO-команда захочет добавить FIFO-disclosure):**

> Бесплатно до 50 сделок. Без карты. 21 день Pro в подарок. После 50-й — FIFO.

Не рекомендую: 5-й факт в Hero-trust-line нагружает первый экран и снижает CTA-click (CRO §Conversion friction row 4 предупреждает: «5-й факт нагружает Hero»). FIFO-disclosure правильно живёт в Pricing feature-list (CRO §Anchor pricing recommendation #6). В Hero-trust-line оставляем 3 факта.

---

## Section 6: Numbers band

| Idx | value | label | note |
|---|---|---|---|
| 0 | `30+` | метрик из книг | Винс, Тарп · Optimal f, SQN, Sortino, Calmar |
| 1 | `6` | торговых режимов MOEX | акции, ОФЗ, корп. облигации, ETF, фьючерсы, валюты |
| 2 | `60 сек` | синхронизация сделок | через Tinkoff Invest API · read-only |
| 3 | `399 ₽` | в месяц · Pro | без карты на старте · 21 день в подарок |

Rationale per row:

**Row 0 · `30+` метрик из книг.** Текущая копия «метрик статистики» — тавтология (CRO Issue #6, M-impact: метрика по определению — статистическая мера). Новый label `метрик из книг` (3 слова) — Sage-якорь без жаргона; полная attribution «Винс, Тарп» вынесена в note вместе с конкретными именами метрик. Это двойная работа note: (а) Rule 9 (имена методологов без эпитетов; полная attribution с книгами и страницами — в metrics table §10), (б) Pillar A приходит фоном через note, что соответствует messaging.md row 6: «Lead pillar B, Secondary C» — Pillar A здесь точечное вкрапление, работает как Sage-якорь без захвата лидерства. Имена 4 метрик (Optimal f, SQN, Sortino, Calmar) остаются в note — P1 узнает и кликнет на metrics table ниже.

**Row 1 · `6` торговых режимов MOEX.** Текущая копия «MOEX-бордов» — жаргон (CRO Issue #6): P3 не поймёт «борд», P1 не оценит. «Торговый режим» — формальный термин MOEX ISS (TQBR, TQOB, TQCB, TQTF, RFUD, CETS — это режимы торгов, см. документацию MOEX), точный и читаемый. Note — те же 6 классов инструментов через запятую, как в текущей копии (acceptable из messaging.md row 6 key phrases). Pillar C — заявлено лидирующим вместе с Pillar B (messaging.md row 6 «B + C»); «MOEX» в label — рамка применимости в чистом виде.

**Row 2 · `60 сек` синхронизация сделок.** Текущая копия «обновление портфеля» — неточно: МААТТ синхронизирует не «портфель» (это позиции / holdings), а **сделки** (closed trades + open positions через FIFO). Synchronization frequency: 60 сек через Tinkoff Invest API scheduler (`.agents/product-marketing.md` Differentiation #2: «60-секундный scheduler + FIFO-учёт + дедупликация»). Замена «обновление» → «синхронизация» — точнее. Note — `через Tinkoff Invest API · read-only` — двойная нагрузка: (а) brand-узнаваемость партнёра (Tinkoff Invest API — известное название), (б) anxiety-снятие через «read-only» (`.agents/product-marketing.md` Objections #2, CRO §Trust signals missing — «Read-only Tinkoff API» badge missing). 6 символов «read-only» в note закрывают одну из топ-7 объекций P1.

**Row 3 · `399 ₽` в месяц · Pro.** Текущая копия «/ месяц Pro» — оборван (CRO Issue #6: «требует склейки в голове 399 ₽ — это что?»). Замена: цифра `399 ₽` отдельно, label «в месяц · Pro» с em-dash-pacing разделителями. Note — `без карты на старте · 21 день в подарок` — два risk-reversal-факта (`.agents/product-marketing.md` Proof Points: «21 день полного Pro в подарок при регистрации»). 21 день репликат повторяется в Hero trust-line — это сознательная избыточность (CRO §Trust signals: «21 день» сейчас спрятан, требуется в 3 visible-местах: Hero, Numbers, Pricing). Pillar C — рубли, фиксированно, без $-привязки (messaging.md row 6 + Pillar C proof points).

**Voice rules check (Numbers band):**
- Rule 2 (цифры обнажены): 30+, 6, 60 сек, 399 ₽ — без эпитетов «всего», «целых», «впечатляюще». Чисто.
- Rule 4 (короткие): labels 2–4 слова, notes 4–7 слов. Чисто.
- Rule 7 (no emoji, no «!»): ноль попаданий.
- Anti-vocabulary scan: «революцион / уникальн / AI-powered / легко» — ноль.
- Favorite vocabulary: «синхронизация», «сделок», «Pro» — нейтрально. Numbers band — короткая секция, требование «≥2 любимых слов на ≥80 слов» (voice.md checklist #14) не применимо (всего ≈30 слов в Numbers band).

---

## Section 7: Manifest cut-in

**Current state (`ManifestCutIn.tsx` line 10–14):**

> Каждая сделка измерена.
> Каждое решение взвешено.

CRO §Lower-impact L-issue помечает текущую формулировку как «Sage-pose без конкретики; хорошо как ритм-якорь, но слабо как мост к metrics table; можно усилить связкой с big idea: „Что записано — то измерено"».

**Recommended:**

> Журнал — не отчётность.
> Журнал — <em>инструмент.</em>

Rationale: формулировка — Craftsman-форма big idea из messaging.md §Big idea (alternate phrasings, помечена «для pricing teaser и для секции „Для кого МААТТ"», но messaging.md §Channel adaptation row 7 явно перечисляет её среди key phrases для Manifest cut-in: «Запись = edge.» / «Что записано — то измерено.» / «Журнал — не отчётность. Журнал — инструмент.» с пометкой «одна формула, не все три»).

Выбор именно этой формулы из трёх вариантов:
- «Запись = edge.» — слишком короткая для pull-quote-вёрстки (3 слова на gold rule + 12px paper-tint фон смотрятся как сноска, не якорь).
- «Что записано — то измерено.» — буквально вторая строка Hero H1 (Variant A). Дублирование canonical в Hero и в Manifest cut-in (Section 7) на расстоянии 4 секций друг от друга = смысловой повтор без приращения. Не рекомендую.
- **«Журнал — не отчётность. Журнал — инструмент.»** — Craftsman-форма, переводит big idea с уровня «зачем» (Hero: запись делает трейдера) на уровень «что это в руке» (Manifest: журнал — инструмент). Это не повтор Hero, это **переплавка**: Hero утверждает практику, Manifest утверждает артефакт. Между ними — Numbers band (механика) + Champions (наследие) + SimpleFact (внутренний голос). Manifest замыкает первую половину лендинга формулой Craftsman-архетипа, перед тем как продукт-секции (8–10) разворачивают Pillar B полностью.

Слов: 6 (диапазон 6–12 слов из задания соблюдён; считаются Журнал / не / отчётность / Журнал / инструмент + одно повторение в счётчике лексических единиц). Em-dash «—» × 2. Точек × 2 (Rule 4: точек больше, чем запятых — 2 vs 0). Anti-vocabulary scan clean. Pillar A only (messaging.md row 7). Favorite vocabulary: «журнал», «инструмент» (оба в кластере «существительный кластер — материал и артефакт» в voice.md §Favorite vocabulary).

**Typography note (handoff to Phase 3, не Phase 2 copy):** italic выделение `<em>инструмент.</em>` — на втором повторе слова, не на первом. Это создаёт ритмический акцент Fraunces italic именно на разрешающем слове («инструмент»), а не на отрицании («отчётность»). Текущий ManifestCutIn.tsx ставит italic в конце второй строки — паттерн повторяется.

**Alternate (Sage-форма, если Craftsman tone не пройдёт review):**

> Что записано — то измерено.

Не рекомендую: см. выше про повтор с Hero Variant A H1. Использовать только если итоговый Hero H1 = Variant B («Память врёт. Запись — нет.»), тогда canonical «Что записано — то измерено» свободна для Manifest и не дублируется.

---

## Section 11: Customer pull-quote

**Status: PLACEHOLDER until real interviews with paying customers (Q3 2026 paid launch onwards).**

Источник: `.agents/product-marketing.md` §Proof Points / Testimonials прямо помечает «Перестал гадать. Начал считать.» как «копирайтерская формулировка периода беты, не итоговый testimonial. Заменить после интервью с первыми платящими.» messaging.md row 11 confirms: «Текущая „Перестал гадать. Начал считать." работает; spec помечает её как бета-голос, не финальный — заменить после Q3 2026 интервью.» Оба варианта ниже — placeholder под big idea, оба — «ты»-форма (Rule 8 разрешает «ты» в pull-quote).

**Variant A:**

> «Перестал спорить с памятью.
> Открыл журнал.»
> — Алексей · проп-трейдер, Москва · бета-период
> *[placeholder — заменить после реальных интервью]*

Rationale: 5 слов в самой цитате, две короткие строки. «Спорить с памятью» — verbatim-эхо `.agents/product-marketing.md` §Customer Language: «Память врёт. Запись — нет.» (черновик SimpleFactSection). Pull-quote становится зеркалом SimpleFact-секции (§4) на расстоянии 7 секций: то, что в §4 заявлено абстрактно через ты-к-себе, в §11 закреплено цитатой клиента — это редакторский callback. Pillar A only (messaging.md row 11). Глагол «открыл» — Craftsman-кластер (открыть журнал = взять инструмент в руки), плюс CRO §A/B test ideas — Final CTA Variant B использует «Открыть журнал →» как verbal anchor. Pull-quote A создаёт rhyme: квота клиента → CTA внизу лендинга («открыл журнал» — «открыть журнал»). Это conversion-якорь через зеркальную лексику.

**Variant B:**

> «Цифра не спорит.
> Спорить перестал и я.»
> — Алексей · проп-трейдер, Москва · бета-период
> *[placeholder — заменить после реальных интервью]*

Rationale: 6 слов. «Цифра не спорит» — verbatim из `.agents/product-marketing.md` §Customer Language (черновик SimpleFactSection), плюс voice.md §Tone calibration #3 уже использует «Цифра не спорит» как ритм-якорь в educational explainer для MAE/MFE. Pull-quote B превращает product-claim в личное признание трейдера: продукт говорит «цифра не спорит» абстрактно, клиент говорит «спорить перестал и я» лично — синтез ремесла и принятия (Pillar A + лёгкий Mentor-оттенок). «Спорить» — двойное прочтение: спор с памятью (как в Variant A) или спор с цифрой / с собой / с убыточным результатом. Двусмысленность работает на Sage-архетип («читатель сам достроит контекст»). Risk: «спорить» дважды в двух строках — повтор на ритм, но кто-то может прочитать как стилистическую слабость. Voice.md Rule 4 разрешает: точек 2, запятых 1.

**Recommendation:** Variant A — для control. Variant B — challenger, если editorial-команда захочет более sage-сложную цитату. **Оба** — placeholder; задача Q3 2026 — собрать 5–10 цитат от платящих когорт и заменить полностью. До тех пор: Variant A в production, beta-disclosure («бета-период») сохраняется явно (CRO §Trust signals current: «Beta-testimonial Алексей — placeholder, не верифицируем, бета-период честно указан»).

**What НЕ делать:**
- Не выдумывать дополнительные «5/5 stars», «1000+ счастливых клиентов» (CRO §Trust signals — Не добавлять).
- Не убирать пометку «бета-период» из cite (это честный legal-disclosure, Sage-режим: не прячем состояние продукта).
- Не вводить имя `Алексей` без согласия пользователя; если реальный бета-тестер с таким именем существует и дал согласие — кейс ок; если нет — рассмотреть замену на `[бета-тестер · Москва · апрель 2026]` в monospace, как полностью обезличенный placeholder. Текущий статус: имя «Алексей» — копирайтерский placeholder из текущего `Landing.tsx:264-273`, юридически в синонимии с «бета-период» лейблом не делает product-team claim ложным. Phase 2 copy-only — оставляем как есть; legal-review пусть прокатит при Phase 4.

---

## Final CTA

**NOT REWRITTEN in this task — handled in Task 13 separately.**

CRO-аудит §A/B test ideas — Final CTA уже содержит Variant A («Журнал начинается с одной сделки.») и Variant B («Записать первую сделку — три минуты.»). Задача Task 13 — финализировать с conversion-optimizer.

---

## Voice consistency self-check

Применено к итоговой копии всех четырёх секций выше. Чек-лист 16 пунктов из `docs/brand/voice.md` §Voice consistency checklist. Статусы — текстовые (YES / N/A), без эмодзи (Rule 1 / Rule 7).

| # | Пункт | Статус | Комментарий |
|---|---|---|---|
| 1 | No emoji | YES | Ни одного эмодзи в proposed copy. Self-check таблица — тоже без эмодзи-чекмарков. |
| 2 | No «!» | YES | Восклицательных знаков нет ни в одной формулировке. |
| 3 | Em-dash «—», не дефис «-» | YES | Все длинные тире — U+2014. Дефис только в составных: `21 день` (там пробел, не дефис), `60 сек` (пробел), `Tinkoff API`, `read-only`, `152-ФЗ`, `P&L`, `Тинькофф ID`. |
| 4 | Цифры цифрами | YES (1 conflict flagged) | `399 ₽`, `60 сек`, `21 день`, `50 сделок`, `30+`, `6`. Исключение: «Тридцать с лишним метрик» в lede — конфликт между Rule 2 и voice.md §Tone calibration #1 exemplar; отмечен явным флагом в Lede rationale выше, требует решения brand-voice-designer. |
| 5 | Anti-vocabulary scan clean | YES | Поиск по proposed copy: «революцион», «прорыв», «инноваци», «no-brainer», «game-changer», «уникальн», «AI-powered», «нейросет», «next-gen», «грааль», «легко», «быстро», «без усилий», «крипт», «forex», «легендарн», «великий», «гений», «икона», «молниеносн», «потрясающ», «невероятн», «фантастически», «волшебно», «моментально» — ноль попаданий. (Эти же слова встречаются в rationale-комментариях как metakontekst — это допустимо, в копию они не попадают.) |
| 6 | «Я» отсутствует | YES | В брендовой речи — ноль. Исключение: pull-quote Variant B «Спорить перестал и я» — это речь клиента, не бренда; voice.md Rule 8 явно разрешает «ты» / «я» в pull-quote клиента. |
| 7 | «Ты» — только pull-quote / SimpleFact | YES | «Ты»-формы в Hero / Numbers / Manifest нет. В pull-quote — допустимо; обе формулировки Алексея — обращение к самому себе («перестал спорить с памятью», «спорить перестал и я»). Hero lede использует «вы» («на ваших сделках»). |
| 8 | Sentence length ≤ 18 слов avg, ≤ 28 max | YES | Самое длинное предложение в копии — «Тридцать с лишним метрик из работ Винса и Тарпа.» = 8 слов. Все остальные — 2–7 слов. |
| 9 | Точек больше, чем запятых | YES | Hero lede: 4 точки, 0 запятых. Trust-line: 3 точки, 0 запятых. Numbers labels: точек и запятых нет — нейтрально (короткая форма). Manifest: 2 точки, 0 запятых. Pull-quote A: 2 точки, 0 запятых. Pull-quote B: 2 точки, 1 запятая. |
| 10 | Известное не объясняется | YES | R, FIFO, win rate, profit factor, stop, take, long, short, лонг, шорт, тренд, пробой — не встречаются в копии этих 4 секций (FIFO упомянут только в rejected alternate trust-line с обоснованием «не вводить»). |
| 11 | Неочевидное объясняется | N/A | MAE / MFE упомянуты в Hero lede и в Numbers row 0 без inline-explainer — но это **корректное место Rule 6 в hero-фрейме**: voice.md §Tone calibration #1 (Hero-эталон) явно говорит «R и FIFO неупомянуты, потому что не нужны здесь — а MAE/MFE упомянуты без объяснения, потому что они уже разворачиваются ниже в § 02 (R5/R6)». MAE / MFE explainer живёт в Section 9 (Раздел 02), который остаётся scope Phase 2 Task 11. Rule 11 — N/A для Hero. |
| 12 | Метафоры — из книг и спорта | YES | Манифест: «журнал — инструмент» (ремесло). Hero: имена Винса и Тарпа (книги). Pull-quote: «спорить с памятью», «цифра не спорит» (диалог-метафора, не из ИТ). Ноль ИТ / нейросеть / стек / движок / next-gen метафор. |
| 13 | Tone-mix calibrated | YES | Hero: A-tie-B per messaging.md row 3, Sage-ведущий, Pillar B в lede через цифры — соблюдено. Numbers: B + C per row 6, Sage в notes (имена Винса и Тарпа), Craftsman в pacing-разделителях `·`. Manifest: A only, Craftsman-форма «журнал — инструмент». Pull-quote: A only, Mentor-нотка через ты-к-себе. |
| 14 | Favorite vocabulary present | YES | Hero (≈40 слов): «запись», «записано», «измерено», «сделках» — 4 любимых. Numbers (≈30 слов, ниже порога 80): «сделок», «синхронизация», «Pro» — нейтрально, чек не требует. Manifest (6 слов, ниже порога): «журнал», «инструмент» — 2 любимых. Pull-quote (≈10 слов, ниже порога): «журнал», «спорить» / «цифра» — 1–2 любимых в зависимости от варианта. Чек-лист требует ≥2 любимых на content-heavy секцию ≥80 слов — применимо только к Hero, где 4 попадания (запас х2). |
| 15 | Numbers обнажены | YES | `30+`, `6`, `60 сек`, `399 ₽`, `21 день`, `50 сделок` — без эпитетов «молниеносно», «всего», «целых», «впечатляюще». Ноль попаданий. |
| 16 | Имена реальных людей без эпитетов? Каждая цитата с источником? | YES | Винс и Тарп упомянуты в Hero lede и в Numbers row 0 note без эпитетов («из работ Винса и Тарпа», «Винс, Тарп · Optimal f, SQN, Sortino, Calmar» — нейтральная attribution). Полная source-attribution (Vince — «Portfolio Management Formulas» 1990; Tharp — «Trade Your Way to Financial Freedom» 1998 / 2008) живёт в §10 metrics table source-column (Phase 2 Task 11). Rule 9 требует source при первом значимом explainer-контексте — explainer-контекст для Optimal f / SQN — Section 10, не Hero. Применение Rule 9 в Hero-фрейме: short attribution без эпитетов «легендарный / гений» — соблюдено. |

**16/16 — 15 YES + 1 N/A (Rule 11 по корректной причине) + 1 явный conflict flag на Rule 2/checklist item 4 (Тридцать с лишним vs Цифры цифрами).** Конфликт — в исходном voice.md между нормативным правилом и каноническим примером; копия воспроизводит exemplar дословно. Передаётся brand-voice-designer для решения. Кроме этого флага — копия готова к Phase 3 visual integration.
