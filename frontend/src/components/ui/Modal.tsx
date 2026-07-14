"use client";
import { useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";
import { clsx } from "clsx";

export interface ModalProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  description?: string;
  children: ReactNode;
  /** Кнопки в footer'е (правый край). */
  footer?: ReactNode;
  /** Ширина модалки. md (480px) — дефолт. */
  size?: "sm" | "md" | "lg" | "xl";
  /** Отключить закрытие по клику на backdrop. */
  blockBackdropClose?: boolean;
}

const sizeClass = {
  sm: "max-w-[400px]",
  md: "max-w-[520px]",
  lg: "max-w-[720px]",
  xl: "max-w-[960px]",
};

/**
 * Drop-in модалка под новый дизайн.
 * - Backdrop: blur, тёмный.
 * - Карточка: `--surface-2`, `--radius-xl`, мягкая тень.
 * - Закрытие: ESC, клик по backdrop, кнопка X.
 * - Body scroll lock пока модалка открыта.
 */
export function Modal({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  size = "md",
  blockBackdropClose = false,
}: ModalProps) {
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };

    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open, onClose]);

  // Focus trap: lock Tab/Shift+Tab внутри карточки + восстановление focus после закрытия.
  useEffect(() => {
    if (!open) return;
    const card = cardRef.current;
    if (!card) return;

    const previousFocus = document.activeElement as HTMLElement | null;

    const getFocusables = () =>
      Array.from(
        card.querySelectorAll<HTMLElement>(
          'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      );

    // Focus на первый интерактивный элемент при открытии.
    const initial = getFocusables();
    initial[0]?.focus();

    const trap = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const focusables = getFocusables();
      if (focusables.length === 0) {
        e.preventDefault();
        return;
      }
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      const active = document.activeElement as HTMLElement | null;
      if (e.shiftKey && (active === first || !card.contains(active))) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && (active === last || !card.contains(active))) {
        e.preventDefault();
        first.focus();
      }
    };

    card.addEventListener("keydown", trap);
    return () => {
      card.removeEventListener("keydown", trap);
      previousFocus?.focus?.();
    };
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      onClick={blockBackdropClose ? undefined : onClose}
    >
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm animate-fadeIn"
        aria-hidden="true"
      />

      {/* Card */}
      <div
        ref={cardRef}
        className={clsx(
          "relative w-full max-h-[90vh] flex flex-col overflow-hidden",
          sizeClass[size],
          "bg-[var(--surface-2)] rounded-[var(--radius-xl)] border border-[var(--border)] shadow-[var(--shadow-xl)] animate-scaleIn",
        )}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? "modal-title" : undefined}
        tabIndex={-1}
      >
        {/* Header */}
        {(title || true) && (
          <div className="flex items-start justify-between gap-4 px-6 pt-5 pb-3">
            <div className="min-w-0 flex-1">
              {title && (
                <h2 id="modal-title" className="text-xl font-bold leading-tight">
                  {title}
                </h2>
              )}
              {description && (
                <p className="mt-1 text-sm text-[var(--text-secondary)]">{description}</p>
              )}
            </div>
            <button
              onClick={onClose}
              className="btn-icon flex-shrink-0"
              aria-label="Закрыть"
              type="button"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Body */}
        <div className="px-6 py-4 overflow-y-auto flex-1">{children}</div>

        {/* Footer */}
        {footer && (
          <div className="flex-shrink-0 flex items-center justify-end gap-2 px-6 py-4 border-t border-[var(--border)]">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
