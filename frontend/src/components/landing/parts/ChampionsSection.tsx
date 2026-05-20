import { CHAMPIONS, CHAMPIONS_LEDE } from "../data/champions";
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
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 lg:gap-10">
          {CHAMPIONS.map((c, idx) => (
            <ChampionCard key={c.slug} champion={c} idx={idx} />
          ))}
        </div>
      </div>
    </section>
  );
}
