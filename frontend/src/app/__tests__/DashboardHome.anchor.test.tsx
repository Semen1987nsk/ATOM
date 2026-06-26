import { describe, it, expect } from 'vitest';
import { anchorSourceLabel } from '../DashboardHome';

describe('anchorSourceLabel', () => {
  it('inferred_anchor → honest auto-restored caption', () => {
    expect(anchorSourceLabel('inferred_anchor')).toMatch(/восстановлена автоматически/);
  });
  it('inferred_blocked → journal-needs-review caption', () => {
    expect(anchorSourceLabel('inferred_blocked')).toMatch(/Журнал требует проверки/);
  });
  it('manual / complete / null → no caption', () => {
    expect(anchorSourceLabel('manual')).toBeNull();
    expect(anchorSourceLabel('complete')).toBeNull();
    expect(anchorSourceLabel(null)).toBeNull();
  });
});
