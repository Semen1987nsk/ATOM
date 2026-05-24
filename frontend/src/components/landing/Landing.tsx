/**
 * Guest landing (Editorial Financial).
 *
 * Стиль зафиксирован в design-system.md v3 и ADR-0006:
 * — Fraunces serif для headlines/lede/pull-quote
 * — Geist Mono для всех чисел
 * — Hairline rules вместо боксов-карточек
 * — Single ochre acid accent
 * — Asymmetric editorial composition (5/7, 7/5)
 *
 * Tone-of-voice (messaging.md): спокойный профи. Триггерные слова:
 * MOEX, Тинькофф, Винс, Тарп, Optimal f, SQN, MAE/MFE, системный.
 * Слова-табу: лучший, грааль, революция, единственный — НЕ использовать.
 */

import Link from "next/link";
import { ArrowRight } from "lucide-react";

const NAV_LINKS = [
  { href: "/manual", label: "Возможности" },
  { href: "/pricing", label: "Тарифы" },
  { href: "/blog", label: "Блог" },
  { href: "/help", label: "Помощь" },
];

const NUMBERS_BAND = [
  { value: "30+", label: "метрик статистики" },
  { value: "10 000", label: "итераций Monte Carlo" },
  { value: "60 сек", label: "обновление портфеля по API" },
  { value: "399 ₽", label: "/ месяц Pro" },
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
    <main className="min-h-screen bg-[var(--paper-base)] text-[var(--ink)]">
      {/* ═════════ 1. HEADER ═════════ */}
      <header className="sticky top-0 z-30 bg-[var(--paper-base)] border-b border-[var(--rule)]">
        <div className="max-w-[1200px] mx-auto flex items-center justify-between px-6 lg:px-12 h-16">
          <Link
            href="/"
            className="font-serif italic text-[26px] font-normal tracking-tight no-underline text-[var(--ink)]"
            style={{ fontFamily: "var(--font-serif), Georgia, serif" }}
          >
            Eqio
          </Link>
          <nav className="hidden md:flex items-center gap-8 text-[13px] text-[var(--ink-2)]">
            {NAV_LINKS.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                className="hover:text-[var(--ink)] transition-colors no-underline"
              >
                {l.label}
              </Link>
            ))}
          </nav>
          <div className="flex items-center gap-3">
            <Link
              href="/login"
              className="text-[13px] text-[var(--ink-2)] hover:text-[var(--ink)] transition-colors no-underline px-3 py-2"
            >
              Войти
            </Link>
            <Link href="/register" className="btn-primary text-[13px]">
              Начать
            </Link>
          </div>
        </div>
      </header>

      {/* ═════════ 2. HERO ═════════ */}
      <section className="px-6 lg:px-12 pt-24 lg:pt-40 pb-24 lg:pb-32 border-b border-[var(--rule-strong)]">
        <div className="max-w-[1200px] mx-auto grid grid-cols-12 gap-6">
          <div className="col-span-12 lg:col-span-9">
            <p className="editorial-eyebrow mb-8">Торговый журнал · MOEX</p>
            <h1 className="editorial-display mb-10">
              Системная торговля
              <br />
              <em>начинается с&nbsp;дневника.</em>
            </h1>
            <p
              className="editorial-lede max-w-3xl mb-12"
              style={{ fontFamily: "var(--font-serif), Georgia, serif" }}
            >
              Тридцать с лишним метрик, MAE/MFE из биржевых свечей и AI-разбор каждого
              закрытия — на ваших сделках MOEX. Без переноса в Excel, без таблиц в Google,
              без подписки в долларах.
            </p>
            <div className="flex flex-col sm:flex-row items-start gap-4">
              <Link
                href="/register"
                className="btn-primary"
                style={{ padding: "14px 28px", fontSize: "15px" }}
              >
                Начать бесплатно <ArrowRight size={16} />
              </Link>
              <Link
                href="/manual"
                className="text-[14px] text-[var(--ink-2)] hover:text-[var(--ink)] transition-colors no-underline inline-flex items-center gap-1 py-[14px]"
              >
                Что внутри <ArrowRight size={13} />
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* ═════════ 3. NUMBERS BAND ═════════ */}
      <section className="px-6 lg:px-12 py-0">
        <div className="max-w-[1200px] mx-auto">
          <div className="editorial-numbers-band">
            {NUMBERS_BAND.map((n) => (
              <div key={n.label}>
                <div className="num text-[clamp(40px,5.5vw,72px)] font-medium leading-none mb-3 text-[var(--ink)]">
                  {n.value}
                </div>
                <div
                  className="text-[14px] italic leading-snug text-[var(--ink-2)]"
                  style={{ fontFamily: "var(--font-serif), Georgia, serif" }}
                >
                  {n.label}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ═════════ 4. FEATURE NARRATIVE #1 — AI-разбор ═════════ */}
      <section className="px-6 lg:px-12 py-24 lg:py-32">
        <div className="max-w-[1200px] mx-auto grid grid-cols-12 gap-6 lg:gap-12">
          <div className="col-span-12 lg:col-span-5 flex flex-col justify-center">
            <p className="editorial-eyebrow mb-6">Раздел 01 · AI-аналитика</p>
            <h2 className="editorial-h2 mb-6">
              AI разбирает каждое&nbsp;закрытие.
            </h2>
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
              style={{ letterSpacing: "0.02em" }}
            >
              Как устроен разбор <ArrowRight size={13} />
            </Link>
          </div>

          <div className="col-span-12 lg:col-span-7 lg:pl-8">
            {/* Editorial mockup AI-вердикта — hairline border, без gradient-обёрток */}
            <figure className="border border-[var(--rule-strong)] p-6 lg:p-8">
              <figcaption className="editorial-eyebrow mb-5 text-[var(--ink-3)]">
                Из журнала · SBER · Long · 14 мая
              </figcaption>
              <div className="rule-bottom pb-5 mb-5">
                <div className="text-[13px] text-[var(--ink-3)] mb-2">Вердикт</div>
                <div className="text-[20px] leading-tight" style={{ fontFamily: "var(--font-serif), Georgia, serif", fontStyle: "italic" }}>
                  «Преждевременный выход. Тейк-профит не достигнут, MFE +1.8R упущен.»
                </div>
              </div>
              <div className="rule-bottom pb-5 mb-5">
                <div className="text-[13px] text-[var(--ink-3)] mb-2">Что повторяется</div>
                <div className="text-[15px] leading-relaxed text-[var(--ink-2)]">
                  Третий выход в зоне 0.7–0.9R за неделю. Паттерн: на третий час удержания
                  закрываете «на всякий случай» — статистически невыгодно.
                </div>
              </div>
              <div className="grid grid-cols-3 gap-6 text-[13px]">
                <div>
                  <div className="text-[var(--ink-3)] mb-1">MAE</div>
                  <div className="num text-[18px]">−0.42 R</div>
                </div>
                <div>
                  <div className="text-[var(--ink-3)] mb-1">MFE</div>
                  <div className="num text-[18px] text-[var(--profit)]">+1.84 R</div>
                </div>
                <div>
                  <div className="text-[var(--ink-3)] mb-1">Реализовано</div>
                  <div className="num text-[18px]">+0.71 R</div>
                </div>
              </div>
            </figure>
          </div>
        </div>
      </section>

      {/* ═════════ 5. FEATURE NARRATIVE #2 — MAE/MFE, зеркальный ═════════ */}
      <section className="px-6 lg:px-12 py-24 lg:py-32 border-t border-[var(--rule)]">
        <div className="max-w-[1200px] mx-auto grid grid-cols-12 gap-6 lg:gap-12">
          <div className="col-span-12 lg:col-span-7 lg:order-1 order-2">
            <figure className="border border-[var(--rule-strong)] p-6 lg:p-8">
              <figcaption className="editorial-eyebrow mb-5 text-[var(--ink-3)]">
                Свечи MOEX · GAZP · 21 апреля
              </figcaption>
              {/* ASCII-визуализация свечей вместо stock-image. Стиль Bloomberg-terminal. */}
              <pre className="num text-[12px] leading-tight text-[var(--ink-2)] overflow-x-auto whitespace-pre">
{`         10:00   11:00   12:00   13:00   14:00   15:00   16:00
 168.40  ─┐
 168.20   │   ┌──┐
 168.00   │   │  │     ▼ MFE +1.82 R
 167.80   │   │  └─┐ ┌──┐
 167.60   │   │    └─┤  │
 167.40   ▲   │      │  └──┐
        вход │      │     └──┐
 167.20      │      │        │    ┌──┐
 167.00      │      │        └─┐ ┌┘  │
 166.80      │      │          └─┤   └──┐  ▲ выход
 166.60      │      │            │      │
 166.40      │      │            │      │
 166.20      └──────┘            └──────┘
                                       ▼ MAE −0.41 R
`}
              </pre>
              <div className="rule mt-5 pt-5 grid grid-cols-4 gap-6 text-[13px]">
                <div>
                  <div className="text-[var(--ink-3)] mb-1">Edge Ratio</div>
                  <div className="num text-[18px]">4.44</div>
                </div>
                <div>
                  <div className="text-[var(--ink-3)] mb-1">MAE p50</div>
                  <div className="num text-[18px]">−0.35 R</div>
                </div>
                <div>
                  <div className="text-[var(--ink-3)] mb-1">MFE p50</div>
                  <div className="num text-[18px] text-[var(--profit)]">+1.55 R</div>
                </div>
                <div>
                  <div className="text-[var(--ink-3)] mb-1">Quality</div>
                  <div className="num text-[18px]">0.78</div>
                </div>
              </div>
            </figure>
          </div>

          <div className="col-span-12 lg:col-span-5 lg:order-2 order-1 flex flex-col justify-center lg:pl-8">
            <p className="editorial-eyebrow mb-6">Раздел 02 · MAE / MFE</p>
            <h2 className="editorial-h2 mb-6">
              Edge ratio из реальных&nbsp;свечей.
            </h2>
            <p className="text-[16px] leading-[1.65] text-[var(--ink-2)] mb-5">
              MAE и MFE — главные количественные метрики для оптимизации стопов и
              тейков. Считаются автоматически по свечам MOEX ISS API, без вашей
              ручной разметки.
            </p>
            <p className="text-[16px] leading-[1.65] text-[var(--ink-2)] mb-8">
              В России такая автоматизация — только у нас. У западных конкурентов
              (TradeZella, Edgewonk) — другие биржи, российских свечей нет.
            </p>
            <Link
              href="/manual#mae-mfe"
              className="text-[13px] text-[var(--accent)] hover:text-[var(--accent-hover)] transition-colors no-underline inline-flex items-center gap-1.5"
              style={{ letterSpacing: "0.02em" }}
            >
              Подробнее о методе <ArrowRight size={13} />
            </Link>
          </div>
        </div>
      </section>

      {/* ═════════ 6. PULL-QUOTE ═════════ */}
      <section className="px-6 lg:px-12">
        <div className="max-w-[1200px] mx-auto">
          <blockquote className="editorial-pullquote">
            «Перестал гадать. Начал&nbsp;считать.»
            <cite>Алексей · проп-трейдер, Москва · бета-период</cite>
          </blockquote>
        </div>
      </section>

      {/* ═════════ 7. МЕТРИКИ ТАБЛИЦЕЙ (вместо bento) ═════════ */}
      <section className="px-6 lg:px-12 py-24 lg:py-32">
        <div className="max-w-[1200px] mx-auto">
          <div className="grid grid-cols-12 gap-6 mb-12">
            <div className="col-span-12 lg:col-span-7">
              <p className="editorial-eyebrow mb-6">Раздел 03 · Аналитический центр</p>
              <h2 className="editorial-h2 mb-6">Тридцать с лишним метрик. По-настоящему.</h2>
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

          <div className="mt-10 flex items-center justify-between gap-6 rule pt-6">
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

      {/* ═════════ 8. PRICING TEASER ═════════ */}
      <section className="px-6 lg:px-12 py-24 lg:py-32 border-t border-[var(--rule-strong)]">
        <div className="max-w-[1200px] mx-auto">
          <p className="editorial-eyebrow mb-6">Раздел 04 · Тарифы</p>
          <h2 className="editorial-h2 mb-16">
            Бесплатно до пятидесяти сделок в&nbsp;месяц.
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-12 md:gap-16">
            {/* Free */}
            <div className="border-t border-[var(--rule)] pt-8">
              <div className="flex items-baseline justify-between mb-6">
                <h3
                  className="text-[26px] font-medium"
                  style={{ fontFamily: "var(--font-serif), Georgia, serif" }}
                >
                  Free
                </h3>
                <div className="num text-[28px] text-[var(--ink-2)]">0 ₽</div>
              </div>
              <ul className="space-y-3 mb-8 list-none p-0 text-[15px] text-[var(--ink-2)] leading-relaxed">
                <li>До 50 сделок в месяц с FIFO-учётом</li>
                <li>Базовые метрики: P&amp;L, Win Rate, Profit Factor</li>
                <li>Импорт CSV / Excel из любого терминала MOEX</li>
                <li>Ручной ввод сделок</li>
              </ul>
              <Link
                href="/register"
                className="text-[14px] text-[var(--ink)] hover:text-[var(--accent)] transition-colors no-underline inline-flex items-center gap-1.5"
              >
                Открыть бесплатно <ArrowRight size={13} />
              </Link>
            </div>

            {/* Pro — featured by accent border-top */}
            <div className="border-t-2 border-[var(--accent)] pt-8">
              <div className="flex items-baseline justify-between mb-6">
                <h3
                  className="text-[26px] font-medium"
                  style={{ fontFamily: "var(--font-serif), Georgia, serif" }}
                >
                  Pro
                </h3>
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

      {/* ═════════ 9. FINAL CTA ═════════ */}
      <section className="px-6 lg:px-12 py-32 lg:py-40 border-t border-[var(--rule)] border-b border-[var(--rule)]">
        <div className="max-w-[860px] mx-auto text-center">
          <h2 className="editorial-h1 mb-10">
            Перестаньте гадать.
            <br />
            <em>Начните считать.</em>
          </h2>
          <p
            className="editorial-lede max-w-2xl mx-auto mb-12"
            style={{ fontFamily: "var(--font-serif), Georgia, serif" }}
          >
            Подключите Тинькофф через API или загрузите CSV. Первая статистика —
            через две минуты.
          </p>
          <Link
            href="/register"
            className="btn-primary inline-flex"
            style={{ padding: "14px 28px", fontSize: "15px" }}
          >
            Начать бесплатно <ArrowRight size={16} />
          </Link>
        </div>
      </section>

      {/* ═════════ 10. FOOTER ═════════ */}
      <footer className="px-6 lg:px-12 py-16 text-[14px]">
        <div className="max-w-[1200px] mx-auto">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-10 mb-12">
            <div>
              <Link
                href="/"
                className="text-[20px] font-normal italic tracking-tight no-underline text-[var(--ink)] mb-4 block"
                style={{ fontFamily: "var(--font-serif), Georgia, serif" }}
              >
                Eqio
              </Link>
              <p className="text-[var(--ink-3)] leading-relaxed text-[13px]">
                Торговый журнал для активных трейдеров MOEX.
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
              <div className="editorial-eyebrow mb-4 text-[var(--ink-2)]">Право</div>
              <nav className="flex flex-col gap-2.5">
                <Link href="/privacy" className="text-[var(--ink-3)] hover:text-[var(--ink)] transition-colors no-underline">Политика конфиденциальности</Link>
                <span className="text-[var(--ink-3)]">152-ФЗ</span>
              </nav>
            </div>
          </div>
          <div className="pt-8 border-t border-[var(--rule)] flex flex-wrap items-center justify-between gap-4 text-[13px] text-[var(--ink-3)]">
            <div>© Eqio · Торговая аналитика для российских трейдеров</div>
            <div>Данные: MOEX ISS · Брокеры через API и CSV</div>
          </div>
        </div>
      </footer>
    </main>
  );
}
