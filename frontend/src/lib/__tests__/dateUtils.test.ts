import { describe, it, expect } from 'vitest';
import { parseApiDate } from '../dateUtils';

describe('parseApiDate', () => {
  it('naive-строку трактует как UTC (добавляет Z)', () => {
    const d = parseApiDate('2026-07-02T12:30:00');
    expect(d.toISOString()).toBe('2026-07-02T12:30:00.000Z');
  });

  it('строку с Z не трогает', () => {
    const d = parseApiDate('2026-07-02T12:30:00Z');
    expect(d.toISOString()).toBe('2026-07-02T12:30:00.000Z');
  });

  it('строку с offset не трогает', () => {
    const d = parseApiDate('2026-07-02T15:30:00+03:00');
    expect(d.toISOString()).toBe('2026-07-02T12:30:00.000Z');
  });
});
