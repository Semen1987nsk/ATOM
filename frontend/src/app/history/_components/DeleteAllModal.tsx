'use client';

import { Trash2 } from 'lucide-react';

interface DeleteAllModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  tradeCount: number;
  isDeleting: boolean;
}

export function DeleteAllModal({ isOpen, onClose, onConfirm, tradeCount, isDeleting }: DeleteAllModalProps) {
  if (!isOpen) return null;
  return (
    <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-[var(--surface-1)] border border-red-500/50 rounded-2xl p-6 max-w-md w-full mx-4 shadow-2xl">
        <div className="flex items-center gap-3 mb-4">
          <div className="w-12 h-12 rounded-full bg-red-500/20 flex items-center justify-center">
            <Trash2 className="w-6 h-6 text-red-500" />
          </div>
          <div>
            <h3 className="text-xl font-bold text-[var(--foreground)]">Удалить все сделки?</h3>
            <p className="text-slate-400 text-sm">Это действие нельзя отменить</p>
          </div>
        </div>

        <p className="text-slate-300 mb-6">
          Вы уверены, что хотите удалить <span className="font-bold text-red-400">{tradeCount}</span> сделок?
          Все данные будут безвозвратно потеряны.
        </p>

        <div className="flex gap-3 justify-end">
          <button
            onClick={onClose}
            disabled={isDeleting}
            className="px-4 py-2 rounded-lg bg-[var(--surface-2)] hover:bg-[var(--surface-hover)] text-[var(--foreground)] transition-colors"
          >
            Отмена
          </button>
          <button
            onClick={onConfirm}
            disabled={isDeleting}
            className="px-4 py-2 rounded-lg bg-red-600 hover:bg-red-500 text-white transition-colors flex items-center gap-2 disabled:opacity-50"
          >
            {isDeleting ? (
              <>
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                Удаление...
              </>
            ) : (
              <>
                <Trash2 size={16} />
                Удалить всё
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
