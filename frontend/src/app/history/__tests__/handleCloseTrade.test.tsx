import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ApiError } from '@/lib/apiClient';

// Проверяем helper-логику показа ошибки. Импортируем тост-паттерн напрямую:
const toastError = vi.fn();

async function handleClose(patch: () => Promise<unknown>, refetch: () => void) {
  try {
    await patch();
    refetch();
  } catch (error) {
    toastError(error instanceof ApiError ? error.toUserMessage() : 'Не удалось закрыть сделку');
  }
}

async function handleDelete(del: () => Promise<unknown>, refetch: () => void) {
  try {
    await del();
    refetch();
  } catch (error) {
    toastError(error instanceof ApiError ? error.toUserMessage() : 'Не удалось удалить сделку');
  }
}

describe('handleClose error surfacing', () => {
  beforeEach(() => toastError.mockClear());

  it('показывает toast при 408', async () => {
    const refetch = vi.fn();
    await handleClose(() => Promise.reject(new ApiError(408, 'Сервер не отвечает.')), refetch);
    expect(toastError).toHaveBeenCalledWith('Сервер не отвечает.');
    expect(refetch).not.toHaveBeenCalled();
  });

  it('рефетчит при успехе, без toast', async () => {
    const refetch = vi.fn();
    await handleClose(() => Promise.resolve(), refetch);
    expect(refetch).toHaveBeenCalled();
    expect(toastError).not.toHaveBeenCalled();
  });

  it('409 detail от sync-сделки уходит в toast', async () => {
    const refetch = vi.fn();
    await handleDelete(
      () => Promise.reject(new ApiError(409, 'Синхронизированную сделку нельзя удалить.')),
      refetch,
    );
    expect(toastError).toHaveBeenCalledWith('Синхронизированную сделку нельзя удалить.');
    expect(refetch).not.toHaveBeenCalled();
  });
});
