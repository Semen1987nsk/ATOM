'use client';

import React, { createContext, useCallback, useContext, useMemo, useRef, useState, ReactNode } from 'react';
import { X } from 'lucide-react';

type ToastKind = 'success' | 'error';

interface ToastItem {
  id: number;
  kind: ToastKind;
  message: string;
}

export interface ToastApi {
  success: (message: string) => void;
  error: (message: string) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

// Ошибке нужно больше времени на прочтение, чем подтверждению успеха.
const DISMISS_MS: Record<ToastKind, number> = { success: 6000, error: 8000 };

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  const push = useCallback((kind: ToastKind, message: string) => {
    const id = nextId.current++;
    setToasts(prev => [...prev, { id, kind, message }]);
    setTimeout(() => dismiss(id), DISMISS_MS[kind]);
  }, [dismiss]);

  const api = useMemo<ToastApi>(() => ({
    success: (message: string) => push('success', message),
    error: (message: string) => push('error', message),
  }), [push]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      {/* aria-live контейнер всегда в DOM (даже пустой) — иначе скринридеры
          не анонсируют первый тост. */}
      <div
        aria-live="polite"
        className="fixed bottom-4 right-4 z-[100] flex w-full max-w-sm flex-col gap-2 pointer-events-none"
      >
        {toasts.map(t => (
          <div
            key={t.id}
            role="status"
            className="pointer-events-auto flex items-start gap-3 px-4 py-3 shadow-lg"
            style={{
              background: 'var(--surface-2)',
              border: '1px solid var(--border)',
              borderLeft: `3px solid var(${t.kind === 'error' ? '--danger' : '--success'})`,
              borderRadius: 'var(--radius-lg)',
            }}
          >
            <span className="flex-1 text-sm text-foreground">{t.message}</span>
            <button
              type="button"
              aria-label="Закрыть уведомление"
              onClick={() => dismiss(t.id)}
              className="mt-0.5 opacity-50 transition-opacity hover:opacity-100"
            >
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error('useToast must be used within ToastProvider');
  }
  return ctx;
}
