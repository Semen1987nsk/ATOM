/**
 * Очистка user-scoped client-состояния при смене пользователя / logout.
 *
 * Корень бага «новый юзер видит данные прошлого» (бейдж «С GLDRUBF» на дашборде):
 * всё client-состояние было привязано к устройству (localStorage), а не к user.id,
 * и не чистилось ни при logout, ни при тихой смене аккаунта. Здесь — единый список
 * ключей, принадлежащих КОНКРЕТНОМУ пользователю; их надо удалять при смене личности.
 *
 * НЕ включаем device-преференсы (язык, cookie-consent, ширина сайдбара, раскладка
 * таблиц/колонок истории и журнала) — они корректно переживают смену юзера на одном
 * устройстве. НЕ добавлять сюда auth-токены: для них есть clearAuthTokens() в
 * apiClient.ts, намеренно ограниченный legacy-ключами (см. XSS-комментарий там).
 *
 * При добавлении нового user-scoped ключа в приложении — допиши его сюда (для
 * React Query та же задача решена через queryClient.clear() в AuthProvider).
 */
export const USER_SCOPED_STORAGE_KEYS = [
  'tradingSettings', // SettingsContext: tradesStartDate/Symbol → бейдж, + currency/pnl/mae
  'empirik_journal_filters_v1', // фильтры журнала: search/setupId/dateRange
  'empirik_reconciliation_banner_dismissed_until', // snooze баннера реконсиляции (per-account)
] as const;

export function clearUserScopedState(): void {
  if (typeof window === 'undefined') return;
  for (const key of USER_SCOPED_STORAGE_KEYS) {
    try {
      localStorage.removeItem(key);
    } catch {
      // private mode / quota — молча игнорируем
    }
  }
}
