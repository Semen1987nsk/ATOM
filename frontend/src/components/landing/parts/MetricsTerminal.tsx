"use client";

import { useMemo, useState } from "react";
import { ChevronRight } from "lucide-react";
import { CountUp } from "@/components/common/CountUp";
import {
  METRICS,
  METRIC_CATEGORIES,
  CATEGORY_COLOR,
  type Metric,
  type MetricCategory,
} from "../data/metrics";

type Filter = MetricCategory | "all";

function CategoryPill({ category }: { category: MetricCategory }) {
  const color = CATEGORY_COLOR[category];
  return (
    <span
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] uppercase tracking-[0.08em] border"
      style={{ color, borderColor: color, backgroundColor: `${color}14` }}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }} />
      {category}
    </span>
  );
}

function MetricDetail({ m }: { m: Metric }) {
  return (
    <div key={m.slug} className="metric-detail-anim">
      <div className="flex items-center justify-between gap-4 mb-5">
        <CategoryPill category={m.category} />
        {m.source !== "—" && (
          <span
            className="text-[11px] uppercase tracking-[0.1em] text-[var(--ink-3)]"
            style={{ fontFamily: "var(--font-mono), monospace" }}
          >
            источник · {m.source}
          </span>
        )}
      </div>

      <h3
        className="text-[clamp(30px,3.4vw,42px)] leading-[1.02] mb-3"
        style={{
          fontFamily: "var(--font-display), 'Helvetica Neue', Arial, sans-serif",
          fontWeight: 800,
          letterSpacing: "-0.025em",
          color: "var(--ink)",
        }}
      >
        {m.metric}
      </h3>
      <p className="text-[15px] text-[var(--ink-3)] mb-7">{m.what}</p>

      <div className="flex flex-wrap items-center gap-4 mb-7">
        <code
          className="inline-block text-[14px] px-3.5 py-2.5 rounded-md border border-[var(--rule-strong)]"
          style={{
            fontFamily: "var(--font-mono), monospace",
            backgroundColor: "var(--paper-2, #eee6d5)",
            color: "var(--ink)",
          }}
        >
          {m.formula}
        </code>
        <span
          className="text-[clamp(22px,2.4vw,30px)] leading-none"
          style={{ fontFamily: "var(--font-mono), monospace", color: "var(--orange)", fontWeight: 600 }}
        >
          {m.sample}
        </span>
      </div>

      <p className="text-[16px] lg:text-[17px] leading-[1.7] text-[var(--ink-2)] max-w-[60ch]">
        {m.explainer}
      </p>
    </div>
  );
}

export function MetricsTerminal() {
  const [filter, setFilter] = useState<Filter>("all");
  const [activeSlug, setActiveSlug] = useState<string>(METRICS[0].slug);

  const filtered = useMemo(
    () => (filter === "all" ? METRICS : METRICS.filter((m) => m.category === filter)),
    [filter],
  );

  const active = filtered.find((m) => m.slug === activeSlug) ?? filtered[0];

  function selectFilter(f: Filter) {
    setFilter(f);
    const next = f === "all" ? METRICS : METRICS.filter((m) => m.category === f);
    if (!next.some((m) => m.slug === activeSlug)) {
      setActiveSlug(next[0]?.slug ?? "");
    }
  }

  const countByCategory = (c: MetricCategory) => METRICS.filter((m) => m.category === c).length;

  return (
    <div>
      {/* caption + animated total */}
      <div className="flex items-end justify-between gap-6 mb-6">
        <p className="editorial-eyebrow">
          Аналитический центр · показано {filtered.length} из {METRICS.length}
        </p>
        <p className="text-[13px] text-[var(--ink-3)] whitespace-nowrap">
          <CountUp
            to={30}
            suffix="+"
            className="text-[var(--orange)] font-semibold"
          />{" "}
          метрик в продукте
        </p>
      </div>

      {/* filter chips */}
      <div className="flex flex-wrap gap-2 mb-8" role="tablist" aria-label="Фильтр метрик по категории">
        <button
          role="tab"
          aria-selected={filter === "all"}
          onClick={() => selectFilter("all")}
          className="px-3.5 py-1.5 rounded-full text-[13px] border transition-colors"
          style={
            filter === "all"
              ? { backgroundColor: "var(--ink)", color: "var(--paper)", borderColor: "var(--ink)" }
              : { color: "var(--ink-2)", borderColor: "var(--rule-strong)" }
          }
        >
          Все <span className="opacity-60">· {METRICS.length}</span>
        </button>
        {METRIC_CATEGORIES.map((c) => {
          const isOn = filter === c;
          const color = CATEGORY_COLOR[c];
          return (
            <button
              key={c}
              role="tab"
              aria-selected={isOn}
              onClick={() => selectFilter(c)}
              className="px-3.5 py-1.5 rounded-full text-[13px] border transition-colors inline-flex items-center gap-1.5"
              style={
                isOn
                  ? { backgroundColor: color, color: "#fff", borderColor: color }
                  : { color: "var(--ink-2)", borderColor: "var(--rule-strong)" }
              }
            >
              <span
                className="w-1.5 h-1.5 rounded-full"
                style={{ backgroundColor: isOn ? "#fff" : color }}
              />
              {c} <span className="opacity-60">· {countByCategory(c)}</span>
            </button>
          );
        })}
      </div>

      {/* terminal split */}
      <div className="grid lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)] border border-[var(--rule-strong)] bg-[var(--paper)]">
        {/* LEFT — metric list */}
        <ul className="m-0 p-0 list-none lg:border-r border-[var(--rule-strong)] lg:max-h-[620px] lg:overflow-y-auto">
          {filtered.map((m) => {
            const isActive = active?.slug === m.slug;
            const color = CATEGORY_COLOR[m.category];
            return (
              <li key={m.slug} className="border-b border-[var(--rule)] last:border-b-0">
                <button
                  type="button"
                  onClick={() => setActiveSlug(m.slug)}
                  aria-current={isActive ? "true" : undefined}
                  className="group w-full text-left flex items-center gap-3 pl-4 pr-3 lg:pl-5 py-3.5 border-l-[3px] transition-colors"
                  style={{
                    borderLeftColor: isActive ? "var(--orange)" : "transparent",
                    backgroundColor: isActive ? "var(--accent-soft, rgba(226,82,28,0.07))" : "transparent",
                  }}
                >
                  <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: color }} />
                  <span
                    className="flex-1 text-[15px] truncate"
                    style={{ color: "var(--ink)", fontWeight: isActive ? 700 : 500 }}
                  >
                    {m.metric}
                  </span>
                  {m.source !== "—" && (
                    <span
                      className="text-[12px] text-[var(--ink-3)] hidden sm:inline"
                      style={{ fontFamily: "var(--font-mono), monospace" }}
                    >
                      {m.source}
                    </span>
                  )}
                  <ChevronRight
                    size={15}
                    className="shrink-0 transition-transform"
                    style={{
                      color: isActive ? "var(--orange)" : "var(--ink-3)",
                      transform: isActive ? "translateX(2px)" : "none",
                    }}
                  />
                </button>

                {/* mobile inline detail (accordion) */}
                {isActive && (
                  <div className="lg:hidden px-4 pt-2 pb-6 border-t border-[var(--rule)] bg-[var(--paper)]">
                    <MetricDetail m={m} />
                  </div>
                )}
              </li>
            );
          })}
        </ul>

        {/* RIGHT — detail panel (desktop) */}
        <div className="hidden lg:block">
          <div className="p-9 lg:p-10">{active && <MetricDetail m={active} />}</div>
        </div>
      </div>
    </div>
  );
}
