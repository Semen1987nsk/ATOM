import { describe, it, expect, vi } from 'vitest';

vi.mock('@/lib/apiClient', () => ({
  getApiUrl: (p: string) => `http://api${p}`,
}));

import { screenshotSrc } from './page';

describe('screenshotSrc', () => {
  it('строит URL через authenticated эндпоинт, не через /uploads', () => {
    const src = screenshotSrc(42);
    expect(src).toBe('http://api/trades/42/screenshot');
    expect(src).not.toContain('/uploads/');
  });
});
