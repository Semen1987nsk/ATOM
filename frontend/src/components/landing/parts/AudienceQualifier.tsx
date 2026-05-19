/**
 * Qualifying section — «Для серьёзного трейдера».
 * 5/7 editorial split: левый блок — title + lede; правый — 2 чек-листа (Для тебя ✓ / Не для тебя ×).
 * Closing line под двумя колонками — мостик к Pricing, ответ на объекцию «Тинькофф „Аналитика"» vs журнал.
 * SSR, без интерактивности.
 */
export function AudienceQualifier() {
  return (
    <section className="px-6 lg:px-12 py-28 lg:py-40 border-t border-[var(--rule)]">
      <div className="max-w-[1200px] mx-auto grid grid-cols-12 gap-6 lg:gap-12">
        <div className="col-span-12 lg:col-span-5">
          <p className="editorial-eyebrow mb-6">Раздел 05 — Для серьёзного трейдера</p>
          <h2 className="editorial-h2 mb-6 text-[var(--ink)]">
            Если торгуете MOEX — вам&nbsp;сюда.
          </h2>
          <p
            className="editorial-lede text-[var(--ink-2)]"
            style={{ fontFamily: "var(--font-serif), var(--font-serif-cyr), Georgia, serif" }}
          >
            Журнал — не отчётность. Журнал — инструмент. Если узнаёте себя в одной из строк справа — это вы.
          </p>
        </div>

        <div className="col-span-12 lg:col-span-7 lg:pl-8 grid grid-cols-1 md:grid-cols-2 gap-8 lg:gap-10">
          <div>
            <div className="editorial-eyebrow mb-5 text-[var(--ink-2)]">Для тебя</div>
            <ul className="space-y-4 list-none p-0 m-0">
              {[
                "Закрываешь 30–200 сделок в месяц на MOEX. Excel сорвался на третьем месяце.",
                "Хочешь увидеть, где стоп стоит слишком далеко, а тейк закрывается слишком рано. MAE и MFE — из биржевых свечей, не на глаз.",
                "Торгуешь через Тинькофф, БКС, Финам, Сбер, Альфу или ВТБ — нужен один журнал на все счета.",
                "Прочёл Винса и Тарпа. Хочешь видеть Optimal f и SQN на своих сделках, а не из бэктеста.",
                "Сравниваешь себя с собой квартал к кварталу, а не с рынком.",
                "Готов, чтобы сделки подтягивались сами через Тинькофф read-only — без передачи пароля и без торговых прав.",
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
                "Торгуете крипту или forex. Это TraderMake.Money и форекс-журналы.",
                "Торгуете NYSE, NASDAQ или LSE. Это TradeZella, Tradervue, Edgewonk.",
                "Торгуете опционы и нужны Greeks или IV-skew. У нас фондовый MOEX без опционной аналитики.",
                "Купили и держите — позиции живут годами. Журнал сделок вам не нужен.",
              ].map((item) => (
                <li key={item} className="flex items-start gap-3 text-[15px] leading-[1.55] text-[var(--ink-3)]">
                  <span className="mt-[2px] flex-shrink-0 num">×</span>
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="col-span-12 mt-12 lg:mt-16 pt-8 border-t border-[var(--rule)]">
          <p
            className="text-[15px] leading-[1.65] text-[var(--ink-2)] max-w-[68ch]"
            style={{ fontFamily: "var(--font-serif), var(--font-serif-cyr), Georgia, serif" }}
          >
            У Тинькофф «Аналитика портфеля» — агрегат: P&amp;L, доходность, состав. У нас — журнал сделок: MAE/MFE из свечей, Optimal f, SQN, Trade Replay, эвристический разбор. Это разный класс продукта.
          </p>
        </div>
      </div>
    </section>
  );
}
