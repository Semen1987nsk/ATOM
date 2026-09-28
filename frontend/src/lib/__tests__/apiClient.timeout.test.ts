import { describe, it, expect, vi } from 'vitest';
import * as ftw from '../fetchWithTimeout';
import { api } from '../apiClient';

describe('apiClient timeoutMs override', () => {
  it('passes custom timeoutMs through to fetchWithTimeout', async () => {
    const spy = vi
      .spyOn(ftw, 'fetchWithTimeout')
      .mockResolvedValue(new Response('{}', { status: 200 }));
    await api.post('/broker/connections/1/sync', { timeoutMs: 120000 });
    // 3-й аргумент fetchWithTimeout — timeoutMs
    expect(spy).toHaveBeenCalled();
    expect(spy.mock.calls[0][2]).toBe(120000);
    spy.mockRestore();
  });
});
