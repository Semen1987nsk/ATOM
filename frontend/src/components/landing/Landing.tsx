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
import { AudienceQualifier } from "./parts/AudienceQualifier";
import { SimpleFactSection } from "./parts/SimpleFactSection";
import { ChampionsSection } from "./parts/ChampionsSection";

const NAV_LINKS = [
  { href: "/manual", label: "Возможности" },
  { href: "/pricing", label: "Тарифы" },
  { href: "/blog", label: "Блог" },
  { href: "/help", label: "Помощь" },
];

const NUMBERS_BAND = [
  { value: "30+", label: "метрик из книг", note: "Винс, Тарп · Optimal f, SQN, Sortino, Calmar" },
  { value: "6", label: "торговых режимов MOEX", note: "акции, ОФЗ, корп. облигации, ETF, фьючерсы, валюты" },
  { value: "60 сек", label: "синхронизация сделок", note: "через Tinkoff Invest API · read-only" },
  { value: "399 ₽", label: "в месяц · Pro", note: "без карты на старте · 21 день в подарок" },
];

const METRICS_TABLE: Array<{ metric: string; source: string; what: string; where: string; explainer?: string }> = [
  { metric: "Optimal f", source: "Винс", what: "Оптимальная доля капитала на сделку", where: "Риск",
    explainer: "Доля капитала на сделку, при которой геометрический рост портфеля максимален. Optimal f = 0.18 означает 18 % риска от равновесия на каждую сделку — больше дороже геометрически, меньше — упускаешь рост." },
  { metric: "SQN", source: "Тарп", what: "Качество торговой системы", where: "Риск",
    explainer: "System Quality Number = √N × (среднее R / σ R). SQN ниже 1.6 — система плохая, 2.0–2.5 — средняя, выше 3.0 — отличная. Считается на твоих закрытых сделках, не на бэктесте." },
  { metric: "R-Expectancy", source: "—", what: "Среднее R-multiple на сделку", where: "Базовая",
    explainer: "Среднее R-multiple по всем закрытым сделкам: суммируешь R каждой сделки и делишь на их число. R-Expectancy = 0,35 означает, что в среднем сделка приносит 0,35 от размера риска. Положительная — стратегия в плюсе на длинной дистанции. Отрицательная — стратегия теряет систематически, не «не повезло». Минимум 50 закрытых сделок для надёжной оценки." },
  { metric: "Profit Factor", source: "—", what: "Сумма прибылей / сумма убытков", where: "Базовая",
    explainer: "Сумма прибылей делённая на сумму убытков. Profit Factor = 1,8 означает, что на каждый рубль убытка приходится 1,8 рубля прибыли. Ниже 1,0 — стратегия теряет. 1,3–1,6 — рабочая. Выше 2,0 — редкая для розничной торговли, проверяй сделки на ошибки разметки. На малой выборке завышается одной крупной сделкой — смотри вместе с R-Expectancy." },
  { metric: "Z-Score", source: "—", what: "Значимость серий — есть ли паттерн", where: "Продвинутая",
    explainer: "Статистическая значимость серий выигрышей и проигрышей в твоей истории сделок. |Z| ниже 1,96 — серии случайны, паттерна нет. |Z| выше 1,96 — серии не случайны. Положительный Z — выигрыши и проигрыши группируются (полосы дольше ожидаемых). Отрицательный — чередуются чаще ожидаемого. Подсказывает, стоит ли менять размер позиции после серии или это шум." },
  { metric: "Sortino Ratio", source: "—", what: "Доходность с поправкой на downside", where: "Продвинутая",
    explainer: "Доходность сверх безрисковой ставки, делённая только на downside-волатильность — стандартное отклонение убыточных периодов. Sortino выше 1,0 — приемлемо, выше 2,0 — хорошо. Отличается от Sharpe тем, что не штрафует за «волатильность вверх»: всплеск прибыли — это не риск. Метрика Фрэнка Сортино; считается на месячной или дневной серии P&L." },
  { metric: "Calmar Ratio", source: "—", what: "CAGR / Max Drawdown", where: "Продвинутая",
    explainer: "Годовая доходность (CAGR) делённая на максимальную просадку за период. Calmar = 2,0 означает: годовая доходность в два раза перекрывает худшую просадку. Ниже 0,5 — слабо: одна плохая полоса съедает год роста. Выше 3,0 — отлично, но проверь длину истории. Метрика Терри Янга, применяется на минимум трёхлетней истории." },
  { metric: "Recovery Factor", source: "—", what: "Чистая прибыль / Max Drawdown", where: "Продвинутая",
    explainer: "Чистая прибыль за период делённая на максимальную просадку. Recovery Factor = 5 означает, что общая прибыль в пять раз перекрывает худшую просадку счёта. Ниже 1,0 — система не отбила свой худший момент. 2,0–3,0 — норма. Выше 5,0 — стратегия с высокой скоростью восстановления. Считается на закрытой equity-кривой, не на open-trade P&L." },
  { metric: "Risk of Ruin", source: "—", what: "Вероятность потерять 20% / 50% депо", where: "Риск",
    explainer: "Вероятность потерять 20 % или 50 % депозита при твоей текущей win rate и среднем R. Считается аналитически по Ральфу Винсу и подтверждается 10 000 Monte Carlo-симуляций." },
  { metric: "Monte Carlo 10 000", source: "—", what: "Worst-case 5 % симуляции", where: "Риск",
    explainer: "10 000 случайных перестановок твоих сделок: тот же набор R, но в другом порядке. Из распределения берётся worst-case 5 % сценариев — пятый процентиль по максимальной просадке и итоговой equity. Подсказывает, какую просадку реально получить при той же стратегии, если бы убыточные сделки сгруппировались иначе. Сравнивай с фактической просадкой: ниже worst-case 5 % — везение пока на твоей стороне." },
  { metric: "MAE / MFE", source: "MOEX", what: "Edge Ratio из реальных свечей", where: "Анализ",
    explainer: "Maximum Adverse Excursion — насколько глубоко цена уходила против тебя внутри сделки. Maximum Favorable Excursion — насколько далеко в твою сторону. Из минутных свечей биржи. Средний MAE убыточных сделок в 1.5 раза дальше стопа — стоп ставится слишком далеко." },
  { metric: "Post-Exit", source: "MOEX", what: "Что было с ценой после выхода", where: "Анализ",
    explainer: "Что было с ценой после твоего выхода: насколько она ушла в твою сторону или против неё на 5, 15, 60 минутах после exit. Считается из тех же минутных свечей MOEX, что и MAE/MFE. Систематически положительный Post-Exit на прибыльных сделках — выходишь рано, тейк закрывается из страха. Систематически отрицательный на убыточных — наоборот, выход вовремя." },
  { metric: "Tail Ratio", source: "—", what: "P95 win / |P05 loss|", where: "Эффективность",
    explainer: "P95 win делённый на модуль P05 loss: размер 95-го перцентиля прибыли по сравнению с 5-м перцентилем убытка. Tail Ratio выше 1,0 — правый хвост толще левого, крупные выигрыши перебивают крупные проигрыши. Ниже 1,0 — система отдаёт на хвостах. Совпадает с философией «срезай убытки, давай прибыли расти» Ливермора, посчитанной на твоих сделках." },
  { metric: "GHPR", source: "—", what: "Geometric Holding Period Return", where: "Эффективность",
    explainer: "Geometric Holding Period Return — геометрическая средняя доходность за один период удержания позиции. Корень N-степени из произведения (1 + R каждой сделки), минус единица. Отличается от арифметической средней тем, что учитывает компаундинг: цепочка +20 % и −20 % даёт −4 %, а не ноль. Если GHPR положителен, депозит растёт геометрически; если отрицателен — разрушается, даже когда арифметическая средняя в плюсе." },
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
      <section
        data-section="hero"
        className="uplift-section-dark px-6 lg:px-12 pt-16 lg:pt-24 pb-20 lg:pb-28"
      >
        <div className="max-w-[1200px] mx-auto grid grid-cols-12 gap-6 lg:gap-10 items-center">
          <div className="col-span-12 lg:col-span-7">
            <p className="editorial-eyebrow mb-7" style={{ color: "var(--paper-on-dark-3)" }}>
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

      {/* 4. SIMPLE FACT */}
      <SimpleFactSection />

      {/* 5. CHAMPIONS */}
      <ChampionsSection />

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

      {/* 7. MANIFEST CUT-IN */}
      <ManifestCutIn />

      {/* 8. SECTION 01 · TRADE REPLAY */}
      <section className="px-6 lg:px-12 py-24 lg:py-32 border-t border-[var(--rule)]">
        <div className="max-w-[1200px] mx-auto grid grid-cols-12 gap-6 lg:gap-12">
          <div className="col-span-12 lg:col-span-5 flex flex-col justify-center">
            <p className="editorial-eyebrow mb-6">Раздел 01 — Trade Replay</p>
            <h2 className="editorial-h2 mb-6 text-[var(--ink)]">Свечи MOEX вокруг каждой&nbsp;сделки.</h2>
            <p className="text-[16px] leading-[1.65] text-[var(--ink-2)] mb-5">
              Минутные свечи MOEX ISS вокруг входа и выхода. На одной шкале —
              маркеры stop и take, точка реального выхода. Видно, где сделка
              пошла против вас и как далеко зашла в вашу сторону. Без ручной
              разметки. Без скриншотов из терминала.
            </p>
            <p className="text-[16px] leading-[1.65] text-[var(--ink-2)] mb-8">
              Trade Replay со свечами MOEX в РФ — только у нас; у TradeZella
              и Edgewonk биржи другие, российских свечей нет.
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

      {/* 9. SECTION 02 · MAE/MFE — mirrored */}
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
            <h2 className="editorial-h2 mb-6 text-[var(--ink)]">MAE и MFE — из минутных свечей&nbsp;биржи.</h2>
            <dl className="border border-[var(--rule)] p-4 mb-6 bg-[var(--paper-tint)]/40">
              <div className="flex gap-3 mb-2 last:mb-0">
                <dt className="num text-[12px] font-medium text-[var(--ink)] uppercase tracking-[0.06em] w-[80px] shrink-0">
                  MAE
                </dt>
                <dd
                  className="text-[14px] leading-[1.55] text-[var(--ink-2)] m-0"
                  style={{ fontFamily: "var(--font-serif), var(--font-serif-cyr), Georgia, serif" }}
                >
                  Maximum Adverse Excursion: насколько глубоко цена уходила
                  против сделки внутри её жизни.
                </dd>
              </div>
              <div className="flex gap-3 mb-2 last:mb-0">
                <dt className="num text-[12px] font-medium text-[var(--ink)] uppercase tracking-[0.06em] w-[80px] shrink-0">
                  MFE
                </dt>
                <dd
                  className="text-[14px] leading-[1.55] text-[var(--ink-2)] m-0"
                  style={{ fontFamily: "var(--font-serif), var(--font-serif-cyr), Georgia, serif" }}
                >
                  Maximum Favorable Excursion: насколько далеко цена уходила
                  в вашу сторону.
                </dd>
              </div>
              <div className="flex gap-3 mb-2 last:mb-0">
                <dt className="num text-[12px] font-medium text-[var(--ink)] uppercase tracking-[0.06em] w-[80px] shrink-0">
                  Edge Ratio
                </dt>
                <dd
                  className="text-[14px] leading-[1.55] text-[var(--ink-2)] m-0"
                  style={{ fontFamily: "var(--font-serif), var(--font-serif-cyr), Georgia, serif" }}
                >
                  средний MFE / средний MAE. {">"} 1 — у системы есть edge;
                  {" "}{"<"} 1 — система берёт убыток на хвостах.
                </dd>
              </div>
            </dl>
            <p className="text-[16px] leading-[1.65] text-[var(--ink-2)] mb-5">
              Считаются по минутным свечам MOEX ISS — биржевым, не из реквоутов
              брокера. Брокерские реквоуты сглаживают экстремумы, биржевые
              свечи — нет. Средний MAE убыточных в 1,5× дальше стопа — стоп
              ставится слишком далеко. Средний MFE прибыльных в 2× дальше
              тейка — тейк закрывается рано. Цифра не спорит.
            </p>
            <p className="text-[16px] leading-[1.65] text-[var(--ink-2)] mb-8">
              В России такой автомат — только у нас; у TradeZella и Edgewonk
              биржи другие, российских свечей нет.
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

      {/* 10. SECTION 03 · METRICS TABLE */}
      <section className="px-6 lg:px-12 py-24 lg:py-32 border-t border-[var(--rule)]">
        <div className="max-w-[1200px] mx-auto">
          <div className="grid grid-cols-12 gap-6 mb-12">
            <div className="col-span-12 lg:col-span-7">
              <p className="editorial-eyebrow mb-6">Раздел 03 — Аналитический центр</p>
              <h2 className="editorial-h2 mb-6 text-[var(--ink)]">Тридцать с лишним метрик. Каждая — из своего&nbsp;источника.</h2>
              <p className="text-[16px] leading-[1.65] text-[var(--ink-2)]">
                Формулы из работ Винса, Тарпа, Сортино, Калмар — посчитанные
                на ваших сделках, не в Excel-шаблоне. Каждая со своим
                назначением, ограничением и интерпретацией. Не «P&L и Win Rate
                с пометкой 30+».
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

      {/* 11. PULL-QUOTE */}
      {/* placeholder — заменить после реальных интервью (Q3 2026 paid launch onwards) */}
      <section className="px-6 lg:px-12 py-20 border-y border-[var(--rule)]">
        <div className="max-w-[920px] mx-auto">
          <div className="w-12 h-px bg-[var(--accent)] mb-10" aria-hidden />
          <blockquote className="editorial-pullquote text-[var(--ink)] m-0 p-0">
            «Перестал спорить с памятью.
            <br />
            <em>Открыл журнал.»</em>
          </blockquote>
          <cite
            className="block mt-6 text-[13px] not-italic text-[var(--ink-3)]"
            style={{ fontFamily: "var(--font-mono), monospace", letterSpacing: "0.08em", textTransform: "uppercase" }}
          >
            Алексей · проп-трейдер, Москва · бета-период
          </cite>
        </div>
      </section>

      {/* 12. SECTION 04 · HEURISTIC REVIEW */}
      <section className="px-6 lg:px-12 py-24 lg:py-32">
        <div className="max-w-[1200px] mx-auto grid grid-cols-12 gap-6 lg:gap-12">
          <div className="col-span-12 lg:col-span-5 flex flex-col justify-center">
            <p className="editorial-eyebrow mb-6">Раздел 04 — Эвристический разбор</p>
            <h2 className="editorial-h2 mb-6 text-[var(--ink)]">Двенадцать правил против типовых&nbsp;ошибок.</h2>
            <p className="text-[16px] leading-[1.65] text-[var(--ink-2)] mb-5">
              После каждого закрытия 12 правил проверяют сделку: FOMO-вход,
              ранний выход без достижения тейка, нарушение размера позиции,
              торговля против сетапа. Правила детерминированные — описаны
              в документации, можно прочитать и оспорить. Без чёрного ящика.
              Без обучения на ваших сделках.
            </p>
            <div
              className="inline-flex items-center mt-6 mb-6 px-2.5 py-1 border border-[var(--rule)] text-[11px] text-[var(--ink-3)] uppercase tracking-[0.08em]"
              style={{ fontFamily: "var(--font-mono), monospace" }}
            >
              AI-разбор · скоро
            </div>
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

      {/* 13. AUDIENCE QUALIFIER */}
      <AudienceQualifier />

      {/* 14. PRICING TEASER */}
      <section className="px-6 lg:px-12 py-24 lg:py-32 border-t border-[var(--rule-strong)]">
        <div className="max-w-[1200px] mx-auto">
          <p className="editorial-eyebrow mb-6">Раздел 06 — Тарифы</p>
          <h2 className="editorial-h2 mb-16 text-[var(--ink)]">Free — чтобы понять. Pro — чтобы&nbsp;изменить.</h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-12 md:gap-16">
            <div className="border-t border-[var(--rule)] pt-8">
              <div className="flex items-baseline justify-between mb-4">
                <h3 className="text-[26px] font-medium" style={{ fontFamily: "var(--font-serif), Georgia, serif" }}>Free</h3>
                <div className="num text-[28px] text-[var(--ink-2)]">0 ₽</div>
              </div>
              <p
                className="text-[14px] italic text-[var(--ink-3)] mb-6 leading-snug"
                style={{ fontFamily: "var(--font-serif), var(--font-serif-cyr), Georgia, serif" }}
              >
                Чтобы понять, что происходит на счёте.
              </p>
              <ul className="space-y-3 mb-8 list-none p-0 text-[15px] text-[var(--ink-2)] leading-relaxed">
                <li>До 50 сделок в месяц с FIFO-учётом. Выше — старые вытесняются.</li>
                <li>P&amp;L, Win Rate, Profit Factor — базовые метрики на закрытых сделках.</li>
                <li>Импорт CSV / Excel из любого терминала MOEX. Ручной ввод сделок.</li>
                <li>Календарный P&amp;L по дням недели — какие дни в плюсе, какие в минусе.</li>
                <li>Журнал на одном счёте. MAE/MFE из свечей — в Pro.</li>
              </ul>
              <Link href="/register" className="text-[14px] text-[var(--ink)] hover:text-[var(--accent)] transition-colors no-underline inline-flex items-center gap-1.5">
                Открыть бесплатно <ArrowRight size={13} />
              </Link>
            </div>

            <div className="border-t-2 border-[var(--accent)] pt-8">
              <div className="flex items-baseline justify-between mb-4">
                <h3 className="text-[26px] font-medium" style={{ fontFamily: "var(--font-serif), Georgia, serif" }}>Pro</h3>
                <div className="num text-[28px] text-[var(--ink)]">
                  399 ₽<span className="text-[14px] text-[var(--ink-3)] font-normal"> / мес</span>
                </div>
              </div>
              <div
                className="inline-flex items-center mb-4 px-2.5 py-1 border border-[var(--accent)] text-[11px] text-[var(--accent)] uppercase tracking-[0.08em]"
                style={{ fontFamily: "var(--font-mono), monospace" }}
              >
                21 день в подарок · без карты
              </div>
              <p
                className="text-[14px] italic text-[var(--ink-3)] mb-6 leading-snug"
                style={{ fontFamily: "var(--font-serif), var(--font-serif-cyr), Georgia, serif" }}
              >
                Чтобы изменить то, что вы там увидели.
              </p>
              <ul className="space-y-3 mb-8 list-none p-0 text-[15px] text-[var(--ink-2)] leading-relaxed">
                <li>MAE и MFE автоматически из минутных свечей MOEX ISS. Видно, где стоп стоит слишком далеко.</li>
                <li>Optimal f (Винс) и SQN (Тарп) на ваших закрытых сделках — не из бэктеста, не из Excel.</li>
                <li>Trade Replay со свечами биржи вокруг входа и выхода. Маркеры stop / take / entry / exit.</li>
                <li>Эвристический разбор по 12 детерминированным правилам. AI-разбор — в roadmap.</li>
                <li>Тинькофф Invest API read-only, обновление 60 сек. CSV / Excel из БКС, Финама, Сбера, Альфы, ВТБ.</li>
                <li>До 5 счетов. Безлимит сделок. Экспорт CSV / PDF.</li>
              </ul>
              <Link href="/register" className="btn-primary">
                Открыть Pro <ArrowRight size={14} />
              </Link>
            </div>
          </div>

          <p className="mt-12 text-center text-[13px] text-[var(--ink-3)]">
            Без карты на старте. 21 день полного Pro в подарок при регистрации. Отмена в один клик. Все данные экспортируются в CSV.
          </p>
        </div>
      </section>

      {/* 15. FINAL CTA */}
      <section className="px-6 lg:px-12 py-32 lg:py-40 border-t border-[var(--rule)] border-b border-[var(--rule)]">
        <div className="max-w-[860px] mx-auto text-center">
          <h2 className="editorial-display mb-10 text-[var(--ink)]">
            Запись делает трейдера.
            <br />
            <em>Начните вести.</em>
          </h2>
          <p className="editorial-lede max-w-2xl mx-auto mb-12">
            Тинькофф через API. CSV из БКС, Финама, Сбера, Альфы, ВТБ. Ручной ввод. Первая статистика — через две минуты.
          </p>
          <Link href="/register" className="btn-primary inline-flex">
            Начать бесплатно <ArrowRight size={16} />
          </Link>
          <p className="mt-6 text-[13px] text-[var(--ink-3)]">
            Без карты. 21 день Pro в подарок. До 50 сделок в месяц — бесплатно бесконечно.
          </p>
        </div>
      </section>

      {/* 16. FOOTER */}
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
                Журнал сделок для активных трейдеров MOEX. На минутных свечах биржи. На вашем брокере через API или CSV.
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
          <div
            className="pt-8 border-t border-[var(--rule)] mb-6 text-[11px] text-[var(--ink-3)] uppercase tracking-[0.08em]"
            style={{ fontFamily: "var(--font-mono), monospace" }}
          >
            152-ФЗ · Хостинг Yandex Cloud · Тинькофф Invest API read-only · 30 дней передумать
          </div>
          <div className="flex flex-wrap items-center justify-between gap-4 text-[13px] text-[var(--ink-3)]">
            <div>© МААТТ · Запись. Учёт. Свидетельство.</div>
            <div>Данные: MOEX ISS · Брокеры через API и CSV · Бета-период · Платный запуск Q3 2026</div>
          </div>
        </div>
      </footer>
    </main>
  );
}
