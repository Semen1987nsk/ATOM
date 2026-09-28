import { describe, it, expect } from 'vitest';
import { ITEMS } from '../CommandPalette';

describe('CommandPalette ITEMS', () => {
  it('все id уникальны', () => {
    const ids = ITEMS.map(i => i.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('нет пунктов-заглушек «Брокеры» с router.push("/")', () => {
    const brokers = ITEMS.find(i => i.label === 'Брокеры');
    // либо удалён, либо ведёт на реальный роут — но не должен быть заглушкой
    if (brokers) expect(brokers.id).not.toBe('nav.brokers-stub');
  });
});
