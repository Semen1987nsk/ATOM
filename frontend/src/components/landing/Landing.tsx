/**
 * Guest landing — МААТТ hand-crafted (Trader Desk + cream palette).
 *
 * См. spec docs/superpowers/specs/2026-05-18-landing-handcrafted-redesign-design.md
 *
 * Изоляция темы: data-theme="maatt-cream" — не течёт в auth-zone.
 */
import { Fragment } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { LiveTicker } from "./parts/LiveTicker";
import { HeroEquityCurve } from "./parts/HeroEquityCurve";
import { InteractiveCandleChart } from "./parts/InteractiveCandleChart";
import { TradeReplayWidget } from "./parts/TradeReplayWidget";
import { ManifestCutIn } from "./parts/ManifestCutIn";
import { MaattOrigin } from "./parts/MaattOrigin";

const NAV_LINKS = [
  { href: "/manual", label: "Возможности" },
  { href: "/pricing", label: "Тарифы" },
  { href: "/blog", label: "Блог" },
  { href: "/help", label: "Помощь" },
];

const NUMBERS_BAND = [
  { value: "30+", label: "метрик статистики", note: "Optimal f, SQN, Sortino, Calmar и др." },
  { value: "6", label: "MOEX-бордов", note: "акции, ОФЗ, корп. облигации, ETF, фьючерсы, валюты" },
  { value: "60 сек", label: "обновление портфеля", note: "через Tinkoff Invest API" },
  { value: "399 ₽", label: "/ месяц Pro", note: "без карты на старте, 21 день в подарок" },
];

const METRICS_TABLE: Array<{ metric: string; source: string; what: string; where: string; explainer?: string }> = [
  { metric: "Optimal f", source: "Винс", what: "Оптимальная доля капитала на сделку", where: "Риск",
    explainer: "Доля капитала на сделку, при которой геометрический рост портфеля максимален. Optimal f = 0.18 означает 18 % риска от равновесия на каждую сделку — больше дороже геометрически, меньше — упускаешь рост." },
  { metric: "SQN", source: "Тарп", what: "Качество торговой системы", where: "Риск",
    explainer: "System Quality Number = √N × (среднее R / σ R). SQN ниже 1.6 — система плохая, 2.0–2.5 — средняя, выше 3.0 — отличная. Считается на твоих закрытых сделках, не на бэктесте." },
  { metric: "R-Expectancy", source: "—", what: "Среднее R-multiple на сделку", where: "Базовая" },
  { metric: "Profit Factor", source: "—", what: "Сумма прибылей / сумма убытков", where: "Базовая" },
  { metric: "Z-Score", source: "—", what: "Значимость серий — есть ли паттерн", where: "Продвинутая" },
  { metric: "Sortino Ratio", source: "—", what: "Доходность с поправкой на downside", where: "Продвинутая" },
  { metric: "Calmar Ratio", source: "—", what: "CAGR / Max Drawdown", where: "Продвинутая" },
  { metric: "Recovery Factor", source: "—", what: "Чистая прибыль / Max Drawdown", where: "Продвинутая" },
  { metric: "Risk of Ruin", source: "—", what: "Вероятность потерять 20% / 50% депо", where: "Риск",
    explainer: "Вероятность потерять 20 % или 50 % депозита при твоей текущей win rate и среднем R. Считается аналитически по Ральфу Винсу и подтверждается 10 000 Monte Carlo-симуляций." },
  { metric: "Monte Carlo 10 000", source: "—", what: "Worst-case 5 % симуляции", where: "Риск" },
  { metric: "MAE / MFE", source: "MOEX", what: "Edge Ratio из реальных свечей", where: "Анализ",
    explainer: "Maximum Adverse Excursion — насколько глубоко цена уходила против тебя внутри сделки. Maximum Favorable Excursion — насколько далеко в твою сторону. Из минутных свечей биржи. Средний MAE убыточных сделок в 1.5 раза дальше стопа — стоп ставится слишком далеко." },
  { metric: "Post-Exit", source: "MOEX", what: "Что было с ценой после выхода", where: "Анализ" },
  { metric: "Tail Ratio", source: "—", what: "P95 win / |P05 loss|", where: "Эффективность" },
  { metric: "GHPR", source: "—", what: "Geometric Holding Period Return", where: "Эффективность" },
];

