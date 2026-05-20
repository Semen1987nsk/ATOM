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
      data-section="simple-fact"
      className="uplift-section-light px-6 lg:px-12 py-24 lg:py-32 border-y border-[var(--rule-strong)]"
    >
      <div className="max-w-[1200px] mx-auto">
        <p className="editorial-eyebrow mb-8">{SIMPLE_FACT_EYEBROW}</p>
        <h2 className="editorial-h2 mb-16 text-[var(--ink)] max-w-[24ch]">
          {SIMPLE_FACT_HEADING}
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-10 lg:gap-16 mb-16">
          {SIMPLE_FACT_ITEMS.map((item) => (
            <div key={item.caption} data-testid="simple-fact-column" className="flex flex-col">
              <div data-fact-numeral className="uplift-numbers mb-4">{item.caption}</div>
              <h3
                className="uplift-h2 text-[clamp(20px,2vw,28px)] mb-3"
                style={{ color: "var(--ink)", letterSpacing: "-0.015em" }}
              >
                {item.heading}
              </h3>
              <p className="text-[15px] lg:text-[16px] leading-[1.65]" style={{ color: "var(--ink-2)" }}>
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
