/**
 * Манифест-cut-in. Pull-quote на сливочном с одной золотой rule сверху.
 * SSR, никакого client JS.
 */
export function ManifestCutIn() {
  return (
    <section className="px-6 lg:px-12 py-20 lg:py-28 border-y border-[var(--rule)]">
      <div className="max-w-[920px] mx-auto">
        <div className="w-12 h-px bg-[var(--accent)] mb-10" aria-hidden />
        <blockquote className="editorial-pullquote text-[var(--ink)] m-0 p-0">
          Каждая сделка <em>измерена.</em>
          <br />
          Каждое решение <em>взвешено.</em>
        </blockquote>
      </div>
    </section>
  );
}
