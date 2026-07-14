"use client";

import { useInView } from "@/hooks/useInView";
import {
  SIMPLE_FACT_EYEBROW,
  SIMPLE_FACT_HEADING,
  SIMPLE_FACT_ITEMS,
  SIMPLE_FACT_BRIDGE,
  type SimpleFactItem,
} from "../data/simple-fact";

function FactRow({ item, idx }: { item: SimpleFactItem; idx: number }) {
  const { ref, inView } = useInView<HTMLDivElement>({ rootMargin: "0px 0px -60px 0px", once: true });
  return (
    <div
      ref={ref}
      data-testid="simple-fact-column"
      data-inview={inView ? "true" : "false"}
      className="uplift-raise grid grid-cols-[56px_1fr] md:grid-cols-[92px_1fr_auto] items-baseline md:items-center gap-x-5 md:gap-x-10 gap-y-2 py-8 md:py-9 border-t border-[var(--rule-strong)]"
      style={{ transitionDelay: `${idx * 100}ms` }}
    >
      {/* Порядковый номер — оранжевая Manrope-цифра.
          Размер форсим inline: тема (.uplift-numbers) задаёт display-кегль 56–96px
          и перебивает Tailwind-классы по специфичности → цифра наезжала на текст. */}
      <div
        data-fact-numeral
        className="uplift-numbers"
        style={{ fontSize: "clamp(30px, 3.8vw, 40px)", lineHeight: 1 }}
      >
        {item.caption}
      </div>

      {/* Заголовок-утверждение + поддержка */}
      <div className="min-w-0">
        <h3
          style={{
            fontFamily: "var(--font-display), 'Helvetica Neue', Arial, sans-serif",
            fontWeight: 800,
            textTransform: "uppercase",
            fontSize: "clamp(17px, 1.7vw, 21px)",
            lineHeight: 1.12,
            letterSpacing: "-0.02em",
            color: "var(--ink)",
          }}
        >
          {item.heading}
        </h3>
        <p className="mt-2 text-[14.5px] lg:text-[15px] leading-[1.55]" style={{ color: "var(--ink-2)" }}>
          {item.body}
        </p>
      </div>

      {/* Иллюстративная строка журнала (демо-образец) */}
      <div
        aria-hidden="true"
        className="col-start-2 md:col-start-3 mt-1 md:mt-0 text-[12px] md:text-[12.5px] md:text-right whitespace-nowrap"
        style={{ fontFamily: "var(--font-mono), monospace", color: "var(--ink-3, #8a8474)" }}
      >
        {item.ledger.pre}
        <span style={{ color: "var(--orange)", fontWeight: 600 }}>{item.ledger.mark}</span>
        {item.ledger.post}
      </div>
    </div>
  );
}

export function SimpleFactSection() {
  return (
    <section
      id="simple-fact"
      data-section="simple-fact"
      className="uplift-section-light px-6 lg:px-12 py-24 lg:py-32 border-y border-[var(--rule-strong)]"
    >
      <div className="max-w-[1100px] mx-auto">
        <p className="editorial-eyebrow mb-8">{SIMPLE_FACT_EYEBROW}</p>
        <h2 className="editorial-h2 mb-12 lg:mb-16 text-[var(--ink)] max-w-[22ch]">
          {SIMPLE_FACT_HEADING}
        </h2>

        {/* Журнал-ledger: записи в столбик с тонкими линейками */}
        <div className="border-b border-[var(--rule-strong)] mb-12">
          {SIMPLE_FACT_ITEMS.map((item, idx) => (
            <FactRow key={item.caption} item={item} idx={idx} />
          ))}
        </div>

        <div className="flex items-start gap-4 max-w-[62ch]">
          <span
            aria-hidden="true"
            className="h-px w-9 shrink-0"
            style={{ marginTop: "0.7em", backgroundColor: "var(--orange)" }}
          />
          <p
            className="italic leading-[1.5]"
            style={{
              fontFamily: "var(--font-serif), var(--font-serif-cyr), Georgia, serif",
              fontSize: "clamp(18px, 1.6vw, 21px)",
              color: "var(--ink)",
            }}
          >
            {SIMPLE_FACT_BRIDGE}
          </p>
        </div>
      </div>
    </section>
  );
}
