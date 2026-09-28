export function ManifestCutIn() {
  return (
    <section
      data-section="manifest"
      className="uplift-section-tint relative overflow-hidden px-6 lg:px-12 py-28 lg:py-36 border-y border-[var(--rule-strong)]"
    >
      <span
        aria-hidden="true"
        className="absolute -top-12 -left-4 lg:-left-10 select-none pointer-events-none"
        style={{
          fontFamily: "var(--font-serif), Georgia, serif",
          fontStyle: "italic",
          fontSize: "clamp(240px, 28vw, 380px)",
          lineHeight: 0.85,
          color: "var(--orange-soft)",
          fontWeight: 300,
        }}
      >
        «
      </span>
      <div className="relative max-w-[920px] mx-auto">
        <blockquote className="editorial-pullquote text-[var(--ink)] m-0 p-0">
          Журнал — не отчётность.
          <br />
          Журнал — <em>инструмент.</em>
        </blockquote>
      </div>
    </section>
  );
}
