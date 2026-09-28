import { describe, it, expect, vi } from 'vitest';
import { ApiError } from '@/lib/apiClient';

const toastError = vi.fn();

async function triggerSync(
  post: () => Promise<void>,
  refetch: () => void,
  setSyncing: (v: number | null) => void,
  id: number,
) {
  setSyncing(id);
  try {
    await post();
    refetch();
  } catch (e) {
    toastError(e instanceof ApiError ? e.toUserMessage() : 'Не удалось запустить синхронизацию');
  } finally {
    setSyncing(null);
  }
}

describe('triggerSync', () => {
  it('держит syncing до завершения await и рефетчит после успеха', async () => {
    const setSyncing = vi.fn();
    const refetch = vi.fn();
    await triggerSync(() => Promise.resolve(), refetch, setSyncing, 5);
    expect(setSyncing).toHaveBeenNthCalledWith(1, 5);
    expect(refetch).toHaveBeenCalled();
    expect(setSyncing).toHaveBeenLastCalledWith(null);
  });

  it('показывает toast при ошибке', async () => {
    toastError.mockClear();
    await triggerSync(() => Promise.reject(new ApiError(429, 'Слишком часто.')),
      vi.fn(), vi.fn(), 5);
    expect(toastError).toHaveBeenCalledWith('Слишком часто.');
  });
});
