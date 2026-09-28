import { CHAMPIONS, CHAMPIONS_LEDE, CHAMPIONS_OUTRO } from "../data/champions";
import { ChampionCard } from "./ChampionCard";

export function ChampionsSection() {
  return (
    <section
      id="champions"
      data-section="champions"
      className="uplift-section-light px-6 lg:px-12 py-24 lg:py-32 border-b border-(--rule-strong)"
    >
      <div className="max-w-[1200px] mx-auto">
        <p className="editorial-eyebrow mb-8">── Дисциплина чемпионов</p>
        <h2 className="uplift-h2 mb-6" style={{ color: "var(--ink)", letterSpacing: "-0.025em" }}>
          Дисциплина чемпионов
        </h2>
        {CHAMPIONS_LEDE && (
          <p className="text-[16px] leading-[1.65] text-[var(--ink-2)] max-w-[60ch] mb-16">
            {CHAMPIONS_LEDE}
          </p>
        )}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 lg:gap-10 lg:[&>*:last-child]:col-start-2">
          {CHAMPIONS.map((c, idx) => (
            <ChampionCard key={c.slug} champion={c} idx={idx} />
          ))}
        </div>
        <div className="mt-16 lg:mt-24 pt-10 lg:pt-12 border-t border-[var(--rule-strong)] grid gap-6 lg:grid-cols-[180px_1fr] lg:gap-16">
          <p className="editorial-eyebrow lg:pt-2">── Итог</p>
          <div className="max-w-[60ch]">
            <p
              className="text-[15px] lg:text-[16px] italic leading-[1.5] text-[var(--ink-3)] mb-4"
              style={{ fontFamily: "var(--font-serif), var(--font-serif-cyr), Georgia, serif" }}
            >
              {CHAMPIONS_OUTRO.lead}
            </p>
            <p className="text-[16px] lg:text-[17px] leading-[1.6] text-[var(--ink-2)] mb-7">
              {CHAMPIONS_OUTRO.body}
            </p>
            <p
              className="text-[clamp(22px,2.8vw,34px)] leading-[1.15]"
              style={{
                fontFamily: "var(--font-serif), var(--font-serif-cyr), Georgia, serif",
                color: "var(--ink)",
                letterSpacing: "-0.01em",
              }}
            >
              {CHAMPIONS_OUTRO.punchLead}{" "}
              <span style={{ color: "var(--orange)", fontStyle: "italic" }}>
                {CHAMPIONS_OUTRO.punchAccent}
              </span>
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
