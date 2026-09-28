import { describe, it, expect } from 'vitest';

// Извлекаем нормализующую логику ровно как в apiClient.request.
function normalizeDetail(errorData: { detail?: unknown }, status: number): string {
  const raw = errorData.detail;
  if (Array.isArray(raw)) {
    return raw.map((d: { msg?: string }) => d?.msg ?? String(d)).join('; ');
  }
  return (raw as string) || `HTTP ${status}`;
}

describe('normalizeDetail (422)', () => {
  it('массив pydantic-ошибок → человекочитаемая строка', () => {
    const detail = [
      { loc: ['body', 'entry_price'], msg: 'Input should be greater than 0', type: 'greater_than' },
      { loc: ['body', 'quantity'], msg: 'Field required', type: 'missing' },
    ];
    expect(normalizeDetail({ detail }, 422)).toBe('Input should be greater than 0; Field required');
  });

  it('строковый detail не трогает', () => {
    expect(normalizeDetail({ detail: 'Уже существует' }, 409)).toBe('Уже существует');
  });
});
