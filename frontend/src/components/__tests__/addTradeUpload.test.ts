import { describe, it, expect, vi } from 'vitest';

const toast = { success: vi.fn(), error: vi.fn() };

async function submit(
  createTrade: () => Promise<{ id: number }>,
  uploadScreenshot: ((id: number) => Promise<void>) | null,
  onSuccess: () => void,
  onClose: () => void,
) {
  let created: { id: number };
  try {
    created = await createTrade();
  } catch {
    toast.error('Не удалось сохранить сделку');
    return;
  }
  if (uploadScreenshot) {
    try {
      await uploadScreenshot(created.id);
      toast.success('Сделка добавлена');
    } catch {
      toast.error('Сделка сохранена, но скриншот не загрузился');
    }
  } else {
    toast.success('Сделка добавлена');
  }
  onSuccess();
  onClose();
}

describe('AddTrade submit', () => {
  it('при сбое upload всё равно onSuccess+onClose и warning-текст', async () => {
    toast.success.mockClear(); toast.error.mockClear();
    const onSuccess = vi.fn(); const onClose = vi.fn();
    await submit(
      () => Promise.resolve({ id: 7 }),
      () => Promise.reject(new Error('upload 500')),
      onSuccess, onClose,
    );
    expect(onSuccess).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith('Сделка сохранена, но скриншот не загрузился');
  });

  it('при сбое создания — не onSuccess', async () => {
    const onSuccess = vi.fn();
    await submit(() => Promise.reject(new Error('409')), null, onSuccess, vi.fn());
    expect(onSuccess).not.toHaveBeenCalled();
  });
});
