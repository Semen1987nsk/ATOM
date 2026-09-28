/**
 * FE-12 (Sprint 5, Batch 8): a11y/UX-тесты Modal.
 *
 * Покрываем:
 *   1. open=false → нет в DOM.
 *   2. open=true → role="dialog" + aria-modal + title.
 *   3. ESC → onClose.
 *   4. Клик на backdrop → onClose (если не blockBackdropClose).
 *   5. blockBackdropClose=true → клик на backdrop НЕ закрывает.
 *   6. Кнопка "Закрыть" (X) → onClose.
 *   7. Focus-trap: первый focusable получает фокус при open.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { Modal } from '../Modal';

describe('Modal', () => {
  it('open=false → ничего не рендерит', () => {
    const { container } = render(
      <Modal open={false} onClose={() => undefined}>
        body
      </Modal>,
    );
    expect(container.firstChild).toBeNull();
  });

  it('open=true → dialog с aria-modal и title', () => {
    render(
      <Modal open={true} onClose={() => undefined} title="Тест модалки">
        content
      </Modal>,
    );

    const dialog = screen.getByRole('dialog');
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAttribute('aria-labelledby', 'modal-title');
    expect(screen.getByText('Тест модалки')).toBeInTheDocument();
    expect(screen.getByText('content')).toBeInTheDocument();
  });

  it('ESC вызывает onClose', () => {
    const onClose = vi.fn();
    render(
      <Modal open={true} onClose={onClose}>
        body
      </Modal>,
    );

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('клик по backdrop вызывает onClose', () => {
    const onClose = vi.fn();
    const { container } = render(
      <Modal open={true} onClose={onClose}>
        body
      </Modal>,
    );

    // Backdrop = первый дочерний div (с onClick на родительском контейнере).
    // Кликаем непосредственно на контейнер модалки.
    const overlay = container.querySelector('.fixed.inset-0') as HTMLElement;
    expect(overlay).not.toBeNull();
    fireEvent.click(overlay);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('blockBackdropClose=true → клик по backdrop НЕ вызывает onClose', () => {
    const onClose = vi.fn();
    const { container } = render(
      <Modal open={true} onClose={onClose} blockBackdropClose>
        body
      </Modal>,
    );

    const overlay = container.querySelector('.fixed.inset-0') as HTMLElement;
    fireEvent.click(overlay);
    expect(onClose).not.toHaveBeenCalled();
  });

  it('кнопка "Закрыть" вызывает onClose', () => {
    const onClose = vi.fn();
    render(
      <Modal open={true} onClose={onClose} title="t">
        body
      </Modal>,
    );

    const closeBtn = screen.getByRole('button', { name: 'Закрыть' });
    fireEvent.click(closeBtn);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('focus-trap: первый focusable элемент получает фокус', () => {
    render(
      <Modal open={true} onClose={() => undefined} title="t">
        <button data-testid="first">First</button>
        <button data-testid="second">Second</button>
      </Modal>,
    );

    // В JSDOM document.activeElement обновляется синхронно после .focus(),
    // но useEffect внутри Modal стреляет асинхронно после render — RTL ждёт его.
    // Кнопка "Закрыть" (X) — самый первый focusable в DOM-порядке, т.к. она в header'е
    // ВЫШЕ children. Проверяем что какой-то focusable получил фокус, и это НЕ body.
    expect(document.activeElement).not.toBe(document.body);
    expect(document.activeElement?.tagName).toBe('BUTTON');
  });
});
