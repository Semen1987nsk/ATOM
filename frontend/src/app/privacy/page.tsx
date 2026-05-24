import Link from 'next/link';

export const metadata = {
  title: 'Политика конфиденциальности | Эмпирик',
  description:
    'Политика обработки персональных данных в Эмпирик в соответствии с 152-ФЗ.',
};

const POLICY_VERSION = 'v1';
const EFFECTIVE_DATE = '07.05.2026';
const CONTACT_EMAIL = 'privacy@empirik.io';

export default function PrivacyPolicyPage() {
  return (
    <main className="min-h-screen bg-[var(--background)] text-[var(--foreground)]">
      <div className="max-w-3xl mx-auto px-6 py-16">
        <Link
          href="/"
          className="text-sm text-[var(--text-tertiary)] hover:text-[var(--foreground)] transition-colors"
        >
          ← На главную
        </Link>

        <h1 className="text-3xl md:text-4xl font-bold mt-6 mb-2">
          Политика конфиденциальности
        </h1>
        <p className="text-sm text-[var(--text-secondary)] mb-10">
          Версия {POLICY_VERSION} · действует с {EFFECTIVE_DATE}
        </p>

        <article className="prose-empirik space-y-8 text-[15px] leading-relaxed">
          <section>
            <h2 className="text-xl font-semibold mb-3">1. Кто оператор</h2>
            <p>
              Оператором персональных данных (ПД) является сервис Эмпирик
              (далее — «Оператор»). Контакт уполномоченного по защите ПД:{' '}
              <a
                href={`mailto:${CONTACT_EMAIL}`}
                className="text-[var(--accent)] underline"
              >
                {CONTACT_EMAIL}
              </a>
              .
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">2. Что мы собираем</h2>
            <ul className="list-disc list-inside space-y-1">
              <li>Email и (опционально) имя — для регистрации и связи.</li>
              <li>Хешированный пароль — для аутентификации.</li>
              <li>
                Данные торговых сделок (тикер, цена, объём, дата) — для расчёта
                аналитики, которую вы запрашиваете.
              </li>
              <li>
                IP-адрес и User-Agent в момент дачи согласия — как
                доказательная база (152-ФЗ ст. 9 ч. 4).
              </li>
              <li>
                UTM-метки и реферер — для понимания эффективности маркетинга;
                это обезличенная статистика.
              </li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">3. Цели обработки</h2>
            <ul className="list-disc list-inside space-y-1">
              <li>Регистрация и обеспечение доступа к сервису.</li>
              <li>
                Расчёт торговой аналитики (Optimal f, SQN, MAE/MFE, Monte Carlo).
              </li>
              <li>Биллинг (приём платежей через ЮKassa).</li>
              <li>Улучшение продукта и связь с пользователем.</li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">
              4. Передача третьим лицам
            </h2>
            <p>
              Мы не передаём ПД третьим лицам в маркетинговых целях. ПД
              передаются только:
            </p>
            <ul className="list-disc list-inside space-y-1 mt-2">
              <li>
                ЮKassa (ООО НКО «ЮMoney», РФ) — для проведения платежей.
              </li>
              <li>
                Хостинг-провайдер на территории РФ — для размещения серверов.
              </li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">
              5. Локализация и срок хранения
            </h2>
            <p>
              ПД граждан РФ хранятся на серверах в Российской Федерации
              (требование ст. 18 ч. 5 152-ФЗ). Срок хранения — до отзыва
              согласия. Платёжные документы хранятся 4 года в соответствии с
              402-ФЗ «О бухгалтерском учёте».
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">
              6. Ваши права (ст. 14 152-ФЗ)
            </h2>
            <ul className="list-disc list-inside space-y-1">
              <li>
                Получить копию ваших ПД — по запросу на{' '}
                <a
                  href={`mailto:${CONTACT_EMAIL}`}
                  className="text-[var(--accent)] underline"
                >
                  {CONTACT_EMAIL}
                </a>
                .
              </li>
              <li>Уточнить или исправить ПД — в личном кабинете.</li>
              <li>
                Отозвать согласие и удалить аккаунт — в настройках профиля.
                Удаление производится в течение 30 дней.
              </li>
              <li>
                Обжаловать действия Оператора в Роскомнадзоре —{' '}
                <a
                  href="https://rkn.gov.ru/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[var(--accent)] underline"
                >
                  rkn.gov.ru
                </a>
                .
              </li>
            </ul>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">7. Cookies</h2>
            <p>
              Мы используем строго необходимые cookies (сессия, CSRF-токен).
              Аналитические cookies (если будут добавлены) запрашивают
              отдельное согласие через баннер.
            </p>
          </section>

          <section>
            <h2 className="text-xl font-semibold mb-3">
              8. Изменения в политике
            </h2>
            <p>
              При существенных изменениях текста политики мы повышаем версию
              ({POLICY_VERSION} → v2 …) и просим пользователя подтвердить
              согласие при следующем входе.
            </p>
          </section>
        </article>
      </div>
    </main>
  );
}
