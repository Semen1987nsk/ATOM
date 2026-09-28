import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { PnLHealthBadge } from '../PnLHealthBadge';

// Примечание: popover бейджа содержит статическую строку-метрику с label
// "Расхождение" (сумма diff_rub), поэтому текст встречается >1 раза при
// наличии data. Для проверки цвета статуса используем getAllByText — важно,
// что метка бейджа = "Расхождение" (красный), а не "Корректно"/"Проверка нужна".
describe('PnLHealthBadge', () => {
  it('investigate от backend НЕ маскируется зелёным при малом diff_pct', () => {
    render(<PnLHealthBadge data={{
      status: 'investigate', diff_pct: 0.3, diff_rub: 100, checked_at: null,
    }} />);
    expect(screen.queryByText('Корректно')).not.toBeInTheDocument();
    expect(screen.getAllByText('Расхождение').length).toBeGreaterThan(0);
  });

  it('investigate при diff_pct=null тоже красный, не серый', () => {
    render(<PnLHealthBadge data={{
      status: 'investigate', diff_pct: null, diff_rub: null, checked_at: null,
    }} />);
    expect(screen.queryByText('Проверка нужна')).not.toBeInTheDocument();
    expect(screen.getAllByText('Расхождение').length).toBeGreaterThan(0);
  });

  it('ok при diff 0.3% и status ok остаётся зелёным', () => {
    render(<PnLHealthBadge data={{
      status: 'ok', diff_pct: 0.3, diff_rub: 100, checked_at: null,
    }} />);
    expect(screen.getByText('Корректно')).toBeInTheDocument();
  });
});
