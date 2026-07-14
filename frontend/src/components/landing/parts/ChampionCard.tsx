"use client";

import Image from "next/image";
import { useInView } from "@/hooks/useInView";
import type { Champion } from "../data/champions";

export function ChampionCard({ champion, idx = 0 }: { champion: Champion; idx?: number }) {
  const { ref, inView } = useInView<HTMLElement>({ rootMargin: "0px 0px -50px 0px", once: true });

  const yearsLabel = champion.deathYear
    ? `${champion.birthYear} — ${champion.deathYear}`
    : `р. ${champion.birthYear}`;

  return (
    <article
      ref={ref as React.RefObject<HTMLElement>}
      data-testid="champion-card"
      data-inview={inView ? "true" : "false"}
      className="uplift-raise border border-[var(--rule)] p-8 bg-[var(--paper)] flex flex-col"
      style={{ transitionDelay: `${idx * 80}ms` }}
    >
      <div className="mb-6 mx-auto" style={{ width: 220, height: 220 }}>
        <Image
          src={champion.portraitSrc}
          alt={`Монограмма — ${champion.firstName} ${champion.lastName}`}
          width={220}
          height={220}
          loading="lazy"
          unoptimized
        />
      </div>
      <h3
        data-champion-name
        className="text-[18px] font-extrabold uppercase tracking-[-0.015em] mb-1 leading-tight"
        style={{ fontFamily: "var(--font-display), sans-serif", color: "var(--ink)" }}
      >
        {champion.firstName} {champion.lastName}
      </h3>
      <div className="num text-[11px] text-[var(--ink-3)] uppercase tracking-[0.06em] mb-6">
        {yearsLabel}
      </div>
      {champion.bio && (
        <p className="text-[14px] leading-[1.55] text-[var(--ink-2)] mb-6">
          {champion.bio}
        </p>
      )}
      {champion.quote && (
        <blockquote
          data-champion-quote
          className="text-[17px] lg:text-[18px] italic text-[var(--ink)] leading-[1.6] pl-5 mb-4 flex-grow m-0"
          style={{
            borderLeft: "3px solid var(--orange)",
            fontFamily: "var(--font-serif), var(--font-serif-cyr), Georgia, serif",
          }}
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
