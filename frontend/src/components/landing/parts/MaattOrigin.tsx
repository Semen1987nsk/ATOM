import { ManuscriptFeather } from "./ManuscriptFeather";

/**
 * Секция бренд-story. Перо + 3 короткие колонки + marginalia.
 * SSR, никакой интерактивности.
 */
export function MaattOrigin() {
  return (
    <section className="px-6 lg:px-12 py-28 lg:py-40 border-t border-[var(--rule)]">
      <div className="max-w-[1200px] mx-auto grid grid-cols-12 gap-6 lg:gap-12 items-start">
        <div className="col-span-12 lg:col-span-3 flex justify-start lg:justify-end">
          <ManuscriptFeather width={140} />
        </div>

        <div className="col-span-12 lg:col-span-9 grid grid-cols-12 gap-6 lg:gap-10">
          <div className="col-span-12 lg:col-span-8">
            <p className="editorial-eyebrow mb-6">Раздел 05 · Имя</p>
            <h2 className="editorial-h2 mb-8 text-[var(--ink)]">
              Маа́т — богиня меры.<br />
              <em>Перо против сердца на загробных весах.</em>
            </h2>
            <p className="editorial-lede mb-5 text-[var(--ink-2)]" style={{ fontStyle: "normal", fontSize: 16 }}>
              В древнеегипетской мифологии Маа́т держит перо страуса. В Дуате его кладут на чашу
              весов против сердца умершего. Сердце легче пера — душа проходит. Тяжелее — нет.
            </p>
            <p className="text-[16px] leading-[1.65] text-[var(--ink-2)]">
              Каждая ваша сделка ложится на ту же чашу — против пера дисциплины. МААТТ — журнал,
              в котором эти весы видны.
            </p>
          </div>

          <aside
            className="col-span-12 lg:col-span-4 border-l border-[var(--accent)] pl-4 text-[13px] leading-[1.5] text-[var(--ink-3)] italic"
            style={{ fontFamily: "var(--font-serif), Georgia, serif" }}
          >
            <div className="editorial-eyebrow mb-3 text-[var(--ink-3)]" style={{ fontStyle: "normal" }}>На полях</div>
            <p className="mb-3">
              Имя на латинице — <em>Maatt</em>, с двумя «t». Произносится так же. Двойная согласная
              — инженерное решение под занятые домены, не отсылка к чему-то.
            </p>
            <p>
              Tagline: <em>«Точно. Чисто. Честно.»</em> Триада задаёт три раздела продукта:
              математика — анти-шум — прозрачность.
            </p>
          </aside>
        </div>
      </div>
    </section>
  );
}
