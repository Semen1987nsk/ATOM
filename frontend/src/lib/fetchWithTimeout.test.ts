import { describe, it, expect } from 'vitest';

import { fetchWithTimeout, TimeoutError, DEFAULT_TIMEOUT_MS } from './fetchWithTimeout';

// A fake fetch that never resolves on its own, but rejects with the signal's
// reason when aborted — mirroring how the real fetch() reacts to AbortSignal.
const hangingFetch: typeof fetch = (_input, init) =>
  new Promise((_resolve, reject) => {
    const signal = init?.signal;
    if (signal) {
      signal.addEventListener('abort', () => reject(signal.reason), { once: true });
    }
  });

describe('fetchWithTimeout', () => {
  it('resolves with the response when fetch returns before the timeout', async () => {
    const fastFetch: typeof fetch = async () => new Response('ok', { status: 200 });
    const res = await fetchWithTimeout('http://x/', {}, 5000, fastFetch);
    expect(res.status).toBe(200);
    expect(await res.text()).toBe('ok');
  });

  it('throws TimeoutError when fetch hangs past the timeout', async () => {
    await expect(
      fetchWithTimeout('http://x/', {}, 50, hangingFetch),
    ).rejects.toBeInstanceOf(TimeoutError);
  });

  it('TimeoutError carries the timeout value', async () => {
    await expect(
      fetchWithTimeout('http://x/', {}, 50, hangingFetch),
    ).rejects.toMatchObject({ timeoutMs: 50 });
  });

  it('caller abort rejects with the caller reason, not a TimeoutError', async () => {
    const controller = new AbortController();
    const reason = new Error('user navigated away');
    const promise = fetchWithTimeout('http://x/', { signal: controller.signal }, 5000, hangingFetch);
    controller.abort(reason);
    await expect(promise).rejects.toBe(reason);
  });

  it('uses DEFAULT_TIMEOUT_MS when no timeout is given', () => {
    expect(typeof DEFAULT_TIMEOUT_MS).toBe('number');
    expect(DEFAULT_TIMEOUT_MS).toBeGreaterThan(0);
    expect(DEFAULT_TIMEOUT_MS).toBeLessThanOrEqual(60000);
  });
});
