import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ErrorBoundary } from '../ErrorBoundary';

function Boom(): never {
  throw new Error('widget crashed');
}

describe('ErrorBoundary custom fallback', () => {
  it('renders provided fallback instead of global UI', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    render(
      <ErrorBoundary fallback={<div>виджет недоступен</div>}>
        <Boom />
      </ErrorBoundary>
    );
    expect(screen.getByText('виджет недоступен')).toBeInTheDocument();
    spy.mockRestore();
  });
});
