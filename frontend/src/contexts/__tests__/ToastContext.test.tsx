/**
 * Sprint 6.5 Batch 2: toast-система ошибок/успеха.
 *
 * Покрываем:
 *   1. Контейнер с aria-live="polite" всегда в DOM.
 *   2. toast.error → тост с role="status" и текстом.
 *   3. Автодисмисс: error живёт 8с (после 6с ещё виден).
 *   4. Автодисмисс: success живёт 6с.
 *   5. Кнопка «Закрыть уведомление» убирает тост.
 *   6. useToast вне провайдера → throw.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';

import { ToastProvider, useToast } from '../ToastContext';

function Harness() {
  const toast = useToast();
  return (
    <>
      <button onClick={() => toast.error('Ошибка сети')}>err</button>
      <button onClick={() => toast.success('Готово')}>ok</button>
    </>
  );
}

function renderWithProvider() {
  return render(
    <ToastProvider>
      <Harness />
    </ToastProvider>,
  );
}

describe('ToastContext', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('контейнер с aria-live="polite" есть в DOM даже без тостов', () => {
    const { container } = renderWithProvider();
    const region = container.querySelector('[aria-live="polite"]');
    expect(region).not.toBeNull();
  });

  it('toast.error показывает тост с role="status" и сообщением', () => {
    renderWithProvider();
    fireEvent.click(screen.getByText('err'));

    const toast = screen.getByRole('status');
    expect(toast).toHaveTextContent('Ошибка сети');
  });

  it('error-тост автодисмиссится через 8с (после 6с ещё виден)', () => {
    renderWithProvider();
    fireEvent.click(screen.getByText('err'));
    expect(screen.getByRole('status')).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(6000);
    });
    expect(screen.getByRole('status')).toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('success-тост автодисмиссится через 6с', () => {
    renderWithProvider();
    fireEvent.click(screen.getByText('ok'));
    expect(screen.getByRole('status')).toHaveTextContent('Готово');

    act(() => {
      vi.advanceTimersByTime(6000);
    });
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('кнопка «Закрыть уведомление» убирает тост', () => {
    renderWithProvider();
    fireEvent.click(screen.getByText('err'));
    expect(screen.getByRole('status')).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText('Закрыть уведомление'));
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('несколько тостов стекуются', () => {
    renderWithProvider();
    fireEvent.click(screen.getByText('err'));
    fireEvent.click(screen.getByText('ok'));

    expect(screen.getAllByRole('status')).toHaveLength(2);
  });

  it('useToast вне ToastProvider бросает ошибку', () => {
    // console.error от React при throw в render глушим, чтобы не шумел вывод.
    const spy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    expect(() => render(<Harness />)).toThrow('useToast must be used within ToastProvider');
    spy.mockRestore();
  });
});
