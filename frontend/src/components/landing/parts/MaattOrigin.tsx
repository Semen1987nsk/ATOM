/**
 * Qualifying section — «Для серьёзного трейдера».
 * 5/7 editorial split: левый блок — title + lede; правый — 2 чек-листа (Для тебя ✓ / Не для тебя ×).
 * SSR, без интерактивности.
 */
export function MaattOrigin() {
  return (
    <section className="px-6 lg:px-12 py-28 lg:py-40 border-t border-[var(--rule)]">
      <div className="max-w-[1200px] mx-auto grid grid-cols-12 gap-6 lg:gap-12">
        <div className="col-span-12 lg:col-span-5">
          <p className="editorial-eyebrow mb-6">Раздел 05 — Для серьёзного трейдера</p>
          <h2 className="editorial-h2 mb-6 text-[var(--ink)]">
            Для серьёзного <em>трейдера.</em>
          </h2>
          <p
            className="editorial-lede text-[var(--ink-2)]"
            style={{ fontFamily: "var(--font-serif), var(--font-serif-cyr), Georgia, serif" }}
          >
            Если узнаёшь себя — это тебе.
          </p>
        </div>

        <div className="col-span-12 lg:col-span-7 lg:pl-8 grid grid-cols-1 md:grid-cols-2 gap-8 lg:gap-10">
          <div>
            <div className="editorial-eyebrow mb-5 text-[var(--ink-2)]">Для тебя</div>
            <ul className="space-y-4 list-none p-0 m-0">
              {[
                "Делаешь от 30 сделок в месяц на MOEX",
                "Хочешь видеть свою альфу в числах, а не «вроде в плюсе»",
                "Устал от Excel и ручного ввода",
                "Понимаешь, что 70 % результата — это дисциплина, а не сигналы",
                "Доверяешь Винсу и Тарпу больше, чем «трейдер-блогерам»",
              ].map((item) => (
                <li key={item} className="flex items-start gap-3 text-[15px] leading-[1.55] text-[var(--ink)]">
                  <span className="text-[var(--accent)] mt-[2px] flex-shrink-0 num">✓</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <div className="editorial-eyebrow mb-5 text-[var(--ink-3)]">Не для тебя</div>
            <ul className="space-y-4 list-none p-0 m-0">
              {[
                "Ищешь сигналы «куда покупать»",
                "Торгуешь вне MOEX — крипта, forex, западные биржи",
                "Хочешь быстро разбогатеть",
              ].map((item) => (
                <li key={item} className="flex items-start gap-3 text-[15px] leading-[1.55] text-[var(--ink-3)]">
                  <span className="mt-[2px] flex-shrink-0 num">×</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}
