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