export function Landing() {
  return (
    <main data-theme="maatt-cream" className="min-h-screen">
      {/* 1. HEADER */}
      <header className="sticky top-0 z-30 bg-[var(--paper)] border-b border-[var(--rule)]">
        <div className="max-w-[1200px] mx-auto flex items-center justify-between px-6 lg:px-12 h-16">
          <Link
            href="/"
            className="text-[22px] italic no-underline text-[var(--ink)]"
            style={{ fontFamily: "var(--font-serif), Georgia, serif", fontWeight: 400, letterSpacing: "-0.015em" }}
          >
            МААТТ
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
              Тридцать с лишним метрик и MAE/MFE из биржевых свечей — на ваших
              сделках MOEX. Автосинхронизация с Тинькофф, никакого Excel.
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
            <p className="mt-6 text-[12px] text-[var(--ink-3)] num">
              Бесплатно до 50 сделок. Без карты. 21 день Pro в подарок.
            </p>
          </div>
          <div className="col-span-12 lg:col-span-5 lg:pl-6">
            <HeroEquityCurve />
          </div>
        </div>
      </section>

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

      {/* 6. NUMBERS BAND */}
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

      {/* 6. SECTION 01 · TRADE REPLAY */}
      <section className="px-6 lg:px-12 py-24 lg:py-32 border-t border-[var(--rule)]">
        <div className="max-w-[1200px] mx-auto grid grid-cols-12 gap-6 lg:gap-12">
          <div className="col-span-12 lg:col-span-5 flex flex-col justify-center">
            <p className="editorial-eyebrow mb-6">Раздел 01 — Trade Replay</p>
            <h2 className="editorial-h2 mb-6 text-[var(--ink)]">Что было до — и&nbsp;после.</h2>
            <p className="text-[16px] leading-[1.65] text-[var(--ink-2)] mb-5">
              Минутные свечи Мосбиржи вокруг входа и выхода — автоматически, без
              ручной разметки. Маркеры stop/take на той же шкале, точка реального
              выхода. Видно: вышли рано из страха или поздно по упрямству.
            </p>
            <p className="text-[16px] leading-[1.65] text-[var(--ink-2)] mb-8">
              В России такой автоматический замер не делает ни один журнал. У западных
              (TradeZella, Edgewonk) — другие биржи, российских свечей нет.
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

      {/* 7. SECTION 02 · MAE/MFE — mirrored */}
      <section className="px-6 lg:px-12 py-24 lg:py-32 border-t border-[var(--rule)]">
        <div className="max-w-[1200px] mx-auto grid grid-cols-12 gap-6 lg:gap-12">
          <div className="col-span-12 lg:col-span-7 lg:order-1 order-2">
            <div className="border border-[var(--rule-strong)] p-6 lg:p-8">
              <div className="editorial-eyebrow mb-5 text-[var(--ink-3)]">Свечи MOEX · SBER · 21 апреля</div>
              <InteractiveCandleChart />
            </div>
          </div>
          <div className="col-span-12 lg:col-span-5 lg:order-2 order-1 flex flex-col justify-center lg:pl-8">
            <p className="editorial-eyebrow mb-6">Раздел 02 — MAE / MFE</p>
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

      {/* 8. SECTION 03 · METRICS TABLE */}
      <section className="px-6 lg:px-12 py-24 lg:py-32 border-t border-[var(--rule)]">
        <div className="max-w-[1200px] mx-auto">
          <div className="grid grid-cols-12 gap-6 mb-12">
            <div className="col-span-12 lg:col-span-7">
              <p className="editorial-eyebrow mb-6">Раздел 03 — Аналитический центр</p>
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
                  <Fragment key={m.metric}>
                    <tr>
                      <td className="text-[var(--ink)] font-medium">{m.metric}</td>
                      <td className="text-[var(--ink-3)] text-[13px]">{m.source}</td>
                      <td className="text-[var(--ink-2)]">{m.what}</td>
                      <td className="text-[var(--ink-3)] text-[13px]">{m.where}</td>
                    </tr>
                    {m.explainer && (
                      <tr className="bg-[var(--accent-soft)]/40">
                        <td colSpan={4} className="text-[13px] leading-[1.55] text-[var(--ink-2)] italic px-3 py-3"
                            style={{ fontFamily: "var(--font-serif), var(--font-serif-cyr), Georgia, serif" }}>
                          {m.explainer}
                        </td>
                      </tr>
                    )}
                  </Fragment>
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

      {/* 10. SECTION 04 · HEURISTIC REVIEW */}
      <section className="px-6 lg:px-12 py-24 lg:py-32">
        <div className="max-w-[1200px] mx-auto grid grid-cols-12 gap-6 lg:gap-12">
          <div className="col-span-12 lg:col-span-5 flex flex-col justify-center">
            <p className="editorial-eyebrow mb-6">Раздел 04 — Эвристический разбор</p>
            <h2 className="editorial-h2 mb-6 text-[var(--ink)]">Второй взгляд на&nbsp;каждую сделку.</h2>
            <p className="text-[16px] leading-[1.65] text-[var(--ink-2)] mb-5">
              После каждого закрытия 12 правил проверяют сделку на типичные ошибки —
              FOMO-вход, ранний выход без достижения тейка, нарушение размера позиции,
              торговля против сетапа.
            </p>
            <p className="text-[16px] leading-[1.65] text-[var(--ink-2)] mb-8">
              Никакой магии глубокого обучения. Только описанные правила, которые ты
              можешь прочитать в документации и оспорить, если не согласен.
            </p>
            <Link
              href="/manual#heuristics"
              className="text-[13px] text-[var(--accent)] hover:text-[var(--accent-hover)] transition-colors no-underline inline-flex items-center gap-1.5"
            >
              Как устроен разбор <ArrowRight size={13} />
            </Link>
          </div>
          <div className="col-span-12 lg:col-span-7 lg:pl-8">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/landing/ai-card-sber-screenshot.png"
              alt="Эвристический разбор сделки SBER — пример вердикта"
              className="w-full h-auto border border-[var(--rule-strong)]"
              loading="lazy"
            />
          </div>
        </div>
      </section>

      {/* 11. МААТТ origin */}
      <MaattOrigin />

      {/* 12. PRICING TEASER */}
      <section className="px-6 lg:px-12 py-24 lg:py-32 border-t border-[var(--rule-strong)]">
        <div className="max-w-[1200px] mx-auto">
          <p className="editorial-eyebrow mb-6">Раздел 06 — Тарифы</p>
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
                МААТТ
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
                <a href="mailto:hello@maatt.ru" className="hover:text-[var(--ink)] transition-colors no-underline">hello@maatt.ru</a>
                <a href="mailto:support@maatt.ru" className="hover:text-[var(--ink)] transition-colors no-underline">support@maatt.ru</a>
                <Link href="/privacy" className="hover:text-[var(--ink)] transition-colors no-underline">Политика · 152-ФЗ</Link>
              </nav>
            </div>
          </div>
          <div className="pt-8 border-t border-[var(--rule)] flex flex-wrap items-center justify-between gap-4 text-[13px] text-[var(--ink-3)]">
            <div>© МААТТ · Точно. Чисто. Честно.</div>
            <div>Данные: MOEX ISS · Брокеры через API и CSV</div>
          </div>
        </div>
      </footer>
    </main>
  );
}
