"use client";

/**
 * DataError — единый inline-блок для ошибок загрузки данных.
 *
 * FE-01 / FE-02. Раньше каждый `useEffect`-fetch в analysis-страницах глушил
 * исключение `.catch(() => setData(null))`, и юзер видел пустой EmptyState
 * без объяснения «нет данных vs сервер упал». Теперь:
 *   - если error → DataError с user-readable текстом + кнопкой retry
 *   - если data=null без error → обычный EmptyState
 *
 * Использует `ApiError.toUserMessage()` (см. `src/lib/apiClient.ts`) — она
 * добавляет суффикс `(id: <8-симв request_id>)`, по которому в support-чате
 * мы найдём строку в логах бэка.
 */
import type { ApiError } from "@/lib/apiClient";

interface DataErrorProps {
  error: ApiError | Error | null;
  onRetry: () => void;
}

export function DataError({ error, onRetry }: DataErrorProps) {
  if (!error) return null;

  const message =
    "toUserMessage" in error &&
    typeof (error as ApiError).toUserMessage === "function"
      ? (error as ApiError).toUserMessage()
      : error.message || "Ошибка загрузки данных";

  return (
    <div className="rounded-lg border border-danger/50 bg-danger/5 p-6 text-center my-4">
      <p className="text-danger font-semibold mb-2">Ошибка загрузки</p>
      <p className="text-sm text-muted mb-4">{message}</p>
      <button onClick={onRetry} className="btn-secondary">
        Повторить
      </button>
    </div>
  );
}

export default DataError;
