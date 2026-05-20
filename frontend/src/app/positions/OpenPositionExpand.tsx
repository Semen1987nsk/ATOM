// frontend/src/app/positions/OpenPositionExpand.tsx
'use client';

import { StickyNote, ImageIcon, Edit2 } from 'lucide-react';
import type { TradeExecution } from './joinPositionsTrades';

interface OpenPositionExpandProps {
  executions: TradeExecution[];
  onEdit: (executionId: number) => void;
}

const fmtDate = (iso: string): string => {
  const d = new Date(iso);
  return d.toLocaleString('ru-RU', {
    day: '2-digit', month: '2-digit', year: '2-digit',
    hour: '2-digit', minute: '2-digit',
  });
};

const fmtPrice = (n: number): string =>
  n.toLocaleString('ru-RU', { maximumFractionDigits: 4 });

const fmtQty = (n: number): string =>
  n.toLocaleString('ru-RU');

export function OpenPositionExpand({ executions, onEdit }: OpenPositionExpandProps) {
  if (executions.length === 0) {
    return (
      <div className="bg-amber-500/5 border border-amber-500/20 rounded-lg p-4 text-sm text-amber-200">
        Trade row для этой позиции ещё не создан. Будет добавлен при следующей
        синхронизации с брокером.
      </div>
    );
  }

  // Default sort: новейший вход сверху (desc по entry_at) — по решению пользователя.
  const sorted = [...executions].sort(
    (a, b) => new Date(b.entry_at).getTime() - new Date(a.entry_at).getTime(),
  );

  return (
    <div className="bg-slate-900/40 rounded-lg p-3 border border-slate-700/30">
      <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2 font-semibold">
        Входы ({executions.length})
      </div>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-[10px] uppercase tracking-wider text-slate-500 border-b border-slate-700/50">
            <th className="text-left py-1.5 pr-2 font-medium">Дата входа</th>
            <th className="text-right py-1.5 px-2 font-medium">Кол-во</th>
            <th className="text-right py-1.5 px-2 font-medium">Цена входа</th>
            <th className="text-left py-1.5 px-2 font-medium">Сетап</th>
            <th className="text-left py-1.5 px-2 font-medium">Заметка</th>
            <th className="text-right py-1.5 pl-2 font-medium">Действия</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((ex) => {
            // Note preview: 1 строка truncate (max 60 символов), full в EditTradeModal.
            const notePreview = ex.notes && ex.notes.length > 60
              ? ex.notes.slice(0, 60) + '…'
              : ex.notes;
            return (
              <tr key={ex.id} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                <td className="py-2 pr-2 text-slate-300 whitespace-nowrap">{fmtDate(ex.entry_at)}</td>
                <td className="py-2 px-2 text-right font-mono tabular-nums text-slate-200">
                  {fmtQty(ex.quantity)}
                </td>
                <td className="py-2 px-2 text-right font-mono tabular-nums text-slate-200">
                  {fmtPrice(ex.entry_price)}
                </td>
                <td className="py-2 px-2 text-slate-300">
                  {ex.setup_name || <span className="text-slate-600">—</span>}
                </td>
                <td className="py-2 px-2 text-slate-300 max-w-[260px]">
                  <div className="flex items-center gap-1.5">
                    {ex.screenshot_url && (
                      <span title="Есть скриншот">
                        <ImageIcon size={12} className="text-cyan-400 shrink-0" />
                      </span>
                    )}
                    {notePreview ? (
                      <span title={ex.notes ?? undefined} className="truncate cursor-help">
                        <StickyNote size={12} className="text-cyan-400 inline mr-1" />
                        {notePreview}
                      </span>
                    ) : (
                      <span className="text-slate-600 text-[11px]">Нет заметки</span>
                    )}
                  </div>
                </td>
                <td className="py-2 pl-2 text-right">
                  <button
                    onClick={() => onEdit(ex.id)}
                    className="inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium text-slate-200 bg-slate-700/50 hover:bg-slate-700"
                  >
                    <Edit2 size={11} />
                    Редактировать
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
