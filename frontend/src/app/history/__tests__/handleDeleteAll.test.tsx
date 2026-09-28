import { describe, it, expect, vi } from 'vitest';

type Trade = { id: number; data_source?: string };

async function deleteAll(
  trades: Trade[],
  del: (id: number) => Promise<void>,
): Promise<{ deleted: number; skipped: number }> {
  const manual = trades.filter(t => t.data_source !== 'tinkoff_v2');
  const skipped = trades.length - manual.length;
  let deleted = 0;
  for (const t of manual) {
    try { await del(t.id); deleted += 1; } catch { /* собираем, не прерываем */ }
  }
  return { deleted, skipped };
}

describe('deleteAll', () => {
  it('пропускает sync-сделки, удаляет manual, не падает', async () => {
    const trades: Trade[] = [
      { id: 1, data_source: 'manual' },
      { id: 2, data_source: 'tinkoff_v2' },
      { id: 3, data_source: 'manual' },
    ];
    const del = vi.fn().mockResolvedValue(undefined);
    const res = await deleteAll(trades, del);
    expect(res).toEqual({ deleted: 2, skipped: 1 });
    expect(del).toHaveBeenCalledTimes(2);
    expect(del).not.toHaveBeenCalledWith(2);
  });
});
